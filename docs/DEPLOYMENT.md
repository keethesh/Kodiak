# Deployment Guide

This guide details how to deploy Kodiak TUI for testing and production environments. Kodiak now features a modern Terminal User Interface (TUI) that provides a streamlined, keyboard-driven experience for security professionals.

## Overview

Kodiak TUI is designed for:
- **Local Development**: Run directly on your workstation
- **Remote Servers**: Deploy on VPS/cloud instances with terminal access
- **Containerized Environments**: Docker support for consistent deployments
- **Team Environments**: Shared database with multiple TUI instances

## Prerequisites

### System Requirements
- **Python 3.11+**
- **PostgreSQL 12+** (or Docker for easy setup)
- **Terminal Emulator** with Unicode support
- **LLM API Key** (Gemini, OpenAI, Claude, etc.)

### Supported Platforms
- ✅ **Linux** (Ubuntu 20.04+, Debian 11+, CentOS 8+)
- ✅ **macOS** (10.15+)
- ✅ **Windows** (Windows 10+ with WSL2 recommended)

## Installation Methods

### Method 1: Poetry (Recommended for Development)

```bash
# Clone repository
git clone https://github.com/yourusername/kodiak.git
cd kodiak

# Install with Poetry
poetry install

# Activate virtual environment
poetry shell
```

### Method 2: pip Installation

```bash
# Clone repository
git clone https://github.com/yourusername/kodiak.git
cd kodiak

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .
```

### Method 3: Docker (Recommended for Production)

```bash
# Clone repository
git clone https://github.com/yourusername/kodiak.git
cd kodiak

# Start database
docker-compose up -d db

# Build and run Kodiak
docker-compose up --build kodiak
```

## Configuration

### 1. LLM Provider Setup

#### Interactive Configuration (Recommended)
```bash
kodiak config
```

#### Manual Configuration
Create a `.env` file in the project root:

```bash
# Gemini (Recommended)
KODIAK_LLM_PROVIDER=gemini
KODIAK_LLM_MODEL=gemini/gemini-1.5-pro
GOOGLE_API_KEY=your_google_api_key_here

# Database Configuration
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_DB=kodiak_db
POSTGRES_USER=kodiak
POSTGRES_PASSWORD=secure_password_here

# Application Settings
KODIAK_DEBUG=false
KODIAK_LOG_LEVEL=INFO
KODIAK_MAX_AGENTS=5
```

### 2. Database Setup

#### Option A: Docker (Easiest)
```bash
# Start PostgreSQL container
docker-compose up -d db

# Initialize database
kodiak init
```

#### Option B: Local PostgreSQL
```bash
# Install PostgreSQL (Ubuntu/Debian)
sudo apt update
sudo apt install postgresql postgresql-contrib

# Create database and user
sudo -u postgres psql
CREATE DATABASE kodiak_db;
CREATE USER kodiak WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE kodiak_db TO kodiak;
\q

# Initialize Kodiak database
kodiak init
```

### 3. Verify Installation
```bash
# Check version
kodiak version

# Test configuration
kodiak config --help

# Launch TUI
kodiak
```

## Production Deployment

### VPS/Cloud Server Deployment

#### 1. Server Setup (Ubuntu 22.04 LTS)
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3.11 python3.11-venv python3-pip postgresql postgresql-contrib git

# Create kodiak user
sudo useradd -m -s /bin/bash kodiak
sudo usermod -aG sudo kodiak
```

#### 2. Database Configuration
```bash
# Configure PostgreSQL
sudo -u postgres psql
CREATE DATABASE kodiak_db;
CREATE USER kodiak WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE kodiak_db TO kodiak;
ALTER USER kodiak CREATEDB;
\q

# Configure PostgreSQL for network access (if needed)
sudo nano /etc/postgresql/14/main/postgresql.conf
# Uncomment: listen_addresses = 'localhost'

sudo nano /etc/postgresql/14/main/pg_hba.conf
# Add: local   kodiak_db   kodiak   md5

sudo systemctl restart postgresql
```

#### 3. Application Deployment
```bash
# Switch to kodiak user
sudo su - kodiak

# Clone and setup
git clone https://github.com/yourusername/kodiak.git
cd kodiak
python3.11 -m venv venv
source venv/bin/activate
pip install -e .

# Configure environment
cp .env.example .env
nano .env  # Add your configuration

# Initialize database
kodiak init

# Test installation
kodiak version
```

#### 4. Process Management with systemd
Create a systemd service for persistent operation:

```bash
sudo nano /etc/systemd/system/kodiak.service
```

```ini
[Unit]
Description=Kodiak TUI Security Testing Suite
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=kodiak
Group=kodiak
WorkingDirectory=/home/kodiak/kodiak
Environment=PATH=/home/kodiak/kodiak/venv/bin
ExecStart=/home/kodiak/kodiak/venv/bin/kodiak
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable kodiak
sudo systemctl start kodiak

