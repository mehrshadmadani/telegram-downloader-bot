import os
import asyncio
import logging
from logging.handlers import TimedRotatingFileHandler
import json
import subprocess
import requests
from datetime import datetime, timezone
import yt_dlp
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeVideo
import instaloader
from instagrapi import Client as InstagrapiClient
from config import (TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, 
                    GROUP_ID, ORDER_TOPIC_ID, MAJID_API_TOKEN, 
                    INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD, NESTCODE_API_KEY)

# --- سیستم لاگ‌گیری حرفه‌ای ---
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
log_handler = TimedRotatingFileHandler('worker.log', when='midnight', interval=1, backupCount=1, encoding='utf-8')
log_handler.setFormatter(log_formatter)
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(log_handler)
root_logger.addHandler(console_handler)
logger = logging.getLogger(__name__)

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
                logger.info("Instagram session loaded and refreshed.")
            else:
                self.instagrapi_client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                self.instagrapi_client.dump_settings(session_file)
                logger.info("Instagram login successful and session saved.")
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
                media_type = media_info.get("media_type")
                dl_path = None
                if media_type in [1, 2]:
                    dl_path = self.instagrapi_client.video_download(media_pk, self.download_dir) if media_type == 2 else self.instagrapi_client.photo_download(media_pk, self.download_dir)
                if dl_path:
                    final_path = os.path.join(self.download_dir, f"{code}{os.path.splitext(dl_path)[1]}")
                    os.rename(dl_path, final_path)
                    self.active_jobs[code]["status"] = "Downloaded"
                    return (final_path, "instagrapi")
            except Exception as e: logger.warning(f"instagrapi failed for {code}: {e}")
            
            try:
                logger.info(f"Attempt 2 (MajidAPI) for CODE: {code}")
                api_url = f"https://api.majidapi.ir/instagram/download?url={url}&out=url&token={MAJID_API_TOKEN}"
                api_response = requests.get(api_url, timeout=20)
                data = api_response.json()
                if data.get("status") == 200:
                    result = data.get("result", {})
                    media_url = result.get("video") or result.get("image")
                    if media_url:
                        media_res = requests.get(media_url, stream=True, timeout=1800)
                        content_type = media_res.headers.get('content-type', '')
                        ext = ".jpg" if "image" in content_type else ".mp4"
                        output_path = os.path.join(self.download_dir, f"{code}{ext}")
                        with open(output_path, 'wb') as f:
                            for chunk in media_res.iter_content(chunk_size=8192): f.write(chunk)
                        self.active_jobs[code]["status"] = "Downloaded"
                        return (output_path, "MajidAPI")
            except Exception as e: logger.warning(f"MajidAPI failed for {code}: {e}")
        else:
            try:
                logger.info(f"Using yt-dlp for {url.split('/')[2]} CODE: {code}")
                output_path = os.path.join(self.download_dir, f"{code} - %(title).30s.%(ext)s")
                base_opts = {'outtmpl': output_path, 'cookiefile': 'cookies.txt', 'ignoreerrors': True, 'quiet': True, 'no_warnings': True, 'socket_timeout': 1800}
                if "soundcloud" in url or "spotify" in url: ydl_opts = {'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]}
                else: ydl_opts = {'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best', 'merge_output_format': 'mp4'}
                ydl_opts.update(base_opts)
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                    for f in os.listdir(self.download_dir):
                        if f.startswith(code):
                            self.active_jobs[code]["status"] = "Downloaded"
                            return (os.path.join(self.download_dir, f), "yt-dlp")
            except Exception as e: logger.error(f"yt-dlp failed for CODE {code}: {e}")
        
        self.active_jobs[code]["status"] = "Download Failed"; return (None, None)

    async def upload_progress(self, sent_bytes, total_bytes, code):
        percentage = int(sent_bytes * 100 / total_bytes)
        if percentage % 10 == 0 or percentage == 100:
            if code in self.active_jobs: self.active_jobs[code]["status"] = f"Uploading: {percentage}%"

    async def process_job(self, message):
        if message.id in self.processed_ids: return
        self.processed_ids.add(message.id)
        try:
            lines = message.text.split('\n')
            url = next(line.replace("URL:", "").strip() for line in lines if line.startswith("URL:"))
            code = next(line.replace("CODE:", "").strip() for line in lines if line.startswith("CODE:"))
            user_id = int(next(line.replace("USER_ID:", "").strip() for line in lines if line.startswith("USER_ID:")))
        except: return
        
        file_path, download_method = await asyncio.to_thread(self.download_media, url, code, user_id)

        if file_path and os.path.exists(file_path):
            file_size = os.path.getsize(file_path); upload_attributes = []
            if file_path.lower().endswith(('.mp4', '.mkv', '.mov')):
                metadata = self.get_video_metadata(file_path)
                if metadata: upload_attributes.append(DocumentAttributeVideo(duration=metadata['duration'], w=metadata['width'], h=metadata['height'], supports_streaming=True))
            try:
                method_str = f"\nMETHOD: {download_method}" if download_method else ""
                caption = f"✅ Uploaded\nCODE: {code}\nSIZE: {file_size}{method_str}"
                await self.app.send_file(
                    message.chat_id, file_path, caption=caption, reply_to=message.id, attributes=upload_attributes,
                    progress_callback=lambda s, t: self.upload_progress(s, t, code)
                )
                self.active_jobs[code]["status"] = "Completed"
            except Exception as e:
                self.active_jobs[code]["status"] = "Upload Failed"
                logger.error(f"Upload failed for {code}: {e}")
            finally:
                if os.path.exists(file_path): os.remove(file_path)

    async def display_dashboard(self):
        while True:
            # os.system('clear' if os.name == 'posix' else 'cls') # پاکسازی صفحه برای دیباگ غیرفعال است
            print("\n" + "="*50)
            print(f"--- 🚀 Dashboard Update [{datetime.now().strftime('%H:%M:%S')}] 🚀 ---")
            print(f"{'Job Code':<12} | {'User ID':<12} | {'Status':<20}")
            print("-" * 50)
            if not self.active_jobs:
                print("... Waiting for new jobs ...")
            else:
                for code, data in list(self.active_jobs.items()):
                    print(f"{code:<12} | {data.get('user_id', 'N/A'):<12} | {data.get('status', 'N/A'):<20}")
                    if data.get('status') in ["Completed", "Download Failed", "Upload Failed"]:
                        await asyncio.sleep(5)
                        self.active_jobs.pop(code, None)
            print("="*50 + "\n")
            await asyncio.sleep(5)

    async def run(self):
        await self.app.start(phone=self.phone)
        me = await self.app.get_me()
        logger.info(f"Worker (Final Debug) ba movaffaghiat be onvane {me.first_name} vared shod.")
        target_chat_id = GROUP_ID
        target_topic_id = ORDER_TOPIC_ID
        try:
            entity = await self.app.get_entity(target_chat_id)
        except Exception as e:
            logger.critical(f"Nemitavan be Group ID dastresi peyda kard. Khata: {e}")
            return
        
        dashboard_task = asyncio.create_task(self.display_dashboard())
        logger.info(f"Worker shoroo be check kardan Topic ID {target_topic_id} kard...")
        while True:
            try:
                async for message in self.app.iter_messages(entity=entity, reply_to=target_topic_id, limit=20):
                    if message.date < self.start_time: break
                    if message.text and "⬇️ NEW JOB" in message.text:
                        asyncio.create_task(self.process_job(message))
                await asyncio.sleep(10)
            except Exception as e:
                logger.error(f"Yek khata dar halghe asli rokh dad: {e}")
                await asyncio.sleep(30)

async def main():
    worker = TelethonWorker(api_id=TELEGRAM_API_ID, api_hash=TELEGRAM_API_HASH, phone=TELEGRAM_PHONE)
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())
