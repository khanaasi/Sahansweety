FROM python:3.10-slim

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

# Hugging Face permissions issues se bachne ke liye full permission grant karein
RUN chmod -R 777 /app

# Hugging Face default port 7860 expose karein
EXPOSE 7860
CMD ["python", "main.py"]