# Check status
sudo systemctl status kodiak
```

### Docker Production Deployment

#### 1. Production Docker Compose
Create `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: kodiak_db
      POSTGRES_USER: kodiak
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
    restart: unless-stopped
    networks:
      - kodiak-network

  kodiak:
    build: .
    environment:
      - POSTGRES_SERVER=db
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
      - KODIAK_LLM_PROVIDER=gemini
      - KODIAK_LLM_MODEL=gemini/gemini-1.5-pro
    depends_on:
      - db
    restart: unless-stopped
    networks:
      - kodiak-network
    stdin_open: true
    tty: true

volumes:
  postgres_data:

networks:
  kodiak-network:
    driver: bridge
```

#### 2. Production Environment
```bash
# Create production environment file
cat > .env.prod << EOF
POSTGRES_PASSWORD=your_very_secure_password
GOOGLE_API_KEY=your_google_api_key
EOF

# Deploy
docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d

# Initialize database
docker-compose -f docker-compose.prod.yml exec kodiak kodiak init
```

## Security Considerations

### Network Security
```bash
# Firewall configuration (UFW)
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow from YOUR_IP_ADDRESS to any port 5432  # PostgreSQL (if remote)
sudo ufw enable
```

### Access Control
- **SSH Key Authentication**: Disable password authentication
- **VPN Access**: Use VPN for remote access to production instances
- **Database Security**: Use strong passwords and restrict network access
- **API Key Security**: Store API keys securely, rotate regularly

### Monitoring and Logging
```bash
# View application logs
journalctl -u kodiak -f

# Database logs
sudo tail -f /var/log/postgresql/postgresql-14-main.log

# Docker logs
docker-compose logs -f kodiak
```

## Backup and Recovery

### Database Backup
```bash
# Create backup script
cat > /home/kodiak/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/home/kodiak/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# Database backup
pg_dump -h localhost -U kodiak kodiak_db > $BACKUP_DIR/kodiak_db_$DATE.sql

# Keep only last 7 days
find $BACKUP_DIR -name "kodiak_db_*.sql" -mtime +7 -delete
EOF

chmod +x /home/kodiak/backup.sh

# Add to crontab
crontab -e
# Add: 0 2 * * * /home/kodiak/backup.sh
```

### Recovery
```bash
# Restore from backup
psql -h localhost -U kodiak kodiak_db < /home/kodiak/backups/kodiak_db_YYYYMMDD_HHMMSS.sql
```

## Troubleshooting

### Common Issues

#### Database Connection Issues
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Test connection
psql -h localhost -U kodiak kodiak_db

# Check logs
sudo tail -f /var/log/postgresql/postgresql-14-main.log
```

#### TUI Display Issues
```bash
# Check terminal capabilities
echo $TERM
tput colors

# Test Unicode support
python -c "print('✅ Unicode test: 🐻 🔍 📊')"

# Update terminal (if needed)
sudo apt install -y ncurses-term
```

#### Performance Issues
```bash
# Check system resources
htop
df -h
free -h

# Check database performance
psql -U kodiak kodiak_db -c "SELECT * FROM pg_stat_activity;"
```

### Getting Help
- **GitHub Issues**: [Report bugs and issues](https://github.com/yourusername/kodiak/issues)
- **Discussions**: [Community support](https://github.com/yourusername/kodiak/discussions)
- **Documentation**: [Full documentation](https://kodiak-docs.org)

## Updating

### Standard Update
```bash
cd kodiak
git pull origin main
pip install -e .  # or poetry install
kodiak init  # Apply any database migrations
```

### Docker Update
```bash
cd kodiak
git pull origin main
docker-compose down
docker-compose up --build -d
```

## Multi-User Setup

For team environments, multiple users can connect to the same database:

### Shared Database Configuration
```bash
# Each user's .env file
POSTGRES_SERVER=shared-db-server.example.com
POSTGRES_PORT=5432
POSTGRES_DB=kodiak_shared
POSTGRES_USER=kodiak_user_1  # Unique per user
POSTGRES_PASSWORD=user_specific_password
```

### User Management
```sql
-- Create additional users
CREATE USER kodiak_user_2 WITH PASSWORD 'password2';
GRANT ALL PRIVILEGES ON DATABASE kodiak_shared TO kodiak_user_2;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO kodiak_user_2;
```

This allows multiple security professionals to collaborate while maintaining separate scan contexts and agent sessions.
