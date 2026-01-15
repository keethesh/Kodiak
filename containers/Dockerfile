# Kodiak Toolbox Container
# Based on Kali Linux with comprehensive security testing tools
# This container provides all security tools; the Kodiak agent orchestrates tool execution

FROM kalilinux/kali-rolling:latest

LABEL maintainer="Kodiak Team <team@kodiak-pentest.com>"
LABEL description="Kodiak Security Toolbox - AI-Powered Penetration Testing Environment"

# Environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV KODIAK_SANDBOX_MODE=true
ENV PATH="/home/kodiak/go/bin:/home/kodiak/.local/bin:/home/kodiak/.npm-global/bin:$PATH"

# Update system and install essential packages
RUN apt-get update && \
    apt-get install -y kali-archive-keyring sudo && \
    apt-get update && \
    apt-get upgrade -y

# Create non-root user for security
RUN useradd -m -s /bin/bash kodiak && \
    usermod -aG sudo kodiak && \
    echo "kodiak ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Create required directories
RUN mkdir -p /home/kodiak/tools \
             /home/kodiak/wordlists \
             /home/kodiak/output \
             /workspace \
             /app && \
    chown -R kodiak:kodiak /home/kodiak /workspace /app

# ============================================================
# CORE SYSTEM PACKAGES
# ============================================================
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    # Essential tools
    wget curl git vim nano unzip tar \
    apt-transport-https ca-certificates gnupg lsb-release \
    build-essential software-properties-common \
    # Development libraries
    gcc libc6-dev pkg-config libpcap-dev libssl-dev \
    # Python environment
    python3 python3-pip python3-dev python3-venv python3-setuptools pipx \
    # Go environment
    golang-go \
    # Network utilities
    net-tools dnsutils whois iproute2 iputils-ping netcat-traditional \
    # Text processing
    jq parallel ripgrep grep less man-db procps htop \
    # Node.js
    nodejs npm \
    # System capabilities
    libcap2-bin gdb tmux \
    && apt-get clean

# ============================================================
# KALI SECURITY TOOLS
# ============================================================
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    # Network scanning
    nmap ncat ndiff masscan \
    # Web application testing
    sqlmap nuclei subfinder naabu ffuf nikto wapiti \
    # Information gathering
    whatweb wafw00f \
    # Exploitation frameworks (optional, large)
    # metasploit-framework \
    && apt-get clean

# Set network capabilities for nmap
RUN setcap cap_net_raw,cap_net_admin,cap_net_bind_service+eip $(which nmap)

# ============================================================
# GO SECURITY TOOLS (ProjectDiscovery suite)
# ============================================================
USER kodiak
WORKDIR /tmp

RUN go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest && \
    go install -v github.com/projectdiscovery/katana/cmd/katana@latest && \
    go install -v github.com/projectdiscovery/dnsx/cmd/dnsx@latest && \
    go install -v github.com/jaeles-project/gospider@latest && \
    go install -v github.com/projectdiscovery/interactsh/cmd/interactsh-client@latest && \
    go install -v github.com/tomnomnom/waybackurls@latest && \
    go install -v github.com/tomnomnom/gf@latest && \
    go install -v github.com/lc/gau/v2/cmd/gau@latest

# Update nuclei templates
RUN nuclei -update-templates

# ============================================================
# PYTHON SECURITY TOOLS
# ============================================================
RUN pipx install arjun && \
    pipx install dirsearch && \
    pipx inject dirsearch setuptools && \
    pipx install wafw00f && \
    pipx install semgrep && \
    pipx install bandit && \
    pipx install jwt-tool

# ============================================================
# NODE.JS SECURITY TOOLS
# ============================================================
ENV NPM_CONFIG_PREFIX=/home/kodiak/.npm-global
RUN mkdir -p /home/kodiak/.npm-global && \
    npm install -g retire@latest && \
    npm install -g eslint@latest && \
    npm install -g js-beautify@latest && \
    npm install -g jshint@latest

# ============================================================
# BROWSER AUTOMATION (Playwright)
# ============================================================
USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libatspi2.0-0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libxkbcommon0 libpango-1.0-0 libcairo2 libasound2t64 \
    fonts-unifont fonts-noto-color-emoji fonts-freefont-ttf fonts-dejavu-core ttf-bitstream-vera \
    && apt-get clean

USER kodiak
RUN pip3 install --user playwright && \
    python3 -m playwright install chromium

# ============================================================
# ADDITIONAL TOOLS
# ============================================================
USER root

# TruffleHog (secret scanning)
RUN curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sh -s -- -b /usr/local/bin

# Trivy (vulnerability scanner)
RUN curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin

# ============================================================
# CLEANUP
# ============================================================
RUN apt-get autoremove -y && \
    apt-get autoclean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

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
