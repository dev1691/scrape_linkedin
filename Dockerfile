FROM python:3.11-slim

# Install dependencies for Chromium + basic tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    gnupg \
    wget \
    unzip \
    fonts-liberation \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    xvfb \
    procps \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Ensure consistent paths (some distros have /usr/bin/chromium-browser)
RUN if [ -f /usr/bin/chromium ]; then ln -sf /usr/bin/chromium /usr/bin/chromium-browser || true; \
    elif [ -f /usr/bin/chromium-browser ]; then ln -sf /usr/bin/chromium-browser /usr/bin/chromium || true; fi

WORKDIR /app

# Copy requirements and install
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy app code
COPY app.py /app/app.py

# Create directories for output and logs (mounted in docker-compose)
RUN mkdir -p /app/output /app/logs

VOLUME ["/app/output", "/app/logs"]

ENV HEADLESS=true
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV PYTHONUNBUFFERED=1

# Run uvicorn for FastAPI
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
