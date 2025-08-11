# تمام بخش‌های دیگر کد از فایل main_bot.py قبلی شما کپی شود
# ...

class AdvancedBot:
    # ... (تمام توابع دیگر مثل قبل هستند)

    async def handle_group_files(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or update.message.message_thread_id != self.order_topic_id or "CODE:" not in update.message.caption: return
        try:
            caption_lines = update.message.caption.split('\n')
            info = {line.split(":", 1)[0].strip(): line.split(":", 1)[1].strip() for line in caption_lines if ":" in line}
            
            code, size = info.get("CODE"), int(info.get("SIZE", 0))
            user_id = self.db.get_user_by_code(code)
            if not user_id: return
            
            self.db.update_job_on_complete(code, 'completed', size)
            
            # --- منطق جدید برای مدیریت کپشن طولانی ---
            
            decoded_caption = ""
            if "CAPTION" in info:
                try:
                    decoded_caption = base64.b64decode(info["CAPTION"]).decode('utf-8').strip()
                except Exception as e:
                    logger.warning(f"Could not decode caption for code {code}: {e}")

            # فوتر دائمی ربات
            footer = ("\n\n—————————————————\n"
                      "🍭 Download by [CokaDownloader](https://t.me/parsvip0_bot?start=0)")

            item_info_str = next((line for line in caption_lines if line.startswith("✅ Uploaded")), "")
            match = re.search(r'\((\d+)/(\d+)\)', item_info_str)
            slide_info = f"\n\nاسلاید {match.group(1)} از {match.group(2)}" if match else ""

            # تابع داخلی برای ارسال فایل
            async def send_media_to_user(media_type, file_id, caption):
                if media_type == 'video': await context.bot.send_video(chat_id=user_id, video=file_id, caption=caption, parse_mode='Markdown')
                elif media_type == 'audio': await context.bot.send_audio(chat_id=user_id, audio=file_id, caption=caption, parse_mode='Markdown')
                elif media_type == 'photo': await context.bot.send_photo(chat_id=user_id, photo=file_id, caption=caption, parse_mode='Markdown')
                elif media_type == 'document': await context.bot.send_document(chat_id=user_id, document=file_id, caption=caption, parse_mode='Markdown')

            media_type = 'video' if update.message.video else 'audio' if update.message.audio else 'photo' if update.message.photo else 'document'
            file_id = update.message.video.file_id if update.message.video else update.message.audio.file_id if update.message.audio else update.message.photo[-1].file_id if update.message.photo else update.message.document.file_id

            # تصمیم‌گیری بر اساس طول کپشن
            if len(decoded_caption) > 1000:
                # اگر کپشن طولانی است: فایل با کپشن کوتاه + ارسال کپشن کامل در پیام جدا
                short_caption = slide_info + footer
                await send_media_to_user(media_type, file_id, short_caption.strip())
                
                # ارسال کپشن طولانی در پیام‌های جداگانه (برای پیام‌های بالای ۴۰۹۶ کاراکتر)
                for i in range(0, len(decoded_caption), 4096):
                    await context.bot.send_message(chat_id=user_id, text=decoded_caption[i:i+4096], parse_mode='Markdown', disable_web_page_preview=True)
            else:
                # اگر کپشن کوتاه است: ارسال فایل با کپشن کامل
                full_caption = decoded_caption + slide_info + footer
                await send_media_to_user(media_type, file_id, full_caption.strip())

        except Exception as e:
            logger.error(f"❌ Error processing group file: {e}", exc_info=True)
    
    # ... (بقیه توابع کلاس بدون تغییر هستند)
