import os
import shutil
from pathlib import Path
from typing import Optional
from fastapi import UploadFile
import aiofiles

from app.config import settings
from app.utils.helpers import ensure_directory_exists, create_secure_filename


class LocalStorage:
    """Local file storage implementation."""
    
    def __init__(self):
        self.storage_path = Path(settings.local_storage_path)
        ensure_directory_exists(str(self.storage_path))
    
    async def save_file(self, file: UploadFile, file_id: str) -> str:
        """Save uploaded file to local storage."""
        secure_filename = create_secure_filename(file.filename, file_id)
        file_path = self.storage_path / secure_filename
        
        # Ensure the file doesn't already exist
        if file_path.exists():
            raise FileExistsError(f"File {secure_filename} already exists")
        
        # Save file asynchronously
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        return str(file_path)
    
    def get_file_path(self, file_id: str, original_filename: str) -> str:
        """Get the full path to a stored file."""
        secure_filename = create_secure_filename(original_filename, file_id)
        return str(self.storage_path / secure_filename)
    
    def file_exists(self, file_id: str, original_filename: str) -> bool:
        """Check if a file exists in storage."""
        file_path = self.get_file_path(file_id, original_filename)
        return os.path.exists(file_path)
    
    def get_file_size(self, file_id: str, original_filename: str) -> Optional[int]:
        """Get the size of a stored file."""
        file_path = self.get_file_path(file_id, original_filename)
        if os.path.exists(file_path):
            return os.path.getsize(file_path)
        return None
    
    def delete_file(self, file_id: str, original_filename: str) -> bool:
        """Delete a file from storage."""
        file_path = self.get_file_path(file_id, original_filename)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
        except Exception:
            return False
    
    def copy_file(self, source_path: str, file_id: str, original_filename: str) -> str:
        """Copy a file to storage."""
        secure_filename = create_secure_filename(original_filename, file_id)
        dest_path = self.storage_path / secure_filename
        
        shutil.copy2(source_path, dest_path)
        return str(dest_path)
    
    def get_download_path(self, file_id: str, original_filename: str) -> Optional[str]:
        """Get the path for file download."""
        file_path = self.get_file_path(file_id, original_filename)
        if os.path.exists(file_path):
            return file_path
        return None 