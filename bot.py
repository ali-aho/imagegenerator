import os
import time
import asyncio
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

ALLOWED_USERS = [
    7037339290
]

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def is_authorized(user_id: int) -> bool:
    return user_id in ALLOWED_USERS


class LiveProgressLogger:
    """کلاس ثبت لاگ زنده و ارسال پروگرس به تلگرام"""
    def __init__(self, loop, status_msg):
        self.loop = loop
        self.status_msg = status_msg
        self.last_update_time = 0
        self.last_text = ""

    def update_text_sync(self, text: str):
        # جلوگیری از اسپم ادیت پیام و بلاک شدن توسط تلگرام (حداقل فاصله ۱.۵ ثانیه)
        now = time.time()
        if now - self.last_update_time > 1.5 and text != self.last_text:
            self.last_update_time = now
            self.last_text = text
            asyncio.run_coroutine_threadsafe(
                self._safe_edit(text),
                self.loop
            )

    async def _safe_edit(self, text: str):
        try:
            await self.status_msg.edit_text(text, parse_mode="Markdown")
        except Exception:
            pass

    def debug(self, msg):
        logging.debug(msg)

    def info(self, msg):
        logging.info(msg)
        if any(keyword in msg.lower() for keyword in ["extracting", "downloading", "merging"]):
            self.update_text_sync(f"ℹ️ *وضعیت:* `{msg[:80]}`")

    def warning(self, msg):
        logging.warning(msg)

    def error(self, msg):
        logging.error(msg)


def download_media(url: str, output_path: str, progress_logger: LiveProgressLogger) -> dict:
    """دانلود مدیا با هوک لایو درصد دانلود"""
    
    def ytdl_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            percent = (downloaded / total * 100) if total > 0 else 0
            speed = d.get('speed', 0) or 0
            speed_mb = speed / (1024 * 1024)

            text = (
                f"📥 *در حال دانلود فایل:*\n"
                f"📊 پیشرفت: `{percent:.1f}%`\n"
                f"⚡ سرعت: `{speed_mb:.2f} MB/s`"
            )
            progress_logger.update_text_sync(text)
        elif d['status'] == 'finished':
            progress_logger.update_text_sync("⚙️ دانلود تمام شد. در حال ادغام صوت و تصویر...")

    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': os.path.join(output_path, '%(id)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'quiet': False,
        'no_warnings': False,
        'logger': progress_logger,
        'progress_hooks': [ytdl_hook],
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'web']
            }
        },
    }

    if os.path.exists("cookies.txt"):
        ydl_opts['cookiefile'] = 'cookies.txt'

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        base, _ = os.path.splitext(filename)
        final_file = f"{base}.mp4"
        if not os.path.exists(final_file):
            final_file = filename
        return {"filepath": final_file, "title": info.get("title", "media")}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ شما اجازه دسترسی به این بات را ندارید.")
        return

    await update.message.reply_text(
        "👋 سلام! لینک ویدیو رو بفرست تا زنده وضعیت دانلودش رو بهت نشون بدم."
    )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ شما اجازه دسترسی به این بات را ندارید.")
        return

    url = update.message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text("لطفاً یک لینک معتبر اینترنتی ارسال کنید.")
        return

    status_msg = await update.message.reply_text("🔍 در حال بررسی لینک و استخراج مشخصات...")

    loop = asyncio.get_running_loop()
    progress_logger = LiveProgressLogger(loop, status_msg)

    filepath = None
    try:
        result = await asyncio.to_thread(download_media, url, DOWNLOAD_DIR, progress_logger)
        filepath = result["filepath"]
        title = result["title"]

        file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
        if file_size_mb > 50:
            await status_msg.edit_text(
                f"⚠️ فایل دانلود شد اما حجم آن ({file_size_mb:.1f}MB) از سقف ۵۰ مگابایت Bot API تلگرام بیشتر است."
            )
            return

        await status_msg.edit_text("📤 در حال آپلود فایل به تلگرام...")
        with open(filepath, "rb") as video_file:
            await update.message.reply_video(
                video=video_file,
                caption=f"🎬 {title}",
                supports_streaming=True
            )

        await status_msg.delete()

    except Exception as e:
        error_detail = str(e)
        logging.error(f"Error downloading {url}: {error_detail}", exc_info=True)
        # نمایش خطای دقیق ترمینال روی پیام تلگرام برای خطایابی
        await status_msg.edit_text(
            f"❌ *خطا در پردازش ویدیو:*\n\n```\n{error_detail[:600]}\n```",
            parse_mode="Markdown"
        )

    finally:
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass


if __name__ == "__main__":
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN یافت نشد! لطفاً در متغیرهای محیطی آن را تنظیم کنید.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    print("ربات دانلودر همراه با سیستم لاگ زنده فعال شد...")
    app.run_polling()
