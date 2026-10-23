# Dockerfile
# صورة تشغيل البوت (Python 3.12 + ffmpeg لدمج الصوت والصورة)

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY bot ./bot

# تشغيل بمستخدم عادي (مو root) + مجلدات الداتا والتنزيل
RUN useradd --create-home botuser \
    && mkdir -p /app/data /app/downloads \
    && chown -R botuser:botuser /app
USER botuser

CMD ["python", "-m", "bot.main"]