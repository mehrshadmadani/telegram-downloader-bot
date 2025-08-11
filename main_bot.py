import os
import psycopg2
import random
import string
import base64
import re
import logging
import subprocess
from functools import wraps
from datetime import datetime, timedelta
import yt_dlp
from instagrapi import Client as InstagrapiClient

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ChatMemberStatus
from telegram.error import BadRequest
from config import (BOT_TOKEN, BACKUP_BOT_TOKEN, GROUP_ID, DB_NAME, DB_USER, DB_PASS, DB_HOST, DB_PORT,
                    ORDER_TOPIC_ID, LOG_TOPIC_ID, ADMIN_IDS, FORCED_JOIN_CHANNELS,
                    INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD,
                    BUTTON_TEXT, BUTTON_URL, FOOTER_TEXT, USER_COOLDOWN_SECONDS,
                    START_MESSAGE, SUBMIT_MESSAGE, FAILURE_MESSAGE,
                    AUTO_BACKUP_INTERVAL_MINUTES)

# --- سیستم لاگ‌گیری ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s')
if logger.hasHandlers():
    logger.handlers.clear()
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)
file_handler_main = logging.FileHandler('main_bot.log', encoding='utf-8')
file_handler_main.setFormatter(formatter)
logger.addHandler(file_handler_main)

class PostgresDB:
    def __init__(self):
        self.conn_params = {"dbname": DB_NAME, "user": DB_USER, "password": DB_PASS, "host": DB_HOST, "port": DB_PORT}
        self.init_database()

    def get_conn(self):
        return psycopg2.connect(**self.conn_params)

    def init_database(self):
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, first_name TEXT, username TEXT, join_date TIMESTAMP WITH TIME ZONE DEFAULT NOW());')
                cur.execute('CREATE TABLE IF NOT EXISTS jobs (id SERIAL PRIMARY KEY, code TEXT UNIQUE NOT NULL, user_id BIGINT REFERENCES users(user_id), url TEXT NOT NULL, status TEXT DEFAULT \'pending\', created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(), completed_at TIMESTAMP WITH TIME ZONE, file_size BIGINT);')

    def add_user_if_not_exists(self, user: Update.effective_user):
        sql = 'INSERT INTO users (user_id, first_name, username) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO NOTHING;'
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (user.id, user.first_name, user.username))
                return cur.rowcount > 0

    def add_job(self, code, user_id, url):
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO jobs (code, user_id, url) VALUES (%s, %s, %s);", (code, user_id, url))

    def get_job_by_code(self, code):
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id, url FROM jobs WHERE code = %s;", (code,))
                result = cur.fetchone()
                return {'user_id': result[0], 'url': result[1]} if result else None

    def update_job_on_complete(self, code, status, file_size):
        sql = "UPDATE jobs SET status = %s, completed_at = NOW(), file_size = %s WHERE code = %s;"
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (status, file_size, code))

    def get_bot_statistics(self):
        stats = {}
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users;")
                stats['total_users'] = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM jobs WHERE status = 'completed';")
                stats['total_downloads'] = cur.fetchone()[0]
                cur.execute("SELECT SUM(file_size) FROM jobs WHERE status = 'completed';")
                total_size_bytes = cur.fetchone()[0]
                stats['total_volume_gb'] = (total_size_bytes or 0) / (1024**3)
        return stats

def membership_required(func):
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user or not FORCED_JOIN_CHANNELS:
            return await func(self, update, context, *args, **kwargs)
        channels_to_join = []
        for channel in FORCED_JOIN_CHANNELS:
            try:
                member = await context.bot.get_chat_member(chat_id=channel, user_id=user.id)
                if member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED]:
                    channels_to_join.append(channel)
            except:
                channels_to_join.append(channel)
        if channels_to_join:
            buttons = [[InlineKeyboardButton(f"عضویت در {channel.lstrip('@')}", url=f"https://t.me/{channel.lstrip('@')}")] for channel in channels_to_join]
            buttons.append([InlineKeyboardButton("✅ بررسی عضویت", callback_data="check_membership")])
            reply_markup = InlineKeyboardMarkup(buttons)
            text = "برای استفاده از ربات، لطفاً در کانال‌های زیر عضو شوید:"
            if update.callback_query:
                await update.callback_query.answer("هنوز عضو تمام کانال‌ها نیستید!", show_alert=True)
            else:
                await update.message.reply_text(text, reply_markup=reply_markup)
            return
        if update.callback_query:
            await update.callback_query.answer("عضویت شما تایید شد!")
            await update.callback_query.delete_message()
        return await func(self, update, context, *args, **kwargs)
    return wrapper

