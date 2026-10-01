FROM python:3.11-slim

# نصب ffmpeg و پاکسازی کش پکیج‌ها
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# نصب پیش‌نیازهای پایتون
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# انتقال کدهای پروژه
COPY . .

# دستور اجرای ربات
CMD ["python", "bot.py"]
