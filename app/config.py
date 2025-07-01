from pydantic_settings import BaseSettings
from typing import Optional, Literal
import os


class Settings(BaseSettings):
    # API Configuration
    app_name: str = "File Upload Service with Virus Scan"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Redis Configuration
    redis_url: str = "redis://localhost:6379/0"
    
    # Celery Configuration
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"
    
    # ClamAV Configuration
    clamav_host: str = "localhost"
    clamav_port: int = 3310
    clamav_timeout: int = 60
    
    # Storage Configuration
    storage_type: Literal["local", "azure"] = "local"
    local_storage_path: str = "./uploads"
    max_file_size: int = 100 * 1024 * 1024  # 100MB
    allowed_extensions: set = {
        ".txt", ".pdf", ".doc", ".docx", ".xls", ".xlsx", 
        ".ppt", ".pptx", ".jpg", ".jpeg", ".png", ".gif", 
        ".zip", ".rar", ".tar", ".gz"
    }
    
    # Azure Blob Storage Configuration (if using Azure)
    azure_storage_account_name: Optional[str] = None
    azure_storage_account_key: Optional[str] = None
    azure_storage_connection_string: Optional[str] = None
    azure_container_name: str = "file-upload-service"
    
    # Security Configuration
    secret_key: str = "your-secret-key-change-this-in-production"
    access_token_expire_minutes: int = 30
    
    # File Processing Configuration
    virus_scan_timeout: int = 300  # 5 minutes
    download_link_expire_hours: int = 24
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Create global settings instance
settings = Settings() 