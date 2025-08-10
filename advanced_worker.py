import os
import asyncio
import logging
from datetime import datetime, timezone
import yt_dlp
from telethon import TelegramClient
from telethon.errors.rpcerrorlist import FloodWaitError
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE

# --- تنظیمات لاگ ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- کلاس ورکر نهایی ---
# اسم کلاس اینجا اصلاح شد
class TelethonWorker:
    def __init__(self, api_id, api_hash, phone):
        self.app = TelegramClient("telethon_session", api_id, api_hash)
        self.phone = phone
        self.download_dir = "downloads"
        os.makedirs(self.download_dir, exist_ok=True)
        self.processed_ids = set()
        # زمان شروع به کار اسکریپت برای نادیده گرفتن پیام‌های قدیمی
        self.start_time = datetime.now(timezone.utc)

    def download_media(self, url, code):
        logger.info(f"Shروع download baraye CODE: {code}")
        output_path = os.path.join(self.download_dir, f"{code} - %(title).30s.%(ext)s")
        
        # بهینه‌سازی: تنظیمات جداگانه برای اینستاگرام
        if "instagram.com" in url:
            ydl_opts = {
                'outtmpl': output_path,
                'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
                'ignoreerrors': True, 'quiet': True, 'no_warnings': True,
            }
        else: # تنظیمات برای یوتیوب و بقیه
            ydl_opts = {
                'outtmpl': output_path,
                'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
                'merge_output_format': 'mp4',
                'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
                'ignoreerrors': True, 'quiet': True, 'no_warnings': True,
            }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)
                for f in os.listdir(self.download_dir):
                    if f.startswith(code):
                        downloaded_file = os.path.join(self.download_dir, f)
                        logger.info(f"Download movaffagh baraye CODE: {code} -> {downloaded_file}")
                        return downloaded_file
            return None
        except Exception as e:
            logger.error(f"Exception dar hengam download (CODE: {code}): {e}")
            return None

    async def upload_progress(self, sent_bytes, total_bytes, code):
        percentage = int(sent_bytes * 100 / total_bytes)
        if percentage % 10 == 0 or percentage == 100:
            logger.info(f"Uploading CODE {code}: {percentage}%")

    async def process_job(self, message):
        if message.id in self.processed_ids: return
        self.processed_ids.add(message.id)
        
        try:
            url = next(line.replace("URL:", "").strip() for line in message.text.split('\n') if line.startswith("URL:"))
            code = next(line.replace("CODE:", "").strip() for line in message.text.split('\n') if line.startswith("CODE:"))
        except Exception: return

        logger.info(f"Kar jadidیاft شد: {code}. Shorooe pardazesh...")
        
        file_path = await asyncio.to_thread(self.download_media, url, code)
        
        if file_path and os.path.exists(file_path):
            logger.info(f"Opload shoroo shod baraye CODE:
