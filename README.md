# File Upload Service with Virus Scan

A production-ready file upload service with asynchronous virus scanning using ClamAV. Built with FastAPI, Celery, Redis, and supports both local and S3 storage.

## Features

✅ **Secure File Upload** - Upload files via REST API with validation  
✅ **Asynchronous Virus Scanning** - Uses ClamAV for malware detection  
✅ **Flexible Storage** - Supports both local filesystem and AWS S3  
✅ **Secure Downloads** - Time-limited download links with JWT tokens  
✅ **File Management** - Complete CRUD operations for files  
✅ **Real-time Status** - Track upload and scan progress  
✅ **Production Ready** - Docker deployment, monitoring, logging  

## Tech Stack

- **FastAPI** - Modern, fast web framework for building APIs
- **Celery** - Distributed task queue for async processing
- **Redis** - Message broker and metadata storage
- **ClamAV** - Open-source antivirus engine
- **AWS S3** - Cloud storage (optional)
- **Docker** - Containerization and deployment

## Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd upload-service
cp .env.example .env
# Edit .env with your configuration
```

### 2. Run with Docker (Recommended)

```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f app
```

The service will be available at:
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Flower (Task Monitor)**: http://localhost:5555

### 3. Manual Setup (Development)

```bash
# Install dependencies
pip install -r requirements.txt

# Start Redis
redis-server

# Start ClamAV
# On macOS: brew install clamav && clamd
# On Ubuntu: sudo apt-get install clamav-daemon

# Start Celery worker
celery -A app.tasks.virus_scan worker --loglevel=info

# Start FastAPI app
uvicorn app.main:app --reload
```

## API Documentation

### Upload File

```bash
POST /upload
Content-Type: multipart/form-data

curl -X POST "http://localhost:8000/upload" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@example.pdf"
```

**Response:**
```json
{
  "file_id": "123e4567-e89b-12d3-a456-426614174000",
  "filename": "example.pdf",
  "file_size": 1024000,
  "upload_timestamp": "2023-12-01T10:30:00",
  "scan_status": "pending",
  "task_id": "celery-task-id"
}
```

### Check File Status

```bash
GET /files/{file_id}/status

curl "http://localhost:8000/files/123e4567-e89b-12d3-a456-426614174000/status"
```

**Response:**
```json
{
  "file_info": {
    "file_id": "123e4567-e89b-12d3-a456-426614174000",
    "filename": "example.pdf",
    "file_size": 1024000,
    "content_type": "application/pdf",
    "upload_timestamp": "2023-12-01T10:30:00",
    "scan_status": "clean",
    "scan_result": {
      "status": "clean",
      "scan_duration": 2.5,
      "engine_version": "ClamAV 0.103.8"
    },
    "download_count": 0
  },
  "message": "File is clean and safe to download."
}
```

### Generate Download Link

```bash
GET /files/{file_id}/download-link

curl "http://localhost:8000/files/123e4567-e89b-12d3-a456-426614174000/download-link"
```

**Response:**
```json
{
  "download_url": "/download/eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "expires_at": "2023-12-02T10:30:00",
  "file_info": { ... }
}
```

### Download File

```bash
GET /download/{token}

curl "http://localhost:8000/download/eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..." \
  --output downloaded-file.pdf
```

### Scan Status Values

- `pending` - File uploaded, scan not started
- `scanning` - Actively being scanned  
- `clean` - No threats detected, safe to download
- `infected` - Virus/malware detected, download blocked
- `error` - Scan failed due to technical issue

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `STORAGE_TYPE` | Storage backend: `local` or `s3` | `local` |
| `MAX_FILE_SIZE` | Maximum file size in bytes | `104857600` (100MB) |
| `ALLOWED_EXTENSIONS` | Comma-separated file extensions | See config.py |
| `VIRUS_SCAN_TIMEOUT` | Max scan time in seconds | `300` |
| `DOWNLOAD_LINK_EXPIRE_HOURS` | Download link validity | `24` |

### AWS S3 Configuration

For S3 storage, set these environment variables:

```bash
STORAGE_TYPE=s3
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-bucket-name
```

## Deployment

### Production Docker Deployment

```bash
# Build and deploy
docker-compose -f docker-compose.yml up -d

# Scale workers
docker-compose up -d --scale worker=4

# Update configuration
vi .env
docker-compose restart app worker
```

### Health Monitoring

```bash
# Check service health
curl http://localhost:8000/health

# Monitor Celery tasks
# Visit http://localhost:5555 (Flower dashboard)

# Check logs
docker-compose logs -f app worker
```

### Security Considerations

1. **Change Secret Key**: Generate a strong `SECRET_KEY` for JWT tokens
2. **CORS Configuration**: Restrict `allow_origins` in production
3. **File Validation**: Review `allowed_extensions` for your use case
4. **Network Security**: Use reverse proxy (nginx) with SSL
5. **Storage Security**: Use IAM roles for S3, encrypt at rest

## Monitoring and Maintenance

### Log Management

```bash
# App logs
docker-compose logs app

# Worker logs  
docker-compose logs worker

# ClamAV logs
docker-compose logs clamav
```

### Database Maintenance

```bash
# Clean up expired file metadata
# Files expire automatically after 7 days in Redis

# Clean up old uploads (if using local storage)
find ./uploads -type f -mtime +7 -delete
```

### Scaling

- **Horizontal**: Add more worker containers
- **Vertical**: Increase worker concurrency
- **Storage**: Use S3 for unlimited capacity
- **Database**: Consider PostgreSQL for metadata if needed

## Troubleshooting

### Common Issues

1. **ClamAV not starting**: Wait for virus definitions to download
2. **Large file uploads**: Increase `MAX_FILE_SIZE` and nginx limits  
3. **Slow scanning**: Add more worker containers
4. **Redis connection**: Check Redis is running and accessible

### Debug Mode

```bash
# Enable debug logging
DEBUG=true docker-compose up

# Test virus scanning directly
docker exec -it upload_service_worker bash
python -c "from app.tasks.virus_scan import ClamAVScanner; print(ClamAVScanner().connect().ping())"
```

## API Reference

Full API documentation is available at `/docs` when the service is running.

## License

[Add your license here]

## Support

[Add support contact information] 