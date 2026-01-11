# Builder stage for Go tools
FROM golang:1.21-alpine AS go-builder
RUN go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
RUN go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
RUN go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest

FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
# Install system dependencies and Tools (Nmap, etc.)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        wget \
        netcat-traditional \
        nmap \
        build-essential \
        libpq-dev \
        unzip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Go Tools (Nuclei, Subfinder, Httpx) - Using binary releases for speed/stability
# Copy Go binaries from builder
COPY --from=go-builder /go/bin/nuclei /usr/local/bin/
COPY --from=go-builder /go/bin/subfinder /usr/local/bin/
COPY --from=go-builder /go/bin/httpx /usr/local/bin/

# Install Poetry via pip (simpler path management in Docker)
RUN pip install poetry==1.7.1

# Set work directory
WORKDIR /app

# Copy dependency files first (for caching)
COPY pyproject.toml poetry.lock ./

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-root --only main

# Copy application code
COPY . .

# Install the app itself
RUN poetry install --only main

# Expose port
EXPOSE 8000

# Copy start script if needed, or just CMD
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
