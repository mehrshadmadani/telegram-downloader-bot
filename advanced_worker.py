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

class TelethonWorker:
    def __init__(self, api_id, api_hash, phone):
        self.app = TelegramClient("telethon_session", api_id, api_hash)
        self.phone = phone
        self.download_dir = "downloads"
        os.makedirs(self.download_dir, exist_ok=True)
        self.processed_ids = set()
        self.start_time = datetime.now(timezone.utc)
        self.active_jobs = {}
        self.instagrapi_client = self.setup_instagrapi_client()

    def setup_instagrapi_client(self):
        """برای لاگین به اینستاگرام و مدیریت سشن تلاش می‌کند."""
        try:
            client = InstagrapiClient()
            session_file = "insta_session.json"
            if os.path.exists(session_file):
                client.load_settings(session_file)
                client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                logger.info("✅ Instagram session loaded successfully.")
            else:
                logger.info("ℹ️ No Instagram session found, logging in...")
                client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                client.dump_settings(session_file)
                logger.info("✅ Instagram login successful and session saved.")
            return client
        except Exception as e:
            logger.error(f"❌ FATAL: Could not login to Instagram. instagrapi will be unavailable. Error: {e}")
            return None

    def get_video_metadata(self, file_path):
        """اطلاعات ویدیو مانند ابعاد و مدت زمان را با ffprobe استخراج می‌کند."""
        try:
            command = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,duration', '-of', 'json', file_path]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
            data = json.loads(result.stdout)['streams'][0]
            return {'duration': int(float(data.get('duration', 0))), 'width': int(data.get('width', 0)), 'height': int(data.get('height', 0))}
        except Exception as e:
            logger.warning(f"⚠️ Could not get video metadata for {file_path}. Reason: {e}")
            return None

    def download_with_yt_dlp(self, url, code):
        """تابع عمومی و اصلی برای دانلود از تمام پلتفرم‌ها (یوتیوب، ساندکلود و...) با yt-dlp."""
        logger.info(f"➡️ [{code}] Attempting download with yt-dlp for URL: {url}")
        
        output_path = os.path.join(self.download_dir, f"{code} - %(title).30s.%(ext)s")
        ydl_opts = {
            'outtmpl': output_path,
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
            'ignoreerrors': True,
            'no_warnings': True,
            'quiet': True,
            'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best',
            'merge_output_format': 'mp4',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=True)
                caption = info_dict.get('description', info_dict.get('title', ''))
                
                downloaded_files = [os.path.join(self.download_dir, f) for f in os.listdir(self.download_dir) if f.startswith(code)]
                if downloaded_files:
                    logger.info(f"✅ [{code}] yt-dlp downloaded {len(downloaded_files)} file(s).")
                    return downloaded_files, caption, "yt-dlp"
        except Exception as e:
            logger.error(f"❌ [{code}] CRITICAL ERROR during yt-dlp download: {e}", exc_info=True)
            
        return [], None, None

    def download_from_instagram(self, url, code):
        """برای دانلود از اینستاگرام ابتدا با instagrapi و سپس با yt-dlp تلاش می‌کند."""
        if self.instagrapi_client:
            try:
                logger.info(f"➡️ [{code}] Attempt 1 (instagrapi) for Instagram.")
                media_pk = self.instagrapi_client.media_pk_from_url(url)
                media_info = self.instagrapi_client.media_info(media_pk).dict()
                caption = media_info.get("caption_text", "")
                resources = media_info.get("resources", []) or [media_info]
                
                downloaded_files = []
                for i, res in enumerate(resources):
                    dl_path = None
                    file_ext = ".jpg"
                    if res.get("media_type") == 2 and res.get('video_url'):
                        dl_path = self.instagrapi_client.video_download(res['pk'], self.download_dir)
                        file_ext = os.path.splitext(dl_path)[1] if dl_path else ".mp4"
                    elif res.get("media_type") == 1 and res.get('thumbnail_url'):
                        dl_path = self.instagrapi_client.photo_download(res['pk'], self.download_dir)
                        file_ext = os.path.splitext(dl_path)[1] if dl_path else ".jpg"
                    
                    if dl_path:
                        final_path = os.path.join(self.download_dir, f"{code}_{i}{file_ext}")
                        os.rename(dl_path, final_path)
                        downloaded_files.append(final_path)
                
                if downloaded_files:
                    logger.info(f"✅ [{code}] instagrapi downloaded {len(downloaded_files)} file(s).")
                    return downloaded_files, caption, "instagrapi"
            except Exception as e:
                logger.warning(f"⚠️ [{code}] instagrapi failed: {e}. Falling back to yt-dlp.")
        
        return self.download_with_yt_dlp(url, code)

    async def upload_single_file(self, message, file_path, code, download_method, index, total, final_caption):
        """یک فایل تکی را آپلود کرده و پس از اتمام، آن را از روی دیسک پاک می‌کند."""
        if not os.path.exists(file_path):
            logger.error(f"❌ [{code}] File {file_path} vanished before upload.")
            return

        file_size = os.path.getsize(file_path)
        logger.info(f"ℹ️ [{code}] Uploading file {index}/{total}: {os.path.basename(file_path)} ({file_size / 1024**2:.2f} MB)")
        
        attributes = []
        if file_path.lower().endswith(('.mp4', '.mkv', '.mov')):
            metadata = self.get_video_metadata(file_path)
            if metadata:
                attributes.append(DocumentAttributeVideo(duration=metadata['duration'], w=metadata['width'], h=metadata['height'], supports_streaming=True))
        
        try:
            caption = f"✅ Uploaded ({index}/{total})\nCODE: {code}\nSIZE: {file_size}\nMETHOD: {download_method}"
            if final_caption:
                encoded_caption = base64.b64encode(final_caption.encode('utf-8')).decode('utf-8')
                caption += f"\nCAPTION:{encoded_caption}"

            await self.app.send_file(
                message.chat_id,
                file_path,
                caption=caption,
                reply_to=message.id,
                attributes=attributes,
                progress_callback=lambda s, t: self.update_upload_status(s, t, code, index, total)
            )
            logger.info(f"✅ [{code}] Successfully uploaded file {index}/{total}.")
        except Exception as e:
            logger.error(f"❌ [{code}] CRITICAL ERROR during upload of {file_path}: {e}", exc_info=True)
            self.active_jobs[code]["status"] = f"Upload Failed {index}/{total}"
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"ℹ️ [{code}] Removed temporary file: {os.path.basename(file_path)}")

    def update_upload_status(self, sent, total, code, index, total_files):
        """برای جلوگیری از لاگ‌های زیاد، وضعیت آپلود را در داشبورد به‌روز می‌کند."""
        percentage = int(sent * 100 / total)
        status_msg = f"Uploading {index}/{total_files}: {percentage}%"
        if code in self.active_jobs and self.active_jobs[code].get("status") != status_msg and percentage % 10 == 0:
            self.active_jobs[code]["status"] = status_msg
    
    async def process_job(self, message):
        """پیام کار جدید را پردازش، دانلود و آپلود می‌کند."""
        # --- START OF MODIFIED SECTION ---
        if message.id in self.processed_ids: return
        self.processed_ids.add(message.id)
        
        try:
            lines = message.text.split('\n')
            url = next(l.split(":", 1)[1].strip() for l in lines if l.startswith("URL:"))
            code = next(l.split(":", 1)[1].strip() for l in lines if l.startswith("CODE:"))
            user_id = int(next(l.split(":", 1)[1].strip() for l in lines if l.startswith("USER_ID:")))
        except Exception:
            logger.error(f"Could not parse job message: {message.text}"); return

        logger.info(f"✅ Processing job [{code}] for user [{user_id}] with URL: {url}")
        self.active_jobs[code] = {"user_id": user_id, "status": "Queued"}
        
        file_paths, caption, method = [], None, None
        
        if "instagram.com" in url:
            self.active_jobs[code]["status"] = "Downloading (Instagram)..."
            file_paths, caption, method = await asyncio.to_thread(self.download_from_instagram, url, code)
        else:
            self.active_jobs[code]["status"] = "Downloading (yt-dlp)..."
            file_paths, caption, method = await asyncio.to_thread(self.download_with_yt_dlp, url, code)
        
        if file_paths:
            self.active_jobs[code]["status"] = "Downloaded, preparing upload..."
            for i, file_path in enumerate(file_paths):
                await self.upload_single_file(message, file_path, code, method, i + 1, len(file_paths), caption if i + 1 == len(file_paths) else "")
            self.active_jobs[code]["status"] = "Completed"
        else:
            self.active_jobs[code]["status"] = "Download Failed"
            logger.error(f"❌ [{code}] All download methods failed. Job ended.")
        # --- END OF MODIFIED SECTION ---

    async def display_dashboard(self):
        """داشبورد وضعیت کارها را در کنسول نمایش می‌دهد."""
        while True:
            os.system('clear' if os.name == 'posix' else 'cls')
            print("--- 🚀 Advanced Downloader Dashboard 🚀 ---")
            print(f"{'Job Code':<12} | {'User ID':<12} | {'Status':<30}")
            print("-" * 60)
            if not self.active_jobs:
                print("... Waiting for new jobs ...")
            else:
                for code, data in list(self.active_jobs.items()):
                    print(f"{code:<12} | {data.get('user_id', 'N/A'):<12} | {data.get('status', 'N/A'):<30}")
                    if data.get('status') in ["Completed", "Download Failed"]:
                        await asyncio.sleep(5)
                        self.active_jobs.pop(code, None)
            print("-" * 60)
            print(f"Last Update: {datetime.now().strftime('%H:%M:%S')}")
            await asyncio.sleep(2)

    async def run(self):
        """کلاس ورکر را راه‌اندازی و اجرا می‌کند."""
        await self.app.start(phone=self.phone)
        me = await self.app.get_me()
        logger.info(f"✅ Worker (Final Version) successfully logged in as {me.first_name}")
        
        try:
            entity = await self.app.get_entity(GROUP_ID)
        except Exception as e:
            logger.critical(f"❌ Could not access Group ID ({GROUP_ID}). Check the ID and your membership. Error: {e}")
            return

        dashboard_task = asyncio.create_task(self.display_dashboard())
        logger.info(f"👂 Worker started listening in Topic ID {ORDER_TOPIC_ID}...")

        while True:
            try:
                async for message in self.app.iter_messages(entity=entity, reply_to=ORDER_TOPIC_ID, limit=20):
                    if message.date < self.start_time:
                        break
                    if message.text and "⬇️ NEW JOB" in message.text:
                        asyncio.create_task(self.process_job(message))
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"🚨 An error occurred in the main loop: {e}", exc_info=True)
                await asyncio.sleep(30)

if __name__ == "__main__":
    worker = TelethonWorker(TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE)
    asyncio.run(worker.run())
