# 灯牌工坊 · 后端镜像
FROM python:3.11-slim

# ffmpeg：服务端渲染要它编码；chromium 用无头模式跑 canvas
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg chromium fonts-noto-cjk fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    LB_STORAGE=/data \
    CHROME_BIN=/usr/bin/chromium

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY cli ./cli

RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
