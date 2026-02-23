# Kodiak Toolbox Container
# Based on Kali Linux with comprehensive security testing tools
# Optimized using multi-stage builds to significantly reduce image size

# ============================================================
# STAGE 1: GO BUILDER
# Compiles ProjectDiscovery tools to avoid adding Go toolchain to final image
# ============================================================
FROM golang:1.24-bookworm AS go-builder

ENV CGO_ENABLED=0

RUN mkdir -p /go/bin
RUN go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest || echo "Warning: Failed to install httpx"
# Katana can require CGO in newer releases; install it as a required binary.
RUN CGO_ENABLED=1 go install -v github.com/projectdiscovery/katana/cmd/katana@latest
RUN go install -v github.com/projectdiscovery/dnsx/cmd/dnsx@latest || echo "Warning: Failed to install dnsx"
RUN go install -v github.com/jaeles-project/gospider@latest || echo "Warning: Failed to install gospider"
RUN go install -v github.com/projectdiscovery/interactsh/cmd/interactsh-client@latest || echo "Warning: Failed to install interactsh"
RUN go install -v github.com/tomnomnom/waybackurls@latest || echo "Warning: Failed to install waybackurls"
RUN go install -v github.com/tomnomnom/gf@latest || echo "Warning: Failed to install gf"
RUN go install -v github.com/lc/gau/v2/cmd/gau@latest || echo "Warning: Failed to install gau"
RUN go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest

# ============================================================
# STAGE 2: FINAL KALI IMAGE
# ============================================================
FROM kalilinux/kali-rolling:latest

LABEL maintainer="Kodiak Team <team@kodiak-pentest.com>"
LABEL description="Kodiak Security Toolbox - AI-Powered Penetration Testing Environment"

# Environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV KODIAK_SANDBOX_MODE=true
ENV PATH="/root/go/bin:/root/.local/bin:/root/.npm-global/bin:$PATH"

# Install core dependencies first
RUN apt-get update --fix-missing && \
    apt-get install -y --no-install-recommends kali-archive-keyring wget curl git unzip tar ca-certificates gnupg

RUN mkdir -p /root/tools \
             /root/wordlists \
             /root/output \
             /root/go/bin \
             /workspace \
             /app



# Install Python and Networking
RUN apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv pipx \
    dnsutils iproute2 iputils-ping

# Install Text Processing and Node
RUN apt-get install -y --no-install-recommends \
    jq parallel ripgrep grep less procps \
    nodejs npm

# Install Scanner tools & libcap
RUN apt-get install -y --no-install-recommends \
    libcap2-bin nmap ncat ndiff masscan \
    sqlmap nuclei subfinder naabu ffuf nikto wapiti whatweb wafw00f \
    katana commix \
    exploitdb seclists && \
    setcap -r /usr/bin/nmap || true && \
    setcap -r /usr/lib/nmap/nmap || true

# Install Playwright browser dependencies
RUN apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libatspi2.0-0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libxkbcommon0 libpango-1.0-0 libcairo2 libasound2t64 \
    fonts-unifont fonts-noto-color-emoji fonts-freefont-ttf fonts-dejavu-core ttf-bitstream-vera