class AdvancedBot:
    def __init__(self, token, group_id, order_topic_id, log_topic_id, admin_ids):
        self.token = token
        self.group_id = int(group_id)
        self.order_topic_id = int(order_topic_id)
        self.log_topic_id = int(log_topic_id)
        self.admin_ids = admin_ids
        self.db = PostgresDB()
        self.app = Application.builder().token(self.token).build()
        self.instagrapi_client = self.setup_instagrapi_client()

    def setup_instagrapi_client(self):
        try:
            client = InstagrapiClient()
            session_file = f"main_bot_instagrapi_session.json"
            if os.path.exists(session_file):
                client.load_settings(session_file)
            client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            client.dump_settings(session_file)
            logger.info("✅ Main Bot Instagrapi session loaded/created.")
            return client
        except Exception as e:
            logger.error(f"❌ Main Bot could not login to Instagram. Error: {e}")
            return None
    
    @membership_required
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        is_new_user = self.db.add_user_if_not_exists(user)
        if is_new_user and self.log_topic_id:
            username = f"@{user.username}" if user.username else "ندارد"
            log_message = (f"🎉 کاربر جدید\n\nنام: {user.first_name}\nنام کاربری: {username}\nآیدی: [{user.id}](tg://user?id={user.id})")
            await context.bot.send_message(chat_id=self.group_id, text=log_message, message_thread_id=self.log_topic_id, parse_mode='Markdown')
        chat_id = update.effective_chat.id
        if update.message:
            await update.message.reply_text(START_MESSAGE)
        else:
            await context.bot.send_message(chat_id=chat_id, text=START_MESSAGE)

    async def manage_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in self.admin_ids: return
        buttons = [[InlineKeyboardButton("📊 آمار ربات", callback_data="bot_stats")]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text("🔐 به پنل مدیریت خوش آمدید:", reply_markup=reply_markup)

    async def stats_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer("در حال محاسبه آمار...")
        stats = self.db.get_bot_statistics()
        text = f"📊 **آمار کلی ربات**\n━━━━━━━━━━━━━━━━━━\n👥 **کل کاربران:** {stats.get('total_users', 0)}\n📥 **کل دانلودها:** {stats.get('total_downloads', 0)}\n💾 **حجم کل:** {stats.get('total_volume_gb', 0):.2f} GB"
        await query.edit_message_text(text, parse_mode='Markdown')

    @membership_required
    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id not in self.admin_ids:
            now = datetime.now()
            last_request_time = context.user_data.get('last_request_time')
            cooldown = timedelta(seconds=USER_COOLDOWN_SECONDS)
            if last_request_time and (now - last_request_time) < cooldown:
                remaining_time = cooldown - (now - last_request_time)
                await update.message.reply_text(f"⏳ برای ارسال لینک بعدی، لطفاً **{int(remaining_time.total_seconds()) + 1}** ثانیه دیگر صبر کنید.", parse_mode='Markdown')
                return
            context.user_data['last_request_time'] = now
        self.db.add_user_if_not_exists(user)
        url = update.message.text.strip()
        code = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        self.db.add_job(code, user.id, url)
        message_for_worker = f"⬇️ NEW JOB\nURL: {url}\nCODE: {code}\nUSER_ID: {user.id}"
        await context.bot.send_message(chat_id=self.group_id, text=message_for_worker, message_thread_id=self.order_topic_id)
        submit_text = SUBMIT_MESSAGE.format(code=code)
        await update.message.reply_text(submit_text, parse_mode='Markdown')

    async def handle_failed_job(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text or update.message.message_thread_id != self.order_topic_id:
            return
        try:
            lines = update.message.text.split('\n')
            code = next(l.split(":", 1)[1].strip() for l in lines if l.startswith("CODE:"))
            job_info = self.db.get_job_by_code(code)
            if job_info and job_info.get('user_id'):
                user_id = job_info['user_id']
                logger.info(f"Notifying user {user_id} about failed job {code}.")
                await context.bot.send_message(chat_id=user_id, text=FAILURE_MESSAGE)
        except Exception as e:
            logger.error(f"Error in handle_failed_job: {e}")

    async def handle_group_files(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.caption or update.message.message_thread_id != self.order_topic_id:
            return
        info = {}
        try:
            caption_lines = update.message.caption.split('\n')
            info = {line.split(":", 1)[0].strip(): line.split(":", 1)[1].strip() for line in caption_lines if ":" in line}
            code, size, method = info.get("CODE"), int(info.get("SIZE", 0)), info.get("METHOD")
            job_info = self.db.get_job_by_code(code)
            if not job_info: return
            user_id, original_url = job_info['user_id'], job_info['url']
            self.db.update_job_on_complete(code, 'completed', size)
            footer = f"\n\n{FOOTER_TEXT}"
            async def send_media_to_user(media_type, file_id, caption_text):
                reply_markup = None
                if BUTTON_TEXT and BUTTON_URL:
                    keyboard = [[InlineKeyboardButton(BUTTON_TEXT, url=BUTTON_URL)]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                actions = {'video': context.bot.send_video, 'audio': context.bot.send_audio, 'photo': context.bot.send_photo, 'document': context.bot.send_document}
                kwargs = {'chat_id': user_id, media_type: file_id, 'caption': caption_text, 'parse_mode': 'Markdown', 'reply_markup': reply_markup}
                if media_type: await actions[media_type](**kwargs)
            media_type = next((mt for mt in ['video', 'audio', 'photo', 'document'] if getattr(update.message, mt)), None)
            file_id = getattr(update.message, media_type).file_id if media_type != 'photo' else getattr(update.message, media_type)[-1].file_id
            if method == "Instagram Profile":
                if not self.instagrapi_client: raise Exception("Main bot's Instagrapi client not ready.")
                username = base64.b64decode(info["CAPTION"]).decode('utf-8').strip()
                user_info = self.instagrapi_client.user_info_by_username(username).model_dump()
                full_caption = (f"👤 **{user_info.get('full_name')}** (`@{user_info.get('username')}`)\n\n"
                                f"**Bio:**\n{user_info.get('biography')}\n\n"
                                f"----------------------------------------\n"
                                f"**Posts:** {user_info.get('media_count')} | "
                                f"**Followers:** {user_info.get('follower_count')} | "
                                f"**Following:** {user_info.get('following_count')}" + footer)
                await send_media_to_user('photo', file_id, full_caption)
            else:
                full_description, title = "", ""
                try:
                    with yt_dlp.YoutubeDL({'quiet': True, 'ignoreerrors': True, 'cookiefile': 'cookies.txt'}) as ydl:
                        meta = ydl.extract_info(original_url, download=False)
                        if meta:
                            full_description, title = meta.get('description', ''), meta.get('title', '')
                except Exception:
                    try: title = base64.b64decode(info["CAPTION"]).decode('utf-8').strip()
                    except: title = "فایل شما"
                item_info_str = next((line for line in caption_lines if line.startswith("✅ Uploaded")), "")
                match = re.search(r'\((\d+)/(\d+)\)', item_info_str)
                slide_info = f"\n\nاسلاید {match.group(1)} از {match.group(2)}" if match else ""
                if full_description and len(full_description) > 1000:
                    short_caption = (title + slide_info + footer).strip()
                    await send_media_to_user(media_type, file_id, short_caption)
                    for i in range(0, len(full_description), 4096):
                        await context.bot.send_message(chat_id=user_id, text=full_description[i:i+4096], disable_web_page_preview=True)
                else:
                    caption_content = full_description if full_description else title
                    full_caption = (caption_content + slide_info + footer).strip()
                    await send_media_to_user(media_type, file_id, full_caption)
        except Exception as e:
            logger.error(f"❌ Error processing group file for code {info.get('CODE', 'N/A')}: {e}", exc_info=True)

    async def check_membership_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.start_command(update, context)

    async def _perform_backup_and_send(self, context: ContextTypes.DEFAULT_TYPE):
        logger.info("Starting backup process...")
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        sql_file, archive_file = f"backup_{timestamp}.sql", f"bot_backup_{timestamp}.tar.gz"
        project_dir, parent_dir = os.getcwd(), os.path.dirname(os.getcwd())
        dir_name = os.path.basename(project_dir)
        try:
            pg_dump_cmd = f"pg_dump -U {DB_USER} -d {DB_NAME} > {sql_file}"
            env = os.environ.copy()
            env['PGPASSWORD'] = DB_PASS
            subprocess.run(pg_dump_cmd, shell=True, check=True, env=env, capture_output=True)
            logger.info(f"Successfully created SQL dump: {sql_file}")
            tar_cmd = (f"tar -czvf {archive_file} --exclude='venv' --exclude='__pycache__' "
                       f"--exclude='downloads' --exclude='*.log' --exclude='*.session*' "
                       f"--exclude='*.json' {dir_name}/{sql_file} {dir_name}")
            subprocess.run(tar_cmd, shell=True, check=True, cwd=parent_dir, capture_output=True)
            logger.info(f"Successfully created archive: {archive_file}")
            backup_bot = Application.builder().token(BACKUP_BOT_TOKEN).build().bot
            caption = f"✅ بکاپ ربات\n\n🗓 تاریخ: {timestamp}\n📦 فایل: `{archive_file}`"
            with open(os.path.join(parent_dir, archive_file), 'rb') as backup_file_obj:
                for admin_id in self.admin_ids:
                    try:
                        backup_file_obj.seek(0)
                        await backup_bot.send_document(chat_id=admin_id, document=backup_file_obj, caption=caption, parse_mode='Markdown')
                    except Exception as send_err:
                        logger.error(f"Could not send backup to admin {admin_id}: {send_err}")
            return True, None
        except subprocess.CalledProcessError as e:
            error_message = f"Backup shell command failed. stderr: {e.stderr.decode()}"
            logger.error(error_message)
            return False, error_message
        except Exception as e:
            error_message = f"An unexpected error occurred during backup: {e}"
            logger.error(error_message, exc_info=True)
            return False, error_message
        finally:
            sql_file_path, archive_file_path = os.path.join(project_dir, sql_file), os.path.join(parent_dir, archive_file)
            if os.path.exists(sql_file_path): os.remove(sql_file_path)
            if os.path.exists(archive_file_path): os.remove(archive_file_path)
            logger.info("Backup cleanup complete.")

    async def backup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id not in self.admin_ids:
            await update.message.reply_text("⛔️ شما اجازه استفاده از این دستور را ندارید.")
            return
        await update.message.reply_text("⏳ در حال شروع فرآیند بکاپ‌گیری دستی...")
        success, error_message = await self._perform_backup_and_send(context)
        if success:
            await update.message.reply_text("✅ فرآیند بکاپ‌گیری با موفقیت انجام شد و فایل برای ادمین‌ها ارسال گردید.")
        else:
            await update.message.reply_text(f"❌ بکاپ‌گیری با خطا مواجه شد.\n\nجزئیات در فایل `main_bot.log` ثبت شد.")

    async def scheduled_backup_job(self, context: ContextTypes.DEFAULT_TYPE):
        logger.info("Running scheduled backup job...")
        await self._perform_backup_and_send(context)

    def run(self):
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("manage", self.manage_command))
        self.app.add_handler(CommandHandler("backup", self.backup_command))
        self.app.add_handler(CallbackQueryHandler(self.stats_callback, pattern="^bot_stats$"))
        self.app.add_handler(CallbackQueryHandler(self.check_membership_callback, pattern="^check_membership$"))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_url))
        self.app.add_handler(MessageHandler((filters.VIDEO | filters.AUDIO | filters.PHOTO | filters.Document.ALL) & filters.Chat(self.group_id) & filters.CAPTION, self.handle_group_files))
        self.app.add_handler(MessageHandler(filters.TEXT & filters.Chat(self.group_id) & filters.Regex(r"^❌ JOB FAILED"), self.handle_failed_job))
        
        if AUTO_BACKUP_INTERVAL_MINUTES > 0:
            job_queue = self.app.job_queue
            interval_seconds = AUTO_BACKUP_INTERVAL_MINUTES * 60
            job_queue.run_repeating(self.scheduled_backup_job, interval=interval_seconds, first=10)
            logger.info(f"✅ Scheduled backup job is set to run every {AUTO_BACKUP_INTERVAL_MINUTES} minutes.")
        else:
            logger.info("ℹ️ Auto backup is disabled.")

        logger.info("🚀 Main Bot is running...")
        self.app.run_polling()

if __name__ == "__main__":
    bot = AdvancedBot(token=BOT_TOKEN, group_id=GROUP_ID, order_topic_id=ORDER_TOPIC_ID, log_topic_id=LOG_TOPIC_ID, admin_ids=ADMIN_IDS)
    bot.run()
