import psycopg2
import random
import string
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from telegram.error import Forbidden
from config import BOT_TOKEN, GROUP_ID, DB_NAME, DB_USER, DB_PASS, DB_HOST, DB_PORT

# --- مدیریت دیتابیس PostgreSQL ---
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
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('INSERT INTO users (user_id, first_name, username) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO NOTHING;', (user.id, user.first_name, user.username))
    def add_job(self, code, user_id, url):
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO jobs (code, user_id, url) VALUES (%s, %s, %s);", (code, user_id, url))
    def update_job_status(self, code, status):
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE jobs SET status = %s, completed_at = NOW() WHERE code = %s;", (status, code))
    def get_user_by_code(self, code):
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM jobs WHERE code = %s;", (code,))
                result = cur.fetchone()
                return result[0] if result else None

# --- ربات اصلی ---
class AdvancedBot:
    def __init__(self, token, group_id):
        self.token = token
        self.group_id = int(group_id)
        self.db = PostgresDB()
        self.app = Application.builder().token(self.token).build()
    def generate_code(self):
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message:
            self.db.add_user_if_not_exists(update.effective_user)
            await update.message.reply_text("🚀 **ربات دانلودر**\n\nلینک یوتیوب یا اینستاگرام خود را بفرستید.")
    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text: return
        user = update.effective_user
        self.db.add_user_if_not_exists(user)
        url = update.message.text.strip()
        code = self.generate_code()
        self.db.add_job(code, user.id, url)
        
        # --- اصلاح کلیدی: اضافه کردن User ID به پیام ---
        message_for_worker = f"⬇️ NEW JOB\nURL: {url}\nCODE: {code}\nUSER_ID: {user.id}"
        
        try:
            await context.bot.send_message(chat_id=self.group_id, text=message_for_worker)
            await update.message.reply_text(f"✅ **درخواست شما ثبت شد!**\n\n🏷️ **کد پیگیری:** `{code}`", parse_mode='Markdown')
        except Exception as e:
            print(f"❌ Error sending job {code} to group: {e}")
    async def handle_group_files(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.caption or "CODE:" not in update.message.caption: return
        try:
            code = update.message.caption.split("CODE:")[1].strip()
            user_id = self.db.get_user_by_code(code)
            if not user_id: return
            caption = "🎉 **دانلود شما آماده‌ست!**"
            if update.message.video:
                await context.bot.send_video(chat_id=user_id, video=update.message.video.file_id, caption=caption, parse_mode='Markdown')
            elif update.message.document:
                await context.bot.send_document(chat_id=user_id, document=update.message.document.file_id, caption=caption, parse_mode='Markdown')
            self.db.update_job_status(code, 'completed')
        except Exception as e:
            print(f"❌ Error sending file to user: {e}")
    def run(self):
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_url))
        self.app.add_handler(MessageHandler((filters.VIDEO | filters.Document.ALL) & filters.Chat(self.group_id) & filters.CAPTION, self.handle_group_files))
        print("🚀 Bot is running with PostgreSQL...")
        self.app.run_polling()
if __name__ == "__main__":
    bot = AdvancedBot(token=BOT_TOKEN, group_id=GROUP_ID)
    bot.run()
