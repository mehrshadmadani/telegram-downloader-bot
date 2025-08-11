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
import instaloader
from instagrapi import Client as InstagrapiClient
from config import (TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, 
                    GROUP_ID, ORDER_TOPIC_ID, MAJID_API_TOKEN, 
                    INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD, NESTCODE_API_KEY)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger("telethon").setLevel(logging.WARNING)

class TelethonWorker:
    def __init__(self, api_id, api_hash, phone):
        self.app = TelegramClient("telethon_session", api_id, api_hash); self.phone = phone
        self.download_dir = "downloads"; os.makedirs(self.download_dir, exist_ok=True)
        self.processed_ids = set(); self.start_time = datetime.now(timezone.utc); self.active_jobs = {}
        self.instaloader_client = instaloader.Instaloader(dirname_pattern=os.path.join(self.download_dir, "{target}"), save_metadata=False, compress_json=False, post_metadata_txt_pattern="")
        self.instagrapi_client = InstagrapiClient()
        try:
            logger.info("Loading Instagram sessions...")
            self.instaloader_client.load_session_from_file(INSTAGRAM_USERNAME)
            self.instagrapi_client.load_settings("insta_session.json")
            self.instagrapi_client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            logger.info("All Instagram sessions loaded successfully.")
        except Exception as e:
            logger.error(f"Session loading failed, attempting fresh login: {e}")
            self.setup_instagram_sessions()

    def setup_instagram_sessions(self):
        try:
            logger.info("Attempting fresh login for instagrapi...")
            self.instagrapi_client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            self.instagrapi_client.dump_settings("insta_session.json")
            logger.info("instagrapi login successful and session saved.")
        except Exception as e:
            logger.error(f"FATAL: instagrapi login failed: {e}")

    def get_video_metadata(self, file_path):
        try:
            command = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,duration', '-of', 'json', file_path]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30); data = json.loads(result.stdout)['streams'][0]
            return {'duration': int(float(data['duration'])), 'width': int(data['width']), 'height': int(data['height'])}
        except: return None
        
    def download_media(self, url, code, user_id):
        self.active_jobs[code] = {"user_id": user_id, "status": "Downloading..."}
        
        if "instagram.com" in url:
            # 1. تلاش با instagrapi
            try:
                logger.info(f"Attempt 1 (instagrapi) for CODE: {code}")
                media_pk = self.instagrapi_client.media_pk_from_url(url); media_info = self.instagrapi_client.media_info(media_pk).dict()
                media_type = media_info.get("media_type"); output_path = None
                if media_type in [1, 2]:
                    output_path = self.instagrapi_client.video_download(media_pk, self.download_dir) if media_type == 2 else self.instagrapi_client.photo_download(media_pk, self.download_dir)
                if output_path:
                    final_path = os.path.join(self.download_dir, f"{code}{os.path.splitext(output_path)[1]}")
                    os.rename(output_path, final_path)
                    self.active_jobs[code]["status"] = "Downloaded"; return final_path
            except Exception as e: logger.warning(f"instagrapi failed for {code}: {e}")
            
            # 2. تلاش با instaloader
            try:
                logger.info(f"Attempt 2 (instaloader) for CODE: {code}")
                shortcode = url.split('/')[-2]; post = instaloader.Post.from_shortcode(self.instaloader_client.context, shortcode)
                self.instaloader_client.download_post(post, target=f"{code}_temp")
                dl_folder = os.path.join(self.download_dir, f"{code}_temp")
                for filename in os.listdir(dl_folder):
                    if not filename.endswith(('.txt', '.json', '.xz')):
                        src = os.path.join(dl_folder, filename); final_path = os.path.join(self.download_dir, f"{code}{os.path.splitext(filename)[1]}")
                        os.rename(src, final_path);
                        for f_extra in os.listdir(dl_folder): os.remove(os.path.join(dl_folder, f_extra))
                        os.rmdir(dl_folder)
                        self.active_jobs[code]["status"] = "Downloaded"; return final_path
            except Exception as e: logger.warning(f"Instaloader failed for {code}: {e}")
            
            # 3. تلاش با yt-dlp
            try:
                logger.info(f"Attempt 3 (yt-dlp) for CODE: {code}")
                output_path_yt = os.path.join(self.download_dir, f"{code} - %(title).30s.%(ext)s")
                ydl_opts = {'outtmpl': output_path_yt, 'cookiefile': 'cookies.txt', 'format': 'best', 'ignoreerrors': True, 'quiet': True, 'no_warnings': True, 'socket_timeout': 1800}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                    for f in os.listdir(self.download_dir):
                        if f.startswith(code): self.active_jobs[code]["status"] = "Downloaded"; return os.path.join(self.download_dir, f)
            except Exception as e: logger.warning(f"yt-dlp failed for {code}: {e}")
            
            # 4. تلاش با MajidAPI
            try:
                logger.info(f"Attempt 4 (MajidAPI) for CODE: {code}")
                api_url = f"https://api.majidapi.ir/instagram/download?url={url}&out=url&token={MAJID_API_TOKEN}"
                api_response = requests.get(api_url, timeout=20); data = api_response.json()
                if data.get("status") == 200:
                    result = data.get("result", {}); media_url = result.get("video") or result.get("image")
                    if media_url:
                        ext = ".jpg" if ".jpg" in media_url.split('?')[0] else ".mp4"; output_path = os.path.join(self.download_dir, f"{code}{ext}")
                        media_res = requests.get(media_url, stream=True, timeout=1800)
                        with open(output_path, 'wb') as f:
                            for chunk in media_res.iter_content(chunk_size=8192): f.write(chunk)
                        self.active_jobs[code]["status"] = "Downloaded"; return output_path
            except Exception as e: logger.warning(f"MajidAPI failed for {code}: {e}")

            # 5. تلاش نهایی با NestCode API
            try:
                logger.info(f"Final Attempt (NestCode API) for CODE: {code}")
                api_url = f"https://open.nestcode.org/apis-1/InstagramDownloader?url={url}&key={NESTCODE_API_KEY}"
                api_response = requests.get(api_url, timeout=30); data = api_response.json()
                if data.get("ok"):
                    media_url = data.get("result", {}).get("link")
                    if media_url:
                        ext = ".jpg" if ".jpg" in media_url.split('?')[0] else ".mp4"; output_path = os.path.join(self.download_dir, f"{code}{ext}")
                        media_res = requests.get(media_url, stream=True, timeout=1800)
                        with open(output_path, 'wb') as f:
                            for chunk in media_res.iter_content(chunk_size=8192): f.write(chunk)
                        self.active_jobs[code]["status"] = "Downloaded"; return output_path
            except Exception as e: logger.error(f"All methods failed. Last error from NestCode API: {e}")

        # --- منطق دانلود برای پلتفرم‌های دیگر ---
        else:
            # ... (کد yt-dlp برای یوتیوب، ساندکلود و ... بدون تغییر) ...
            logger.info(f"Using yt-dlp for {url.split('/')[2]} CODE: {code}")
            output_path = os.path.join(self.download_dir, f"{code} - %(title).30s.%(ext)s")
            base_opts = {'outtmpl': output_path, 'cookiefile': 'cookies.txt', 'ignoreerrors': True, 'quiet': True, 'no_warnings': True, 'socket_timeout': 1800}
            if "soundcloud" in url or "spotify" in url: ydl_opts = {'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]}
            else: ydl_opts = {'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best', 'merge_output_format': 'mp4'}
            ydl_opts.update(base_opts)
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                    for f in os.listdir(self.download_dir):
                        if f.startswith(code): return os.path.join(self.download_dir, f)
            except Exception as e: logger.error(f"yt-dlp failed for CODE {code}: {e}")
        
        self.active_jobs[code]["status"] = "Download Failed"; return None

    # ... (بقیه توابع کلاس بدون تغییر) ...
    async def upload_progress(self, sent_bytes, total_bytes, code):
        percentage = int(sent_bytes * 100 / total_bytes);
        if percentage % 10 == 0 or percentage == 100:
            if code in self.active_jobs: self.active_jobs[code]["status"] = f"Uploading: {percentage}%"
    async def process_job(self, message):
        if message.id in self.processed_ids: return
        self.processed_ids.add(message.id)
        try:
            lines = message.text.split('\n'); url = next(l.replace("URL:", "").strip() for l in lines if l.startswith("URL:")); code = next(l.replace("CODE:", "").strip() for l in lines if l.startswith("CODE:")); user_id = int(next(l.replace("USER_ID:", "").strip() for l in lines if l.startswith("USER_ID:")))
        except: return
        file_path = await asyncio.to_thread(self.download_media, url, code, user_id)
        if file_path and os.path.exists(file_path):
            file_size = os.path.getsize(file_path); upload_attributes = []
            if file_path.lower().endswith(('.mp4', '.mkv', '.mov')):
                metadata = self.get_video_metadata(file_path)
                if metadata: upload_attributes.append(DocumentAttributeVideo(duration=metadata['duration'], w=metadata['width'], h=metadata['height'], supports_streaming=True))
            try:
                caption = f"✅ Uploaded\nCODE: {code}\nSIZE: {file_size}"
                await self.app.send_file(
                    message.chat_id, file_path, caption=caption, reply_to=message.id, attributes=upload_attributes,
                    progress_callback=lambda s, t: self.upload_progress(s, t, code)
                )
                self.active_jobs[code]["status"] = "Completed"
            except: self.active_jobs[code]["status"] = "Upload Failed"
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
        logger.info(f"Worker (Ultimate Version) ba movaffaghiat be onvane {me.first_name} vared shod.")
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
    print("--- Rah andazi Ultimate Worker ---")
    asyncio.run(main())
