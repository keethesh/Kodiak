# Kodiak Application Container
# This is a lightweight container for running the Kodiak TUI/API
# Security tools are in the separate Toolbox container (containers/Dockerfile)

FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TERM=xterm-256color \
    KODIAK_DB_TYPE=sqlite

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        wget \
        git \
        bash \
        less \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install UV package manager
RUN pip install uv

# Set work directory
WORKDIR /app

# Copy dependency files first (for caching)
COPY pyproject.toml ./
COPY poetry.lock* ./

# Install dependencies using UV
RUN uv pip install --system "kodiak-pentest[local]" || \
    (pip install poetry && poetry config virtualenvs.create false && poetry install --only main)

# Copy application code
COPY . .

# Create kodiak user for security
RUN useradd -m -s /bin/bash kodiak && \
    chown -R kodiak:kodiak /app

USER kodiak

# Default command launches TUI
CMD ["kodiak"]
