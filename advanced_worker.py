import os
import asyncio
import logging
import json
import subprocess
import base64
from datetime import datetime, timezone

import yt_dlp
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeVideo
from instagrapi import Client as InstagrapiClient

from config import (TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE,
                    GROUP_ID, ORDER_TOPIC_ID, INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)

# --- سیستم لاگ‌گیری دقیق ---
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
        # self.instagrapi_client = self.setup_instagrapi_client() # برای تمرکز روی مشکل اصلی، فعلا غیرفعال است

    def setup_instagrapi_client(self):
        try:
            client = InstagrapiClient()
            session_file = "insta_session.json"
            if os.path.exists(session_file):
                client.load_settings(session_file)
                client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                logger.info("✅ Instagram session loaded successfully.")
            else:
                client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                client.dump_settings(session_file)
                logger.info("✅ Instagram login successful and session saved.")
            return client
        except Exception as e:
            logger.error(f"❌ FATAL: Could not login to Instagram. Error: {e}")
            return None

    def get_video_metadata(self, file_path):
        try:
            command = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,duration', '-of', 'json', file_path]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
            data = json.loads(result.stdout)['streams'][0]
            return {'duration': int(float(data.get('duration', 0))), 'width': int(data.get('width', 0)), 'height': int(data.get('height', 0))}
        except Exception as e:
            logger.warning(f"⚠️ Could not get video metadata for {os.path.basename(file_path)}. Reason: {e}")
            return None

    def download_media(self, url, code):
        """
        تابع اصلی دانلود که تمام منطق yt-dlp را در خود دارد.
        این تابع ابتدا اطلاعات را چک کرده و سپس دانلود می‌کند تا ضد خطا باشد.
        """
        logger.info(f"➡️ [{code}] Starting download process for URL: {url}")
        output_path = os.path.join(self.download_dir, f"{code}.%(ext)s")
        
        common_opts = {
            'outtmpl': output_path,
            'cookiefile': 'cookies.txt',
            'ignoreerrors': True, 'no_warnings': True, 'quiet': True,
        }
        
        # 1. بررسی اولیه برای گرفتن اطلاعات (Pre-flight Check)
        logger.info(f"ℹ️ [{code}] Performing pre-flight check to get video info...")
        with yt_dlp.YoutubeDL(common_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            if not info_dict:
                raise Exception("Failed to get video info. YouTube may require login/cookies.")
        
        # 2. اگر اطلاعات با موفقیت دریافت شد، شروع به دانلود
        logger.info(f"✅ [{code}] Pre-flight check successful. Starting actual download...")
        ydl_opts_download = {
            **common_opts,
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
        try:
            if not os.path.exists(file_path):
                raise Exception(f"File vanished before upload: {os.path.basename(file_path)}")

            file_size = os.path.getsize(file_path)
            self.active_jobs[code]["status"] = f"Uploading {index}/{total_files}..."
            logger.info(f"ℹ️ [{code}] Uploading file {index}/{total_files}: {os.path.basename(file_path)} ({file_size / 1024**2:.2f} MB)")
            
            attributes, caption_to_group = [], f"✅ Uploaded ({index}/{total_files})\nCODE: {code}\nSIZE: {file_size}\nMETHOD: {download_method}"
            if file_path.lower().endswith(('.mp4', '.mkv', '.mov')):
                metadata = self.get_video_metadata(file_path)
                if metadata: attributes.append(DocumentAttributeVideo(duration=metadata['duration'], w=metadata['width'], h=metadata['height'], supports_streaming=True))
            
            if original_caption and index == total_files:
                encoded_caption = base64.b64encode(original_caption.encode('utf-8')).decode('utf-8')
                caption_to_group += f"\nCAPTION:{encoded_caption}"

            await self.app.send_file(message.chat_id, file_path, caption=caption_to_group, reply_to=message.id, attributes=attributes,
                                     progress_callback=lambda s, t: self.update_upload_status(s, t, code, index, total_files))
            logger.info(f"✅ [{code}] Successfully uploaded file {index}/{total_files}.")
        except Exception as e:
            raise e
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

    def update_upload_status(self, sent, total, code, index, total_files):
        percentage = int(sent * 100 / total)
        self.active_jobs[code]["status"] = f"Uploading {index}/{total_files}: {percentage}%"
    
    async def process_job(self, message):
        code, url, user_id = "N/A", "N/A", 0
        try:
            lines = message.text.split('\n')
            url = next(l.split(":", 1)[1].strip() for l in lines if l.startswith("URL:"))
            code = next(l.split(":", 1)[1].strip() for l in lines if l.startswith("CODE:"))
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
            if "CODE:" in error_short:
                 error_short = "Could not parse job message"
            # Ensure the job code exists before updating
            if code in self.active_jobs:
                self.active_jobs[code].update({"status": "Failed", "error": error_short[:60]})
            logger.error(f"❌ [{code}] Job failed entirely. Error: {error_short}")

    async def display_dashboard(self):
        while True:
            os.system('clear' if os.name == 'posix' else 'cls')
            print("--- 🚀 Advanced Downloader Dashboard (Final) 🚀 ---")
            print(f"{'Job Code':<12} | {'User ID':<12} | {'Status':<35}")
            print("-" * 65)
            
            if not self.active_jobs:
                print("... Waiting for new jobs ...")
            else:
                for code, data in list(self.active_jobs.items()):
                    print(f"{code:<12} | {data.get('user_id', 'N/A'):<12} | {data.get('status', 'N/A'):<35}")
                    if data.get("error"):
                        print(f"{'':<12} | {'':<12} | └─ ❗Error: {data['error'][:45]}")
                    if data.get('status') in ["Completed", "Failed"]:
                        await asyncio.sleep(10)
                        self.active_jobs.pop(code, None)

            print("-" * 65)
            print(f"Last Update: {datetime.now().strftime('%H:%M:%S')}")
            await asyncio.sleep(2)

    async def run(self):
        await self.app.start(phone=self.phone)
        me = await self.app.get_me()
        logger.info(f"✅ Worker (Final Version) successfully logged in as {me.first_name}")
        
        dashboard_task = asyncio.create_task(self.display_dashboard())
        logger.info(f"👂 Worker started listening...")

        while True:
            try:
                async for message in self.app.iter_messages(GROUP_ID, reply_to=ORDER_TOPIC_ID, limit=10):
                    if message.date < self.start_time: break
                    if message.text and "⬇️ NEW JOB" in message.text:
                        asyncio.create_task(self.process_job(message))
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"🚨 An error occurred in the main loop: {e}", exc_info=True)
                await asyncio.sleep(30)

if __name__ == "__main__":
    print("--- Starting Final Worker ---")
    worker = TelethonWorker(TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE)
    asyncio.run(worker.run())
