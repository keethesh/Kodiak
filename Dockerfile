# Builder stage for Go tools
FROM golang:alpine AS go-builder
RUN go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
RUN go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
RUN go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest

FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TERM=xterm-256color \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

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
        bash \
        less \
        vim \
        # Playwright dependencies
        libnss3 \
        libnspr4 \
        libatk-bridge2.0-0 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libgbm1 \
        libxss1 \
        libasound2 \
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
COPY pyproject.toml ./
COPY poetry.lock* ./

# Configure Poetry and install dependencies
RUN poetry config virtualenvs.create false

# If poetry.lock doesn't exist, generate it and install
RUN if [ ! -f poetry.lock ]; then \
        poetry lock --no-update; \
    fi && \
    poetry install --only main --no-root

# Copy application code
COPY . .

# Install Playwright Browsers (using python -m since playwright is installed via poetry)
# Set PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 during poetry install to avoid conflicts
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
RUN poetry install --only main
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0

# Now install Playwright browsers
RUN python -m playwright install --with-deps chromium

# Default command provides shell access for TUI usage
# Use: docker-compose run --rm kodiak python -m kodiak
# Or: docker-compose exec kodiak bash
CMD ["bash"]
