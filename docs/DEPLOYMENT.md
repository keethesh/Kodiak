# Deployment Guide

This guide details how to deploy Kodiak to a Linux VPS (Ubuntu/Debian recommended) for testing and production. Kodiak is designed as a security tool without authentication requirements, making deployment straightforward for individual security professionals and teams.

## Prerequisites

On your VPS, ensure you have:
1.  **Git**: `sudo apt install git`
2.  **Docker Engine**: [Install Guide](https://docs.docker.com/engine/install/ubuntu/)
3.  **Docker Compose**: usually included with Docker Desktop or `sudo apt install docker-compose-plugin`

## Step-by-Step Deployment

### 1. Clone the Repository
Connect to your VPS via SSH and clone the repository:

```bash
# Replace with your actual repo URL
git clone https://github.com/keethesh/Kodiak.git
cd Kodiak
```

### 2. Configure Environment (Optional)
The default configuration works out-of-the-box for testing, but you can create a `.env` file in the `backend/` directory if you need to override settings (like LLM API keys).

```bash
cd backend
nano .env
# Add: GOOGLE_API_KEY=your_google_api_key
# Add: KODIAK_LLM_PROVIDER=gemini
# Add: KODIAK_LLM_MODEL=gemini/gemini-1.5-pro
cd ..
```

### 3. Start the Engine
Run the entire stack (PostgreSQL + Backend + Frontend) in detached mode:

```bash
docker-compose up --build -d
```

### 4. Verify Installation

#### Check Containers
Ensure all containers are running:
```bash
docker-compose ps
```

#### Check Logs
Follow the logs to see the startup process:
```bash
docker-compose logs -f
```

#### Access the Application
- **Frontend**: `http://<YOUR_VPS_IP>:3000` (Main Interface)
- **Backend API**: `http://<YOUR_VPS_IP>:8000/docs` (Swagger UI)

> **Note**: Ensure ports **3000** and **8000** are open in your VPS firewall.

## Security Considerations

Since Kodiak operates without authentication, consider these security measures for production deployments:

### Network Security
```bash
# Restrict access to specific IPs using iptables
sudo iptables -A INPUT -p tcp --dport 3000 -s YOUR_IP_ADDRESS -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 8000 -s YOUR_IP_ADDRESS -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 3000 -j DROP
sudo iptables -A INPUT -p tcp --dport 8000 -j DROP
```

### Reverse Proxy with TLS
Consider using nginx or Traefik with Let's Encrypt for TLS termination:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Updating

When you push new code to GitHub, update your VPS:

```bash
cd Kodiak
git pull origin main
docker-compose up --build -d
```

## Production Hardening

For production deployments, consider:

1. **Database Security**: Use strong PostgreSQL passwords and restrict database access
2. **Container Security**: Run containers with non-root users where possible
3. **Log Management**: Configure log rotation and centralized logging
4. **Backup Strategy**: Implement regular database backups
5. **Monitoring**: Set up monitoring for container health and resource usage
