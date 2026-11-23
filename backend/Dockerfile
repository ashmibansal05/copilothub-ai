
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10

WORKDIR /app

# Copy dependency requirements first for Docker caching
COPY requirements.txt .

# Install backend and lightweight RAG dependencies
RUN pip install --timeout 300 --retries 10 -r requirements.txt

# Copy application source code
COPY . .

EXPOSE 8000

# Apply database migrations and start FastAPI
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
