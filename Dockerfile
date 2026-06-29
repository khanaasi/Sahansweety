FROM python:3.10-slim

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

# Hugging Face permissions issues se bachne ke liye permissions grant karein
RUN chmod -R 777 /app

EXPOSE 7860
CMD ["python", "main.py"]
