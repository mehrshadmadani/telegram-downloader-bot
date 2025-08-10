import os
import asyncio
import logging
import yt_dlp
from pyrogram import Client, filters
from pyrogram.errors import ApiIdInvalid, ApiIdPublishedFlood
from pyrogram.types import Message

# --- تنظیمات لاگ برای دیباگ ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- کلاس اصلی Worker ---
class AdvancedWorker:
    def __init__(self, api_id, api_hash, session_name="advanced_worker"):
        self.app = Client(
            name=session_name,
            api_id=api_id,
            api_hash=api_hash
        )
        self.download_dir = "downloads"
        os.makedirs(self.download_dir, exist_ok=True)
        self.active_codes = set() # برای جلوگیری از پردازش تکراری

    def download_media(self, url, code):
        logger.info(f"Starting download for CODE: {code}")
        output_path = os.path.join(self.download_dir, f"{code}_%(title).30s.%(ext)s")
        
        ydl_opts = {
            'outtmpl': output_path,
            'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
            'merge_output_format': 'mp4',
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
            'ignoreerrors': True,
            'quiet': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # پیدا کردن فایل دانلود شده چون اسمش دقیق مشخص نیست
                for f in os.listdir(self.download_dir):
                    if f.startswith(code):
                        downloaded_file = os.path.join(self.download_dir, f)
                        logger.info(f"Download successful for CODE: {code} -> {downloaded_file}")
                        return downloaded_file
            logger.error(f"Download failed for CODE: {code}. No file was created.")
            return None
        except Exception as e:
            logger.error(f"Exception during download for CODE {code}: {e}")
            return None

    async def progress(self, current, total, code):
        percentage = int(current * 100 / total)
        # لاگ آپلود در هر ۲۵٪
        if percentage % 25 == 0:
             logger.info(f"Uploading for {code}: {percentage}%")

    async def process_job(self, message: Message):
        if "URL:" not in message.text or "CODE:" not in message.text:
            return

        lines = message.text.split('\n')
        try:
            url = next(line.replace("URL:", "").strip() for line in lines if line.startswith("URL:"))
            code = next(line.replace("CODE:", "").strip() for line in lines if line.startswith("CODE:"))
        except StopIteration:
            return # فرمت پیام درست نیست

        # اگر این کد در حال پردازش است، آن را نادیده بگیر
        if code in self.active_codes:
            return
        
        self.active_codes.add(code)
        logger.info(f"Processing job for CODE: {code}")

        loop = asyncio.get_event_loop()
        file_path = await loop.run_in_executor(None, self.download_media, url, code)

        if not file_path or not os.path.exists(file_path):
            logger.error(f"Upload failed for CODE: {code} because file does not exist.")
            await message.reply_text(f"❌ Download FAILED for CODE: {code}")
        else:
            logger.info(f"Uploading file: {file_path}")
            try:
                await self.app.send_document(
                    chat_id=message.chat.id,
                    document=file_path,
                    caption=f"✅ Uploaded\nCODE: {code}",
                    progress=self.progress,
                    progress_args=(code,)
                )
                logger.info(f"Upload successful for CODE: {code}")
            except Exception as e:
                logger.error(f"Failed to upload file for CODE {code}: {e}")
                await message.reply_text(f"❌ Upload FAILED for CODE: {code}\nError: {e}")
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Cleaned up file: {file_path}")
        
        # حذف کد از لیست کدهای فعال
        self.active_codes.remove(code)


    async def run(self):
        try:
            await self.app.start()
            logger.info("Worker has started successfully.")
        except (ApiIdInvalid, ApiIdPublishedFlood):
            logger.critical("API ID / API HASH is invalid. Exiting.")
            return
        except Exception as e:
            logger.critical(f"An error occurred during client startup: {e}")
            return

        target_chat_id = int(input("Enter the GROUP ID for the worker to listen to: "))

        @self.app.on_message(filters.chat(target_chat_id) & filters.regex("⬇️ NEW JOB"))
        async def new_job_handler(_, message: Message):
            asyncio.create_task(self.process_job(message))

        logger.info(f"Worker is now listening for jobs in chat ID: {target_chat_id}")
        # این حلقه خالی برنامه را در حال اجرا نگه می‌دارد
        while True:
            await asyncio.sleep(3600)


if __name__ == "__main__":
    print("--- Rah andazi Advanced Worker ---")
    print("Baraye login be API ID va API Hash niaz darid.")
    print("Mitoonid az my.telegram.org begirid.")
    
    try:
        api_id = int(input("Lotfan API ID khod ra vared konid: "))
        api_hash = input("Lotfan API HASH khod ra vared konid: ")
    except ValueError:
        print("API ID bayad adad bashad. Barname motavaghef shod.")
    else:
        worker = AdvancedWorker(api_id=api_id, api_hash=api_hash)
        asyncio.run(worker.run())
