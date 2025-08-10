import os
import asyncio
import logging
import yt_dlp
from pyrogram import Client
from pyrogram.errors import FloodWait

# --- تنظیمات لاگ برای دیباگ ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- کلاس اصلی Worker (نسخه نهایی و پایدار) ---
class FinalWorker:
    def __init__(self, api_id, api_hash, session_name="advanced_worker"):
        self.app = Client(name=session_name, api_id=api_id, api_hash=api_hash)
        self.download_dir = "downloads"
        os.makedirs(self.download_dir, exist_ok=True)
        self.processed_ids = set()

    def download_media(self, url, code):
        logger.info(f"Shروع download baraye CODE: {code}")
        output_path = os.path.join(self.download_dir, f"{code} - %(title).30s.%(ext)s")
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

    async def upload_progress(self, current, total, code):
        percentage = int(current * 100 / total)
        if percentage % 10 == 0:
            logger.info(f"Uploading CODE {code}: {percentage}%")

    async def process_job(self, message):
        if message.id in self.processed_ids:
            return
        
        self.processed_ids.add(message.id)
        
        try:
            if not message.text: return
            url = next(line.replace("URL:", "").strip() for line in message.text.split('\n') if line.startswith("
