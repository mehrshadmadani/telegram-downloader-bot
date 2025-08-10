import os
import asyncio
import logging
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import Message

# --- تنظیمات لاگ برای دیباگ ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- کلاس اصلی Worker ---
class AdvancedWorker:
    def __init__(self, session_name="advanced_worker"):
        self.app = Client(session_name)
        self.download_dir = "downloads"
        os.makedirs(self.download_dir, exist_ok=True)

    def download_media(self, url, code):
        """
        Media downloader using yt-dlp.
        It runs in a separate thread to avoid blocking.
        """
        logger.info(f"Starting download for CODE: {code}")
        output_path = os.path.join(self.download_dir, f"{code}_%(title).20s.%(ext)s")
        
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
                if info:
                    filename = ydl.prepare_filename(info)
                    final_filename = os.path.splitext(filename)[0] + '.mp4'
                    if os.path.exists(final_filename):
                        logger.info(f"Download successful for CODE: {code} -> {final_filename}")
                        return final_filename
            logger.error(f"Download failed for CODE: {code}. No file was created.")
            return None
        except Exception as e:
            logger.error(f"Exception during download for CODE {code}: {e}")
            return None

    async def progress(self, current, total, message):
        """
        A simple progress callback for uploads.
        """
        percentage = f"{current * 100 / total:.1f}%"
        if int(percentage.split('.')[0]) % 25 == 0: # Log every 25%
             logger.info(f"Uploading for {message.text.split('CODE:')[1].strip()}: {percentage}")


    async def process_job(self, message: Message):
        """
        Processes a single job message from the group.
        """
        if "URL:" not in message.text or "CODE:" not in message.text:
            return

        lines = message.text.split('\n')
        url = lines[1].replace("URL:", "").strip()
        code = lines[2].replace("CODE:", "").strip()
        
        logger.info(f"Processing job for CODE: {code}")

        # Run download in a separate thread to not block the asyncio event loop
        loop = asyncio.get_event_loop()
        file_path = await loop.run_in_executor(None, self.download_media, url, code)

        if not file_path or not os.path.exists(file_path):
            logger.error(f"Upload failed for CODE: {code} because file does not exist.")
            await message.reply_text(f"❌ Download FAILED for CODE: {code}")
            return

        logger.info(f"Uploading file: {file_path}")
        
        try:
            # Upload the file back to the same group
            await self.app.send_document(
                chat_id=message.chat.id,
                document=file_path,
                caption=f"✅ Uploaded\nCODE: {code}",
                progress=self.progress,
                progress_args=(message,)
            )
            logger.info(f"Upload successful for CODE: {code}")
        except Exception as e:
            logger.error(f"Failed to upload file for CODE {code}: {e}")
            await message.reply_text(f"❌ Upload FAILED for CODE: {code}\nError: {e}")
        finally:
            # Clean up the downloaded file
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Cleaned up file: {file_path}")


    def run(self):
        """
        Starts the worker client and listens for new jobs.
        """
        # Define the message handler
        @self.app.on_message(filters.text & filters.private)
        async def handler(client, message):
            # This handler is a placeholder for direct messages to the userbot.
            # The main logic is in `process_job`, triggered by group messages.
            # We are using `get_chat_history` instead of a group handler for simplicity.
            pass

        async def main_loop():
            await self.app.start()
            logger.info("Worker has started. Listening for jobs...")
            
            # Get the target group ID from user input
            dialogs = [d.chat.id async for d in self.app.get_dialogs() if d.chat.is_supergroup or d.chat.is_channel]
            target_chat_id = int(input("Enter the GROUP ID for the worker: "))


            while True:
                try:
                    # Fetch last messages from the group and process them
                    async for msg in self.app.get_chat_history(chat_id=target_chat_id, limit=10):
                         if msg.text and "⬇️ NEW JOB" in msg.text:
                              asyncio.create_task(self.process_job(msg))
                    
                    await asyncio.sleep(10) # Wait for 10 seconds before checking again

                except Exception as e:
                    logger.error(f"An error occurred in the main loop: {e}")
                    await asyncio.sleep(30) # Wait longer on error
            
            await self.app.stop()


        # Run the main loop
        self.app.run(main_loop())


if __name__ == "__main__":
    print("--- Rah andazi Advanced Worker ---")
    print("Baraye login, momkene be API ID, API Hash va shomare telephone niaz bashe.")
    print("File .session eijad mishe ta dafe'at ba'di niaz be login nadashte bashid.")
    
    worker = AdvancedWorker()
    worker.run()
