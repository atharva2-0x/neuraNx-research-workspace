FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# Install dependencies with timeout and retries so apt never hangs indefinitely
RUN apt-get update -o Acquire::Retries=3 \
    && apt-get install -y --no-install-recommends -o Acquire::Retries=3 -o Acquire::http::Timeout="30" \
       tesseract-ocr \
    || echo "Tesseract installation skipped; native PDF parsing will be used" \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml requirements.txt ./
COPY app ./app
RUN pip install --no-cache-dir '.[local]'
COPY ui ./ui
RUN useradd --create-home analyst && mkdir -p /app/data/input /app/data/processed && chown -R analyst:analyst /app
USER analyst
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
