import os
import sqlite3
import random
import string
from datetime import datetime
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

# --- مدیریت دیتابیس ---
class DatabaseManager:
    def __init__(self, db_path="jobs.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            ''')
            conn.commit()

    def add_job(self, code, user_id, url):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO jobs (code, user_id, url) VALUES (?, ?, ?)",
                (code, user_id, url)
            )
            conn.commit()

    def update_job_status(self, code, status):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE jobs SET status = ?, completed_at = ? WHERE code = ?",
                (status, datetime.now(), code)
            )
            conn.commit()

    def get_user_by_code(self, code):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM jobs WHERE code = ?", (code,))
            result = cursor.fetchone()
            return result[0] if result else None

# --- ربات اصلی تلگرام ---
class AdvancedBot:
    def __init__(self, token, group_id):
        self.token = token
        self.group_id = int(group_id)
        self.db = DatabaseManager()
        self.app = Application.builder().token(self.token).build()

    def generate_code(self):
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

    def is_valid_url(self, url):
        valid_domains = ["youtube.com", "youtu.be", "instagram.com"]
        return any(domain in url.lower() for domain in valid_domains)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome_text = """
🚀 **ربات دانلودر پیشرفته**

کافیه لینک یوتیوب یا اینستاگرام خودتون رو بفرستید تا فایلش رو تحویل بگیرید.

⚡ **ویژگی‌ها:**
- سرعت بالا و پردازش همزمان
- پشتیبانی از لینک‌های مختلف
- دانلود و ارسال سریع

منتظر لینکتون هستم!
        """
        await update.message.reply_text(welcome_text, parse_mode='Markdown')

    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        url = update.message.text.strip()
        user_id = update.effective_user.id

        if not self.is_valid_url(url):
            await update.message.reply_text("❌ **لینک نامعتبره!**\nلطفاً یک لینک معتبر از یوتیوب یا اینستاگرام بفرستید.", parse_mode='Markdown')
            return

        code = self.generate_code()
        self.db.add_job(code, user_id, url)
        
        # پیام برای ارسال به گروه دانلودر
        message_for_worker = f"⬇️ NEW JOB\nURL: {url}\nCODE: {code}"
        
        try:
            # ارسال کار به گروه دانلودر
            await context.bot.send_message(chat_id=self.group_id, text=message_for_worker)
            
            # پاسخ به کاربر
            response_text = f"✅ **درخواست شما ثبت شد!**\n\n🏷️ **کد پیگیری:** `{code}`\n\n⏳ در صف دانلود قرار گرفت. به محض آماده شدن فایل، براتون ارسال می‌شه."
            await update.message.reply_text(response_text, parse_mode='Markdown')
            print(f"✅ Job {code} for user {user_id} sent to worker group.")

        except Exception as e:
            print(f"❌ Error sending job to group: {e}")
            await update.message.reply_text("⛔️ مشکلی در ارتباط با سیستم دانلود پیش اومده. لطفاً بعداً دوباره تلاش کنید.")


    async def handle_group_files(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # فقط پیام‌های گروه دانلودر رو پردازش کن
        if update.effective_chat.id != self.group_id:
            return
        
        # دنبال پیام‌هایی باش که فایل دارن و کپشن اون‌ها کد داره
        if not update.message.caption or "CODE:" not in update.message.caption:
            return

        try:
            # استخراج کد از کپشن
            code = update.message.caption.split("CODE:")[1].strip()
            user_id = self.db.get_user_by_code(code)

            if not user_id:
                print(f"❌ Code {code} from group file not found in database.")
                return

            print(f"✅ File received for code {code}. Forwarding to user {user_id}...")
            # فوروارد مستقیم فایل به کاربر
            await update.message.forward(chat_id=user_id)
            
            # ارسال پیام تأیید به کاربر
            await context.bot.send_message(
                chat_id=user_id,
                text="🎉 **دانلود شما آماده‌ست!**\n\nاز استفاده شما متشکریم!",
                parse_mode='Markdown'
            )
            
            # آپدیت وضعیت در دیتابیس
            self.db.update_job_status(code, 'completed')
            print(f"✅ File with code {code} successfully sent to user {user_id}.")

        except Exception as e:
            print(f"❌ Error forwarding file to user: {e}")

    def run(self):
        # Handler ها
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_url))
        
        # این Handler فقط فایل‌های دارای کپشن در گروه رو پردازش می‌کنه
        self.app.add_handler(MessageHandler(
            (filters.VIDEO | filters.Document.ALL | filters.PHOTO) & filters.Chat(chat_id=self.group_id) & filters.CAPTION,
            self.handle_group_files
        ))

        print("🚀 Bot is running...")
        self.app.run_polling()


if __name__ == "__main__":
    print("--- راه اندازی ربات دانلودر ---")
    bot_token = input("🤖 توکن ربات تلگرام (Bot Token) رو وارد کنید: ")
    group_id = input("🎯 آیدی عددی گروه دانلودر (Group ID) رو وارد کنید: ")
    
    if not bot_token or not group_id:
        print("❌ توکن و آیدی گروه الزامی است. برنامه متوقف شد.")
    else:
        bot = AdvancedBot(token=bot_token, group_id=group_id)
        bot.run()
