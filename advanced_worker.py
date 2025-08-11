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
from instagrapi import Client # کتابخانه جدید
from instagrapi.exceptions import LoginRequired
from config import (TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, 
                    GROUP_ID, ORDER_TOPIC_ID, MAJID_API_TOKEN, 
                    INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)

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
        
        # --- راه‌اندازی کلاینت instagrapi ---
        self.insta_client = Client()
        session_file = "insta_session.json"
        try:
            if os.path.exists(session_file):
                logger.info("Loading Instagram session from file...")
                self.insta_client.load_settings(session_file)
                self.insta_client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            else:
                logger.info("Instagram session file not found. Logging in with username/password...")
                self.insta_client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                self.insta_client.dump_settings(session_file)
            logger.info("Instagram login/session load successful.")
        except Exception as e:
            logger.error(f"FATAL: Failed to login to Instagram with instagrapi: {e}")

    # ... (توابع get_video_metadata, upload_progress, display_dashboard بدون تغییر) ...
    def get_video_metadata(self, file_path):
        try:
            command = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,duration', '-of', 'json', file_path]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30); data = json.loads(result.stdout)['streams'][0]
            return {'duration': int(float(data['duration'])), 'width': int(data['width']), 'height': int(data['height'])}
        except: return None
    
    def download_media(self, url, code, user_id):
        self.active_jobs[code] = {"user_id": user_id, "status": "Downloading..."}
        
        # --- منطق دانلود با instagrapi ---
        if "instagram.com" in url:
            try:
                logger.info(f"Attempting download with instagrapi for CODE: {code}")
                media_pk = self.insta_client.media_pk_from_url(url)
                media_info = self.insta_client.media_info(media_pk).dict()

                media_type = media_info.get("media_type")
                output_path = None

                if media_type == 1: # Photo
                    output_path = self.insta_client.photo_download(media_pk, folder=self.download_dir)
                elif media_type == 2: # Video
                    output_path = self.insta_client.video_download(media_pk, folder=self.download_dir)
                elif media_type == 8: # Album/Carousel
                    # دانلود اولین آیتم از آلبوم
                    first_item = media_info['resources'][0]
                    if first_item['media_type'] == 1:
                        output_path = self.insta_client.photo_download(first_item['pk'], folder=self.download_dir)
                    elif first_item['media_type'] == 2:
                        output_path = self.insta_client.video_download(first_item['pk'], folder=self.download_dir)

                if output_path:
                    # تغییر نام فایل به کد منحصر به فرد
                    final_path = os.path.join(self.download_dir, f"{code}{os.path.splitext(output_path)[1]}")
                    os.rename(output_path, final_path)
                    self.active_jobs[code]["status"] = "Downloaded"; return final_path

            except Exception as e:
                logger.error(f"instagrapi failed for CODE {code}: {e}. No further fallbacks.")

        # --- منطق دانلود برای پلتفرم‌های دیگر (yt-dlp) ---
        else:
            logger.info(f"Using yt-dlp for CODE: {code}")
            # ... (کد yt-dlp بدون تغییر) ...
            output_path = os.path.join(self.download_dir, f"{code} - %(title).30s.%(ext)s")
            base_opts = {'outtmpl': output_path, 'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None, 'ignoreerrors': True, 'quiet': True, 'no_warnings': True, 'socket_timeout': 1800}
            if "soundcloud" in url or "spotify" in url: ydl_opts = {'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]}
            else: ydl_opts = {'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best', 'merge_output_format': 'mp4'}
            ydl_opts.update(base_opts)
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                    for f in os.listdir(self.download_dir):
                        if f.startswith(code): self.active_jobs[code]["status"] = "Downloaded"; return os.path.join(self.download_dir, f)
            except Exception as e: logger.error(f"yt-dlp download failed for CODE {code}: {e}")
        
        self.active_jobs[code]["status"] = "Download Failed"; return None

    # ... (بقیه توابع کلاس بدون تغییر) ...
    async def upload_progress(self, sent_bytes, total_bytes, code):
        percentage = int(sent_bytes * 100 / total_bytes);
        if percentage % 10 == 0 or percentage == 100:
            if code in self.active_jobs: self.active_jobs[code]["status"] = f"Uploading: {percentage}%"
    async def process_job(self, message):
        if message.id in self.processed_ids: return
        self.processed_ids.add(message.id)
        try:
            lines = message.text.split('\n'); url = next(l.replace("URL:", "").strip() for l in lines if l.startswith("URL:")); code = next(l.replace("CODE:", "").strip() for l in lines if l.startswith("CODE:")); user_id = int(next(l.replace("USER_ID:", "").strip() for l in lines if l.startswith("USER_ID:")))
        except: return
        file_path = await asyncio.to_thread(self.download_media, url, code, user_id)
        if file_path and os.path.exists(file_path):
            file_size = os.path.getsize(file_path); upload_attributes = []
            if file_path.lower().endswith(('.mp4', '.mkv', '.mov')):
                metadata = self.get_video_metadata(file_path)
                if metadata: upload_attributes.append(DocumentAttributeVideo(duration=metadata['duration'], w=metadata['width'], h=metadata['height'], supports_streaming=True))
            try:
                caption = f"✅ Uploaded\nCODE: {code}\nSIZE: {file_size}"
                await self.app.send_file(
                    message.chat_id, file_path, caption=caption, reply_to=message.id, attributes=upload_attributes,
                    progress_callback=lambda s, t: self.upload_progress(s, t, code)
                )
                self.active_jobs[code]["status"] = "Completed"
            except: self.active_jobs[code]["status"] = "Upload Failed"
            finally:
                if os.path.exists(file_path): os.remove(file_path)
    async def display_dashboard(self):
        while True:
            os.system('clear' if os.name == 'posix' else 'cls'); print("--- 🚀 Advanced Downloader Dashboard 🚀 ---")
            print(f"{'Job Code':<12} | {'User ID':<12} | {'Status':<20}"); print("-" * 50)
            if not self.active_jobs: print("... Waiting for new jobs ...")
            else:
                for code, data in list(self.active_jobs.items()):
                    print(f"{code:<12} | {data.get('user_id', 'N/A'):<12} | {data.get('status', 'N/A'):<20}")
                    if data.get('status') in ["Completed", "Download Failed", "Upload Failed"]:
                        await asyncio.sleep(3); self.active_jobs.pop(code, None)
            print("-" * 50); print(f"Last Update: {datetime.now().strftime('%H:%M:%S')}"); await asyncio.sleep(1)
    async def run(self):
        await self.app.start(phone=self.phone)
        me = await self.app.get_me()
        logger.info(f"Worker (instagrapi Version) ba movaffaghiat be onvane {me.first_name} vared shod.")
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
    worker = TelethonWorker(api_id=TELEGRAM_API_ID, api_hash=TELEGRAM_API_HASH, phone=TELEGRAM_PHONE); await worker.run()
if __name__ == "__main__":
    print("--- Rah andazi instagrapi Worker ---"); asyncio.run(main())
