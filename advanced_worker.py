import os
import asyncio
import logging
import json
import subprocess
import requests
import base64
from datetime import datetime, timezone
import yt_dlp
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeVideo
import instaloader
from instagrapi import Client as InstagrapiClient
from config import (TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, 
                    GROUP_ID, ORDER_TOPIC_ID, MAJID_API_TOKEN, 
                    INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD, NESTCODE_API_KEY)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger("telethon").setLevel(logging.WARNING)

class TelethonWorker:
    def __init__(self, api_id, api_hash, phone):
        self.app = TelegramClient("telethon_session", api_id, api_hash); self.phone = phone
        self.download_dir = "downloads"; os.makedirs(self.download_dir, exist_ok=True)
        self.processed_ids = set(); self.start_time = datetime.now(timezone.utc); self.active_jobs = {}
        self.instaloader_client = instaloader.Instaloader(dirname_pattern=os.path.join(self.download_dir, "{target}"), save_metadata=False, compress_json=False, post_metadata_txt_pattern="")
        self.instagrapi_client = InstagrapiClient()
        try:
            logger.info("Loading Instagram sessions...")
            self.instaloader_client.load_session_from_file(INSTAGRAM_USERNAME)
            self.instagrapi_client.load_settings("insta_session.json")
            self.instagrapi_client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            logger.info("All Instagram sessions loaded successfully.")
        except Exception as e:
            logger.error(f"Session loading failed, attempting fresh login: {e}")
            self.setup_instagram_sessions()

    def setup_instagram_sessions(self):
        try:
            logger.info("Attempting fresh login for instagrapi...")
            self.instagrapi_client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            self.instagrapi_client.dump_settings("insta_session.json")
            logger.info("instagrapi login successful and session saved.")
        except Exception as e:
            logger.error(f"FATAL: instagrapi login failed: {e}")

    def get_video_metadata(self, file_path):
        try:
            command = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,duration', '-of', 'json', file_path]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30); data = json.loads(result.stdout)['streams'][0]
            return {'duration': int(float(data['duration'])), 'width': int(data['width']), 'height': int(data['height'])}
        except: return None
        
    def _download_from_url(self, url, code, index=0):
        media_res = requests.get(url, stream=True, timeout=1800)
        media_res.raise_for_status()
        content_type = media_res.headers.get('content-type', '')
        ext = ".jpg" if "image" in content_type else ".mp4"
        output_path = os.path.join(self.download_dir, f"{code}_{index}{ext}")
        with open(output_path, 'wb') as f:
            for chunk in media_res.iter_content(chunk_size=8192): f.write(chunk)
        return output_path

    def download_media(self, url, code, user_id):
        self.active_jobs[code] = {"user_id": user_id, "status": "Downloading..."}
        if "instagram.com" in url:
            methods = [self._try_instagrapi, self._try_majidapi, self._try_nestcode_api, self._try_yt_dlp_insta]
            for method in methods:
                try:
                    file_paths, caption, method_name = method(url, code)
                    if file_paths:
                        self.active_jobs[code]["status"] = "Downloaded"; return (file_paths, caption, method_name)
                except Exception as e:
                    logger.warning(f"Method {method.__name__} failed for {code}: {e}")
        else:
            try:
                file_paths, caption, method = self._download_with_yt_dlp(url, code)
                if file_paths:
                    self.active_jobs[code]["status"] = "Downloaded"; return (file_paths, caption, method)
            except Exception as e:
                logger.error(f"yt-dlp failed for CODE {code}: {e}")
        self.active_jobs[code]["status"] = "Download Failed"; return ([], None, None)

    def _try_instagrapi(self, url, code):
        media_pk = self.instagrapi_client.media_pk_from_url(url); media_info = self.instagrapi_client.media_info(media_pk).dict()
        caption = media_info.get("caption_text", ""); resources = media_info.get("resources", [])
        if not resources: resources = [media_info]
        downloaded_files = []
        for i, res in enumerate(resources):
            dl_path = None
            if res.get("media_type") == 2: dl_path = self.instagrapi_client.video_download(res['pk'], self.download_dir)
            elif res.get("media_type") == 1: dl_path = self.instagrapi_client.photo_download(res['pk'], self.download_dir)
            if dl_path:
                final_path = os.path.join(self.download_dir, f"{code}_{i}{os.path.splitext(dl_path)[1]}")
                os.rename(dl_path, final_path); downloaded_files.append(final_path)
        return (downloaded_files, caption, "instagrapi")

    def _try_majidapi(self, url, code):
        api_url = f"https://api.majidapi.ir/instagram/download?url={url}&out=url&token={MAJID_API_TOKEN}"
        data = requests.get(api_url, timeout=20).json()
        if data.get("status") == 200:
            result = data.get("result", {}); caption = result.get("caption", "")
            media_urls = result.get("carousel") or result.get("images") or ([result.get("video")] if result.get("video") else [])
            downloaded_files = [self._download_from_url(media_url, code, i) for i, media_url in enumerate(media_urls)]
            if downloaded_files: return (downloaded_files, caption, "MajidAPI")
        return ([], None, None)

    def _try_nestcode_api(self, url, code):
        api_url = f"https://open.nestcode.org/apis-1/InstagramDownloader?url={url}&key={NESTCODE_API_KEY}"
        data = requests.get(api_url, timeout=30).json()
        if data.get("status") == "success":
            result = data.get("data", {}); caption = result.get("caption", "")
            media_urls = result.get("medias", [])
            downloaded_files = [self._download_from_url(media_url, code, i) for i, media_url in enumerate(media_urls)]
            if downloaded_files: return (downloaded_files, caption, "NestCode API")
        return ([], None, None)
        
    def _try_yt_dlp_insta(self, url, code):
        output_path_yt = os.path.join(self.download_dir, f"{code} - %(title).30s.%(ext)s")
        ydl_opts = {'outtmpl': output_path_yt, 'cookiefile': 'cookies.txt', 'format': 'best', 'ignoreerrors': True, 'quiet': True, 'no_warnings': True, 'socket_timeout': 1800}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True); caption = info_dict.get('description', '')
            downloaded_files = [os.path.join(self.download_dir, f) for f in os.listdir(self.download_dir) if f.startswith(code)]
            if downloaded_files: return (downloaded_files, caption, "yt-dlp")
        return ([], None, None)

    def _download_with_yt_dlp(self, url, code):
        logger.info(f"Using yt-dlp for {url.split('/')[2]} CODE: {code}")
        output_path = os.path.join(self.download_dir, f"{code} - %(title).30s.%(ext)s")
        base_opts = {'outtmpl': output_path, 'cookiefile': 'cookies.txt', 'ignoreerrors': True, 'quiet': True, 'no_warnings': True, 'socket_timeout': 1800}
        if "soundcloud" in url or "spotify" in url: ydl_opts = {'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]}
        else: ydl_opts = {'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best', 'merge_output_format': 'mp4'}
        ydl_opts.update(base_opts)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True); caption = info_dict.get('description', '')
            downloaded_files = [os.path.join(self.download_dir, f) for f in os.listdir(self.download_dir) if f.startswith(code)]
            if downloaded_files: return (downloaded_files, caption, "yt-dlp")
        return ([], None, None)
    
    # --- تابع حذف شده در اینجا دوباره اضافه شد ---
    async def upload_progress(self, sent_bytes, total_bytes, code, index, total):
        percentage = int(sent_bytes * 100 / total_bytes)
        if percentage % 20 == 0 or percentage == 100:
            if code in self.active_jobs:
                self.active_jobs[code]["status"] = f"Uploading {index}/{total}: {percentage}%"

    async def process_job(self, message):
        if message.id in self.processed_ids: return
        self.processed_ids.add(message.id)
        try:
            lines = message.text.split('\n'); url = next(l.replace("URL:", "").strip() for l in lines if l.startswith("URL:")); code = next(l.replace("CODE:", "").strip() for l in lines if l.startswith("CODE:")); user_id = int(next(l.replace("USER_ID:", "").strip() for l in lines if l.startswith("USER_ID:")))
        except: return
        file_paths, original_caption, download_method = await asyncio.to_thread(self.download_media, url, code, user_id)
        if file_paths:
            total_files = len(file_paths)
            upload_tasks = []
            for i, file_path in enumerate(file_paths):
                task = self.upload_single_file(message, file_path, code, user_id, download_method, i + 1, total_files, original_caption)
                upload_tasks.append(task)
            results = await asyncio.gather(*upload_tasks)
            if False in results:
                self.active_jobs[code]["status"] = "Upload Failed"
            else:
                self.active_jobs[code]["status"] = "Completed"
    
    async def upload_single_file(self, message, file_path, code, user_id, download_method, index, total, original_caption):
        if not os.path.exists(file_path): return False
        self.active_jobs[code]["status"] = f"Uploading {index}/{total}"
        file_size = os.path.getsize(file_path); upload_attributes = []
        if file_path.lower().endswith(('.mp4', '.mkv', '.mov')):
            metadata = self.get_video_metadata(file_path)
            if metadata: upload_attributes.append(DocumentAttributeVideo(duration=metadata['duration'], w=metadata['width'], h=metadata['height'], supports_streaming=True))
        try:
            caption_str = ""
            if index == total and original_caption:
                encoded_caption = base64.b64encode(original_caption.encode('utf-8')).decode('utf-8')
                caption_str = f"\nCAPTION:{encoded_caption}"
            caption = f"✅ Uploaded ({index}/{total})\nCODE: {code}\nSIZE: {file_size}\nMETHOD: {download_method}{caption_str}"
            await self.app.send_file(
                message.chat_id, file_path, caption=caption, reply_to=message.id, attributes=upload_attributes,
                progress_callback=lambda s, t: self.upload_progress(s, t, code, index, total)
            )
            return True
        except Exception as e:
            logger.error(f"Upload failed for {file_path}: {e}")
            return False
        finally:
            if os.path.exists(file_path): os.remove(file_path)

    async def display_dashboard(self):
        while True:
            os.system('clear' if os.name == 'posix' else 'cls'); print("--- 🚀 Advanced Downloader Dashboard 🚀 ---")
            print(f"{'Job Code':<12} | {'User ID':<12} | {'Status':<25}"); print("-" * 55)
            if not self.active_jobs: print("... Waiting for new jobs ...")
            else:
                for code, data in list(self.active_jobs.items()):
                    print(f"{code:<12} | {data.get('user_id', 'N/A'):<12} | {data.get('status', 'N/A'):<25}")
                    if data.get('status') in ["Completed", "Upload Failed"]:
                        await asyncio.sleep(5); self.active_jobs.pop(code, None)
            print("-" * 55); print(f"Last Update: {datetime.now().strftime('%H:%M:%S')}"); await asyncio.sleep(1)

    async def run(self):
        await self.app.start(phone=self.phone)
        me = await self.app.get_me()
        logger.info(f"Worker (Final Fallback) ba movaffaghiat be onvane {me.first_name} vared shod.")
        target_chat_id = GROUP_ID; target_topic_id = ORDER_TOPIC_ID
        try: entity = await self.app.get_entity(target_chat_id)
        except Exception as e: logger.critical(f"Nemitavan be Group ID dastresi peyda kard. Khata: {e}"); return
        dashboard_task = asyncio.create_task(self.display_dashboard())
        logger.info(f"Worker shoroo be check kardan Topic ID {target_topic_id} kard...")
        while True:
            try:
                async for message in self.app.iter_messages(entity=entity, reply_to=target_topic_id, limit=20):
                    if message.date < self.start_time: break
                    if message.text and "⬇️ NEW JOB" in message.text:
                        asyncio.create_task(self.process_job(message))
                await asyncio.sleep(10)
            except Exception as e: logger.error(f"Yek khata dar halghe asli rokh dad: {e}"); await asyncio.sleep(30)
async def main():
    worker = TelethonWorker(api_id=TELEGRAM_API_ID, api_hash=TELEGRAM_API_HASH, phone=TELEGRAM_PHONE)
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())
