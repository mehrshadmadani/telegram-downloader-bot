import os
import asyncio
import logging
import yt_dlp
from pyrogram import Client
from pyrogram.errors import FloodWait
import time

# --- تنظیمات لاگ برای دیباگ ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- کلاس اصلی Worker (نسخه پایدار و سریال) ---
class StableWorker:
    def __init__(self, api_id, api_hash, session_name="advanced_worker"):
        self.app = Client(name=session_name, api_id=api_id, api_hash=api_hash)
        self.download_dir = "downloads"
        os.makedirs(self.download_dir, exist_ok=True)
        self.processed_ids = set()

    def download_media(self, url, code):
        logger.info(f"Shروع download baraye CODE: {code}")
        output_path = os.path.join(self.download_dir, f"{code} - %(title).30s.%(ext)s")
        ydl_opts = {
            'outtmpl': output_path,
            'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
            'merge_output_format': 'mp4',
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
            'ignoreerrors': True, 'quiet': True, 'no_warnings': True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)
                for f in os.listdir(self.download_dir):
                    if f.startswith(code):
                        downloaded_file = os.path.join(self.download_dir, f)
                        logger.info(f"Download movaffagh baraye CODE: {code} -> {downloaded_file}")
                        return downloaded_file
            return None
        except Exception as e:
            logger.error(f"Exception dar hengam download (CODE: {code}): {e}")
            return None

    async def upload_progress(self, current, total, code):
        """ این تابع درصد آپلود را نمایش می‌دهد """
        percentage = int(current * 100 / total)
        # برای جلوگیری از لاگ زیاد، هر ۱۰ درصد یک بار چاپ می‌کنیم
        if percentage % 10 == 0:
            logger.info(f"Uploading CODE {code}: {percentage}%")

    async def process_job(self, message):
        """ دانلود و سپس آپلود به صورت سریالی """
        if message.id in self.processed_ids:
            return
        
        self.processed_ids.add(message.id)
        
        try:
            if not message.text: return
            url = next(line.replace("URL:", "").strip() for line in message.text.split('\n') if line.startswith("URL:"))
            code = next(line.replace("CODE:", "").strip() for line in message.text.split('\n') if line.startswith("CODE:"))
        except (StopIteration, AttributeError):
            return

        logger.info(f"Kar jadidیاft شد: {code}. Shorooe pardazesh...")
        
        # --- مرحله دانلود ---
        file_path = await asyncio.get_event_loop().run_in_executor(
            None, self.download_media, url, code
        )
        
        # --- مرحله آپلود ---
        if file_path and os.path.exists(file_path):
            logger.info(f"Opload shoroo shod baraye CODE: {code}")
            try:
                await self.app.send_document(
                    chat_id=message.chat.id,
                    document=file_path,
                    caption=f"✅ Uploaded\nCODE: {code}",
                    progress=self.upload_progress,
                    progress_args=(code,) # ارسال کد به تابع نمایشگر درصد
                )
                logger.info(f"✅ Upload KAMEL shod baraye CODE: {code}")
            except FloodWait as e:
                logger.warning(f"Flood wait baraye {e.value} sanieh. Sabr mikonim...")
                await asyncio.sleep(e.value)
            except Exception as e:
                logger.error(f"Khata dar upload (CODE: {code}): {e}")
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"File pak shod: {file_path}")
        else:
            logger.error(f"Download namovaffagh bood baraye CODE: {code}. File peyda nashod.")

    async def run(self):
        await self.app.start()
        me = await self.app.get_me()
        logger.info(f"Worker (Stable Version) ba movaffaghiat be onvane {me.first_name} vared shod.")
        
        target_chat_id = int(input("Lotfan adad Group ID ra vared konid: "))
        
        # قبل از شروع حلقه اصلی، یک بار گروه را چک می‌کنیم تا از معتبر بودن آن مطمئن شویم
        try:
            await self.app.get_chat(target_chat_id)
            logger.info(f"Dastresi be Group ID {target_chat_id} ba movaffaghiat anjam shod.")
        except Exception as e:
            logger.critical(f"Nemitavan be Group ID {target_chat_id} dastresi peyda kard. Khata: {e}")
            logger.critical("Motmaen shavid worker ozve group ast. Barname motavaghef shod.")
            return

        logger.info(f"Worker shoroo be check kardan payamha kard...")
        while True:
            try:
                async for message in self.app.get_chat_history(chat_id=target_chat_id, limit=5):
                    if message.text and "⬇️ NEW JOB" in message.text:
                        # دیگر از تسک موازی استفاده نمی‌کنیم، منتظر اتمام هر کار می‌مانیم
                        await self.process_job(message)
                await asyncio.sleep(10) # هر ۱۰ ثانیه یک بار گروه را چک کن
            except Exception as e:
                logger.error(f"Yek khata dar halghe asli rokh dad: {e}")
                await asyncio.sleep(30)

if __name__ == "__main__":
    print("--- Rah andazi Stable Worker ---")
    try:
        api_id = int(input("Lotfan API ID khod ra vared konid: "))
        api_hash = input("Lotfan API HASH khod ra vared konid: ")
    except ValueError:
        print("API ID bayad adad bashad.")
    else:
        worker = StableWorker(api_id=api_id, api_hash=api_hash)
        asyncio.run(worker.run())
