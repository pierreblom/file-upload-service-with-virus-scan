# Production Deployment Guide

This guide covers deploying the File Upload Service with Virus Scan in a production environment.

## Prerequisites

- Docker and Docker Compose
- Domain name with SSL certificate
- (Optional) AWS account for S3 storage

## Production Configuration

### 1. Environment Configuration

Create a production `.env` file:

```bash
# Production API Configuration
APP_NAME="File Upload Service"
APP_VERSION="1.0.0"
DEBUG=false

# Server Configuration
HOST=0.0.0.0
PORT=8000

# Redis Configuration (use managed Redis in production)
REDIS_URL=redis://your-redis-server:6379/0

# Celery Configuration
CELERY_BROKER_URL=redis://your-redis-server:6379/0
CELERY_RESULT_BACKEND=redis://your-redis-server:6379/0

# ClamAV Configuration
CLAMAV_HOST=clamav
CLAMAV_PORT=3310
CLAMAV_TIMEOUT=120

# Storage Configuration - Use S3 for production
STORAGE_TYPE=s3
MAX_FILE_SIZE=524288000  # 500MB

# S3 Configuration
AWS_ACCESS_KEY_ID=your_production_access_key
AWS_SECRET_ACCESS_KEY=your_production_secret_key
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-production-bucket

# Security Configuration - CHANGE THIS!
SECRET_KEY=generate-a-very-long-random-secure-key-here
ACCESS_TOKEN_EXPIRE_MINUTES=60

# File Processing Configuration
VIRUS_SCAN_TIMEOUT=600  # 10 minutes for larger files
DOWNLOAD_LINK_EXPIRE_HOURS=24
```

### 2. Docker Compose Production Override

Create `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  app:
    restart: always
    environment:
      - DEBUG=false
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.upload-service.rule=Host(`your-domain.com`)"
      - "traefik.http.routers.upload-service.tls=true"
      - "traefik.http.routers.upload-service.tls.certresolver=letsencrypt"

  worker:
    restart: always
    deploy:
      replicas: 3
    environment:
      - DEBUG=false

  redis:
    restart: always
    command: redis-server --appendonly yes --requirepass your_redis_password
    volumes:
      - redis_data:/data
      - ./redis.conf:/usr/local/etc/redis/redis.conf

  clamav:
    restart: always
    volumes:
      - clamav_db:/var/lib/clamav

  # Remove flower in production or secure it
  flower:
    environment:
      - FLOWER_BASIC_AUTH=admin:secure_password_here
```

### 3. Nginx Reverse Proxy

Create `nginx.conf`:

```nginx
upstream upload_service {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/ssl/cert.pem;
    ssl_certificate_key /path/to/ssl/key.pem;

    client_max_body_size 500M;
    proxy_read_timeout 600s;

    location / {
        proxy_pass http://upload_service;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /upload {
        proxy_pass http://upload_service;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Increase timeouts for large file uploads
        proxy_read_timeout 1800s;
        proxy_send_timeout 1800s;
    }
}
```

### 4. Security Hardening

#### A. Docker Security

```bash
# Run containers as non-root user
docker-compose exec app id
# Should show: uid=1000(app) gid=1000(app)

# Scan images for vulnerabilities
docker scout cves upload-service_app
```

#### B. Network Security

```bash
# Create isolated network
docker network create upload_service_network

# Update docker-compose to use custom network
networks:
  upload_service_network:
    external: true
```

#### C. File System Security

```bash
# Set proper permissions
chmod 700 uploads/
chown -R 1000:1000 uploads/

# Enable SELinux/AppArmor if available
```

### 5. Monitoring and Logging

#### A. Application Logs

```yaml
# Add to docker-compose.prod.yml
services:
  app:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

#### B. Health Checks

```yaml
# Add to services in docker-compose.prod.yml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

#### C. Monitoring with Prometheus

Create `prometheus.yml`:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'upload-service'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: /metrics
```

### 6. Backup Strategy

#### A. Redis Backup

```bash
# Automated Redis backup
docker exec upload_service_redis redis-cli BGSAVE

# Copy backup
docker cp upload_service_redis:/data/dump.rdb ./backups/
```

#### B. S3 File Backup

```bash
# S3 Cross-region replication or backup to Glacier
aws s3api put-bucket-replication \
  --bucket your-production-bucket \
  --replication-configuration file://replication.json
```

### 7. Deployment Commands

```bash
# Deploy to production
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Scale workers based on load
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale worker=5

# Rolling updates
docker-compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps app worker

# Check service status
docker-compose ps
curl https://your-domain.com/health
```

### 8. Maintenance Tasks

#### A. Regular Updates

```bash
# Update virus definitions (ClamAV updates automatically)
docker-compose exec clamav freshclam

# Update application
git pull
docker-compose build
docker-compose up -d
```

#### B. Cleanup Tasks

```bash
# Clean old uploads (if using local storage)
find ./uploads -type f -mtime +30 -delete

# Clean Docker images
docker system prune -a

# Clean Redis expired keys (automatic)
docker-compose exec redis redis-cli --scan --pattern "file:*" | head -10
```

### 9. Performance Tuning

#### A. Redis Optimization

```bash
# In redis.conf
maxmemory 1gb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
```

#### B. Worker Optimization

```bash
# Scale workers based on CPU cores
WORKERS=$(nproc)
docker-compose up -d --scale worker=$WORKERS
```

#### C. ClamAV Optimization

```bash
# Increase scan limits for large files
echo "MaxScanSize 500M" >> clamav.conf
echo "MaxFileSize 500M" >> clamav.conf
```

### 10. Troubleshooting Production Issues

#### A. Common Issues

```bash
# Check all service logs
docker-compose logs --tail=100

# Check specific service
docker-compose logs clamav

# Check Redis connection
docker-compose exec redis redis-cli ping

# Check ClamAV status
docker-compose exec clamav clamdscan --ping
```

#### B. Performance Monitoring

```bash
# Monitor resource usage
docker stats

# Check API response times
curl -w "@curl-format.txt" -o /dev/null -s "https://your-domain.com/health"
```

### 11. Disaster Recovery

#### A. Backup Verification

```bash
# Test Redis backup restore
docker run --rm -v redis_data:/data redis:7-alpine redis-server --dir /data --dbfilename dump.rdb

# Test S3 access
aws s3 ls s3://your-production-bucket/
```

#### B. Recovery Procedures

```bash
# Restore from backup
docker-compose down
docker volume rm redis_data
docker-compose up -d redis
docker cp backup/dump.rdb upload_service_redis:/data/
docker-compose restart redis
```

## Security Checklist

- [ ] Changed default SECRET_KEY
- [ ] Using HTTPS with valid SSL certificate
- [ ] Redis protected with password
- [ ] S3 bucket with proper IAM policies
- [ ] Regular security updates applied
- [ ] File size and type restrictions configured
- [ ] Rate limiting implemented (via nginx/proxy)
- [ ] Monitoring and alerting configured
- [ ] Backup and recovery tested
- [ ] Container security scanning enabled

## Performance Benchmarks

Expected performance with default configuration:
- **Upload**: 10-50 MB/s (network dependent)
- **Scan**: 5-20 MB/s (CPU dependent)
- **Download**: 50-200 MB/s (storage dependent)
- **Concurrent uploads**: 10-50 (worker dependent)

Scale workers and adjust limits based on your requirements. 