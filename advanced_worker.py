import os
import asyncio
import logging
import yt_dlp
from pyrogram import Client, filters
from pyrogram.errors import ApiIdInvalid, ApiIdPublishedFlood
from pyrogram.types import Message
import time

# --- تنظیمات لاگ برای دیباگ ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- کلاس اصلی Worker ---
class AdvancedWorker:
    def __init__(self, api_id, api_hash, session_name="advanced_worker"):
        self.app = Client(name=session_name, api_id=api_id, api_hash=api_hash)
        self.download_dir = "downloads"
        os.makedirs(self.download_dir, exist_ok=True)
        self.processed_ids = set() # برای جلوگیری از پردازش پیام تکراری

    def download_media(self, url, code):
        logger.info(f"Shروع download baraye CODE: {code}")
        output_path = os.path.join(self.download_dir, f"{code}_%(title).30s.%(ext)s")
        
        ydl_opts = {
            'outtmpl': output_path,
            'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
            'merge_output_format': 'mp4',
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
            'ignoreerrors': True,
            'quiet': True,
            'no_warnings': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)
                for f in os.listdir(self.download_dir):
                    if f.startswith(code):
                        downloaded_file = os.path.join(self.download_dir, f)
                        logger.info(f"Download movaffagh baraye CODE: {code} -> {downloaded_file}")
                        return downloaded_file
            logger.error(f"Download namovaffagh baraye CODE: {code}. File sakhte nashod.")
            return None
        except Exception as e:
            logger.error(f"Exception dar hengam download baraye CODE {code}: {e}")
            return None

    async def upload_file(self, chat_id, file_path, code):
        try:
            logger.info(f"Dar hale upload file: {file_path}")
            await self.app.send_document(
                chat_id=chat_id,
                document=file_path,
                caption=f"✅ Uploaded\nCODE: {code}"
            )
            logger.info(f"Upload movaffagh baraye CODE: {code}")
        except Exception as e:
            logger.error(f"Khata dar upload file baraye CODE {code}: {e}")
            await self.app.send_message(chat_id, f"❌ Upload FAILED for CODE: {code}\nError: {e}")
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"File pak shod: {file_path}")

    async def process_job(self, message: Message):
        if message.message_id in self.processed_ids:
            return
        
        self.processed_ids.add(message.message_id)

        try:
            url = next(line.replace("URL:", "").strip() for line in message.text.split('\n') if line.startswith("URL:"))
            code = next(line.replace("CODE:", "").strip() for line in message.text.split('\n') if line.startswith("CODE:"))
        except (StopIteration, AttributeError):
            return

        logger.info(f"Dar hale pardazesh kar baraye CODE: {code}")

        loop = asyncio.get_event_loop()
        file_path = await loop.run_in_executor(None, self.download_media, url, code)

        if file_path and os.path.exists(file_path):
            await self.upload_file(message.chat.id, file_path, code)
        else:
            logger.error(f"Upload namovaffagh baraye CODE: {code} chon file vojood nadarad.")
            await self.app.send_message(message.chat.id, f"❌ Download FAILED for CODE: {code}")

    async def run(self):
        try:
            await self.app.start()
            me = await self.app.get_me()
            logger.info(f"Worker ba movaffaghiat be onvane {me.first_name} vared shod.")
        except Exception as e:
            logger.critical(f"Khata dar start kardan client: {e}")
            return

        target_chat_id_str = input("Lotfan adad Group ID ra baraye check kardan vared konid: ")
        target_chat_id = int(target_chat_id_str)

        logger.info(f"Worker shoroo be check kardan Group ID: {target_chat_id} kard...")

        while True:
            try:
                # گرفتن ۱۰ پیام آخر از گروه
                async for message in self.app.get_chat_history(chat_id=target_chat_id, limit=10):
                    if message.text and "⬇️ NEW JOB" in message.text:
                       # ایجاد یک تسک جدید برای پردازش پیام که برنامه اصلی متوقف نشود
                       asyncio.create_task(self.process_job(message))
                
                # هر ۵ ثانیه یک بار چک کن
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Yek khata dar halghe asli rokh dad: {e}")
                await asyncio.sleep(20) # در صورت خطا بیشتر صبر کن

if __name__ == "__main__":
    print("--- Rah andazi Advanced Worker ---")
    try:
        api_id = int(input("Lotfan API ID khod ra vared konid: "))
        api_hash = input("Lotfan API HASH khod ra vared konid: ")
    except ValueError:
        print("API ID bayad adad bashad. Barname motavaghef shod.")
    else:
        worker = AdvancedWorker(api_id=api_id, api_hash=api_hash)
        asyncio.run(worker.run())
