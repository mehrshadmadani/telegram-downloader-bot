import os
import asyncio
import logging
import json
import subprocess
import requests
import base64
from datetime import datetime, timezone
import yt_dlp
from pyrogram import Client, filters # کتابخانه جدید
from pyrogram.errors import FloodWait
from config import (TELEGRAM_API_ID, TELEGRAM_API_HASH, 
                    GROUP_ID, ORDER_TOPIC_ID, MAJID_API_TOKEN, 
                    INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD, NESTCODE_API_KEY)

# --- سیستم لاگ‌گیری ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

class PyrogramWorker:
    def __init__(self, api_id, api_hash):
        # --- استفاده از کلاینت Pyrogram ---
        self.app = Client("pyrogram_session", api_id=api_id, api_hash=api_hash)
        self.download_dir = "downloads"
        os.makedirs(self.download_dir, exist_ok=True)
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
        # ... (منطق دانلود بدون تغییر باقی می‌ماند) ...
        self.active_jobs[code] = {"user_id": user_id, "status": "Downloading..."}
        if "instagram.com" in url:
            try:
                logger.info(f"Attempt 1 (instagrapi) for CODE: {code}")
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
                if downloaded_files:
                    self.active_jobs[code]["status"] = "Downloaded"; return (downloaded_files, caption, "instagrapi")
            except Exception as e: logger.warning(f"instagrapi failed: {e}")
        try:
            platform = "yt-dlp (Fallback)" if "instagram.com" in url else "yt-dlp"
            logger.info(f"Final Attempt ({platform}) for CODE: {code}")
            output_path = os.path.join(self.download_dir, f"{code} - %(title).30s.%(ext)s")
            base_opts = {'outtmpl': output_path, 'cookiefile': 'cookies.txt', 'ignoreerrors': True, 'quiet': True, 'no_warnings': True, 'socket_timeout': 1800}
            if "soundcloud.com" in url or "spotify" in url: ydl_opts = {'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]}
            elif "instagram.com" in url: ydl_opts = {'format': 'best'}
            else: ydl_opts = {'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best', 'merge_output_format': 'mp4'}
            ydl_opts.update(base_opts)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=True)
                caption = info_dict.get('description', '')
                downloaded_files = []
                for f in os.listdir(self.download_dir):
                    if f.startswith(code):
                        downloaded_files.append(os.path.join(self.download_dir, f))
                if downloaded_files:
                    self.active_jobs[code]["status"] = "Downloaded"; return (downloaded_files, caption, "yt-dlp")
        except Exception as e:
            logger.error(f"Final method (yt-dlp) failed for CODE {code}: {e}")
        self.active_jobs[code]["status"] = "Download Failed"; return ([], None, None)

    async def upload_progress(self, current, total, code, index, total_files):
        percentage = int(current * 100 / total)
        if percentage % 20 == 0 or percentage == 100:
            if code in self.active_jobs:
                self.active_jobs[code]["status"] = f"Uploading {index}/{total_files}: {percentage}%"

    async def process_job_wrapper(self, message):
        """یک پوشش برای مدیریت خطاها و آپدیت داشبورد"""
        code = "unknown"
        try:
            lines = message.text.split('\n')
            url = next(line.replace("URL:", "").strip() for line in lines if line.startswith("URL:"))
            code = next(line.replace("CODE:", "").strip() for line in lines if line.startswith("CODE:"))
            user_id = int(next(line.replace("USER_ID:", "").strip() for line in lines if line.startswith("USER_ID:")))
            
            file_paths, original_caption, download_method = await asyncio.to_thread(self.download_media, url, code, user_id)
            
            if file_paths:
                total_files = len(file_paths)
                for i, file_path in enumerate(file_paths):
                    if os.path.exists(file_path):
                        await self.upload_single_file(message, file_path, code, user_id, download_method, i + 1, total_files, original_caption)
                self.active_jobs[code]["status"] = "Completed"
            else:
                self.active_jobs[code]["status"] = "Download Failed"
        except Exception as e:
            logger.error(f"An error occurred in process_job for code {code}: {e}")
            if code in self.active_jobs:
                self.active_jobs[code]["status"] = "Process Failed"

    async def upload_single_file(self, message, file_path, code, user_id, download_method, index, total, original_caption):
        file_size = os.path.getsize(file_path)
        caption_str = ""
        if index == total and original_caption:
            encoded_caption = base64.b64encode(original_caption.encode('utf-8')).decode('utf-8')
            caption_str = f"\nCAPTION:{encoded_caption}"
        final_caption = f"✅ Uploaded ({index}/{total})\nCODE: {code}\nSIZE: {file_size}\nMETHOD: {download_method}{caption_str}"
        
        # --- استفاده از توابع آپلود Pyrogram ---
        if file_path.lower().endswith(('.mp4', '.mkv', '.mov')):
            metadata = self.get_video_metadata(file_path)
            await self.app.send_video(
                chat_id=GROUP_ID, video=file_path, caption=final_caption,
                reply_to_message_id=message.id, supports_streaming=True,
                duration=metadata.get('duration', 0), width=metadata.get('width', 0), height=metadata.get('height', 0),
                progress=self.upload_progress, progress_args=(code, index, total)
            )
        elif file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
             await self.app.send_photo(
                chat_id=GROUP_ID, photo=file_path, caption=final_caption,
                reply_to_message_id=message.id,
                progress=self.upload_progress, progress_args=(code, index, total)
            )
        else: # Audio and other documents
            await self.app.send_document(
                chat_id=GROUP_ID, document=file_path, caption=final_caption,
                reply_to_message_id=message.id,
                progress=self.upload_progress, progress_args=(code, index, total)
            )
        if os.path.exists(file_path): os.remove(file_path)

    async def display_dashboard(self):
        # ... (بدون تغییر) ...
        while True:
            os.system('clear' if os.name == 'posix' else 'cls'); print("--- 🚀 Advanced Downloader Dashboard 🚀 ---")
            print(f"{'Job Code':<12} | {'User ID':<12} | {'Status':<25}"); print("-" * 55)
            if not self.active_jobs: print("... Waiting for new jobs ...")
            else:
                for code, data in list(self.active_jobs.items()):
                    print(f"{code:<12} | {data.get('user_id', 'N/A'):<12} | {data.get('status', 'N/A'):<25}")
                    if data.get('status') in ["Completed", "Download Failed", "Upload Failed", "Process Failed"]:
                        await asyncio.sleep(5); self.active_jobs.pop(code, None)
            print("-" * 55); print(f"Last Update: {datetime.now().strftime('%H:%M:%S')}"); await asyncio.sleep(1)

    async def run(self):
        # --- تعریف Handler برای گوش دادن به پیام‌ها ---
        @self.app.on_message(filters.chat(GROUP_ID) & filters.topic(ORDER_TOPIC_ID) & filters.regex("⬇️ NEW JOB"))
        async def new_job_handler(client, message):
            asyncio.create_task(self.process_job_wrapper(message))

        await self.app.start()
        me = await self.app.get_me()
        logger.info(f"Worker (Pyrogram Version) ba movaffaghiat be onvane {me.first_name} vared shod.")
        dashboard_task = asyncio.create_task(self.display_dashboard())
        logger.info(f"Worker shoroo be check kardan Topic ID {ORDER_TOPIC_ID} kard...")
        await asyncio.Event().wait() # اسکریپت را برای همیشه در حال اجرا نگه می‌دارد

if __name__ == "__main__":
    worker = PyrogramWorker(api_id=TELEGRAM_API_ID, api_hash=TELEGRAM_API_HASH)
    asyncio.run(worker.run())
