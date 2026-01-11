# Deployment Guide

This guide details how to deploy Kodiak to a Linux VPS (Ubuntu/Debian recommended) for testing and production.

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
The default configuration works out-of-the-box for testing, but you can create a `.env` file in the `backend/` directory if you need to override secrets (like OpenAI API Key).

```bash
cd backend
nano .env
# Add: OPENAI_API_KEY=sk-...
cd ..
```

### 3. Start the Engine
Run the entire stack (PostgreSQL + Backend) in detached mode:

```bash
docker-compose up --build -d
```

### 4. Verify Installation

#### Check Containers
Ensure both `kodiak-backend` and `kodiak-db` are running:
```bash
docker-compose ps
```

#### Check Logs
Follow the logs to see the startup process:
```bash
docker-compose logs -f backend
```
You should see: `Uvicorn running on http://0.0.0.0:8000`

#### Test the API
You can test the connectivity using `curl` from the VPS:

```bash
curl http://localhost:8000/docs
```
Or open `http://<YOUR_VPS_IP>:8000/docs` in your browser (ensure port 8000 is allowed in your VPS firewall/security group).

## Updating

When you push new code to GitHub, update your VPS:

```bash
cd Kodiak
git pull origin main
docker-compose up --build -d
```
