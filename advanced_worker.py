import os
import asyncio
import logging
import yt_dlp
from pyrogram import Client
from pyrogram.errors import FloodWait

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

UPLOAD_WORKERS = 3 # تعداد آپلودهای همزمان

class AdvancedWorker:
    def __init__(self, api_id, api_hash, session_name="advanced_worker"):
        self.app = Client(name=session_name, api_id=api_id, api_hash=api_hash)
        self.download_dir = "downloads"
        self.upload_queue = asyncio.Queue() # صف برای مدیریت آپلودها
        os.makedirs(self.download_dir, exist_ok=True)
        self.processed_ids = set()

    def download_media(self, url, code):
        logger.info(f"Shروع download baraye CODE: {code}")
        output_path = os.path.join(self.download_dir, f"{code}_%(title).30s.%(ext)s")
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
            logger.error(f"Exception dar hengam download baraye CODE {code}: {e}")
            return None

    async def upload_worker(self, worker_id):
        logger.info(f"Kargar upload #{worker_id} shoroo be kar kard.")
        while True:
            chat_id, file_path, code = await self.upload_queue.get()
            logger.info(f"Kargar #{worker_id} dar hale upload file baraye CODE: {code}")
            try:
                await self.app.send_document(chat_id=chat_id, document=file_path, caption=f"✅ Uploaded\nCODE: {code}")
                logger.info(f"Upload movaffagh baraye CODE: {code} tavasote kargar #{worker_id}")
            except FloodWait as e:
                logger.warning(f"Flood wait baraye {e.value} sanieh. Dobare talash mishavad...")
                await asyncio.sleep(e.value)
                await self.upload_queue.put((chat_id, file_path, code)) # برگرداندن به صف
            except Exception as e:
                logger.error(f"Khata dar upload file (CODE: {code}): {e}")
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"File pak shod: {file_path}")
                self.upload_queue.task_done()

    async def process_job(self, message):
        if message.id in self.processed_ids: return
        self.processed_ids.add(message.id)
        try:
            if not message.text: return
            url = next(line.replace("URL:", "").strip() for line in message.text.split('\n') if line.startswith("URL:"))
            code = next(line.replace("CODE:", "").strip() for line in message.text.split('\n') if line.startswith("CODE:"))
        except (StopIteration, AttributeError): return

        logger.info(f"Kar jadidیاft شد: {code}. Pardazesh anjam mishavad...")
        loop = asyncio.get_event_loop()
        file_path = await loop.run_in_executor(None, self.download_media, url, code)
        if file_path and os.path.exists(file_path):
            await self.upload_queue.put((message.chat.id, file_path, code))
            logger.info(f"File baraye CODE {code} be saf-e upload ezafe shod.")
        else:
            await self.app.send_message(message.chat.id, f"❌ Download FAILED for CODE: {code}")

    async def run(self):
        await self.app.start()
        me = await self.app.get_me()
        logger.info(f"Worker ba movaffaghiat be onvane {me.first_name} vared shod.")
        
        upload_tasks = []
        for i in range(UPLOAD_WORKERS):
            task = asyncio.create_task(self.upload_worker(i + 1))
            upload_tasks.append(task)

        target_chat_id = int(input("Lotfan adad Group ID ra vared konid: "))
        logger.info(f"Worker shoroo be check kardan Group ID: {target_chat_id} kard...")
        while True:
            try:
                async for message in self.app.get_chat_history(chat_id=target_chat_id, limit=20):
                    if message.text and "⬇️ NEW JOB" in message.text:
                       asyncio.create_task(self.process_job(message))
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Yek khata dar halghe asli rokh dad: {e}")
                await asyncio.sleep(20)

if __name__ == "__main__":
    print("--- Rah andazi Advanced Worker ---")
    try:
        api_id = int(input("Lotfan API ID khod ra vared konid: "))
        api_hash = input("Lotfan API HASH khod ra vared konid: ")
    except ValueError:
        print("API ID bayad adad bashad.")
    else:
        worker = AdvancedWorker(api_id=api_id, api_hash=api_hash)
        asyncio.run(worker.run())
