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
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Go Tools (Nuclei, Subfinder, Httpx) - Using binary releases for speed/stability
RUN curl -L -o nuclei.zip https://github.com/projectdiscovery/nuclei/releases/download/v3.1.8/nuclei_3.1.8_linux_amd64.zip \
    && unzip nuclei.zip \
    && mv nuclei /usr/local/bin/ \
    && rm nuclei.zip \
    && curl -L -o subfinder.zip https://github.com/projectdiscovery/subfinder/releases/download/v2.6.4/subfinder_2.6.4_linux_amd64.zip \
    && unzip subfinder.zip \
    && mv subfinder /usr/local/bin/ \
    && rm subfinder.zip \
    && curl -L -o httpx.zip https://github.com/projectdiscovery/httpx/releases/download/v1.3.9/httpx_1.3.9_linux_amd64.zip \
    && unzip httpx.zip \
    && mv httpx /usr/local/bin/ \
    && rm httpx.zip

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
