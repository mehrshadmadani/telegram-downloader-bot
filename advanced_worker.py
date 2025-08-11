import os
import asyncio
import logging
import json
import subprocess
import requests
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
        self.app = TelegramClient("telethon_session", api_id, api_hash)
        self.phone = phone
        self.download_dir = "downloads"
        os.makedirs(self.download_dir, exist_ok=True)
        self.processed_ids = set()
        self.start_time = datetime.now(timezone.utc)
        self.active_jobs = {}
        self.instagrapi_client = InstagrapiClient()
        session_file = "insta_session.json"
        try:
            if os.path.exists(session_file):
                self.instagrapi_client.load_settings(session_file)
                self.instagrapi_client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            else:
                self.instagrapi_client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                self.instagrapi_client.dump_settings(session_file)
            logger.info("Instagram session via instagrapi loaded/created successfully.")
        except Exception as e:
            logger.error(f"FATAL: Failed to login to Instagram with instagrapi: {e}")

    def get_video_metadata(self, file_path):
        try:
            command = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,duration', '-of', 'json', file_path]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
            data = json.loads(result.stdout)['streams'][0]
            return {'duration': int(float(data['duration'])), 'width': int(data['width']), 'height': int(data['height'])}
        except: return None
        
    def _download_from_url(self, url, code, index=0):
        """تابع کمکی برای دانلود فایل از لینک مستقیم"""
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
        downloaded_files = []
        method = "Unknown"

        if "instagram.com" in url:
            try:
                # 1. تلاش با instagrapi
                logger.info(f"Attempt 1 (instagrapi) for CODE: {code}")
                media_pk = self.instagrapi_client.media_pk_from_url(url)
                resources = self.instagrapi_client.media_resources(media_pk)
                if not resources: # اگر پست تکی بود
                    resources = [self.instagrapi_client.media_info(media_pk)]
                
                for i, res in enumerate(resources):
                    res = res.dict()
                    dl_path = None
                    if res.get("media_type") == 2:
                        dl_path = self.instagrapi_client.video_download(res['pk'], folder=self.download_dir)
                    elif res.get("media_type") == 1:
                        dl_path = self.instagrapi_client.photo_download(res['pk'], folder=self.download_dir)
                    
                    if dl_path:
                        final_path = os.path.join(self.download_dir, f"{code}_{i}{os.path.splitext(dl_path)[1]}")
                        os.rename(dl_path, final_path)
                        downloaded_files.append(final_path)
                
                if downloaded_files:
                    self.active_jobs[code]["status"] = "Downloaded"; return (downloaded_files, "instagrapi")
            except Exception as e:
                logger.warning(f"instagrapi failed: {e}")

            # 2. تلاش با MajidAPI
            try:
                logger.info(f"Attempt 2 (MajidAPI) for CODE: {code}")
                api_url = f"https://api.majidapi.ir/instagram/download?url={url}&out=url&token={MAJID_API_TOKEN}"
                data = requests.get(api_url, timeout=20).json()
                if data.get("status") == 200:
                    result = data.get("result", {})
                    media_urls = result.get("carousel") or result.get("images") or ([result.get("video")] if result.get("video") else [])
                    for i, media_url in enumerate(media_urls):
                        output_path = self._download_from_url(media_url, code, i)
                        downloaded_files.append(output_path)
                    if downloaded_files:
                        self.active_jobs[code]["status"] = "Downloaded"; return (downloaded_files, "MajidAPI")
            except Exception as e:
                logger.warning(f"MajidAPI failed: {e}")
        
        # منطق دانلود برای پلتفرم‌های دیگر
        try:
            logger.info(f"Using yt-dlp for CODE: {code}")
            output_path = os.path.join(self.download_dir, f"{code} - %(title).30s.%(ext)s")
            # ... بقیه کد yt-dlp ...
            base_opts = {'outtmpl': output_path, 'cookiefile': 'cookies.txt', 'ignoreerrors': True, 'quiet': True, 'no_warnings': True, 'socket_timeout': 1800}
            if "soundcloud" in url or "spotify" in url: ydl_opts = {'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]}
            else: ydl_opts = {'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best', 'merge_output_format': 'mp4'}
            ydl_opts.update(base_opts)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                for f in os.listdir(self.download_dir):
                    if f.startswith(code):
                        downloaded_files.append(os.path.join(self.download_dir, f))
                if downloaded_files:
                    self.active_jobs[code]["status"] = "Downloaded"; return (downloaded_files, "yt-dlp")
        except Exception as e:
            logger.error(f"All methods failed. Last error from yt-dlp: {e}")
        
        self.active_jobs[code]["status"] = "Download Failed"; return ([], None)

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
        
        file_paths, download_method = await asyncio.to_thread(self.download_media, url, code, user_id)

        if file_paths:
            total_files = len(file_paths)
            for i, file_path in enumerate(file_paths):
                if os.path.exists(file_path):
                    file_size = os.path.getsize(file_path); upload_attributes = []
                    if file_path.lower().endswith(('.mp4', '.mkv', '.mov')):
                        metadata = self.get_video_metadata(file_path)
                        if metadata: upload_attributes.append(DocumentAttributeVideo(duration=metadata['duration'], w=metadata['width'], h=metadata['height'], supports_streaming=True))
                    try:
                        method_str = f"\nMETHOD: {download_method}"
                        caption = f"✅ Uploaded ({i+1}/{total_files})\nCODE: {code}\nSIZE: {file_size}{method_str}"
                        await self.app.send_file(
                            message.chat_id, file_path, caption=caption, reply_to=message.id, attributes=upload_attributes,
                            progress_callback=lambda s, t: self.upload_progress(s, t, code, i+1, total_files)
                        )
                    except Exception as e:
                        logger.error(f"Upload failed for {file_path}: {e}")
                    finally:
                        if os.path.exists(file_path): os.remove(file_path)
            self.active_jobs[code]["status"] = "Completed"
    
    # ... (بقیه توابع کلاس بدون تغییر) ...
    async def display_dashboard(self):
        while True:
            os.system('clear' if os.name == 'posix' else 'cls'); print("--- 🚀 Advanced Downloader Dashboard 🚀 ---")
            print(f"{'Job Code':<12} | {'User ID':<12} | {'Status':<25}"); print("-" * 55)
            if not self.active_jobs: print("... Waiting for new jobs ...")
            else:
                for code, data in list(self.active_jobs.items()):
                    print(f"{code:<12} | {data.get('user_id', 'N/A'):<12} | {data.get('status', 'N/A'):<25}")
                    if data.get('status') == "Completed":
                        await asyncio.sleep(5); self.active_jobs.pop(code, None)
            print("-" * 55); print(f"Last Update: {datetime.now().strftime('%H:%M:%S')}"); await asyncio.sleep(1)
    async def run(self):
        await self.app.start(phone=self.phone)
        me = await self.app.get_me()
        logger.info(f"Worker (Album Support) ba movaffaghiat be onvane {me.first_name} vared shod.")
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
