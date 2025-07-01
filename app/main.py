import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, BackgroundTasks, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import redis
import uvicorn

from app.config import settings
from app.models import (
    FileUploadResponse, FileInfo, FileStatusResponse, 
    DownloadLinkResponse, ErrorResponse, ScanStatus, VirusScanResult
)
from app.utils.helpers import (
    generate_file_id, is_allowed_file, get_file_mime_type,
    generate_download_token, verify_download_token, format_file_size
)
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage
from app.tasks.virus_scan import scan_file_for_viruses

# Initialize FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="A secure file upload service with virus scanning capabilities",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Redis for file metadata storage
redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)

# Initialize storage
if settings.storage_type == "s3":
    storage = S3Storage()
else:
    storage = LocalStorage()


def get_file_metadata(file_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve file metadata from Redis."""
    try:
        metadata_str = redis_client.get(f"file:{file_id}")
        if metadata_str:
            return json.loads(metadata_str)
        return None
    except Exception:
        return None


def save_file_metadata(file_id: str, metadata: Dict[str, Any]) -> bool:
    """Save file metadata to Redis."""
    try:
        redis_client.setex(
            f"file:{file_id}", 
            86400 * 7,  # 7 days expiration
            json.dumps(metadata, default=str)
        )
        return True
    except Exception:
        return False


def update_file_scan_result(file_id: str, scan_result: VirusScanResult) -> bool:
    """Update file metadata with scan results."""
    try:
        metadata = get_file_metadata(file_id)
        if metadata:
            metadata['scan_status'] = scan_result.status.value
            metadata['scan_result'] = scan_result.dict()
            metadata['scan_timestamp'] = scan_result.scan_timestamp.isoformat()
            return save_file_metadata(file_id, metadata)
        return False
    except Exception:
        return False


@app.get("/", response_model=Dict[str, str])
async def root():
    """Health check endpoint."""
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.app_version,
        "status": "healthy"
    }


@app.get("/health", response_model=Dict[str, str])
async def health_check():
    """Detailed health check."""
    try:
        # Test Redis connection
        redis_client.ping()
        redis_status = "healthy"
    except Exception:
        redis_status = "unhealthy"
    
    return {
        "status": "healthy" if redis_status == "healthy" else "degraded",
        "redis": redis_status,
        "storage": settings.storage_type,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """
    Upload a file and initiate virus scanning.
    
    - **file**: The file to upload (multipart/form-data)
    
    Returns file metadata and initiates asynchronous virus scanning.
    """
    
    # Validate file
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided"
        )
    
    if not is_allowed_file(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed extensions: {', '.join(settings.allowed_extensions)}"
        )
    
    # Check file size
    file_content = await file.read()
    file_size = len(file_content)
    
    if file_size > settings.max_file_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {format_file_size(settings.max_file_size)}"
        )
    
    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file not allowed"
        )
    
    # Reset file pointer
    await file.seek(0)
    
    try:
        # Generate unique file ID
        file_id = generate_file_id()
        
        # Save file to storage
        file_path = await storage.save_file(file, file_id)
        
        # Prepare file metadata
        file_metadata = {
            "file_id": file_id,
            "filename": file.filename,
            "file_size": file_size,
            "content_type": file.content_type or "application/octet-stream",
            "upload_timestamp": datetime.utcnow().isoformat(),
            "scan_status": ScanStatus.PENDING.value,
            "scan_result": None,
            "scan_timestamp": None,
            "download_count": 0,
            "last_downloaded": None,
            "file_path": file_path
        }
        
        # Save metadata to Redis
        if not save_file_metadata(file_id, file_metadata):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save file metadata"
            )
        
        # Start virus scan task
        task = scan_file_for_viruses.delay(
            file_id, 
            file.filename, 
            {"file_size": file_size, "content_type": file.content_type}
        )
        
        # Update metadata with task ID
        file_metadata["task_id"] = task.id
        save_file_metadata(file_id, file_metadata)
        
        return FileUploadResponse(
            file_id=file_id,
            filename=file.filename,
            file_size=file_size,
            upload_timestamp=datetime.fromisoformat(file_metadata["upload_timestamp"]),
            scan_status=ScanStatus.PENDING,
            task_id=task.id
        )
        
    except FileExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="File already exists"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}"
        )


@app.get("/files/{file_id}/status", response_model=FileStatusResponse)
async def get_file_status(file_id: str):
    """
    Get the current status of a file, including virus scan results.
    
    - **file_id**: The unique identifier of the file
    """
    
    metadata = get_file_metadata(file_id)
    if not metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    # Create FileInfo object
    file_info = FileInfo(
        file_id=metadata["file_id"],
        filename=metadata["filename"],
        file_size=metadata["file_size"],
        content_type=metadata["content_type"],
        upload_timestamp=datetime.fromisoformat(metadata["upload_timestamp"]),
        scan_status=ScanStatus(metadata["scan_status"]),
        scan_result=metadata.get("scan_result"),
        scan_timestamp=datetime.fromisoformat(metadata["scan_timestamp"]) if metadata.get("scan_timestamp") else None,
        download_count=metadata.get("download_count", 0),
        last_downloaded=datetime.fromisoformat(metadata["last_downloaded"]) if metadata.get("last_downloaded") else None
    )
    
    # Generate appropriate message based on scan status
    status_messages = {
        ScanStatus.PENDING: "File uploaded successfully. Virus scan is pending.",
        ScanStatus.SCANNING: "File is currently being scanned for viruses.",
        ScanStatus.CLEAN: "File is clean and safe to download.",
        ScanStatus.INFECTED: "File contains viruses and is not safe to download.",
        ScanStatus.ERROR: "Virus scan failed. Please contact support."
    }
    
    return FileStatusResponse(
        file_info=file_info,
        message=status_messages.get(file_info.scan_status, "Unknown status")
    )


@app.get("/files/{file_id}/download-link", response_model=DownloadLinkResponse)
async def generate_download_link(file_id: str):
    """
    Generate a secure, time-limited download link for a file.
    
    - **file_id**: The unique identifier of the file
    
    Only allows downloads of files that have passed virus scanning.
    """
    
    metadata = get_file_metadata(file_id)
    if not metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    scan_status = ScanStatus(metadata["scan_status"])
    
    # Only allow downloads of clean files
    if scan_status != ScanStatus.CLEAN:
        if scan_status == ScanStatus.INFECTED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="File contains viruses and cannot be downloaded"
            )
        elif scan_status in [ScanStatus.PENDING, ScanStatus.SCANNING]:
            raise HTTPException(
                status_code=status.HTTP_202_ACCEPTED,
                detail="File is still being scanned. Please try again later."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="File scan failed. Please contact support."
            )
    
    # Check if file exists in storage
    if not storage.file_exists(file_id, metadata["filename"]):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found in storage"
        )
    
    # Generate download token
    download_token = generate_download_token(file_id)
    
    # Create download URL
    download_url = f"/download/{download_token}"
    
    # Calculate expiration time
    expires_at = datetime.utcnow() + timedelta(hours=settings.download_link_expire_hours)
    
    # Create FileInfo object
    file_info = FileInfo(
        file_id=metadata["file_id"],
        filename=metadata["filename"],
        file_size=metadata["file_size"],
        content_type=metadata["content_type"],
        upload_timestamp=datetime.fromisoformat(metadata["upload_timestamp"]),
        scan_status=ScanStatus(metadata["scan_status"]),
        scan_result=metadata.get("scan_result"),
        scan_timestamp=datetime.fromisoformat(metadata["scan_timestamp"]) if metadata.get("scan_timestamp") else None,
        download_count=metadata.get("download_count", 0),
        last_downloaded=datetime.fromisoformat(metadata["last_downloaded"]) if metadata.get("last_downloaded") else None
    )
    
    return DownloadLinkResponse(
        download_url=download_url,
        expires_at=expires_at,
        file_info=file_info
    )


@app.get("/download/{token}")
async def download_file(token: str):
    """
    Download a file using a secure token.
    
    - **token**: The download token from the download link
    """
    
    # Verify download token
    file_id = verify_download_token(token)
    if not file_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired download token"
        )
    
    # Get file metadata
    metadata = get_file_metadata(file_id)
    if not metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    # Double-check scan status
    if ScanStatus(metadata["scan_status"]) != ScanStatus.CLEAN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="File is not safe for download"
        )
    
    try:
        if settings.storage_type == "s3":
            # For S3, generate a presigned URL
            download_url = storage.generate_presigned_url(
                file_id, 
                metadata["filename"], 
                expiration=3600
            )
            if not download_url:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Failed to generate download URL"
                )
            
            # Update download statistics
            metadata["download_count"] = metadata.get("download_count", 0) + 1
            metadata["last_downloaded"] = datetime.utcnow().isoformat()
            save_file_metadata(file_id, metadata)
            
            # Redirect to S3 presigned URL
            return JSONResponse(
                content={"download_url": download_url},
                status_code=status.HTTP_302_FOUND
            )
        else:
            # For local storage, serve file directly
            file_path = storage.get_download_path(file_id, metadata["filename"])
            if not file_path or not os.path.exists(file_path):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="File not found in storage"
                )
            
            # Update download statistics
            metadata["download_count"] = metadata.get("download_count", 0) + 1
            metadata["last_downloaded"] = datetime.utcnow().isoformat()
            save_file_metadata(file_id, metadata)
            
            return FileResponse(
                path=file_path,
                filename=metadata["filename"],
                media_type=metadata["content_type"]
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download file: {str(e)}"
        )


@app.delete("/files/{file_id}")
async def delete_file(file_id: str):
    """
    Delete a file and its metadata.
    
    - **file_id**: The unique identifier of the file
    """
    
    metadata = get_file_metadata(file_id)
    if not metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    try:
        # Delete from storage
        deleted = storage.delete_file(file_id, metadata["filename"])
        
        # Delete metadata from Redis
        redis_client.delete(f"file:{file_id}")
        
        return {
            "message": "File deleted successfully" if deleted else "File metadata deleted (file may not have existed in storage)",
            "file_id": file_id
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete file: {str(e)}"
        )


@app.get("/files", response_model=Dict[str, Any])
async def list_files(skip: int = 0, limit: int = 50):
    """
    List uploaded files (for admin purposes).
    
    - **skip**: Number of files to skip
    - **limit**: Maximum number of files to return
    """
    
    try:
        # Get all file keys from Redis
        file_keys = redis_client.keys("file:*")
        
        # Paginate
        paginated_keys = file_keys[skip:skip + limit]
        
        files = []
        for key in paginated_keys:
            metadata_str = redis_client.get(key)
            if metadata_str:
                metadata = json.loads(metadata_str)
                files.append({
                    "file_id": metadata["file_id"],
                    "filename": metadata["filename"],
                    "file_size": metadata["file_size"],
                    "upload_timestamp": metadata["upload_timestamp"],
                    "scan_status": metadata["scan_status"],
                    "download_count": metadata.get("download_count", 0)
                })
        
        return {
            "files": files,
            "total": len(file_keys),
            "skip": skip,
            "limit": limit
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list files: {str(e)}"
        )


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.detail,
            detail=getattr(exc, 'detail', None)
        ).dict()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="Internal server error",
            detail=str(exc) if settings.debug else None
        ).dict()
    )


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    ) 