import os
import asyncio
import logging
import json
import subprocess
import base64
import requests
from datetime import datetime, timezone
from functools import partial

import yt_dlp
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeVideo
import instaloader
from instagrapi import Client as InstagrapiClient

from config import (TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE,
                    GROUP_ID, ORDER_TOPIC_ID, MAJID_API_TOKEN,
                    INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD, NESTCODE_API_KEY)

# --- سیستم لاگ‌گیری پیشرفته ---
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
logging.getLogger("instaloader").setLevel(logging.WARNING)
logging.getLogger("instagrapi").setLevel(logging.WARNING)

class TelethonWorker:
    def __init__(self, api_id, api_hash, phone):
        self.app = TelegramClient("telethon_session", api_id, api_hash)
        self.phone = phone
        self.download_dir = "downloads"
        os.makedirs(self.download_dir, exist_ok=True)
        self.processed_ids = set()
        self.start_time = datetime.now(timezone.utc)
        self.active_jobs = {}
        self.instagrapi_client = self.setup_instagrapi_client()
        self.instaloader_client = self.setup_instaloader_client()

    def setup_instagrapi_client(self):
        try:
            client = InstagrapiClient()
            session_file = f"instagrapi_session_{INSTAGRAM_USERNAME}.json"
            if os.path.exists(session_file):
                client.load_settings(session_file)
            client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            client.dump_settings(session_file)
            logger.info("✅ Instagrapi session loaded/created successfully.")
            return client
        except Exception as e:
            logger.error(f"❌ FATAL: Could not login with Instagrapi. Error: {e}")
            return None

    def setup_instaloader_client(self):
        try:
            L = instaloader.Instaloader(download_videos=True, download_pictures=True, download_video_thumbnails=False, save_metadata=False, compress_json=False)
            session_file = f"instaloader_session_{INSTAGRAM_USERNAME}"
            if os.path.exists(session_file):
                L.load_session_from_file(INSTAGRAM_USERNAME, session_file)
            else:
                L.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                L.save_session_to_file(session_file)
            logger.info("✅ Instaloader session loaded/created successfully.")
            return L
        except Exception as e:
            logger.error(f"❌ FATAL: Could not login with Instaloader. Error: {e}")
            return None
            
    def _download_from_url(self, url, file_path):
        with requests.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return file_path

    def _try_instagrapi(self, url, code):
        logger.info(f"[{code}] Attempt 1: Instagrapi")
        if not self.instagrapi_client: raise Exception("Instagrapi client not logged in.")
        media_pk = self.instagrapi_client.media_pk_from_url(url)
        media_info = self.instagrapi_client.media_info(media_pk).dict()
        caption = media_info.get("caption_text", "")
        resources = media_info.get("resources", []) or [media_info]
        downloaded_files = []
        for i, res in enumerate(resources):
            dl_path, ext = None, ".jpg"
            if res.get("media_type") == 2:
                dl_path, ext = self.instagrapi_client.video_download(res['pk'], self.download_dir), ".mp4"
            elif res.get("media_type") == 1:
                dl_path, ext = self.instagrapi_client.photo_download(res['pk'], self.download_dir), ".jpg"
            if dl_path:
                final_path = os.path.join(self.download_dir, f"{code}_{i}{ext}")
                os.rename(dl_path, final_path)
                downloaded_files.append(final_path)
        if downloaded_files: return downloaded_files, caption, "Instagrapi"
        return [], None, None

    def _try_instaloader(self, url, code):
        logger.info(f"[{code}] Attempt 2: Instaloader")
        if not self.instaloader_client: raise Exception("Instaloader client not logged in.")
        shortcode = url.split('/')[-2]
        post = instaloader.Post.from_shortcode(self.instaloader_client.context, shortcode)
        downloaded_files, temp_dir = [], os.path.join(self.download_dir, code)
        self.instaloader_client.download_post(post, target=temp_dir)
        caption = post.caption or ""
        for i, filename in enumerate(sorted(os.listdir(temp_dir))):
            if not filename.endswith(('.jpg', '.mp4')): continue
            old_path = os.path.join(temp_dir, filename)
            new_path = os.path.join(self.download_dir, f"{code}_{i}{os.path.splitext(filename)[1]}")
            os.rename(old_path, new_path)
            downloaded_files.append(new_path)
        if os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir)
        if downloaded_files: return downloaded_files, caption, "Instaloader"
        return [], None, None

    def _try_yt_dlp_insta(self, url, code):
        logger.info(f"[{code}] Attempt 3: yt-dlp for Instagram")
        return self.download_other_platforms(url, code)

    def _try_majidapi(self, url, code):
        logger.info(f"[{code}] Attempt 4: MajidAPI")
        api_url = f"https://api.majidapi.ir/instagram/download?url={url}&out=url&token={MAJID_API_TOKEN}"
        data = requests.get(api_url, timeout=30).json()
        if data.get("status") != 200: raise Exception(f"MajidAPI Error: {data.get('result')}")
        result = data.get("result", {})
        caption = result.get("caption", "")
        media_urls = result.get("carousel") or ([result.get("video")] if result.get("video") else []) or result.get("images")
        downloaded_files = []
        for i, media_url in enumerate(media_urls):
            ext = ".mp4" if "video" in media_url else ".jpg"
            output_path = os.path.join(self.download_dir, f"{code}_{i}{ext}")
            self._download_from_url(media_url, output_path)
            downloaded_files.append(output_path)
        if downloaded_files: return downloaded_files, caption, "MajidAPI"
        return [], None, None

    def _try_nestcode_api(self, url, code):
        logger.info(f"[{code}] Attempt 5: NestCode API")
        api_url = f"https://open.nestcode.org/apis-1/InstagramDownloader?url={url}&key={NESTCODE_API_KEY}"
        data = requests.get(api_url, timeout=30).json()
        if data.get("status") != "success": raise Exception(f"NestCode API Error: {data.get('data')}")
        result = data.get("data", {})
        caption = result.get("caption", "")
        media_urls = result.get("medias", [])
        downloaded_files = []
        for i, media_url in enumerate(media_urls):
            ext = ".mp4" if "video" in media_url else ".jpg"
            output_path = os.path.join(self.download_dir, f"{code}_{i}{ext}")
            self._download_from_url(media_url, output_path)
            downloaded_files.append(output_path)
        if downloaded_files: return downloaded_files, caption, "NestCode API"
        return [], None, None

    def download_from_instagram(self, url, code):
        methods = [self._try_instagrapi, self._try_instaloader, self._try_yt_dlp_insta, self._try_majidapi, self._try_nestcode_api]
        for method_func in methods:
            try:
                file_paths, caption, method_name = method_func(url, code)
                if file_paths:
                    logger.info(f"✅ [{code}] Successfully downloaded using {method_name}.")
                    return file_paths, caption, method_name
            except Exception as e:
                logger.warning(f"⚠️ [{code}] Method {method_func.__name__} failed: {e}")
        return [], None, None

    def download_other_platforms(self, url, code):
        # ... (کد کامل تابع download_media از پاسخ قبلی اینجا قرار می‌گیرد، نامش را تغییر دادیم) ...
        pass

    # ... (تمام توابع دیگر: get_video_metadata, upload_single_file, process_job, run و ... اینجا قرار می‌گیرند) ...
    # ... لطفاً این توابع را از کد کامل پاسخ قبلی کپی کنید ...
