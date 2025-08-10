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
        self.conn_params = {
            "dbname": DB_NAME, "user": DB_USER, "password": DB_PASS,
            "host": DB_HOST, "port": DB_PORT
        }
        self.init_database()

    def get_conn(self):
        return psycopg2.connect(**self.conn_params)

    def init_database(self):
        try:
            with self.get_conn() as conn:
                with conn.cursor() as cur:
                    # ساخت جدول کاربران
                    cur.execute('''
                        CREATE TABLE IF NOT EXISTS users (
                            user_id BIGINT PRIMARY KEY,
                            first_name TEXT,
                            username TEXT,
                            join_date TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                        );
                    ''')
                    # ساخت جدول کارها با کلید خارجی به جدول کاربران
                    cur.execute('''
                        CREATE TABLE IF NOT EXISTS jobs (
                            id SERIAL PRIMARY KEY,
                            code TEXT UNIQUE NOT NULL,
                            user_id BIGINT REFERENCES users(user_id),
                            url TEXT NOT NULL,
                            status TEXT DEFAULT 'pending',
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            completed_at TIMESTAMP WITH TIME ZONE
                        );
                    ''')
            print("✅ Database tables checked/created successfully.")
        except Exception as e:
            print(f"❌ Error initializing database: {e}")

    def add_user_if_not_exists(self, user: Update.effective_user):
        sql = '''
            INSERT INTO users (user_id, first_name, username) 
            VALUES (%s, %s, %s) 
            ON CONFLICT (user_id) DO NOTHING;
        '''
        try:
            with self.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (user.id, user.first_name, user.username))
        except Exception as e:
            print(f"❌ Error adding user: {e}")
    
    def add_job(self, code, user_id, url):
        sql = "INSERT INTO jobs (code, user_id, url) VALUES (%s, %s, %s);"
        try:
            with self.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (code, user_id, url))
        except Exception as e:
            print(f"❌ Error adding job: {e}")

    def update_job_status(self, code, status):
        sql = "UPDATE jobs SET status = %s, completed_at = NOW() WHERE code = %s;"
        try:
            with self.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (status, code))
        except Exception as e:
            print(f"❌ Error updating job status: {e}")

    def get_user_by_code(self, code):
        sql = "SELECT user_id FROM jobs WHERE code = %s;"
        try:
            with self.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (code,))
                    result = cur.fetchone()
                    return result[0] if result else None
        except Exception as e:
            print(f"❌ Error getting user by code: {e}")
            return None

# --- ربات اصلی ---
class AdvancedBot:
    def __init__(self, token, group_id):
        self.token = token
        self.group_id = int(group_id)
        self.db = PostgresDB() # استفاده از دیتابیس جدید
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
        
        message_for_worker = f"⬇️ NEW JOB\nURL: {url}\nCODE: {code}"
        
        try:
            await context.bot.send_message(chat_id=self.group_id, text=message_for_worker)
            response_text = f"✅ **درخواست شما ثبت شد!**\n\n🏷️ **کد پیگیری:** `{code}`"
            await update.message.reply_text(response_text, parse_mode='Markdown')
            print(f"✅ Job {code} for user {user.id} sent to worker group.")
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
            print(f"✅ File with code {code} sent to user {user_id}.")
        except Forbidden:
            print(f"❌ User {user_id} has blocked the bot.")
        except Exception as e:
            print(f"❌ Error sending file to user: {e}")

    def run(self):
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_url))
        self.app.add_handler(MessageHandler(
            (filters.VIDEO | filters.Document.ALL) & filters.Chat(self.group_id) & filters.CAPTION,
            self.handle_group_files
        ))
        print("🚀 Bot is running with PostgreSQL...")
        self.app.run_polling()

if __name__ == "__main__":
    bot = AdvancedBot(token=BOT_TOKEN, group_id=GROUP_ID)
    bot.run()
