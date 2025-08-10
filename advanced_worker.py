import os
import asyncio
import logging
from datetime import datetime, timezone
import yt_dlp
from telethon import TelegramClient
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE

# --- تنظیمات لاگ ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- کلاس ورکر نهایی با داشبورد ---
class TelethonWorker:
    def __init__(self, api_id, api_hash, phone):
        self.app = TelegramClient("telethon_session", api_id, api_hash)
        self.phone = phone
        self.download_dir = "downloads"
        os.makedirs(self.download_dir, exist_ok=True)
        self.processed_ids = set()
        self.start_time = datetime.now(timezone.utc)
        # دیکشنری برای نگهداری وضعیت کارهای فعال برای داشبورد
        self.active_jobs = {}

    def download_media(self, url, code, user_id):
        self.active_jobs[code] = {"user_id": user_id, "status": "Downloading..."}
        logger.info(f"Shروع download baraye CODE: {code}")
        output_path = os.path.join(self.download_dir, f"{code} - %(title).30s.%(ext)s")
        
        if "instagram.com" in url:
            ydl_opts = {'outtmpl': output_path, 'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None, 'ignoreerrors': True, 'quiet': True, 'no_warnings': True}
        else:
            ydl_opts = {'outtmpl': output_path, 'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best', 'merge_output_format': 'mp4', 'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None, 'ignoreerrors': True, 'quiet': True, 'no_warnings': True}

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)
                for f in os.listdir(self.download_dir):
                    if f.startswith(code):
                        downloaded_file = os.path.join(self.download_dir, f)
                        self.active_jobs[code]["status"] = "Downloaded"
                        return downloaded_file
            return None
        except Exception as e:
            self.active_jobs[code]["status"] = "Download Failed"
            logger.error(f"Exception dar hengam download (CODE: {code}): {e}")
            return None

    async def upload_progress(self, sent_bytes, total_bytes, code):
        percentage = int(sent_bytes * 100 / total_bytes)
        if percentage % 10 == 0 or percentage == 100:
            if code in self.active_jobs:
                self.active_jobs[code]["status"] = f"Uploading: {percentage}%"

    async def process_job(self, message):
        if message.id in self.processed_ids: return
        self.processed_ids.add(message.id)
        
        try:
            user_id = message.sender_id # در تلگرام، فرستنده پیام در گروه همان ربات اصلی است
            url = next(line.replace("URL:", "").strip() for line in message.text.split('\n') if line.startswith("URL:"))
            code = next(line.replace("CODE:", "").strip() for line in message.text.split('\n') if line.startswith("CODE:"))
        except Exception: return

        file_path = await asyncio.to_thread(self.download_media, url, code, user_id)
        
        if file_path and os.path.exists(file_path):
            try:
                await self.app.send_file(
                    message.chat_id, file_path, caption=f"✅ Uploaded\nCODE: {code}",
                    progress_callback=lambda s, t: self.upload_progress(s, t, code)
                )
                self.active_jobs[code]["status"] = "Completed"
            except Exception as e:
                self.active_jobs[code]["status"] = "Upload Failed"
                logger.error(f"Khata dar upload (CODE: {code}): {e}")
            finally:
                if os.path.exists(file_path): os.remove(file_path)
        else:
            if code in self.active_jobs: self.active_jobs.pop(code)
            logger.error(f"Download namovaffagh bood baraye CODE: {code}.")

    async def display_dashboard(self):
        """ این تابع داشبورد را در ترمینال نمایش می‌دهد و هر ثانیه آپدیت می‌کند """
        while True:
            os.system('clear' if os.name == 'posix' else 'cls')
            print("--- 🚀 Advanced Downloader Dashboard 🚀 ---")
            print("-" * 50)
            print(f"{'Job Code':<12} | {'User ID':<12} | {'Status':<20}")
            print("-" * 50)
            
            if not self.active_jobs:
                print("... Waiting for new jobs ...")
            else:
                for code, data in list(self.active_jobs.items()):
                    print(f"{code:<12} | {data.get('user_id', 'N/A'):<12} | {data.get('status', 'N/A'):<20}")
                    if data.get('status') in ["Completed", "Download Failed", "Upload Failed"]:
                        # تسک‌های تمام شده را بعد از چند ثانیه از داشبورد حذف کن
                        await asyncio.sleep(0.1) # کمی تاخیر برای نمایش وضعیت نهایی
                        self.active_jobs.pop(code)

            print("-" * 50)
            print(f"Last Update: {datetime.now().strftime('%H:%M:%S')}")
            await asyncio.sleep(1)

    async def run(self):
        await self.app.start(phone=self.phone)
        me = await self.app.get_me()
        logger.info(f"Worker (Dashboard Version) ba movaffaghiat be onvane {me.first_name} vared shod.")

        # حل اخطار RuntimeWarning با استفاده از iter_dialogs
        logger.info("Cache garm mishavad...")
        async for _ in self.app.iter_dialogs():
            pass
        logger.info("Cache garm shod.")

        target_chat_id = int(input("Lotfan adad Group ID ra vared konid: "))
        
        try:
            entity = await self.app.get_entity(target_chat_id)
        except Exception as e:
            logger.critical(f"Nemitavan be Group ID {target_chat_id} dastresi peyda kard. Khata: {e}")
            return

        # اجرای داشبورد به عنوان یک تسک پس‌زمینه
        dashboard_task = asyncio.create_task(self.display_dashboard())

        logger.info(f"Worker shoroo be check kardan payamha kard...")
        while True:
            try:
                async for message in self.app.iter_messages(entity=entity, limit=20):
                    if message.date < self.start_time: break
                    if message.text and "⬇️ NEW JOB" in message.text:
                        asyncio.create_task(self.process_job(message))
                await asyncio.sleep(10)
            except Exception as e:
                logger.error(f"Yek khata dar halghe asli rokh dad: {e}")
                await asyncio.sleep(30)

async def main():
    worker = TelethonWorker(
        api_id=TELEGRAM_API_ID, api_hash=TELEGRAM_API_HASH, phone=TELEGRAM_PHONE
    )
    await worker.run()

if __name__ == "__main__":
    print("--- Rah andazi Final Worker (Telethon) ---")
    asyncio.run(main())
