from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class ScanStatus(str, Enum):
    PENDING = "pending"
    SCANNING = "scanning"
    CLEAN = "clean"
    INFECTED = "infected"
    ERROR = "error"


class FileUploadResponse(BaseModel):
    file_id: str = Field(..., description="Unique identifier for the uploaded file")
    filename: str = Field(..., description="Original filename")
    file_size: int = Field(..., description="File size in bytes")
    upload_timestamp: datetime = Field(..., description="When the file was uploaded")
    scan_status: ScanStatus = Field(..., description="Current virus scan status")
    task_id: Optional[str] = Field(None, description="Celery task ID for virus scan")


class FileInfo(BaseModel):
    file_id: str
    filename: str
    file_size: int
    content_type: str
    upload_timestamp: datetime
    scan_status: ScanStatus
    scan_result: Optional[Dict[str, Any]] = None
    scan_timestamp: Optional[datetime] = None
    download_count: int = 0
    last_downloaded: Optional[datetime] = None


class VirusScanResult(BaseModel):
    file_id: str
    status: ScanStatus
    scan_timestamp: datetime
    scan_duration: float  # in seconds
    engine_version: Optional[str] = None
    threats_found: Optional[list] = None
    error_message: Optional[str] = None


class DownloadLinkResponse(BaseModel):
    download_url: str = Field(..., description="Temporary download URL")
    expires_at: datetime = Field(..., description="When the download link expires")
    file_info: FileInfo = Field(..., description="File information")


class FileStatusResponse(BaseModel):
    file_info: FileInfo
    message: str


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow) 