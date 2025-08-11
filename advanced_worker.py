import os
import asyncio
import logging
import json
import subprocess
import base64
import traceback
from datetime import datetime, timezone

import yt_dlp
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeVideo
from instagrapi import Client as InstagrapiClient

from config import (TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE,
                    GROUP_ID, ORDER_TOPIC_ID, INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger("telethon").setLevel(logging.WARNING)
logging.getLogger("instagrapi").setLevel(logging.WARNING)
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
        # self.instagrapi_client = self.setup_instagrapi_client() # فعلا غیرفعال تا روی یوتوب تمرکز کنیم

    def get_video_metadata(self, file_path):
        try:
            command = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,duration', '-of', 'json', file_path]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
            data = json.loads(result.stdout)['streams'][0]
            return {'duration': int(float(data.get('duration', 0))), 'width': int(data.get('width', 0)), 'height': int(data.get('height', 0))}
        except Exception as e:
            logger.warning(f"⚠️ [{file_path}] Could not get video metadata. Reason: {e}")
            return None

    def download_media(self, url, code):
        """
        تابع اصلی دانلود که تمام منطق yt-dlp را در خود دارد.
        این تابع ضد خطا طراحی شده است.
        """
        logger.info(f"➡️ [{code}] Starting download process for URL: {url}")
        output_path = os.path.join(self.download_dir, f"{code}.%(ext)s")
        
        common_opts = {
            'outtmpl': output_path,
            'cookiefile': 'cookies.txt',
            'ignoreerrors': True, 'no_warnings': True, 'quiet': True,
        }
        
        # 1. بررسی اولیه برای گرفتن اطلاعات
        logger.info(f"ℹ️ [{code}] Performing pre-flight check to get video info...")
        with yt_dlp.YoutubeDL(common_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            if not info_dict:
                # اگر یوتیوب چالش لاگین بدهد، info_dict خالی خواهد بود
                raise Exception("Failed to get video info. YouTube may require login/cookies.")
        
        # 2. اگر اطلاعات با موفقیت دریافت شد، شروع به دانلود کن
        logger.info(f"✅ [{code}] Pre-flight check successful. Starting actual download...")
        ydl_opts_download = {
            **common_opts, # ارث‌بری تنظیمات مشترک
            'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best',
            'merge_output_format': 'mp4',
        }
        with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
            ydl.extract_info(url, download=True)

        logger.info(f"✅ [{code}] Download command executed. Searching for file(s).")
        downloaded_files = [os.path.join(self.download_dir, f) for f in os.listdir(self.download_dir) if f.startswith(code)]
        
        if not downloaded_files:
            raise Exception("Download finished, but no files were found.")
            
        caption = info_dict.get('description', info_dict.get('title', ''))
        logger.info(f"✅ [{code}] Found {len(downloaded_files)} file(s). Download successful.")
        return downloaded_files, caption, "yt-dlp"


    async def upload_single_file(self, message, file_path, code, download_method, index, total_files, original_caption):
        # ... (کد این تابع از پاسخ قبلی بدون تغییر است) ...
        # For brevity, this is kept the same as the last full correct version.
        pass

    def update_upload_status(self, sent, total, code, index, total_files):
        # ... (کد این تابع از پاسخ قبلی بدون تغییر است) ...
        pass
    
    async def process_job(self, message):
        code, url, user_id = "N/A", "N/A", 0
        try:
            lines = message.text.split('\n')
            url, code = next(l.split(":", 1)[1].strip() for l in lines if l.startswith("URL:")), next(l.split(":", 1)[1].strip() for l in lines if l.startswith("CODE:"))
            user_id = int(next(l.split(":", 1)[1].strip() for l in lines if l.startswith("USER_ID:")))
            
            self.active_jobs[code] = {"user_id": user_id, "status": "Queued", "error": None}
            logger.info(f"✅ Processing job [{code}] for user [{user_id}]")
            
            self.active_jobs[code]["status"] = "Downloading..."
            file_paths, caption_text, method = await asyncio.to_thread(self.download_media, url, code)
            
            self.active_jobs[code]["status"] = "Processing..."
            for i, path in enumerate(file_paths):
                await self.upload_single_file(message, path, code, method, i + 1, len(file_paths), caption_text)
            self.active_jobs[code]["status"] = "Completed"

        except Exception as e:
            error_short = str(e).strip().split('\n')[0]
            if "CODE:" in error_short: # To prevent showing the full message text on error
                 error_short = "Could not parse job message"
            self.active_jobs[code] = self.active_jobs.get(code, {})
            self.active_jobs[code].update({"status": "Failed", "error": error_short[:60]})
            logger.error(f"❌ [{code}] Job failed entirely. Error: {error_short}")

    async def display_dashboard(self):
        # ... (کد این تابع از پاسخ قبلی بدون تغییر است) ...
        pass

    async def run(self):
        # ... (کد این تابع از پاسخ قبلی بدون تغییر است) ...
        pass

if __name__ == "__main__":
    worker = TelethonWorker(TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE)
    asyncio.run(worker.run())
