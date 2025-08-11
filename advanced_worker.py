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
from instagramy import InstagramUser # کتابخانه جدید
from config import (TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, 
                    GROUP_ID, ORDER_TOPIC_ID, MAJID_API_TOKEN, 
                    INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TelethonWorker:
    def __init__(self, api_id, api_hash, phone):
        # ... (بدون تغییر) ...
        self.app = TelegramClient("telethon_session", api_id, api_hash); self.phone = phone
        self.download_dir = "downloads"; os.makedirs(self.download_dir, exist_ok=True)
        self.processed_ids = set(); self.start_time = datetime.now(timezone.utc); self.active_jobs = {}

    def get_video_metadata(self, file_path):
        # ... (بدون تغییر) ...
        try:
            command = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,duration', '-of', 'json', file_path]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
            data = json.loads(result.stdout)['streams'][0]
            return {'duration': int(float(data['duration'])), 'width': int(data['width']), 'height': int(data['height'])}
        except: return None

    def download_media(self, url, code, user_id):
        self.active_jobs[code] = {"user_id": user_id, "status": "Downloading..."}
        
        # --- منطق دانلود چند مرحله‌ای برای اینستاگرام ---
        if "instagram.com" in url:
            # --- تلاش اول: API ---
            logger.info(f"Attempt 1 (API) for CODE: {code}")
            try:
                api_url = f"https://api.majidapi.ir/instagram/download?url={url}&out=url&token={MAJID_API_TOKEN}"
                api_response = requests.get(api_url, timeout=20)
                data = api_response.json()
                if data.get("status") == 200:
                    result = data.get("result", {})
                    media_url = result.get("video") or result.get("image")
                    if media_url:
                        ext = ".jpg" if ".jpg" in media_url.split('?')[0] else ".mp4"
                        output_path = os.path.join(self.download_dir, f"{code}{ext}")
                        media_res = requests.get(media_url, stream=True, timeout=1800)
                        with open(output_path, 'wb') as f:
                            for chunk in media_res.iter_content(chunk_size=8192): f.write(chunk)
                        self.active_jobs[code]["status"] = "Downloaded"; return output_path
            except Exception as e:
                logger.warning(f"API failed: {e}. Trying next method.")

            # --- تلاش دوم: instagram-scraper (با لاگین) ---
            logger.info(f"Attempt 2 (Scraper) for CODE: {code}")
            try:
                scraper_command = [
                    'instagram-scraper', url,
                    '-u', INSTAGRAM_USERNAME, '-p', INSTAGRAM_PASSWORD,
                    '-d', self.download_dir, '--latest', '--request-timeout', '30'
                ]
                subprocess.run(scraper_command, check=True, capture_output=True)
                # پیدا کردن فایل دانلود شده (نام آن معمولا شامل تاریخ و یوزرنیم است)
                for root, _, files in os.walk(self.download_dir):
                    for file in files:
                        if url.split('/')[-2] in file: # یک روش حدودی برای پیدا کردن فایل
                            downloaded_path = os.path.join(root, file)
                            final_path = os.path.join(self.download_dir, f"{code}{os.path.splitext(file)[1]}")
                            os.rename(downloaded_path, final_path)
                            self.active_jobs[code]["status"] = "Downloaded"; return final_path
            except Exception as e:
                logger.warning(f"Scraper failed: {e}. Trying next method.")

            # --- تلاش سوم: yt-dlp (با کوکی) ---
            logger.info(f"Attempt 3 (yt-dlp) for CODE: {code}")
            # ... (بقیه کد دانلود با yt-dlp بدون تغییر) ...

        # --- منطق دانلود برای پلتفرم‌های دیگر ---
        logger.info(f"Using yt-dlp for CODE: {code} (Platform: Other)")
        # ... (کد دانلود برای یوتیوب، ساندکلود و ... بدون تغییر) ...

    # ... (بقیه توابع کلاس بدون تغییر) ...
