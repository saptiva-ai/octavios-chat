# Deployment Guide - 414.saptiva.com (Production Domain)

## Overview

This guide covers deploying the Capital 414 chat application to production with:
- ✅ Custom domain: `414.saptiva.com`
- ✅ Nginx reverse proxy
- ✅ SSL/TLS certificates (Let's Encrypt)
- ✅ Automatic certificate renewal
- ✅ Production security headers

## Prerequisites

- Server: `server.example.com` (Ubuntu 24.04 LTS)
- User: `jf` with sudo access and SSH key configured
- Domain `414.saptiva.com` DNS A record pointing to `server.example.com`
- Ports 80 and 443 open in firewall

## Architecture

```
Internet
    ↓
414.saptiva.com (HTTPS:443)
    ↓
Nginx (container)
    ├→ capital414-chat-web:3000 (Next.js)
    └→ capital414-chat-api:8001 (FastAPI)
         ├→ mongodb:27017
         ├→ redis:6379
         ├→ minio:9000
         └→ languagetool:8010
```

## Step 1: Server Setup (One-time)

The server has already been configured with:
- ✅ Docker & Docker Compose installed
- ✅ System dependencies (git, curl, jq, make)
- ✅ Project code transferred
- ✅ Environment variables configured

To verify setup:
```bash
make status-demo
```

If you need to set up a new server:
```bash
make setup-demo-server
```

## Step 2: DNS Configuration

**CRITICAL**: Before proceeding, ensure DNS is configured:

```bash
# Verify domain resolves to server IP
dig +short 414.saptiva.com
# Should return: server.example.com
```

If DNS is not configured:
1. Go to your DNS provider (e.g., Cloudflare, Route53)
2. Create an A record:
   - **Name**: `414` (or `414.saptiva.com` depending on provider)
   - **Type**: `A`
   - **Value**: `server.example.com`
   - **TTL**: `300` (5 minutes)
3. Wait for propagation (5-30 minutes)

## Step 3: Deploy Application (Without SSL first)

First, deploy the application containers WITHOUT SSL:

```bash
# 1. Build Docker images locally
cd /home/jazielflo/Proyects/capital414-chat
docker build -f apps/api/Dockerfile -t octavios-api:latest --target production apps/api
docker build -f apps/web/Dockerfile -t octavios-web:latest --target runner .

# 2. Deploy to server
make deploy-demo

# 3. Verify deployment
make status-demo
```

This deploys:
- MongoDB
- Redis
- MinIO
- LanguageTool
- FastAPI API
- Next.js Web

**Note**: At this point, the app is running on HTTP only (ports 3000 and 8001).

## Step 4: Configure SSL/TLS Certificates

### Option A: Automatic Setup (Recommended)

Run the SSL setup script on the server:

```bash
# SSH into server
ssh jf@server.example.com

# Navigate to project
cd /home/jf/capital414-chat

# Run SSL setup script
./scripts/setup-ssl-414.sh
```

This script will:
1. Verify DNS resolution
2. Create certificate directories
3. Generate dummy certificates
4. Start nginx
5. Obtain Let's Encrypt certificates
6. Configure automatic renewal

### Option B: Manual Setup

```bash
# SSH into server
ssh jf@server.example.com
cd /home/jf/capital414-chat

# 1. Create directories
mkdir -p data/certbot/conf
mkdir -p data/certbot/www
mkdir -p logs/nginx

# 2. Start stack with nginx (using special docker-compose)
docker compose -f infra/docker-compose.414.saptiva.com.yml up -d

# 3. Obtain certificates
docker compose -f infra/docker-compose.414.saptiva.com.yml run --rm certbot certonly --webroot \
  -w /var/www/certbot \
  --email devops@saptiva.com \
  --agree-tos \
  --no-eff-email \
  -d 414.saptiva.com

# 4. Reload nginx
docker compose -f infra/docker-compose.414.saptiva.com.yml exec nginx nginx -s reload
```

## Step 5: Deploy with Domain & SSL

Once SSL is configured, deploy the full stack:

```bash
# On your local machine
cd /home/jazielflo/Proyects/capital414-chat

# Deploy with domain configuration
make deploy-demo

# On the server, start the stack with domain config
ssh jf@server.example.com
cd /home/jf/capital414-chat
docker compose -f infra/docker-compose.414.saptiva.com.yml up -d
```

## Step 6: Verification

### Health Checks

```bash
# From local machine
make status-demo

# Expected output:
#   API: healthy
#   Web: HTTP 200
```

### Manual Verification

```bash
# Test HTTPS
curl -I https://414.saptiva.com
# Should return: HTTP/2 200

# Test API health
curl https://414.saptiva.com/api/health
# Should return: {"status":"healthy",...}

# Test SSL certificate
curl -v https://414.saptiva.com 2>&1 | grep "SSL certificate"
# Should show: Let's Encrypt certificate
```

### Browser Testing

1. Open https://414.saptiva.com in browser
2. Verify SSL lock icon (🔒) in address bar
3. Check certificate details:
   - Issued by: Let's Encrypt
   - Valid for: 414.saptiva.com
   - Expires: ~90 days from issue

### SSL Labs Test (Optional)

For comprehensive SSL analysis:
1. Go to https://www.ssllabs.com/ssltest/
2. Enter `414.saptiva.com`
3. Wait for scan completion
4. Expected grade: A or A+

## Troubleshooting

### Issue: Domain doesn't resolve

**Symptoms**: `dig 414.saptiva.com` returns no results

**Solution**:
1. Verify DNS A record exists
2. Wait for DNS propagation (use `dig +trace 414.saptiva.com`)
3. Try flushing DNS cache: `sudo resolvectl flush-caches`

### Issue: Certificate request fails

**Symptoms**: Certbot returns "DNS resolution failed"

**Solution**:
```bash
# Wait for DNS to propagate
watch -n 5 'dig +short 414.saptiva.com'

# Try staging environment first (testing)
./scripts/setup-ssl-414.sh --staging

# Once staging works, get real certificate
./scripts/setup-ssl-414.sh
```

### Issue: Nginx returns 502 Bad Gateway

**Symptoms**: HTTPS works but returns 502

**Solution**:
```bash
# Check API container is running
docker ps | grep capital414-chat-api

# Check API logs
docker logs capital414-chat-api

# Verify API health directly
docker exec capital414-chat-api curl -f http://localhost:8001/api/health
```

### Issue: SSL certificate not found

**Symptoms**: Nginx logs show "ssl_certificate" file not found

**Solution**:
```bash
# Verify certificates exist
ls -la /home/jf/capital414-chat/data/certbot/conf/live/414.saptiva.com/

# If missing, re-run certbot
docker compose -f infra/docker-compose.414.saptiva.com.yml run --rm certbot \
  certonly --webroot -w /var/www/certbot \
  --email devops@saptiva.com \
  --agree-tos \
  -d 414.saptiva.com
```

## Certificate Renewal

Certificates are automatically renewed by the `certbot` container every 12 hours.

### Manual Renewal

```bash
# SSH into server
ssh jf@server.example.com
cd /home/jf/capital414-chat

# Renew certificates
docker compose -f infra/docker-compose.414.saptiva.com.yml run --rm certbot renew

# Reload nginx
docker compose -f infra/docker-compose.414.saptiva.com.yml exec nginx nginx -s reload
```

### Check Certificate Expiration

```bash
# From local machine
echo | openssl s_client -servername 414.saptiva.com -connect 414.saptiva.com:443 2>/dev/null | \
  openssl x509 -noout -dates
```

## Makefile Commands Reference

```bash
# Server setup (one-time)
make setup-demo-server          # Install Docker, transfer code

# Deployment
make deploy-demo                # Full deployment with build
make deploy-demo-fast           # Fast deployment (skip build)
make deploy-demo-safe           # Safe deployment with backups

# Monitoring
make status-demo                # Check server health
make logs-demo                  # View all logs
make logs-demo-api              # View API logs only
make logs-demo-web              # View web logs only

# Access
make ssh-demo                   # SSH into server
```

## Security Considerations

### SSL/TLS Configuration

The nginx configuration implements:
- ✅ TLS 1.2 and 1.3 only
- ✅ Strong cipher suites (Mozilla Intermediate)
- ✅ OCSP stapling
- ✅ Security headers:
  - Strict-Transport-Security (HSTS)
  - X-Frame-Options: DENY
  - X-Content-Type-Options: nosniff
  - X-XSS-Protection
  - Referrer-Policy
  - Permissions-Policy

### Firewall Rules

Ensure only necessary ports are open:
```bash
# On server
sudo ufw status

# Should show:
# 22/tcp (SSH)
# 80/tcp (HTTP - for ACME challenge)
# 443/tcp (HTTPS)
```

### Database Access

MongoDB and Redis are NOT exposed publicly (no port bindings in production).

### MinIO Access

MinIO console (port 9001) is exposed for admin access. Restrict to VPN or whitelist IPs:
```yaml
# In docker-compose.414.saptiva.com.yml
services:
  minio:
    ports:
      - "127.0.0.1:9001:9001"  # Localhost only
```

## Production Checklist

Before going live:

- [ ] DNS A record configured and propagated
- [ ] SSL certificates obtained and validated
- [ ] Application deployed and healthy
- [ ] HTTPS redirect working (HTTP→HTTPS)
- [ ] Security headers present (check browser dev tools)
- [ ] SSL Labs grade A or better
- [ ] Database backups configured
- [ ] Monitoring/alerts configured
- [ ] Rate limiting verified
- [ ] Firewall rules configured

## Rollback Plan

If deployment fails:

```bash
# Check deployment history
make deploy-history

# Rollback to previous version
ssh jf@server.example.com
cd /home/jf/capital414-chat
./scripts/rollback.sh
```

## Support

For issues or questions:
- Check logs: `make logs-demo`
- Server status: `make status-demo`
- Documentation: `docs/deployment/`
- GitHub Issues: https://github.com/saptiva-ai/capital414-chat/issues

## Next Steps

After successful deployment:
1. Configure monitoring (Grafana/Prometheus)
2. Set up log aggregation
3. Configure backup retention policies
4. Test disaster recovery procedures
5. Document runbook for common operations
