FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    POETRY_VERSION=1.7.1 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    # Add poetry and venv to PATH
    PATH="$POETRY_HOME/bin:/app/.venv/bin:$PATH"

# Install system dependencies and Tools (Nmap, etc.)
# We install standard tools here so the "LocalExecutor" (which is local to the container) finds them.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        netcat-traditional \
        nmap \
        build-essential \
        libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Set work directory
WORKDIR /app

# Copy dependency files first (for caching)
COPY pyproject.toml poetry.lock ./

# Install dependencies
RUN poetry install --no-root --only main

# Copy application code
COPY . .

# Install the app itself
RUN poetry install --only main

# Expose port
EXPOSE 8000

# Copy start script if needed, or just CMD
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
