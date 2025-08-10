import psycopg2
import random
import string
from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
# --- اصلاحیه: وارد کردن ChatMemberStatus از مسیر درست ---
from telegram.constants import ChatMemberStatus
from config import (BOT_TOKEN, GROUP_ID, DB_NAME, DB_USER, DB_PASS, 
                    DB_HOST, DB_PORT, ORDER_TOPIC_ID, LOG_TOPIC_ID, ADMIN_IDS, FORCED_JOIN_CHANNELS)

# ... (کلاس PostgresDB بدون هیچ تغییری اینجا قرار میگیرد) ...
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
                cur.execute('CREATE TABLE IF NOT EXISTS jobs (id SERIAL PRIMARY KEY, code TEXT UNIQUE NOT NULL, user_id BIGINT REFERENCES users(user_id), url TEXT NOT NULL, status TEXT DEFAULT \'pending\', created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(), completed_at TIMESTAMP WITH TIME ZONE);')
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
    def get_user_by_code(self, code):
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM jobs WHERE code = %s;", (code,))
                result = cur.fetchone()
                return result[0] if result else None
    def update_job_status(self, code, status):
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE jobs SET status = %s, completed_at = NOW() WHERE code = %s;", (status, code))

# --- دکوراتور برای چک کردن جوین اجباری ---
def membership_required(func):
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user or not FORCED_JOIN_CHANNELS: return await func(self, update, context, *args, **kwargs)

        channels_to_join = []
        for channel in FORCED_JOIN_CHANNELS:
            try:
                member = await context.bot.get_chat_member(chat_id=channel, user_id=user.id)
                # --- اصلاحیه: استفاده از ChatMemberStatus ---
                if member.status not in [ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]:
                    channels_to_join.append(channel)
            except Exception:
                channels_to_join.append(channel)
        
        if channels_to_join:
            buttons = [[InlineKeyboardButton(f" عضویت در {channel.lstrip('@')}", url=f"https://t.me/{channel.lstrip('@')}")] for channel in channels_to_join]
            buttons.append([InlineKeyboardButton("✅ بررسی عضویت", callback_data="check_membership")])
            reply_markup = InlineKeyboardMarkup(buttons)
            # اگر پیام از نوع callback_query (کلیک روی دکمه) بود، پیام را ویرایش کن
            if update.callback_query:
                await update.callback_query.edit_message_text("هنوز عضو تمام کانال‌ها نیستید. لطفاً عضو شوید و دوباره تلاش کنید:", reply_markup=reply_markup)
            else:
                await update.message.reply_text("برای استفاده از ربات، لطفاً در کانال‌های زیر عضو شوید:", reply_markup=reply_markup)
            return

        # اگر کاربر عضو بود و روی دکمه کلیک کرده بود، پیام قبلی را پاک کن و پیام جدید بفرست
        if update.callback_query:
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

    @membership_required
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        is_new_user = self.db.add_user_if_not_exists(user)
        if is_new_user and self.log_topic_id:
            username = f"@{user.username}" if user.username else "ندارد"
            log_message = (f"🎉 کاربر جدید\n\nنام: {user.first_name}\nنام کاربری: {username}\nآیدی: [{user.id}](tg://user?id={user.id})")
            try:
                await context.bot.send_message(chat_id=self.group_id, text=log_message, message_thread_id=self.log_topic_id, parse_mode='Markdown')
            except Exception as e:
                print(f"❌ Could not send new user log: {e}")
        await update.message.reply_text("✅ خوش آمدید! شما عضو کانال‌های مورد نیاز هستید.\n\nمی‌توانید لینک خود را ارسال کنید.")

    async def manage_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in self.admin_ids:
            await update.message.reply_text("access denied.")
            return
        await update.message.reply_text("🔐 به پنل مدیریت خوش آمدید.")

    @membership_required
    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        self.db.add_user_if_not_exists(user)
        url = update.message.text.strip()
        code = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        self.db.add_job(code, user.id, url)
        message_for_worker = f"⬇️ NEW JOB\nURL: {url}\nCODE: {code}\nUSER_ID: {user.id}"
        try:
            await context.bot.send_message(chat_id=self.group_id, text=message_for_worker, message_thread_id=self.order_topic_id)
            await update.message.reply_text(f"✅ **درخواست ثبت شد!**\n\n🏷️ **کد پیگیری:** `{code}`", parse_mode='Markdown')
        except Exception as e:
            print(f"❌ Error sending job to order topic: {e}")

    async def handle_group_files(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or update.message.message_thread_id != self.order_topic_id or "CODE:" not in update.message.caption: return
        try:
            code = update.message.caption.split("CODE:")[1].strip()
            user_id = self.db.get_user_by_code(code)
            if not user_id: return
            caption = "🎉 **دانلود شما آماده‌ست!**"
            if update.message.video:
                await context.bot.send_video(chat_id=user_id, video=update.message.video.file_id, caption=caption, parse_mode='Markdown')
            elif update.message.document and ('video' in update.message.document.mime_type or update.message.document.file_name.endswith(('.mp4', '.mkv'))):
                await context.bot.send_video(chat_id=user_id, video=update.message.document.file_id, caption=caption, parse_mode='Markdown')
            elif update.message.document:
                await context.bot.send_document(chat_id=user_id, document=update.message.document.file_id, caption=caption, parse_mode='Markdown')
            self.db.update_job_status(code, 'completed')
        except Exception as e:
            print(f"❌ Error sending file to user: {e}")
    
    @membership_required
    async def check_membership_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        # بعد از اینکه کاربر روی دکمه کلیک کرد، تابع start_command دوباره چک می‌کند
        # اگر عضو شده باشد، پیام خوشامدگویی را دریافت می‌کند
        await self.start_command(query.message, context)

    def run(self):
        from telegram.ext import CallbackQueryHandler
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("manage", self.manage_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_url))
        self.app.add_handler(MessageHandler((filters.VIDEO | filters.Document.ALL) & filters.Chat(self.group_id) & filters.CAPTION, self.handle_group_files))
        self.app.add_handler(CallbackQueryHandler(self.check_membership_callback, pattern="^check_membership$"))
        print("🚀 Bot is running with Forced Join...")
        self.app.run_polling()
        
if __name__ == "__main__":
    bot = AdvancedBot(
        token=BOT_TOKEN, group_id=GROUP_ID, 
        order_topic_id=ORDER_TOPIC_ID, log_topic_id=LOG_TOPIC_ID,
        admin_ids=ADMIN_IDS
    )
    bot.run()
