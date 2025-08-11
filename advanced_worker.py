import os
import asyncio
import logging
import json
import subprocess
import requests # اضافه کردن کتابخانه requests
from datetime import datetime, timezone
import yt_dlp
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeVideo
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, GROUP_ID, ORDER_TOPIC_ID

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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

    def get_video_metadata(self, file_path):
        # ... (این تابع بدون تغییر است) ...
        try:
            command = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,duration', '-of', 'json', file_path]
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)['streams'][0]
            return {'duration': int(float(data['duration'])), 'width': int(data['width']), 'height': int(data['height'])}
        except: return None

    def download_media(self, url, code, user_id):
        self.active_jobs[code] = {"user_id": user_id, "status": "Downloading..."}
        
        # --- منطق دانلود هوشمند و جدید ---
        try:
            # اگر اینستاگرام بود، از API استفاده کن
            if "instagram.com" in url:
                api_url = f"https://api.majidapi.ir/api/instagram?url={url}"
                response = requests.get(api_url, timeout=60).json()
                
                media_url = None
                file_ext = ".jpg" # پیش‌فرض برای عکس
                
                if response.get("result"):
                    if response["result"]["type"] == "photo" and response["result"]["images"]:
                        media_url = response["result"]["images"][0]
                    elif response["result"]["type"] == "video" and response["result"]["video"]:
                        media_url = response["result"]["video"]
                        file_ext = ".mp4"

                if not media_url:
                    logger.error(f"API response did not contain a valid media URL. Full response:\n{json.dumps(response, indent=2)}")
                    raise ValueError("Media URL not found in API response")

                # دانلود مستقیم فایل از لینک دریافتی از API
                file_path = os.path.join(self.download_dir, f"{code}{file_ext}")
                with requests.get(media_url, stream=True) as r:
                    r.raise_for_status()
                    with open(file_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                
                self.active_jobs[code]["status"] = "Downloaded"
                return file_path
            
            # برای بقیه پلتفرم‌ها از yt-dlp استفاده کن
            else:
                output_path = os.path.join(self.download_dir, f"{code} - %(title).30s.%(ext)s")
                if "soundcloud.com" in url or "spotify.com" in url:
                    ydl_opts = {'outtmpl': output_path, 'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None, 'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]}
                else: # YouTube
                    ydl_opts = {'outtmpl': output_path, 'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best', 'merge_output_format': 'mp4', 'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None}
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                    for f in os.listdir(self.download_dir):
                        if f.startswith(code):
                            downloaded_file = os.path.join(self.download_dir, f)
                            self.active_jobs[code]["status"] = "Downloaded"
                            return downloaded_file
            return None

        except Exception as e:
            self.active_jobs[code]["status"] = "Download Failed"
            logger.error(f"Khata dar download baraye CODE {code}: {e}")
            return None

    # ... (بقیه توابع کلاس بدون تغییر هستند) ...
    async def upload_progress(self, sent_bytes, total_bytes, code):
        percentage = int(sent_bytes * 100 / total_bytes)
        if percentage % 10 == 0 or percentage == 100:
            if code in self.active_jobs: self.active_jobs[code]["status"] = f"Uploading: {percentage}%"
    async def process_job(self, message):
        if message.id in self.processed_ids: return
        self.processed_ids.add(message.id)
        try:
            lines = message.text.split('\n'); url = next(l.replace("URL:", "").strip() for l in lines if l.startswith("URL:"))
            code = next(l.replace("CODE:", "").strip() for l in lines if l.startswith("CODE:"))
            user_id = int(next(l.replace("USER_ID:", "").strip() for l in lines if l.startswith("USER_ID:")))
        except: return
        file_path = await asyncio.to_thread(self.download_media, url, code, user_id)
        if file_path and os.path.exists(file_path):
            file_size = os.path.getsize(file_path); upload_attributes = []
            if file_path.lower().endswith(('.mp4', '.mkv', '.mov')):
                metadata = self.get_video_metadata(file_path)
                if metadata: upload_attributes.append(DocumentAttributeVideo(duration=metadata['duration'], w=metadata['width'], h=metadata['height'], supports_streaming=True))
            try:
                caption = f"✅ Uploaded\nCODE: {code}\nSIZE: {file_size}"
                await self.app.send_file(message.chat_id, file_path, caption=caption, reply_to=message.id, attributes=upload_attributes, progress_callback=lambda s, t: self.upload_progress(s, t, code))
                self.active_jobs[code]["status"] = "Completed"
            except Exception as e: self.active_jobs[code]["status"] = "Upload Failed"; logger.error(f"Khata dar upload (CODE: {code}): {e}")
            finally:
                if os.path.exists(file_path): os.remove(file_path)
    async def display_dashboard(self):
        while True:
            os.system('clear' if os.name == 'posix' else 'cls'); print("--- 🚀 Advanced Downloader Dashboard 🚀 ---")
            print(f"{'Job Code':<12} | {'User ID':<12} | {'Status':<20}"); print("-" * 50)
            if not self.active_jobs: print("... Waiting for new jobs ...")
            else:
                for code, data in list(self.active_jobs.items()):
                    print(f"{code:<12} | {data.get('user_id', 'N/A'):<12} | {data.get('status', 'N/A'):<20}")
                    if data.get('status') in ["Completed", "Download Failed", "Upload Failed"]:
                        await asyncio.sleep(3); self.active_jobs.pop(code, None)
            print("-" * 50); print(f"Last Update: {datetime.now().strftime('%H:%M:%S')}"); await asyncio.sleep(1)
    async def run(self):
        await self.app.start(phone=self.phone)
        me = await self.app.get_me()
        logger.info(f"Worker (API Downloader) ba movaffaghiat be onvane {me.first_name} vared shod.")
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
    print("--- Rah andazi API Downloader Worker ---"); asyncio.run(main())
