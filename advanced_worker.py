import os
import asyncio
import logging
import json
import subprocess
import base64
from datetime import datetime, timezone
from functools import partial

import yt_dlp
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeVideo
# from instagrapi import Client as InstagrapiClient # In this version we focus on yt-dlp

from config import (TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE,
                    GROUP_ID, ORDER_TOPIC_ID) # INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD

# --- سیستم لاگ‌گیری پیشرفته (هم در کنسول و هم در فایل) ---
# ۱. ایجاد یک لاگر اصلی
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# ۲. فرمت لاگ
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
# ۳. هندلر برای چاپ در کنسول
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)
# ۴. هندلر برای نوشتن در فایل
file_handler = logging.FileHandler('bot.log', encoding='utf-8')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# جلوگیری از لاگ‌های اضافی کتابخانه‌ها
logging.getLogger("telethon").setLevel(logging.WARNING)
logging.getLogger("yt_dlp").setLevel(logging.WARNING)

class TelethonWorker:
    def __init__(self, api_id, api_hash, phone):
        self.app = TelegramClient("telethon_session", api_id, api_hash)
        self.phone = phone
        self.download_dir = "downloads"
        os.makedirs(self.download_dir, exist_ok=True)
        self.processed_ids = set()
        self.start_time = datetime.now(timezone.utc)
        self.active_jobs = {}

    def yt_dlp_progress_hook(self, d, code):
        """این تابع در حین دانلود توسط yt-dlp فراخوانی می‌شود."""
        if d['status'] == 'downloading':
            percent_str = d.get('_percent_str', '0.0%').strip()
            speed_str = d.get('_speed_str', 'N/A').strip()
            self.active_jobs[code]["status"] = f"Downloading: {percent_str} at {speed_str}"
        elif d['status'] == 'finished':
            self.active_jobs[code]["status"] = "Download Finished, Processing..."


    def download_media(self, url, code):
        """تابع اصلی دانلود که حالا از progress hook پشتیبانی می‌کند."""
        try:
            logger.info(f"➡️ [{code}] Starting download process for URL: {url}")
            output_path = os.path.join(self.download_dir, f"{code}.%(ext)s")
            
            ydl_opts = {
                'outtmpl': output_path,
                'cookiefile': 'cookies.txt',
                'ignoreerrors': True, 'no_warnings': True, 'quiet': True,
                'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best',
                'merge_output_format': 'mp4',
                'progress_hooks': [partial(self.yt_dlp_progress_hook, code=code)], # <--- قابلیت جدید
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=True) # دانلود و اجرای هوک
            
            logger.info(f"✅ [{code}] Download process finished. Searching for file(s).")
            downloaded_files = [os.path.join(self.download_dir, f) for f in os.listdir(self.download_dir) if f.startswith(code)]
            
            if not downloaded_files:
                raise Exception("yt-dlp finished but no files were found.")
            
            # استخراج کپشن بعد از دانلود
            caption = info_dict.get('description', info_dict.get('title', '')) if info_dict else ""
            return downloaded_files, caption, "yt-dlp"

        except Exception as e:
            logger.error(f"❌ [{code}] Error in download_media: {e}", exc_info=True)
            raise e


    async def process_job(self, message):
        code, url, user_id = "N/A", "N/A", 0
        try:
            # ... (بخش خواندن پیام مثل قبل) ...
            lines = message.text.split('\n')
            url, code = next(l.split(":", 1)[1].strip() for l in lines if l.startswith("URL:")), next(l.split(":", 1)[1].strip() for l in lines if l.startswith("CODE:"))
            user_id = int(next(l.split(":", 1)[1].strip() for l in lines if l.startswith("USER_ID:")))
            
            self.active_jobs[code] = {"user_id": user_id, "status": "Queued", "error": None}
            logger.info(f"✅ Job [{code}] for user [{user_id}] received.")
            
            file_paths, caption_text, method = await asyncio.to_thread(self.download_media, url, code)
            
            self.active_jobs[code]["status"] = "Processing..."
            for i, path in enumerate(file_paths):
                # ... (بخش آپلود مثل قبل) ...
                await self.upload_single_file(message, path, code, method, i + 1, len(file_paths), caption_text)
            
            self.active_jobs[code]["status"] = "Completed"

        except Exception as e:
            # ... (بخش مدیریت خطا مثل قبل) ...
            error_short = str(e).strip().split('\n')[0]
            if "CODE:" in error_short: error_short = "Could not parse job message"
            if code in self.active_jobs:
                self.active_jobs[code].update({"status": "Failed", "error": error_short[:60]})
            logger.error(f"❌ [{code}] Job failed entirely. Error: {error_short}")

    # ... سایر توابع مثل get_video_metadata, upload_single_file, display_dashboard, run, و main ...
    # این توابع را از پاسخ کامل قبلی کپی کنید.

if __name__ == "__main__":
    print("--- Starting Final Worker with Advanced Logging ---")
    worker = TelethonWorker(TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE)
    asyncio.run(worker.run())
