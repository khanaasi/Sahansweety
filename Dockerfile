FROM python:3.10-slim

# Install system dependencies (FFmpeg & Fonts for video processing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cache and install python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . /app

# Grant full read/write/execute permissions
RUN chmod -R 777 /app

CMD ["python", "ai_studio_code (1).py"]
