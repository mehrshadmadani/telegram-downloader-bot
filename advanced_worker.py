#!/usr/bin/env python3
import os
import zipfile
import tempfile
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    import aiohttp
    import aiofiles
except ImportError:
    # این قسمت برای نصب پکیج‌ها در صورت نبودن آنهاست.
    # توصیه می‌شود از محیط‌های مجازی (virtual environments) استفاده کنید
    # تا از تداخل با پکیج‌های سیستمی جلوگیری شود.
    # مثال: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
    print("Installing required packages...")
    os.system("pip install aiohttp aiofiles")
    import aiohttp
    import aiofiles

CONFIG_FILE = "backup_config.json"
MAX_FILE_SIZE = 45 * 1024 * 1024  # 45MB (تلگرام حداکثر 50MB قبول میکنه)

class TelegramBackupBot:
    def __init__(self):
        self.bot_token = None
        self.admin_id = None  # اضافه شدن admin_id
        self.group_id = None # این متغیر همچنان در کانفیگ می‌ماند اما برای ارسال به پی‌وی استفاده نمی‌شود.
        self.topic_id = None # این متغیر همچنان در کانفیگ می‌ماند اما برای ارسال به پی‌وی استفاده نمی‌شود.
        self.source_dir = None
        
    def load_config(self):
        """بارگذاری تنظیمات از فایل"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    self.bot_token = config.get('bot_token')
                    self.admin_id = config.get('admin_id') # بارگذاری admin_id
                    self.group_id = config.get('group_id')
                    self.topic_id = config.get('topic_id')
                    self.source_dir = config.get('source_dir')
                    return True
            except Exception as e:
                print(f"Error loading config: {e}")
        return False
    
    def save_config(self):
        """ذخیره تنظیمات در فایل"""
        config = {
            'bot_token': self.bot_token,
            'admin_id': self.admin_id, # ذخیره admin_id
            'group_id': self.group_id,
            'topic_id': self.topic_id,
            'source_dir': self.source_dir
        }
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            print(f"✅ Configuration saved to {CONFIG_FILE}")
        except Exception as e:
            print(f"❌ Error saving config: {e}")
    
    def setup_cron_job(self):
        """تنظیم cron job برای اجرای خودکار"""
        print("\n⏰ Automatic Backup Setup")
        print("=" * 30)
        
        setup_cron = input("Do you want to setup automatic backups? (y/n): ").strip().lower()
        if setup_cron not in ['y', 'yes']:
            print("ℹ️ You can setup automatic backups later by running this script again.")
            return
        
        while True:
            try:
                minutes = input("⏱️ Enter backup interval in minutes (e.g., 15, 30, 60): ").strip()
                minutes = int(minutes)
                if minutes < 1:
                    print("❌ Interval must be at least 1 minute!")
                    continue
                break
            except ValueError:
                print("❌ Please enter a valid number!")
        
        # ساخت cron entry
        current_dir = os.path.abspath(os.getcwd())
        cron_command = f"*/{minutes} * * * * cd {current_dir} && python3 backup_bot.py --run >> backup.log 2>&1"
        
        print(f"\n📋 Cron job to be added:")
        print(f"    {cron_command}")
        
        confirm = input("\nAdd this cron job? (y/n): ").strip().lower()
        if confirm not in ['y', 'yes']:
            print("ℹ️ Cron job not added. You can add it manually later:")
            print(f"    crontab -e")
            print(f"    Add line: {cron_command}")
            return
        
        try:
            # دریافت crontab فعلی
            result = os.popen("crontab -l 2>/dev/null").read()
            
            # بررسی اگر قبلاً وجود داره
            if "backup_bot.py --run" in result:
                print("⚠️ A backup cron job already exists!")
                replace = input("Replace existing cron job? (y/n): ").strip().lower()
                if replace not in ['y', 'yes']:
                    return
                
                # حذف خط‌های قبلی
                lines = result.split('\n')
                lines = [line for line in lines if "backup_bot.py --run" not in line and line.strip()]
                result = '\n'.join(lines)
            
            # اضافه کردن خط جدید
            if result and not result.endswith('\n'):
                result += '\n'
            result += cron_command + '\n'
            
            # نوشتن crontab جدید
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp_file:
                tmp_file.write(result)
                tmp_path = tmp_file.name
            
            os.system(f"crontab {tmp_path}")
            os.unlink(tmp_path)
            
            print(f"✅ Cron job added successfully!")
            print(f"🔄 Automatic backups will run every {minutes} minute(s)")
            print("📋 To view all cron jobs: crontab -l")
            print("🗑️ To remove cron jobs: crontab -e")
            
        except Exception as e:
            print(f"❌ Failed to add cron job: {e}")
            print("Please add it manually:")
            print(f"    crontab -e")
            print(f"    Add line: {cron_command}")
    
    def get_user_input(self):
        """دریافت اطلاعات از کاربر"""
        print("🔧 Telegram Backup Bot Setup")
        print("=" * 40)
        
        # Bot Token
        while not self.bot_token:
            token = input("🤖 Enter Bot Token (from @BotFather): ").strip()
            if token and token.startswith(('bot', 'Bot')) == False:
                if ':' in token and len(token) > 20:
                    self.bot_token = token
                else:
                    print("❌ Invalid bot token format!")
            else:
                print("❌ Please enter a valid bot token!")
        
        # Admin ID (جدید)
        while not self.admin_id:
            admin_input = input("👤 Enter your Telegram User ID (Admin ID) to receive backups in private chat: ").strip()
            try:
                self.admin_id = int(admin_input)
                # یک تست ساده برای معتبر بودن آیدی
                if not (self.admin_id > 0 or self.admin_id < 0): # IDs can be negative for channels/groups
                    print("❌ Invalid Admin ID! User ID should be a non-zero integer.")
                    self.admin_id = None
                    continue
                break
            except ValueError:
                print("❌ Please enter a valid numeric Admin ID!")

        # Group ID (اختیاری - برای نگهداری در کانفیگ اما استفاده نمی‌شود)
        group_input = input("👥 Enter Group ID (optional, for future group backups, press Enter to skip): ").strip()
        if group_input:
            try:
                if group_input.startswith('-100'):
                    self.group_id = int(group_input)
                elif group_input.startswith('-'):
                    self.group_id = int(group_input)
                else:
                    self.group_id = int(f"-100{group_input}")
            except ValueError:
                print("⚠️ Invalid group ID, skipping...")
                self.group_id = None
        else:
            self.group_id = None
        
        # Topic ID (اختیاری - برای نگهداری در کانفیگ اما استفاده نمی‌شود)
        topic_input = input("📌 Enter Topic ID (optional, for future group backups, press Enter to skip): ").strip()
        if topic_input:
            try:
                self.topic_id = int(topic_input)
            except ValueError:
                print("⚠️ Invalid topic ID, skipping...")
                self.topic_id = None
        else:
            self.topic_id = None
        
        # Source Directory
        while not self.source_dir:
            current_dir = os.getcwd()
            dir_input = input(f"📁 Enter source directory (default: {current_dir}): ").strip()
            
            if not dir_input:
                self.source_dir = current_dir
            else:
                if os.path.exists(dir_input):
                    self.source_dir = os.path.abspath(dir_input)
                else:
                    print(f"❌ Directory '{dir_input}' does not exist!")
                    continue
            break
        
        print("\n✅ Configuration completed!")
        print(f"Bot Token: {self.bot_token[:10]}...")
        print(f"Admin User ID: {self.admin_id}") # نمایش admin_id
        print(f"Group ID (Saved but not used for private chat): {self.group_id if self.group_id else 'None'}")
        print(f"Topic ID (Saved but not used for private chat): {self.topic_id if self.topic_id else 'None'}")
        print(f"Source Directory: {self.source_dir}")
        
        self.save_config()
        
        # سوال برای تنظیم cron job
        self.setup_cron_job()
    
    def create_compressed_backup(self):
        """ساخت بکاپ فشرده"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # ساخت فایل موقت
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_file:
            backup_path = tmp_file.name
        
        print(f"📦 Creating backup from: {self.source_dir}")
        
        # فایل‌ها و پوشه‌هایی که نباید بکاپ بشن
        exclude_patterns = {
            '__pycache__', '.git', '.venv', 'venv', 'node_modules',
            '.pytest_cache', '.coverage', 'dist', 'build', '*.pyc',
            '*.pyo', '*.log', '*.tmp', '.DS_Store', 'Thumbs.db',
            'backup_config.json'  # فایل کانفیگ رو هم حذف میکنیم
        }
        
        total_files = 0
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
            for root, dirs, files in os.walk(self.source_dir):
                # فیلتر کردن پوشه‌ها
                dirs[:] = [d for d in dirs if not any(pattern in d for pattern in exclude_patterns)]
                
                for file in files:
                    # فیلتر کردن فایل‌ها
                    if any(file.endswith(ext) or pattern in file for pattern in exclude_patterns):
                        continue
                    
                    file_path = os.path.join(root, file)
                    arc_name = os.path.relpath(file_path, self.source_dir)
                    
                    try:
                        zipf.write(file_path, arc_name)
                        total_files += 1
                    except Exception as e:
                        print(f"⚠️ Warning: Could not backup {file_path}: {e}")
        
        # بررسی سایز فایل
        file_size = os.path.getsize(backup_path)
        size_mb = file_size / (1024 * 1024)
        
        print(f"📊 Backup created: {total_files} files, {size_mb:.2f} MB")
        
        if file_size > MAX_FILE_SIZE:
            print(f"⚠️ Warning: File size ({size_mb:.2f} MB) exceeds Telegram limit!")
            
            # سعی در فشرده‌سازی بیشتر
            print("🔧 Trying maximum compression by including essential files only...")
            os.unlink(backup_path)
            
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_file:
                backup_path = tmp_file.name
            
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_STORED) as zipf: # ZIP_STORED بدون فشرده‌سازی
                # فقط فایل‌های اصلی رو بکاپ میکنیم (شما می‌توانید این لیست را تغییر دهید)
                essential_extensions = {'.py', '.json', '.txt', '.md', '.yml', '.yaml', '.env'}
                
                for root, dirs, files in os.walk(self.source_dir):
                    dirs[:] = [d for d in dirs if d not in {'__pycache__', '.git', '.venv', 'venv'}]
                    
                    for file in files:
                        file_ext = os.path.splitext(file)[1].lower()
                        if file_ext in essential_extensions or file in {'requirements.txt', 'Dockerfile'}:
                            file_path = os.path.join(root, file)
                            arc_name = os.path.relpath(file_path, self.source_dir)
                            zipf.write(file_path, arc_name)
            
            file_size = os.path.getsize(backup_path)
            size_mb = file_size / (1024 * 1024)
            print(f"📦 Compressed backup (essential files): {size_mb:.2f} MB")
            
        return backup_path, f"backup_{timestamp}.zip"
    
    async def send_to_telegram(self, file_path, filename):
        """ارسال فایل به تلگرام"""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendDocument"
        
        # تنظیم پارامترها برای ارسال به ادمین
        data = {
            'chat_id': self.admin_id, # تغییر از group_id به admin_id
            'caption': f"🔄 Auto Backup\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n📁 {os.path.basename(self.source_dir)}"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                with open(file_path, 'rb') as f:
                    form_data = aiohttp.FormData()
                    form_data.add_field('chat_id', str(data['chat_id']))
                    form_data.add_field('caption', data['caption'])
                    
                    # topic_id حذف شد، چون برای ارسال به پی‌وی کاربرد ندارد.
                    # if self.topic_id:
                    #     form_data.add_field('message_thread_id', str(self.topic_id))
                    
                    form_data.add_field('document', f, filename=filename)
                    
                    print(f"📤 Uploading backup to Telegram (to Admin ID: {self.admin_id})...")
                    async with session.post(url, data=form_data) as response:
                        result = await response.json()
                        
                        if response.status == 200 and result.get('ok'):
                            print("✅ Backup sent successfully!")
                            return True
                        else:
                            error_msg = result.get('description', 'Unknown error')
                            print(f"❌ Failed to send backup: {error_msg}")
                            # پیام خطای خاص برای حالت "bot can't initiate conversation"
                            if "bot can't initiate conversation with the user" in error_msg.lower():
                                print("💡 Hint: Please start a conversation with your bot first (send /start or any message).")
                            return False
        
        except Exception as e:
            print(f"❌ Error sending backup: {e}")
            return False
    
    async def run_backup(self):
        """اجرای فرآیند بکاپ"""
        try:
            # ساخت بکاپ
            backup_path, filename = self.create_compressed_backup()
            
            # بررسی اینکه آیا admin_id تنظیم شده است
            if not self.admin_id:
                print("❌ Admin User ID is not set. Please run with --setup to configure.")
                if os.path.exists(backup_path):
                    os.unlink(backup_path) # پاک کردن فایل موقت
                return False

            # ارسال به تلگرام
            success = await self.send_to_telegram(backup_path, filename)
            
            # پاک کردن فایل موقت
            if os.path.exists(backup_path):
                os.unlink(backup_path) # این خط برای حذف فایل موقت است، اکنون فعال شده است.
                print("🗑️ Temporary backup file deleted")
            
            return success
            
        except Exception as e:
            print(f"❌ Backup failed: {e}")
            return False

def main():
    bot = TelegramBackupBot()
    
    # بررسی آرگومان‌های command line
    if len(sys.argv) > 1:
        if sys.argv[1] == '--setup':
            bot.get_user_input()
            return
        elif sys.argv[1] == '--run':
            if not bot.load_config():
                print("❌ No configuration found! Run with --setup first.")
                return
        else:
            print("Usage:")
            print("  python3 backup_bot.py --setup    (Initial setup)")
            print("  python3 backup_bot.py --run      (Run backup)")
            return
    
    # اگر کانفیگ وجود نداره، راه‌اندازی اولیه
    if not bot.load_config():
        print("🔧 First time setup required...")
        bot.get_user_input()
    
    # اجرای بکاپ
    print("\n🚀 Starting backup process...")
    success = asyncio.run(bot.run_backup())
    
    if success:
        print("🎉 Backup completed successfully!")
    else:
        print("💥 Backup failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
