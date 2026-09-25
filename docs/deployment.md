# Oracle Cloud Infrastructure (OCI) Deployment Guide

This document provides step-by-step instructions for deploying the **Universal Options Market Dashboard** backend on an Oracle Cloud Compute instance (Ubuntu 22.04 / 24.04 LTS).

---

## 1. Prerequisites

1. **OCI Compute Instance**:
   - Recommended: VM.Standard.A1.Flex (4 OCPUs, 24 GB RAM - Always Free Eligible) or VM.Standard.E4.Flex.
   - Operating System: Ubuntu 22.04 / 24.04 Minimal LTS.
   - Public IP Address assigned.

2. **OCI VCN Ingress Rules**:
   Open ports in your Virtual Cloud Network Security List:
   - Port `80` (HTTP)
   - Port `443` (HTTPS)
   - Port `22` (SSH management)
   - Keep internal ports `5432` (Postgres) and `6379` (Redis) private within Docker bridge network.

---

## 2. Server Provisioning

SSH into your instance:
```bash
ssh -i ~/.ssh/id_rsa ubuntu@<YOUR_ORACLE_PUBLIC_IP>
```

Update packages and install Docker:
```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y curl git ufw fail2ban ca-certificates gnupg

# Install Docker Engine & Compose
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker ubuntu
```

Configure local firewall:
```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

---

## 3. Clone Repository & Configure Environment

```bash
git clone <YOUR_REPOSITORY_URL> options-dashboard
cd options-dashboard

# Copy example environment configuration
cp .env.example .env
nano .env
```

Configure your Angel One credentials:
```env
APP_ENV=production
PROJECT_NAME="Universal Options Market Dashboard"
API_V1_PREFIX="/api/v1"
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
TIMEZONE="Asia/Kolkata"

POSTGRES_SERVER=postgres
POSTGRES_PORT=5432
POSTGRES_DB=options_market_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=GENERATE_A_STRONG_PASSWORD

REDIS_HOST=redis
REDIS_PORT=6379

ANGEL_API_KEY="YOUR_ANGEL_ONE_SMARTAPI_KEY"
ANGEL_CLIENT_CODE="YOUR_CLIENT_CODE"
ANGEL_PASSWORD="YOUR_CLIENT_PIN"
ANGEL_TOTP_SECRET="YOUR_BASE32_TOTP_SECRET"
```

---

## 4. Launch Stack with Docker Compose

```bash
cd docker
docker compose up -d --build
```

Verify service status:
```bash
docker compose ps
docker compose logs -f backend
```

Test the live health endpoint:
```bash
curl http://localhost/health
curl http://localhost/status
```

---

## 5. Systemd Auto-Restart on Host Boot

Create `/etc/systemd/system/options-dashboard.service`:
```ini
[Unit]
Description=Universal Options Market Dashboard Stack
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/ubuntu/options-dashboard/docker
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

Enable the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable options-dashboard.service
```
