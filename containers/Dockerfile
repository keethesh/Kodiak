# Kodiak Toolbox Container
# Based on Kali Linux with comprehensive security testing tools
# Optimized using multi-stage builds to significantly reduce image size

# ============================================================
# STAGE 1: GO BUILDER
# Compiles ProjectDiscovery tools to avoid adding Go toolchain to final image
# ============================================================
FROM golang:1.22-bookworm AS go-builder

ENV CGO_ENABLED=0

RUN go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest && \
    go install -v github.com/projectdiscovery/katana/cmd/katana@latest && \
    go install -v github.com/projectdiscovery/dnsx/cmd/dnsx@latest && \
    go install -v github.com/jaeles-project/gospider@latest && \
    go install -v github.com/projectdiscovery/interactsh/cmd/interactsh-client@latest && \
    go install -v github.com/tomnomnom/waybackurls@latest && \
    go install -v github.com/tomnomnom/gf@latest && \
    go install -v github.com/lc/gau/v2/cmd/gau@latest

# ============================================================
# STAGE 2: FINAL KALI IMAGE
# ============================================================
FROM kalilinux/kali-rolling:latest

LABEL maintainer="Kodiak Team <team@kodiak-pentest.com>"
LABEL description="Kodiak Security Toolbox - AI-Powered Penetration Testing Environment"

# Environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV KODIAK_SANDBOX_MODE=true
ENV PATH="/home/kodiak/go/bin:/home/kodiak/.local/bin:/home/kodiak/.npm-global/bin:$PATH"

# Create non-root user for security
RUN useradd -m -s /bin/bash kodiak && \
    usermod -aG sudo kodiak && \
    echo "kodiak ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers && \
    mkdir -p /home/kodiak/tools \
             /home/kodiak/wordlists \
             /home/kodiak/output \
             /home/kodiak/go/bin \
             /workspace \
             /app && \
    chown -R kodiak:kodiak /home/kodiak /workspace /app

# Install all apt dependencies in a single layer, clean aggressively
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    # Core system
    kali-archive-keyring sudo wget curl git unzip tar ca-certificates gnupg \
    # Python environment
    python3 python3-pip python3-venv pipx \
    # Network utilities
    dnsutils iproute2 iputils-ping \
    # Text processing
    jq parallel ripgrep grep less procps \
    # Node.js
    nodejs npm \
    # System capabilities & Kali Scanner Tools
    libcap2-bin nmap ncat ndiff masscan \
    sqlmap nuclei subfinder naabu ffuf nikto wapiti whatweb wafw00f \
    # Playwright browser dependencies (only exactly what's needed for chromium)
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libatspi2.0-0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libxkbcommon0 libpango-1.0-0 libcairo2 libasound2t64 \
    fonts-unifont fonts-noto-color-emoji fonts-freefont-ttf fonts-dejavu-core ttf-bitstream-vera && \
    # Set nmap capabilities
    setcap cap_net_raw,cap_net_admin,cap_net_bind_service+eip $(which nmap) && \
    # Clean apt caches entirely
    apt-get autoremove -y && \
    apt-get autoclean && \
    rm -rf /var/lib/apt/lists/*

# Copy compiled Go tools from builder stage
COPY --from=go-builder /go/bin/* /home/kodiak/go/bin/

# Update nuclei templates (run as kodiak to store in home dir)
USER kodiak
RUN /home/kodiak/go/bin/nuclei -update-templates

# Install Python and Node tools
USER root
RUN pipx install arjun && \
    pipx install dirsearch && \
    pipx inject dirsearch setuptools && \
    pipx install wafw00f && \
    pipx install semgrep && \
    pipx install bandit && \
    pipx install jwt-tool && \
    # Setup Node tools
    mkdir -p /home/kodiak/.npm-global && \
    npm install -g retire@latest eslint@latest js-beautify@latest jshint@latest && \
    chown -R kodiak:kodiak /home/kodiak/.npm-global && \
    # Install TruffleHog
    curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sh -s -- -b /usr/local/bin && \
    # Install Trivy
    curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin && \
    # Clean up caches
    npm cache clean --force && \
    rm -rf /root/.cache/pipx /root/.cache/pip /tmp/*

# Install Playwright Chromium specifically (avoid bulky full installs)
USER kodiak
RUN pip3 install --user playwright && \
    # Install ONLY chromium directly and delete the bloated unused package downloads
    python3 -m playwright install chromium && \
    rm -rf /home/kodiak/.cache/pip && \
    # Strip unnecessary browser binaries if they downloaded anyway
    find /home/kodiak/.cache/ms-playwright -mindepth 1 -maxdepth 1 ! -name 'chromium-*' -exec rm -rf {} +

# ============================================================
# ENTRYPOINT SETUP
# ============================================================
USER kodiak
WORKDIR /workspace

# Add tool paths to profile
RUN echo 'export PATH="/home/kodiak/go/bin:/home/kodiak/.local/bin:/home/kodiak/.npm-global/bin:$PATH"' >> /home/kodiak/.bashrc && \
    echo 'export PATH="/home/kodiak/go/bin:/home/kodiak/.local/bin:/home/kodiak/.npm-global/bin:$PATH"' >> /home/kodiak/.profile

# Copy entrypoint script
USER root
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER kodiak
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["/bin/bash"]
