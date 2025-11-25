# Cloudflare SSL Configuration Guide

## Overview

The application `414.saptiva.com` is deployed behind Cloudflare's proxy, which handles SSL/TLS termination at the edge. This guide explains the configuration and setup.

## Current Architecture

```
User's Browser
    ↓ HTTPS (TLS 1.3)
Cloudflare Edge
    ↓ HTTP or HTTPS (depends on SSL mode)
Nginx (34.172.67.93:80)
    ↓
Application (Next.js + FastAPI)
```

## SSL Modes in Cloudflare

Cloudflare offers 4 SSL modes:

### 1. **Off** (Not Secure)
- ❌ Not recommended
- HTTP only, no encryption

### 2. **Flexible** (Basic)
- ✅ **Currently Recommended for Quick Setup**
- HTTPS to Cloudflare, HTTP to origin
- Fast deployment (no cert needed on server)
- ⚠️ Warning: Origin to Cloudflare traffic is unencrypted

### 3. **Full** (Better Security)
- HTTPS to Cloudflare, HTTPS to origin
- Requires SSL cert on server (can be self-signed)
- More secure than Flexible

### 4. **Full (Strict)** (Best Security)
- ✅ **Recommended for Production**
- HTTPS end-to-end with valid certificate
- Requires valid SSL cert on origin

## Quick Deployment (Current Setup)

### Step 1: Configure Cloudflare DNS

1. Log in to Cloudflare dashboard
2. Select domain `saptiva.com`
3. Go to **DNS** section
4. Ensure A record exists:
   ```
   Type: A
   Name: 414
   Content: 34.172.67.93
   Proxy status: Proxied (orange cloud) ✓
   TTL: Auto
   ```

### Step 2: Set SSL Mode to Flexible

1. Go to **SSL/TLS** → **Overview**
2. Set encryption mode to: **Flexible**
3. Save changes

### Step 3: Deploy Application

```bash
# From your local machine
cd /home/jazielflo/Proyects/client-project-chat
./scripts/deploy-cloudflare-414.sh
```

### Step 4: Verify Deployment

```bash
# Check server status
make status-demo

# Test HTTPS
curl -I https://414.saptiva.com

# Test API health
curl https://414.saptiva.com/api/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2025-11-04T02:00:00Z",
  "checks": {
    "database": {"status": "healthy"},
    "redis": {"status": "healthy"}
  }
}
```

## Upgrading to Full (Strict) SSL

For production, upgrade to Full (Strict) SSL for better security:

### Option A: Let's Encrypt (Free)

**Requirements:**
- Temporarily disable Cloudflare proxy (grey cloud)
- Ports 80 and 443 accessible from internet

**Steps:**

1. **Disable Cloudflare Proxy Temporarily:**
   ```
   Cloudflare Dashboard → DNS → 414 record → Click orange cloud → Grey cloud
   ```

2. **Wait for DNS propagation (2-5 minutes):**
   ```bash
   dig +short 414.saptiva.com
   # Should return: 34.172.67.93 (not Cloudflare IPs)
   ```

3. **Run SSL setup on server:**
   ```bash
   ssh jf@34.172.67.93
   cd /home/jf/client-project-chat
   ./scripts/setup-ssl-414.sh
   ```

4. **Switch to Full (Strict) SSL mode:**
   - Cloudflare → SSL/TLS → Overview → Full (strict)

5. **Re-enable Cloudflare proxy:**
   - Cloudflare → DNS → 414 record → Click grey cloud → Orange cloud

### Option B: Cloudflare Origin Certificate (Recommended)

**Advantages:**
- No need to disable proxy
- 15-year validity
- Automatic renewal

**Steps:**

1. **Generate Origin Certificate:**
   ```
   Cloudflare Dashboard → SSL/TLS → Origin Server
   → Create Certificate

   Settings:
   - Let Cloudflare generate private key
   - Hostnames: *.saptiva.com, saptiva.com
   - Validity: 15 years
   - Click: Create
   ```

2. **Copy Certificate and Key:**
   - Save `Origin Certificate` to `/tmp/origin-cert.pem`
   - Save `Private Key` to `/tmp/origin-key.pem`

3. **Install on Server:**
   ```bash
   ssh jf@34.172.67.93
   cd /home/jf/client-project-chat

   # Create SSL directory
   mkdir -p data/ssl

   # Copy certificates (from your local machine)
   scp /tmp/origin-cert.pem jf@34.172.67.93:/home/jf/client-project-chat/data/ssl/fullchain.pem
   scp /tmp/origin-key.pem jf@34.172.67.93:/home/jf/client-project-chat/data/ssl/privkey.pem

   # Secure permissions
   chmod 600 data/ssl/privkey.pem
   chmod 644 data/ssl/fullchain.pem
   ```

