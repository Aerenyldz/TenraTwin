# TENRA Voice Twin - Server Dockerfile
FROM python:3.11-slim

WORKDIR /app

# System dependencies for audio handling
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

EXPOSE 8008

ENV OLLAMA_URL=http://host.docker.internal:11434
ENV CALL_MODEL=hermes3:8b

CMD ["uvicorn", "server.api:app", "--host", "0.0.0.0", "--port", "8008"]
