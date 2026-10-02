import os
import asyncio
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp

# لاگ برای پیگیری وضعیت و خطاها
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# تنظیمات اصلی
BOT_TOKEN = os.getenv("BOT_TOKEN")

# لیست آیدی‌های عددی تلگرام افراد مجاز (User ID عددی نه یوزرنیم)
ALLOWED_USERS = [
    7037339290
]

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def is_authorized(user_id: int) -> bool:
    """بررسی دسترسی کاربر به ربات"""
    return user_id in ALLOWED_USERS


def download_media(url: str, output_path: str) -> dict:
    """دانلود مدیا با yt-dlp (اجرا در ترد جداگانه)"""
    ydl_opts = {
        # انتخاب کیفیت مناسب و سازگار با تلگرام
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': os.path.join(output_path, '%(id)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        # شبیه‌سازی کلاینت‌های مختلف برای دور زدن محدودیت‌ها و ربات‌یاب‌های یوتیوب
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'web']
            }
        },
    }

    # در صورت وجود فایل کوکی (برای حل قطعی بلاک آی‌پی‌های سرورها)
    if os.path.exists("cookies.txt"):
        ydl_opts['cookiefile'] = 'cookies.txt'

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        # در صورت تبدیل فرمت به mp4 نام نهایی را بررسی می‌کنیم
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
        "👋 سلام! لینک ویدیو یا صوت رو از هر سایتی (یوتیوب، اینستاگرام، تیک‌تاک و ...) بفرست تا برات دانلود و ارسال کنم."
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

    status_msg = await update.message.reply_text("⏳ در حال پردازش و دانلود مدیا...")

    filepath = None
    try:
        # اجرای عملیات سنگین دانلود در بک‌گراند بدون بلاک کردن ربات
        result = await asyncio.to_thread(download_media, url, DOWNLOAD_DIR)
        filepath = result["filepath"]
        title = result["title"]

        # بررسی محدودیت حجم تلگرام (حداکثر ۵۰ مگابایت برای بات استاندارد)
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
        logging.error(f"Error downloading {url}: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ در دریافت یا ارسال فایل خطایی رخ داد:\n`{str(e)[:100]}`", parse_mode="Markdown")

    finally:
        # حذف فایل دانلود شده برای پر نشدن حافظه سرور
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

    print("ربات دانلودر آماده به کار است...")
    app.run_polling()
