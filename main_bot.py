import psycopg2
import random
import string
import base64
import re
import logging
from functools import wraps
import yt_dlp
from instagrapi import Client as InstagrapiClient

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ChatMemberStatus
from telegram.error import BadRequest
from config import (BOT_TOKEN, GROUP_ID, DB_NAME, DB_USER, DB_PASS, DB_HOST, DB_PORT, 
                    ORDER_TOPIC_ID, LOG_TOPIC_ID, ADMIN_IDS, FORCED_JOIN_CHANNELS,
                    INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)

# --- سیستم لاگ‌گیری ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s')
if logger.hasHandlers(): logger.handlers.clear()
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
            if os.path.exists(session_file): client.load_settings(session_file)
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
        await update.message.reply_text("✅ خوش آمدید!\n\nمی‌توانید لینک خود را ارسال کنید.")

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
        self.db.add_user_if_not_exists(user)
        url = update.message.text.strip()
        code = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        self.db.add_job(code, user.id, url)
        message_for_worker = f"⬇️ NEW JOB\nURL: {url}\nCODE: {code}\nUSER_ID: {user.id}"
        await context.bot.send_message(chat_id=self.group_id, text=message_for_worker, message_thread_id=self.order_topic_id)
        await update.message.reply_text(f"✅ **درخواست ثبت شد!**\n\n🏷️ **کد پیگیری:** `{code}`", parse_mode='Markdown')

    async def handle_group_files(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.caption or update.message.message_thread_id != self.order_topic_id:
            return
        try:
            caption_lines = update.message.caption.split('\n')
            info = {line.split(":", 1)[0].strip(): line.split(":", 1)[1].strip() for line in caption_lines if ":" in line}
            
            code, size, method = info.get("CODE"), int(info.get("SIZE", 0)), info.get("METHOD")
            job_info = self.db.get_job_by_code(code)
            if not job_info: return
            
            user_id, original_url = job_info['user_id'], job_info['url']
            self.db.update_job_on_complete(code, 'completed', size)

            footer = ("\n\n—————————————————\n"
                      "🍭 Download by [CokaDownloader](https://t.me/parsvip0_bot?start=0)")
            
            async def send_media_to_user(media_type, file_id, caption_text):
                actions = {'video': context.bot.send_video, 'audio': context.bot.send_audio, 'photo': context.bot.send_photo, 'document': context.bot.send_document}
                kwargs = {'chat_id': user_id, media_type: file_id, 'caption': caption_text, 'parse_mode': 'Markdown'}
                await actions[media_type](**kwargs)
            
            media_type = next((mt for mt in ['video', 'audio', 'photo', 'document'] if getattr(update.message, mt)), None)
            file_id = getattr(update.message, media_type).file_id if media_type != 'photo' else getattr(update.message, media_type)[-1].file_id

            if method == "Instagram Profile":
                if not self.instagrapi_client: raise Exception("Main bot's Instagrapi client not ready.")
                username = base64.b64decode(info["CAPTION"]).decode('utf-8').strip()
                user_info = self.instagrapi_client.user_info_by_username(username).dict()
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
                            full_description = meta.get('description', '')
                            title = meta.get('title', '')
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

    def run(self):
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("manage", self.manage_command))
        self.app.add_handler(CallbackQueryHandler(self.stats_callback, pattern="^bot_stats$"))
        self.app.add_handler(CallbackQueryHandler(self.check_membership_callback, pattern="^check_membership$"))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_url))
        self.app.add_handler(MessageHandler((filters.VIDEO | filters.AUDIO | filters.PHOTO | filters.Document.ALL) & filters.Chat(self.group_id) & filters.CAPTION, self.handle_group_files))
        logger.info("🚀 Main Bot is running...")
        self.app.run_polling()

if __name__ == "__main__":
    bot = AdvancedBot(token=BOT_TOKEN, group_id=GROUP_ID, order_topic_id=ORDER_TOPIC_ID, log_topic_id=LOG_TOPIC_ID, admin_ids=ADMIN_IDS)
    bot.run()
