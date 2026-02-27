FROM python:3.11-slim

# Install FFmpeg (required for discord.py voice/audio streaming)
# and clean up apt cache to keep the image small
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

CMD ["python", "bot.py"]
