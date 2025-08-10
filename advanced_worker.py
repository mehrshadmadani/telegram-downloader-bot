import os
import asyncio
import logging
from datetime import datetime, timezone
import yt_dlp
from telethon import TelegramClient
from telethon.errors.rpcerrorlist import FloodWaitError
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE

# --- تنظیمات لاگ ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- کلاس ورکر نهایی ---
class TelethonWorker:
    def __init__(self, api_id, api_hash, phone):
        self.app = TelegramClient("telethon_session", api_id, api_hash)
        self.phone = phone
        self.download_dir = "downloads"
        os.makedirs(self.download_dir, exist_ok=True)
        self.processed_ids = set()
        self.start_time = datetime.now(timezone.utc)

    def download_media(self, url, code):
        logger.info(f"Shروع download baraye CODE: {code}")
        output_path = os.path.join(self.download_dir, f"{code} - %(title).30s.%(ext)s")
        
        if "instagram.com" in url:
            ydl_opts = {
                'outtmpl': output_path,
                'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
                'ignoreerrors': True, 'quiet': True, 'no_warnings': True,
            }
        else:
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

    async def upload_progress(self, sent_bytes, total_bytes, code):
        percentage = int(sent_bytes * 100 / total_bytes)
        if percentage % 10 == 0 or percentage == 100:
            logger.info(f"Uploading CODE {code}: {percentage}%")

    async def process_job(self, message):
        if message.id in self.processed_ids: return
        self.processed_ids.add(message.id)
        
        try:
            url = next(line.replace("URL:", "").strip() for line in message.text.split('\n') if line.startswith("URL:"))
            code = next(line.replace("CODE:", "").strip() for line in message.text.split('\n') if line.startswith("CODE:"))
        except Exception: return

        logger.info(f"Kar jadidیاft شد: {code}. Shorooe pardazesh...")
        
        file_path = await asyncio.to_thread(self.download_media, url, code)
        
        if file_path and os.path.exists(file_path):
            logger.info(f"Opload shoroo shod baraye CODE: {code}")
            try:
                await self.app.send_file(
                    message.chat_id, file_path, caption=f"✅ Uploaded\nCODE: {code}",
                    progress_callback=lambda s, t: self.upload_progress(s, t, code)
                )
                logger.info(f"✅ Upload KAMEL shod baraye CODE: {code}")
            except Exception as e:
                logger.error(f"Khata dar upload (CODE: {code}): {e}")
            finally:
                if os.path.exists(file_path): os.remove(file_path)
        else:
            logger.error(f"Download namovaffagh bood baraye CODE: {code}. File peyda nashod.")

    async def run(self):
        await self.app.start(phone=self.phone)
        me = await self.app.get_me()
        logger.info(f"Worker (Telethon Version) ba movaffaghiat be onvane {me.first_name} vared shod.")

        logger.info("Cache garm mishavad, dar hale gereftan list-e chat-ha...")
        try:
            async for _ in self.app.get_dialogs():
                pass
            logger.info("Cache garm shod.")
        except Exception as e:
            logger.warning(f"Khata dar gereftan dialog-ha: {e}")

        target_chat_id = int(input("Lotfan adad Group ID ra vared konid: "))
        
        try:
            entity = await self.app.get_entity(target_chat_id)
            logger.info(f"Dastresi be Group '{entity.title}' ba movaffaghiat anjam shod.")
        except Exception as e:
            logger.critical(f"Nemitavan be Group ID {target_chat_id} dastresi peyda kard. Khata: {e}")
            return

        logger.info(f"Worker shoroo be check kardan payamha kard...")
        while True:
            try:
                async for message in self.app.iter_messages(entity=entity, limit=20):
                    if message.date < self.start_time:
                        break
                    
                    if message.text and "⬇️ NEW JOB" in message.text:
                        await self.process_job(message)
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
