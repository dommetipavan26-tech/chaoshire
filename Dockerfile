FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend.py index.html ./
COPY chaoshire ./chaoshire

RUN useradd --create-home --uid 10001 chaoshire \
    && mkdir -p /app/data \
    && chown -R chaoshire:chaoshire /app/data
USER chaoshire

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

CMD ["sh", "-c", "python -m uvicorn backend:app --host 0.0.0.0 --port ${PORT}"]