4. **Update Docker Compose:**
   ```bash
   # On server
   cd /home/jf/client-project-chat

   # Use the 414.saptiva.com docker-compose with SSL
   docker compose -f infra/docker-compose.414.saptiva.com.yml up -d
   ```

5. **Update Cloudflare SSL Mode:**
   ```
   Cloudflare Dashboard → SSL/TLS → Overview → Full (strict)
   ```

6. **Verify:**
   ```bash
   # Test HTTPS
   curl -I https://414.saptiva.com

   # Check certificate
   echo | openssl s_client -servername 414.saptiva.com -connect 414.saptiva.com:443 2>/dev/null | openssl x509 -noout -issuer -subject
   ```

## Additional Cloudflare Settings

### HSTS (HTTP Strict Transport Security)

Enable HSTS for additional security:

```
Cloudflare → SSL/TLS → Edge Certificates
→ HTTP Strict Transport Security (HSTS)

Settings:
- Enable HSTS: ON
- Max Age: 12 months
- Include subdomains: ON
- Preload: OFF (only enable if ready to commit)
```

### Always Use HTTPS

Force HTTPS for all connections:

```
Cloudflare → SSL/TLS → Edge Certificates
→ Always Use HTTPS: ON
```

### Minimum TLS Version

Set minimum TLS version:

```
Cloudflare → SSL/TLS → Edge Certificates
→ Minimum TLS Version: TLS 1.2
```

### Automatic HTTPS Rewrites

Enable automatic HTTPS rewrites:

```
Cloudflare → SSL/TLS → Edge Certificates
→ Automatic HTTPS Rewrites: ON
```

## Troubleshooting

### Error 521: Web Server is Down

**Cause:** Origin server not responding

**Solutions:**
1. Check if nginx container is running:
   ```bash
   ssh jf@34.172.67.93
   docker ps | grep nginx
   ```

2. Check nginx logs:
   ```bash
   docker logs client-project-chat-nginx
   ```

3. Verify port 80 is open:
   ```bash
   curl http://34.172.67.93/health
   ```

### Error 525: SSL Handshake Failed

**Cause:** SSL/TLS mismatch between Cloudflare and origin

**Solutions:**
1. Verify SSL mode in Cloudflare
2. Check origin certificate is valid
3. Ensure nginx is listening on port 443 with valid certificate

### Error 526: Invalid SSL Certificate

**Cause:** Origin certificate is not valid

**Solutions:**
1. Switch to **Full** mode (accepts self-signed certs)
2. Or install valid certificate on origin
3. Or use Cloudflare Origin Certificate

### Connection Timeout

**Cause:** Firewall blocking traffic or service not responding

**Solutions:**
1. Verify firewall allows port 80:
   ```bash
   sudo ufw status
   ```

2. Check if service is healthy:
   ```bash
   make status-demo
   ```

## Security Best Practices

1. ✅ **Use Full (Strict) SSL mode** in production
2. ✅ **Enable HSTS** with 12-month max-age
3. ✅ **Use Cloudflare Origin Certificate** for easy management
4. ✅ **Enable Always Use HTTPS**
5. ✅ **Set Minimum TLS Version to 1.2**
6. ✅ **Enable Automatic HTTPS Rewrites**
7. ✅ **Configure WAF rules** for additional security
8. ✅ **Enable Rate Limiting** in Cloudflare

## Monitoring

### Check SSL Certificate Status

```bash
# From local machine
echo | openssl s_client -servername 414.saptiva.com -connect 414.saptiva.com:443 2>/dev/null | openssl x509 -noout -dates

# Expected output:
# notBefore=Nov  4 00:00:00 2025 GMT
# notAfter=Feb  2 23:59:59 2026 GMT
```

### SSL Labs Test

Test SSL configuration:
1. Go to: https://www.ssllabs.com/ssltest/
2. Enter: `414.saptiva.com`
3. Expected grade: **A** or **A+**

### Cloudflare Analytics

Monitor traffic and security:
```
Cloudflare Dashboard → Analytics → Traffic
```

View metrics:
- Requests per second
- Bandwidth usage
- SSL/TLS version distribution
- Top countries
- Threats blocked

## Support

For Cloudflare-specific issues:
- Cloudflare Community: https://community.cloudflare.com/
- Cloudflare Support: https://support.cloudflare.com/

For application issues:
- Check logs: `make logs-demo`
- Server status: `make status-demo`
- Documentation: `docs/deployment/`
