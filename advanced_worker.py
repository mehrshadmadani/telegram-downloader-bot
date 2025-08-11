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
from telethon.tl.types import DocumentAttributeVideo
import instaloader
from instagrapi import Client as InstagrapiClient # این خط برای رفع خطا اضافه شده است
from config import (TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, 
                    GROUP_ID, ORDER_TOPIC_ID, MAJID_API_TOKEN, 
                    INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)

# --- سیستم لاگ‌گیری ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
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
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
            data = json.loads(result.stdout)['streams'][0]
            return {'duration': int(float(data['duration'])), 'width': int(data['width']), 'height': int(data['height'])}
        except: return None
        
    def download_media(self, url, code, user_id):
        self.active_jobs[code] = {"user_id": user_id, "status": "Downloading..."}
        if "instagram.com" in url:
            try:
                logger.info(f"Attempt 1 (instagrapi) for CODE: {code}")
                media_pk = self.instagrapi_client.media_pk_from_url(url)
                media_info = self.instagrapi_client.media_info(media_pk).dict()
                caption = media_info.get("caption_text", "")
                resources = media_info.get("resources", [])
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
            except Exception as e:
                logger.warning(f"instagrapi failed: {e}")
        try:
            platform = "yt-dlp (Fallback)" if "instagram.com" in url else "yt-dlp"
            logger.info(f"Final Attempt ({platform}) for CODE: {code}")
            output_path = os.path.join(self.download_dir, f"{code} - %(title).30s.%(ext)s")
            base_opts = {'outtmpl': output_path, 'cookiefile': 'cookies.txt', 'ignoreerrors': True, 'quiet': True, 'no_warnings': True, 'socket_timeout': 1800}
            if "soundcloud.com" in url or "spotify" in url:
                ydl_opts = {'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]}
            elif "instagram.com" in url:
                ydl_opts = {'format': 'best'}
            else: # YouTube
                ydl_opts = {'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best', 'merge_output_format': 'mp4'}
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

    async def upload_single_file(self, message, file_path, code, user_id, download_method, index, total, original_caption):
        if not os.path.exists(file_path): return False
        self.active_jobs[code]["status"] = f"Uploading {index}/{total}"
        file_size = os.path.getsize(file_path); upload_attributes = []
        if file_path.lower().endswith(('.mp4', '.mkv', '.mov')):
            metadata = self.get_video_metadata(file_path)
            if metadata: upload_attributes.append(DocumentAttributeVideo(duration=metadata['duration'], w=metadata['width'], h=metadata['height'], supports_streaming=True))
        
        for attempt in range(3):
            try:
                caption_str = ""
                if index == total and original_caption:
                    encoded_caption = base64.b64encode(original_caption.encode('utf-8')).decode('utf-8')
                    caption_str = f"\nCAPTION:{encoded_caption}"
                caption = f"✅ Uploaded ({index}/{total})\nCODE: {code}\nSIZE: {file_size}\nMETHOD: {download_method}{caption_str}"
                
                await self.app.send_file(
                    message.chat_id, file_path, caption=caption, reply_to=message.id, attributes=upload_attributes,
                    part_size_kb=512,
                    progress_callback=lambda s, t: self.upload_progress(s, t, code, index, total)
                )
                logger.info(f"Upload successful for {file_path} on attempt {attempt+1}")
                return True
            except Exception as e:
                logger.warning(f"Upload attempt {attempt+1} failed for {file_path}: {e}")
                if attempt < 2:
                    await asyncio.sleep(5)
        
        logger.error(f"Upload permanently failed for {file_path} after 3 attempts.")
        return False

    async def process_job(self, message):
        if message.id in self.processed_ids: return
        self.processed_ids.add(message.id)
        try:
            lines = message.text.split('\n'); url = next(l.replace("URL:", "").strip() for l in lines if l.startswith("URL:")); code = next(l.replace("CODE:", "").strip() for l in lines if l.startswith("CODE:")); user_id = int(next(l.replace("USER_ID:", "").strip() for l in lines if l.startswith("USER_ID:")))
        except: return
        
        file_paths, original_caption, download_method = await asyncio.to_thread(self.download_media, url, code, user_id)

        if file_paths:
            total_files = len(file_paths)
            upload_tasks = []
            for i, file_path in enumerate(file_paths):
                task = self.upload_single_file(message, file_path, code, user_id, download_method, i + 1, total_files, original_caption)
                upload_tasks.append(task)
            
            results = await asyncio.gather(*upload_tasks)
            if False in results:
                self.active_jobs[code]["status"] = "Upload Failed"
            else:
                self.active_jobs[code]["status"] = "Completed"

    async def display_dashboard(self):
        while True:
            os.system('clear' if os.name == 'posix' else 'cls'); print("--- 🚀 Advanced Downloader Dashboard 🚀 ---")
            print(f"{'Job Code':<12} | {'User ID':<12} | {'Status':<25}"); print("-" * 55)
            if not self.active_jobs: print("... Waiting for new jobs ...")
            else:
                for code, data in list(self.active_jobs.items()):
                    print(f"{code:<12} | {data.get('user_id', 'N/A'):<12} | {data.get('status', 'N/A'):<25}")
                    if data.get('status') in ["Completed", "Upload Failed"]:
                        await asyncio.sleep(5); self.active_jobs.pop(code, None)
            print("-" * 55); print(f"Last Update: {datetime.now().strftime('%H:%M:%S')}"); await asyncio.sleep(1)

    async def run(self):
        await self.app.start(phone=self.phone)
        me = await self.app.get_me()
        logger.info(f"Worker (Final Version) ba movaffaghiat be onvane {me.first_name} vared shod.")
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
