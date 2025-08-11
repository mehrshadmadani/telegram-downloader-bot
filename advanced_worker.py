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
        try:
            command = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,duration', '-of', 'json', file_path]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
            data = json.loads(result.stdout)['streams'][0]
            return {'duration': int(float(data.get('duration', 0))), 'width': int(data.get('width', 0)), 'height': int(data.get('height', 0))}
        except Exception as e:
            logger.warning(f"⚠️ Could not get video metadata for {file_path}. Reason: {e}")
            return None

    def download_with_yt_dlp(self, url, code):
        logger.info(f"➡️ [{code}] Entering yt-dlp download function for URL: {url}")
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
                ydl.extract_info(url, download=True)
            
            logger.info(f"✅ [{code}] yt-dlp extract_info finished. Searching for downloaded file(s).")
            downloaded_files = [os.path.join(self.download_dir, f) for f in os.listdir(self.download_dir) if f.startswith(code)]
            
            if downloaded_files:
                logger.info(f"✅ [{code}] Found {len(downloaded_files)} file(s). Returning from function.")
                with yt_dlp.YoutubeDL({'quiet': True, 'ignoreerrors': True}) as ydl_info:
                    info_dict = ydl_info.extract_info(url, download=False)
                    caption = info_dict.get('description', info_dict.get('title', ''))
                return downloaded_files, caption, "yt-dlp"
            else:
                logger.warning(f"⚠️ [{code}] yt-dlp finished but no files were found starting with the code.")
                return [], None, None
        except Exception as e:
            logger.error(f"❌ [{code}] CRITICAL ERROR inside yt-dlp function: {e}", exc_info=True)
            return [], None, None

    def download_from_instagram(self, url, code):
        if self.instagrapi_client:
            try:
                logger.info(f"➡️ [{code}] Attempt 1 (instagrapi) for Instagram.")
                media_pk = self.instagrapi_client.media_pk_from_url(url)
                media_info = self.instagrapi_client.media_info(media_pk).dict()
                caption = media_info.get("caption_text", "")
                resources = media_info.get("resources", []) or [media_info]
                
                downloaded_files = []
                for i, res in enumerate(resources):
                    dl_path, file_ext = None, ".jpg"
                    if res.get("media_type") == 2 and res.get('video_url'):
                        dl_path, file_ext = self.instagrapi_client.video_download(res['pk'], self.download_dir), ".mp4"
                    elif res.get("media_type") == 1 and res.get('thumbnail_url'):
                        dl_path, file_ext = self.instagrapi_client.photo_download(res['pk'], self.download_dir), ".jpg"
                    
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

    async def upload_single_file(self, message, file_path, code, download_method, index, total_files, original_caption):
        """
        این تابع متخصص آپلود یک فایل است. منطق آن از نسخه پایدار الهام گرفته شده
        و برای کار با قابلیت‌های جدید بهینه شده است.
        """
        if not os.path.exists(file_path):
            logger.error(f"❌ [{code}] File {file_path} vanished before upload.")
            return

        file_size = os.path.getsize(file_path)
        logger.info(f"ℹ️ [{code}] Uploading file {index}/{total_files}: {os.path.basename(file_path)} ({file_size / 1024**2:.2f} MB)")
        
        # آماده‌سازی مشخصات ویدیو برای استریمینگ بهتر
        attributes = []
        if file_path.lower().endswith(('.mp4', '.mkv', '.mov')):
            metadata = self.get_video_metadata(file_path)
            if metadata:
                attributes.append(DocumentAttributeVideo(duration=metadata['duration'], w=metadata['width'], h=metadata['height'], supports_streaming=True))
        
        try:
            # ساخت کپشن نهایی برای ارسال به گروه
            # این کپشن توسط ربات اصلی خوانده می‌شود
            caption_to_group = f"✅ Uploaded ({index}/{total_files})\nCODE: {code}\nSIZE: {file_size}\nMETHOD: {download_method}"
            
            # کپشن اصلی (توضیحات پست) فقط به آخرین فایل اضافه می‌شود
            if original_caption and index == total_files:
                encoded_caption = base64.b64encode(original_caption.encode('utf-8')).decode('utf-8')
                caption_to_group += f"\nCAPTION:{encoded_caption}"

            # شروع آپلود فایل
            await self.app.send_file(
                message.chat_id,
                file_path,
                caption=caption_to_group,
                reply_to=message.id,
                attributes=attributes,
                progress_callback=lambda s, t: self.update_upload_status(s, t, code, index, total_files)
            )
            logger.info(f"✅ [{code}] Successfully uploaded file {index}/{total_files}.")

        except Exception as e:
            logger.error(f"❌ [{code}] CRITICAL ERROR during upload of {file_path}: {e}", exc_info=True)
            self.active_jobs[code]["status"] = f"Upload Failed {index}/{total_files}"
        finally:
            # پاک‌سازی فایل از سرور پس از اتمام آپلود (چه موفق چه ناموفق)
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"ℹ️ [{code}] Removed temporary file: {os.path.basename(file_path)}")

    def update_upload_status(self, sent, total, code, index, total_files):
        percentage = int(sent * 100 / total)
        status_msg = f"Uploading {index}/{total_files}: {percentage}%"
        if code in self.active_jobs and self.active_jobs[code].get("status") != status_msg and percentage % 10 == 0:
            self.active_jobs[code]["status"] = status_msg
    
    async def process_job(self, message):
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
        
        file_paths, caption_text, method = [], None, None
        
        if "instagram.com" in url:
            self.active_jobs[code]["status"] = "Downloading (Instagram)..."
            file_paths, caption_text, method = await asyncio.to_thread(self.download_from_instagram, url, code)
        else:
            self.active_jobs[code]["status"] = "Downloading (yt-dlp)..."
            file_paths, caption_text, method = await asyncio.to_thread(self.download_with_yt_dlp, url, code)
        
        logger.info(f"✅ [{code}] Returned from download thread. Found {len(file_paths)} file(s).")
        
        if file_paths:
            self.active_jobs[code]["status"] = "Downloaded, preparing upload..."
            # به ازای هر فایل دانلود شده، تابع متخصص آپلود را صدا می‌زنیم
            for i, path in enumerate(file_paths):
                await self.upload_single_file(message, path, code, method, i + 1, len(file_paths), caption_text)
            self.active_jobs[code]["status"] = "Completed"
        else:
            self.active_jobs[code]["status"] = "Download Failed"
            logger.error(f"❌ [{code}] All download methods failed. Job ended.")

    async def display_dashboard(self):
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
                    if data.get('status') in ["Completed", "Download Failed", "Upload Failed"]:
                        await asyncio.sleep(5)
                        self.active_jobs.pop(code, None)
            print("-" * 60)
            print(f"Last Update: {datetime.now().strftime('%H:%M:%S')}")
            await asyncio.sleep(2)

    async def run(self):
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
                    if message.date < self.start_time: break
                    if message.text and "⬇️ NEW JOB" in message.text:
                        asyncio.create_task(self.process_job(message))
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"🚨 An error occurred in the main loop: {e}", exc_info=True)
                await asyncio.sleep(30)

if __name__ == "__main__":
    worker = TelethonWorker(TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE)
    asyncio.run(worker.run())
