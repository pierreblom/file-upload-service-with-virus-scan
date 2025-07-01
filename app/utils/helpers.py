import os
import uuid
import hashlib
import magic
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple
from jose import JWTError, jwt
from cryptography.fernet import Fernet

from app.config import settings


def generate_file_id() -> str:
    """Generate a unique file identifier."""
    return str(uuid.uuid4())


def get_file_extension(filename: str) -> str:
    """Get file extension from filename."""
    return Path(filename).suffix.lower()


def is_allowed_file(filename: str) -> bool:
    """Check if the file extension is allowed."""
    extension = get_file_extension(filename)
    return extension in settings.allowed_extensions


def get_file_mime_type(file_path: str) -> str:
    """Get MIME type of a file."""
    try:
        return magic.from_file(file_path, mime=True)
    except Exception:
        return "application/octet-stream"


def calculate_file_hash(file_path: str) -> str:
    """Calculate SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def create_secure_filename(original_filename: str, file_id: str) -> str:
    """Create a secure filename using file ID and original extension."""
    extension = get_file_extension(original_filename)
    return f"{file_id}{extension}"


def generate_download_token(file_id: str, expires_delta: Optional[timedelta] = None) -> str:
    """Generate a JWT token for secure file downloads."""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=settings.download_link_expire_hours)
    
    to_encode = {
        "file_id": file_id,
        "exp": expire,
        "type": "download"
    }
    
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm="HS256")
    return encoded_jwt


def verify_download_token(token: str) -> Optional[str]:
    """Verify download token and return file_id if valid."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        file_id: str = payload.get("file_id")
        token_type: str = payload.get("type")
        
        if file_id is None or token_type != "download":
            return None
            
        return file_id
    except JWTError:
        return None


def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"


def ensure_directory_exists(directory_path: str) -> None:
    """Ensure that a directory exists, create if it doesn't."""
    Path(directory_path).mkdir(parents=True, exist_ok=True)


def safe_remove_file(file_path: str) -> bool:
    """Safely remove a file, return True if successful."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False
    except Exception:
        return False 