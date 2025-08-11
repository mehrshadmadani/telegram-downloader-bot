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
from config import (TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, 
                    GROUP_ID, ORDER_TOPIC_ID, MAJID_API_TOKEN, 
                    INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)

# --- سیستم لاگ‌گیری ---
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
        # ... (بقیه __init__ بدون تغییر)

    # ... (تمام توابع دانلود media و get_video_metadata بدون تغییر) ...
    def get_video_metadata(self, file_path):
        try:
            command = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,duration', '-of', 'json', file_path]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30); data = json.loads(result.stdout)['streams'][0]
            return {'duration': int(float(data['duration'])), 'width': int(data['width']), 'height': int(data['height'])}
        except: return None
        
    def download_media(self, url, code, user_id):
        self.active_jobs[code] = {"user_id": user_id, "status": "Downloading..."}
        if "instagram.com" in url:
            # ... (زنجیره دانلود اینستاگرام بدون تغییر) ...
            pass
        else:
            # ... (دانلود برای پلتفرم‌های دیگر بدون تغییر) ...
            try:
                logger.info(f"Using yt-dlp for {url.split('/')[2]} CODE: {code}")
                output_path = os.path.join(self.download_dir, f"{code} - %(title).30s.%(ext)s")
                base_opts = {'outtmpl': output_path, 'cookiefile': 'cookies.txt', 'ignoreerrors': True, 'quiet': True, 'no_warnings': True, 'socket_timeout': 1800}
                if "soundcloud" in url or "spotify" in url: ydl_opts = {'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]}
                else: ydl_opts = {'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best', 'merge_output_format': 'mp4'}
                ydl_opts.update(base_opts)
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info_dict = ydl.extract_info(url, download=True)
                    caption = info_dict.get('description', '')
                    downloaded_files = [os.path.join(self.download_dir, f) for f in os.listdir(self.download_dir) if f.startswith(code)]
                    if downloaded_files:
                        self.active_jobs[code]["status"] = "Downloaded"; return (downloaded_files, caption, "yt-dlp")
            except Exception as e: logger.error(f"yt-dlp failed for CODE {code}: {e}")

        self.active_jobs[code]["status"] = "Download Failed"; return ([], None, None)

    async def process_job(self, message):
        if message.id in self.processed_ids: return
        self.processed_ids.add(message.id)
        try:
            lines = message.text.split('\n'); url = next(l.replace("URL:", "").strip() for l in lines if l.startswith("URL:")); code = next(l.replace("CODE:", "").strip() for l in lines if l.startswith("CODE:")); user_id = int(next(l.replace("USER_ID:", "").strip() for l in lines if l.startswith("USER_ID:")))
        except: return
        
        file_paths, original_caption, download_method = await asyncio.to_thread(self.download_media, url, code, user_id)

        if file_paths:
            total_files = len(file_paths)
            all_successful = True
            for i, file_path in enumerate(file_paths):
                if os.path.exists(file_path):
                    self.active_jobs[code]["status"] = f"Uploading {i+1}/{total_files}"
                    try:
                        # --- بازگشت به روش آپلود ساده و پایدار شما ---
                        file_size = os.path.getsize(file_path)
                        caption_str = ""
                        if i == total_files - 1 and original_caption:
                            encoded_caption = base64.b64encode(original_caption.encode('utf-8')).decode('utf-8')
                            caption_str = f"\nCAPTION:{encoded_caption}"
                        caption = f"✅ Uploaded ({i+1}/{total_files})\nCODE: {code}\nSIZE: {file_size}\nMETHOD: {download_method}{caption_str}"
                        
                        await self.app.send_file(
                            message.chat_id,
                            file_path,
                            caption=caption,
                            reply_to=message.id,
                            force_document=False # اجازه به تلگرام برای تشخیص نوع فایل
                        )
                        # --- پایان بخش اصلاح شده ---
                    except Exception as e:
                        logger.error(f"Upload failed for {file_path}: {e}")
                        all_successful = False
                    finally:
                        if os.path.exists(file_path): os.remove(file_path)
            
            if all_successful:
                self.active_jobs[code]["status"] = "Completed"
            else:
                self.active_jobs[code]["status"] = "Upload Failed"

    # ... (بقیه توابع کلاس بدون تغییر) ...
    async def display_dashboard(self):
        while True:
            os.system('clear' if os.name == 'posix' else 'cls'); print("--- 🚀 Advanced Downloader Dashboard 🚀 ---")
            print(f"{'Job Code':<12} | {'User ID':<12} | {'Status':<25}"); print("-" * 55)
            if not self.active_jobs: print("... Waiting for new jobs ...")
            else:
                for code, data in list(self.active_jobs.items()):
                    print(f"{code:<12} | {data.get('user_id', 'N/A'):<12} | {data.get('status', 'N/A'):<25}")
                    if data.get('status') in ["Completed", "Download Failed", "Upload Failed"]:
                        await asyncio.sleep(5); self.active_jobs.pop(code, None)
            print("-" * 55); print(f"Last Update: {datetime.now().strftime('%H:%M:%S')}"); await asyncio.sleep(1)

    async def run(self):
        await self.app.start(phone=self.phone)
        me = await self.app.get_me()
        logger.info(f"Worker (Stable Uploader) ba movaffaghiat be onvane {me.first_name} vared shod.")
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
