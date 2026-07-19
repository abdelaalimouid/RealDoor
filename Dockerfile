# RealDoor API image.
#   docker build -t realdoor-api .
#   docker run -p 8000:8000 -e OPENAI_API_KEY=sk-... -v /path/to/data:/app/data realdoor-api
#
# The reference dataset is provided at runtime (mounted at /app/data or via REALDOOR_PACK),
# not baked into the image.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY realdoor ./realdoor
COPY api ./api

ENV REALDOOR_PACK=/app/data \
    TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata \
    PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
