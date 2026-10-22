FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY stylelens ./stylelens
# CPU-only torch keeps the image small; the [ml] extra pulls bge-m3 / reranker support.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install ".[ml,ocr]"
COPY alembic.ini ./
COPY alembic ./alembic

EXPOSE 8000
CMD ["uvicorn", "stylelens.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
