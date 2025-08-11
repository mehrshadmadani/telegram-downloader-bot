import os
import asyncio
import logging
import json
import subprocess
import base64
from datetime import datetime, timezone
from functools import partial

import yt_dlp
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeVideo

from config import (TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE,
                    GROUP_ID, ORDER_TOPIC_ID)

# --- سیستم لاگ‌گیری پیشرفته (هم در کنسول و هم در فایل) ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s')

if logger.hasHandlers():
    logger.handlers.clear()

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

file_handler = logging.FileHandler('bot.log', encoding='utf-8')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

logging.getLogger("telethon").setLevel(logging.WARNING)
logging.getLogger("yt_dlp").setLevel(logging.WARNING)

class TelethonWorker:
    def __init__(self, api_id, api_hash, phone):
        self.app = TelegramClient("telethon_session", api_id, api_hash)
        self.phone = phone
        self.download_dir = "downloads"
        os.makedirs(self.download_dir, exist_ok=True)
        self.processed_ids = set()
        self.start_time = datetime.now(timezone.utc)
        self.active_jobs = {}

    def yt_dlp_progress_hook(self, d, code):
        if d['status'] == 'downloading':
            percent_str = d.get('_percent_str', '0.0%').strip()
            speed_str = d.get('_speed_str', 'N/A').strip()
            self.active_jobs[code]["status"] = f"Downloading: {percent_str} at {speed_str}"
        elif d['status'] == 'finished':
            self.active_jobs[code]["status"] = "Download Finished, Merging..."

    def download_media(self, url, code):
        try:
            logger.info(f"[{code}] Starting download process for URL: {url}")
            output_path = os.path.join(self.download_dir, f"{code}.%(ext)s")
            
            ydl_opts = {
                'outtmpl': output_path,
                'cookiefile': 'cookies.txt',
                'ignoreerrors': True, 'no_warnings': True, 'quiet': True,
                'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best',
                'merge_output_format': 'mp4',
                'progress_hooks': [partial(self.yt_dlp_progress_hook, code=code)],
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=True)
            
            downloaded_files = [os.path.join(self.download_dir, f) for f in os.listdir(self.download_dir) if f.startswith(code)]
            if not downloaded_files:
                raise Exception("yt-dlp finished but no files were found.")
            
            caption = info_dict.get('description', info_dict.get('title', '')) if info_dict else ""
            return downloaded_files, caption, "yt-dlp"
        except Exception as e:
            logger.error(f"[{code}] Error in download_media: {e}", exc_info=True)
            raise e

    def get_video_metadata(self, file_path):
        try:
            command = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,duration', '-of', 'json', file_path]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
            data = json.loads(result.stdout)['streams'][0]
            return {'duration': int(float(data.get('duration', 0))), 'width': int(data.get('width', 0)), 'height': int(data.get('height', 0))}
        except Exception as e:
            logger.warning(f"[{os.path.basename(file_path)}] Could not get video metadata. Reason: {e}")
            return None

    async def upload_single_file(self, message, file_path, code, download_method, index, total_files, original_caption):
        try:
            if not os.path.exists(file_path):
                raise Exception(f"File vanished before upload: {os.path.basename(file_path)}")

            file_size = os.path.getsize(file_path)
            self.active_jobs[code]["status"] = f"Uploading {index}/{total_files}..."
            logger.info(f"[{code}] Uploading file {index}/{total_files}: {os.path.basename(file_path)} ({file_size / 1024**2:.2f} MB)")
            
            attributes = []
            caption_to_group = f"✅ Uploaded ({index}/{total_files})\nCODE: {code}\nSIZE: {file_size}\nMETHOD: {download_method}"

            if file_path.lower().endswith(('.mp4', '.mkv', '.mov')):
                metadata = self.get_video_metadata(file_path)
                if metadata: attributes.append(DocumentAttributeVideo(duration=metadata['duration'], w=metadata['width'], h=metadata['height'], supports_streaming=True))
            
            if original_caption and index == total_files:
                encoded_caption = base64.b64encode(original_caption.encode('utf-8')).decode('utf-8')
                caption_to_group += f"\nCAPTION:{encoded_caption}"

            await self.app.send_file(message.chat_id, file_path, caption=caption_to_group, reply_to=message.id, attributes=attributes,
                                     progress_callback=lambda s, t: self.update_upload_status(s, t, code, index, total_files))
        except Exception as e:
            raise e
        finally:
            if os.path.exists(file_path): os.remove(file_path)

    def update_upload_status(self, sent, total, code, index, total_files):
        percentage = int(sent * 100 / total)
        self.active_jobs[code]["status"] = f"Uploading {index}/{total_files}: {percentage}%"
    
    async def process_job(self, message):
        code, url, user_id = "N/A", "N/A", 0
        try:
            lines = message.text.split('\n')
            url = next(l.split(":", 1)[1].strip() for l in lines if l.startswith("URL:"))
            code = next(l.split(":", 1)[1].strip() for l in lines if l.startswith("CODE:"))
            user_id = int(next(l.split(":", 1)[1].strip() for l in lines if l.startswith("USER_ID:")))
            
            self.active_jobs[code] = {"user_id": user_id, "status": "Queued", "error": None}
            logger.info(f"[{code}] Job received for user [{user_id}].")
            
            file_paths, caption_text, method = await asyncio.to_thread(self.download_media, url, code)
            
            self.active_jobs[code]["status"] = "Processing..."
            for i, path in enumerate(file_paths):
                await self.upload_single_file(message, path, code, method, i + 1, len(file_paths), caption_text)
            
            self.active_jobs[code]["status"] = "Completed"
        except Exception as e:
            error_short = str(
