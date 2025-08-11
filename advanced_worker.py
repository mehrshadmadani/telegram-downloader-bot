import os
import asyncio
import logging
import json
import subprocess
import base64
import requests
import shutil
from datetime import datetime, timezone
from functools import partial

import yt_dlp
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeVideo
import instaloader
from instagrapi import Client as InstagrapiClient

from config import (TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE,
                    GROUP_ID, ORDER_TOPIC_ID, MAJID_API_TOKEN,
                    INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD, NESTCODE_API_KEY)

# --- سیستم لاگ‌گیری ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s')
if logger.hasHandlers():
    logger.handlers.clear()
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)
file_handler = logging.FileHandler('bot.log', encoding='utf-8')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logging.getLogger("telethon").setLevel(logging.WARNING)
logging.getLogger("yt_dlp").setLevel(logging.WARNING)
logging.getLogger("instaloader").setLevel(logging.WARNING)
logging.getLogger("instagrapi").setLevel(logging.WARNING)

class TelethonWorker:
    def __init__(self, api_id, api_hash, phone):
        self.app = TelegramClient("telethon_session", api_id, api_hash)
        self.phone = phone
        self.download_dir = "downloads"
        os.makedirs(self.download_dir, exist_ok=True)
        self.processed_ids = set()
        self.start_time = datetime.now(timezone.utc)
        self.active_jobs = {}
        self.instagrapi_client = self.setup_instagrapi_client()
        self.instaloader_client = self.setup_instaloader_client()

    def setup_instagrapi_client(self):
        try:
            client = InstagrapiClient()
            session_file = f"instagrapi_session_{INSTAGRAM_USERNAME}.json"
            if os.path.exists(session_file):
                client.load_settings(session_file)
            client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            client.dump_settings(session_file)
            logger.info("✅ Instagrapi session loaded/created successfully.")
            return client
        except Exception as e:
            logger.error(f"❌ Could not login with Instagrapi. Error: {e}")
            return None

    def setup_instaloader_client(self):
        try:
            L = instaloader.Instaloader(download_videos=True, download_pictures=True, download_video_thumbnails=False, save_metadata=False, compress_json=False)
            session_file = f"instaloader_session_{INSTAGRAM_USERNAME}"
            if os.path.exists(session_file):
                L.load_session_from_file(INSTAGRAM_USERNAME, session_file)
            else:
                L.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                L.save_session_to_file(session_file)
            logger.info("✅ Instaloader session loaded/created successfully.")
            return L
        except Exception as e:
            logger.error(f"❌ Could not login with Instaloader. Error: {e}")
            return None
            
    def _download_from_url(self, url, file_path):
        with requests.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return file_path

    def _try_instagrapi(self, url, code):
        logger.info(f"[{code}] Attempt 1: Instagrapi")
        if not self.instagrapi_client: raise Exception("Instagrapi client not logged in.")
        media_pk = self.instagrapi_client.media_pk_from_url(url)
        media_info = self.instagrapi_client.media_info(media_pk).dict()
        caption = media_info.get("caption_text", "")
        resources = media_info.get("resources", []) or [media_info]
        downloaded_files = []
        for i, res in enumerate(resources):
            dl_path, ext = None, ".jpg"
            if res.get("media_type") == 2:
                dl_path, ext = self.instagrapi_client.video_download(res['pk'], self.download_dir), ".mp4"
            elif res.get("media_type") == 1:
                dl_path, ext = self.instagrapi_client.photo_download(res['pk'], self.download_dir), ".jpg"
            if dl_path:
                final_path = os.path.join(self.download_dir, f"{code}_{i}{ext}")
                os.rename(dl_path, final_path)
                downloaded_files.append(final_path)
        if downloaded_files: return downloaded_files, caption, "Instagrapi"
        return [], None, None

    def _try_instaloader(self, url, code):
        logger.info(f"[{code}] Attempt 2: Instaloader")
        if not self.instaloader_client: raise Exception("Instaloader client not logged in.")
        shortcode = url.split('/')[-2]
        post = instaloader.Post.from_shortcode(self.instaloader_client.context, shortcode)
        downloaded_files, temp_dir = [], os.path.join(self.download_dir, code)
        self.instaloader_client.download_post(post, target=temp_dir)
        caption = post.caption or ""
        for i, filename in enumerate(sorted(os.listdir(temp_dir))):
            if not filename.endswith(('.jpg', '.mp4')): continue
            old_path = os.path.join(temp_dir, filename)
            new_path = os.path.join(self.download_dir, f"{code}_{i}{os.path.splitext(filename)[1]}")
            os.rename(old_path, new_path)
            downloaded_files.append(new_path)
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        if downloaded_files: return downloaded_files, caption, "Instaloader"
        return [], None, None

    def _try_yt_dlp_insta(self, url, code):
        logger.info(f"[{code}] Attempt 3: yt-dlp for Instagram")
        return self.download_other_platforms(url, code)

    def _try_majidapi(self, url, code):
        logger.info(f"[{code}] Attempt 4: MajidAPI")
        api_url = f"https://api.majidapi.ir/instagram/download?url={url}&out=url&token={MAJID_API_TOKEN}"
        data = requests.get(api_url, timeout=30).json()
        if data.get("status") != 200: raise Exception(f"MajidAPI Error: {data.get('result')}")
        
        result = data.get("result", {})
        caption = result.get("caption", "")
        
        media_urls = result.get("carousel") or ([result.get("video")] if result.get("video") else []) or result.get("images")
        downloaded_files = []
        for i, media_url in enumerate(media_urls):
            ext = ".mp4" if "video" in media_url or ".mp4" in media_url else ".jpg"
            output_path = os.path.join(self.download_dir, f"{code}_{i}{ext}")
            self._download_from_url(media_url, output_path)
            downloaded_files.append(output_path)
        if downloaded_files: return downloaded_files, caption, "MajidAPI"
        return [], None, None

    def _try_nestcode_api(self, url, code):
        logger.info(f"[{code}] Attempt 5: NestCode API")
        api_url = f"https://open.nestcode.org/apis-1/InstagramDownloader?url={url}&key={NESTCODE_API_KEY}"
        data = requests.get(api_url, timeout=30).json()
        if data.get("status") != "success": raise Exception(f"NestCode API Error: {data.get('data')}")
        
        result = data.get("data", {})
        caption = result.get("caption", "")

        media_urls = result.get("medias", [])
        downloaded_files = []
        for i, media_url in enumerate(media_urls):
            ext = ".mp4" if "video" in media_url or ".mp4" in media_url else ".jpg"
            output_path = os.path.join(self.download_dir, f"{code}_{i}{ext}")
            self._download_from_url(media_url, output_path)
            downloaded_files.append(output_path)
        if downloaded_files: return downloaded_files, caption, "NestCode API"
        return [], None, None

    def download_from_instagram(self, url, code):
        methods = [self._try_instagrapi, self._try_instaloader, self._try_yt_dlp_insta, self._try_majidapi, self._try_nestcode_api]
        for method_func in methods:
            try:
                file_paths, caption, method_name = method_func(url, code)
                if file_paths:
                    logger.info(f"✅ [{code}] Successfully downloaded using {method_name}.")
                    return file_paths, caption, method_name
            except Exception as e:
                logger.warning(f"⚠️ [{code}] Method {method_func.__name__} failed: {e}")
        return [], None, None

    def yt_dlp_progress_hook(self, d, code):
        if d['status'] == 'downloading':
            percent_str = d.get('_percent_str', '0.0%').strip()
            speed_str = d.get('_speed_str', 'N/A').strip()
            if code in self.active_jobs:
                self.active_jobs[code]["status"] = f"Downloading: {percent_str} at {speed_str}"
        elif d['status'] == 'finished':
            if code in self.active_jobs:
                self.active_jobs[code]["status"] = "Download Finished, Merging..."

    def download_other_platforms(self, url, code):
        try:
            logger.info(f"[{code}] Starting download process for URL: {url}")
            output_path = os.path.join(self.download_dir, f"{code}.%(ext)s")
            ydl_opts = {
                'outtmpl': output_path, 'cookiefile': 'cookies.txt',
                'ignoreerrors': True, 'no_warnings': True, 'quiet': True,
                'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best',
                'merge_output_format': 'mp4',
                'progress_hooks': [partial(self.yt_dlp_progress_hook, code=code)],
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=True)
            downloaded_files = [os.path.join(self.download_dir, f) for f in os.listdir(self.download_dir) if f.startswith(code)]
            if not downloaded_files:
                raise Exception("yt-dlp finished but no files were found.")
            caption = info_dict.get('title', '') if info_dict else ""
            return downloaded_files, caption, "yt-dlp"
        except Exception as e:
            logger.error(f"[{code}] Error in download_other_platforms: {e}", exc_info=True)
            raise e

    def get_video_metadata(self, file_path):
        try:
            command = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,duration', '-of', 'json', file_path]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
            data = json.loads(result.stdout)['streams'][0]
            return {'duration': int(float(data.get('duration', 0))), 'width': int(data.get('width', 0)), 'height': int(data.get('height', 0))}
        except Exception as e:
            logger.warning(f"[{os.path.basename(file_path)}] Could not get video metadata. Reason: {e}")
            return None

    async def upload_single_file(self, message, file_path, code, download_method, index, total_files, original_caption):
        try:
            if not os.path.exists(file_path):
                raise Exception(f"File vanished: {os.path.basename(file_path)}")
            file_size = os.path.getsize(file_path)
            self.active_jobs[code]["status"] = f"Uploading {index}/{total_files}..."
            logger.info(f"[{code}] Uploading {index}/{total_files}: {os.path.basename(file_path)} ({file_size / 1024**2:.2f} MB)")
            attributes, caption_to_group = [], f"✅ Uploaded ({index}/{total_files})\nCODE: {code}\nSIZE: {file_size}\nMETHOD: {download_method}"
            if file_path.lower().endswith(('.mp4', '.mkv', '.mov')):
                metadata = self.get_video_metadata(file_path)
                if metadata: attributes.append(DocumentAttributeVideo(duration=metadata['duration'], w=metadata['width'], h=metadata['height'], supports_streaming=True))
            if original_caption and index == total_files:
                truncated_caption = original_caption[:700]
                encoded_caption = base64.b64encode(truncated_caption.encode('utf-8')).decode('utf-8')
                caption_to_group += f"\nCAPTION:{encoded_caption}"
            await self.app.send_file(message.chat_id, file_path, caption=caption_to_group, reply_to=message.id, attributes=attributes,
                                     progress_callback=lambda s, t: self.update_upload_status(s, t, code, index, total_files))
        except Exception as e:
            raise e
        finally:
            if os.path.exists(file_path): os.remove(file_path)

    def update_upload_status(self, sent, total, code, index, total_files):
        if code in self.active_jobs:
            percentage = int(sent * 100 / total)
            self.active_jobs[code]["status"] = f"Uploading {index}/{total_files}: {percentage}%"
    
    async def process_job(self, message):
        code, url, user_id = "N/A", "N/A", 0
        try:
            lines = message.text.split('\n')
            url = next(l.split(":", 1)[1].strip() for l in lines if l.startswith("URL:"))
            code = next(l.split(":", 1)[1].strip() for l in lines if l.startswith("CODE:"))
            user_id = int(next(l.split(":", 1)[1].strip() for l in lines if l.startswith("USER_ID:")))
            self.active_jobs[code] = {"user_id": user_id, "status": "Queued", "error": None}
            logger.info(f"[{code}] Job received for user [{user_id}].")
            
            if "instagram.com" in url:
                self.active_jobs[code]["status"] = "Downloading (Instagram)..."
                file_paths, caption_text, method = await asyncio.to_thread(self.download_from_instagram, url, code)
            else:
                file_paths, caption_text, method = await asyncio.to_thread(self.download_other_platforms, url, code)
            
            if code in self.active_jobs: self.active_jobs[code]["status"] = "Processing..."
            for i, path in enumerate(file_paths):
                await self.upload_single_file(message, path, code, method, i + 1, len(file_paths), caption_text)
            if code in self.active_jobs: self.active_jobs[code]["status"] = "Completed"
        except Exception as e:
            error_short = str(e).strip().split('\n')[0]
            if "CODE:" in error_short: error_short = "Could not parse job message"
            if code in self.active_jobs:
                self.active_jobs[code].update({"status": "Failed", "error": error_short[:70]})
            logger.error(f"[{code}] Job failed entirely. Error: {error_short}")

    async def display_dashboard(self):
        while True:
            os.system('clear' if os.name == 'posix' else 'cls')
            print("--- 🚀 Advanced Downloader Dashboard (Final v5) 🚀 ---")
            print(f"{'Job Code':<12} | {'User ID':<12} | {'Status':<50}")
            print("-" * 80)
            if not self.active_jobs: print("... Waiting for new jobs ...")
            else:
                for code, data in list(self.active_jobs.items()):
                    print(f"{code:<12} | {data.get('user_id', 'N/A'):<12} | {data.get('status', 'N/A'):<50}")
                    if data.get("error"): print(f"{'':<12} | {'':<12} | └─ ❗Error: {data['error']}")
                    if data.get('status') in ["Completed", "Failed"]:
                        await asyncio.sleep(10)
                        self.active_jobs.pop(code, None)
            print("-" * 80)
            print(f"Last Update: {datetime.now().strftime('%H:%M:%S')} | Logs: tail -f bot.log")
            await asyncio.sleep(1)

    async def run(self):
        try:
            await self.app.start(phone=self.phone)
            me = await self.app.get_me()
            logger.info(f"Worker (Final v5) successfully logged in as {me.first_name}")
        except Exception as e:
            logger.critical(f"Could not start the worker. Error: {e}")
            return
        dashboard_task = asyncio.create_task(self.display_dashboard())
        logger.info(f"Worker started listening for new jobs...")
        while True:
            try:
                async for message in self.app.iter_messages(GROUP_ID, reply_to=ORDER_TOPIC_ID, limit=10):
                    if message.date < self.start_time: break
                    if message.text and "⬇️ NEW JOB" in message.text and message.id not in self.processed_ids:
                        self.processed_ids.add(message.id)
                        asyncio.create_task(self.process_job(message))
                await asyncio.sleep(3)
            except Exception as e:
                logger.error(f"An error occurred in the main loop: {e}", exc_info=True)
                await asyncio.sleep(30)

if __name__ == "__main__":
    logger.info("--- Starting Final Worker (v5) ---")
    worker = TelethonWorker(TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE)
    asyncio.run(worker.run())
