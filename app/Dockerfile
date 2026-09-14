FROM python:3.12.7-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download Pico CSS at build time so the app works without external network at runtime
RUN mkdir -p static && \
    python -c "import urllib.request; urllib.request.urlretrieve('https://cdn.jsdelivr.net/npm/@picocss/pico@2.0.6/css/pico.min.css', 'static/pico.min.css')"

COPY . .

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
