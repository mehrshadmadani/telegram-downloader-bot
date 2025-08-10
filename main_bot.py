import sqlite3
import random
import string
from datetime import datetime
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from telegram.constants import ChatType
from telegram.error import Forbidden

# --- کلاس دیتابیس (بدون تغییر) ---
class DatabaseManager:
    def __init__(self, db_path="jobs.db"):
        self.db_path = db_path
        self.init_database()
    def init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL, url TEXT NOT NULL, status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, completed_at TIMESTAMP
                )
            ''')
    def add_job(self, code, user_id, url):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO jobs (code, user_id, url) VALUES (?, ?, ?)",(code, user_id, url))
    def update_job_status(self, code, status):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE jobs SET status = ?, completed_at = ? WHERE code = ?",(status, datetime.now(), code))
    def get_user_by_code(self, code):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT user_id FROM jobs WHERE code = ?", (code,))
            result = cursor.fetchone()
            return result[0] if result else None

# --- ربات اصلی با مدیریت خطای بهتر ---
class AdvancedBot:
    def __init__(self, token, group_id):
        self.token = token
        self.group_id = int(group_id)
        self.db = DatabaseManager()
        self.app = Application.builder().token(self.token).build()

    def generate_code(self):
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

    def is_valid_url(self, url):
        return any(domain in url.lower() for domain in ["youtube.com", "youtu.be", "instagram.com"])

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🚀 **ربات دانلودر پیشرفته**\n\nکافیه لینک یوتیوب یا اینستاگرام خودتون رو بفرستید.", parse_mode='Markdown')

    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text: return
        url = update.message.text.strip()
        user_id = update.effective_user.id

        if not self.is_valid_url(url):
            await update.message.reply_text("❌ **لینک نامعتبره!**", parse_mode='Markdown')
            return

        code = self.generate_code()
        self.db.add_job(code, user_id, url)
        message_for_worker = f"⬇️ NEW JOB\nURL: {url}\nCODE: {code}"
        
        try:
            await context.bot.send_message(chat_id=self.group_id, text=message_for_worker)
            response_text = f"✅ **درخواست شما ثبت شد!**\n\n🏷️ **کد پیگیری:** `{code}`\n\n⏳ در صف دانلود قرار گرفت."
            await update.message.reply_text(response_text, parse_mode='Markdown')
            print(f"✅ Job {code} for user {user_id} sent to worker group.")
        except Forbidden:
            print(f"❌ Bot blocked by group or user. Failed to send job {code}.")
            await update.message.reply_text("⛔️ مشکلی در ارسال به گروه دانلود پیش اومده.")
        except Exception as e:
            print(f"❌ Error sending job to group: {e}")
            await update.message.reply_text("⛔️ یک خطای پیش‌بینی نشده رخ داد.")

    async def handle_group_files(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.caption or "CODE:" not in update.message.caption: return
        
        try:
            code = update.message.caption.split("CODE:")[1].strip()
            user_id = self.db.get_user_by_code(code)
            if not user_id: return

            await update.message.forward(chat_id=user_id)
            await context.bot.send_message(chat_id=user_id, text="🎉 **دانلود شما آماده‌ست!**", parse_mode='Markdown')
            self.db.update_job_status(code, 'completed')
            print(f"✅ File with code {code} successfully sent to user {user_id}.")
        except Forbidden:
            print(f"❌ User {user_id} has blocked the bot. Could not send file for code {code}.")
        except Exception as e:
            print(f"❌ Error forwarding file to user: {e}")

    def run(self):
        self.app.add_handler(CommandHandler("start", self.start_command))
        # فیلتر دقیق‌تر: فقط پیام‌های متنی در چت خصوصی
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, self.handle_url))
        self.app.add_handler(MessageHandler(
            (filters.VIDEO | filters.Document.ALL | filters.PHOTO) & filters.Chat(self.group_id) & filters.CAPTION,
            self.handle_group_files
        ))
        print("🚀 Bot is running...")
        self.app.run_polling()

if __name__ == "__main__":
    bot_token = input("🤖 Bot Token ro vared konid: ")
    group_id = input("🎯 Group ID ro vared konid: ")
    bot = AdvancedBot(token=bot_token, group_id=group_id)
    bot.run()