# Clean up apt caches
RUN apt-get autoremove -y && \
    apt-get autoclean && \
    rm -rf /var/lib/apt/lists/*

# Copy compiled Go tools from builder stage
COPY --from=go-builder /go/bin/* /root/go/bin/

# Update nuclei templates
RUN /root/go/bin/nuclei -update-templates

# Install Python and Node tools
RUN pipx install arjun || echo "Warning: Failed to install arjun"
RUN pipx install dirsearch || echo "Warning: Failed to install dirsearch"
RUN pipx inject dirsearch setuptools || echo "Warning: Failed to inject dirsearch setuptools"
RUN pipx install wafw00f || echo "Warning: Failed to install wafw00f"
RUN pipx install semgrep || echo "Warning: Failed to install semgrep"
RUN pipx install bandit || echo "Warning: Failed to install bandit"
RUN pipx install jwt-tool || echo "Warning: Failed to install jwt-tool"

# Setup Node tools
RUN mkdir -p /root/.npm-global && \
    npm install -g retire@latest eslint@latest js-beautify@latest jshint@latest

# Install TruffleHog and Trivy
RUN curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sh -s -- -b /usr/local/bin || echo "Warning: Failed to install trufflehog"
RUN curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin || echo "Warning: Failed to install trivy"

# Clean up caches
RUN npm cache clean --force && \
    rm -rf /root/.cache/pipx /root/.cache/pip /tmp/*

# Install Playwright Chromium specifically (avoid bulky full installs)
# Avoid --force-reinstall on Kali/apt Python because distro-managed packages
# (e.g. typing-extensions) may not have RECORD metadata for uninstall.
RUN pip3 install --break-system-packages --upgrade playwright && \
    # Install ONLY chromium directly and delete the bloated unused package downloads
    playwright install chromium && \
    rm -rf /root/.cache/pip && \
    # Strip unnecessary browser binaries if they downloaded anyway
    find /root/.cache/ms-playwright -mindepth 1 -maxdepth 1 ! -name 'chromium-*' -exec rm -rf {} +

# ============================================================
# ENTRYPOINT SETUP
# ============================================================
WORKDIR /workspace

# Add tool paths to profile
RUN echo 'export PATH="/root/go/bin:/root/.local/bin:/root/.npm-global/bin:$PATH"' >> /root/.bashrc && \
    echo 'export PATH="/root/go/bin:/root/.local/bin:/root/.npm-global/bin:$PATH"' >> /root/.profile

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Normalize and enforce required tool command names.
RUN set -eux; \
    if ! command -v katana >/dev/null 2>&1; then \
        for candidate in /root/go/bin/katana /usr/bin/katana-framework /usr/bin/katana-cli; do \
            if [ -x "$candidate" ]; then \
                ln -sf "$candidate" /usr/local/bin/katana; \
                break; \
            fi; \
        done; \
    fi; \
    if ! command -v searchsploit >/dev/null 2>&1; then \
        for candidate in /usr/share/exploitdb/searchsploit /opt/exploitdb/searchsploit; do \
            if [ -x "$candidate" ]; then \
                ln -sf "$candidate" /usr/local/bin/searchsploit; \
                break; \
            fi; \
        done; \
    fi; \
    if ! command -v searchsploit >/dev/null 2>&1; then \
        git clone --depth 1 https://github.com/offensive-security/exploitdb.git /opt/exploitdb; \
        chmod +x /opt/exploitdb/searchsploit; \
        ln -sf /opt/exploitdb/searchsploit /usr/local/bin/searchsploit; \
    fi; \
    if ! command -v commix >/dev/null 2>&1; then \
        for candidate in /usr/bin/commix.py /usr/share/commix/commix.py /opt/commix/commix.py; do \
            if [ -f "$candidate" ]; then \
                chmod +x "$candidate" || true; \
                ln -sf "$candidate" /usr/local/bin/commix; \
                break; \
            fi; \
        done; \
    fi; \
    if ! command -v commix >/dev/null 2>&1; then \
        git clone --depth 1 https://github.com/commixproject/commix.git /opt/commix; \
        chmod +x /opt/commix/commix.py; \
        ln -sf /opt/commix/commix.py /usr/local/bin/commix; \
    fi

# Fail fast if required toolbox binaries are missing.
RUN set -eux; \
    missing=0; \
    for tool in nuclei searchsploit katana commix; do \
        if ! command -v "$tool" >/dev/null 2>&1; then \
            echo "Missing required toolbox binary: $tool" >&2; \
            missing=1; \
        fi; \
    done; \
    [ "$missing" -eq 0 ]

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["/bin/bash"]
