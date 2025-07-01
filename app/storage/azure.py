from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient, generate_blob_sas, BlobSasPermissions
from azure.core.exceptions import ResourceNotFoundError, ResourceExistsError
from typing import Optional
from fastapi import UploadFile
from datetime import datetime, timedelta
import tempfile
import os

from app.config import settings
from app.utils.helpers import create_secure_filename


class AzureStorage:
    """Azure Blob Storage implementation."""
    
    def __init__(self):
        self.container_name = settings.azure_container_name
        
        # Initialize Azure Blob Service Client
        try:
            if settings.azure_storage_connection_string:
                # Use connection string (recommended)
                self.blob_service_client = BlobServiceClient.from_connection_string(
                    settings.azure_storage_connection_string
                )
                self.account_name = self._extract_account_name_from_connection_string()
                self.account_key = self._extract_account_key_from_connection_string()
            elif settings.azure_storage_account_name and settings.azure_storage_account_key:
                # Use account name and key
                self.account_name = settings.azure_storage_account_name
                self.account_key = settings.azure_storage_account_key
                account_url = f"https://{self.account_name}.blob.core.windows.net"
                self.blob_service_client = BlobServiceClient(
                    account_url=account_url,
                    credential=self.account_key
                )
            else:
                raise ValueError("Azure storage credentials not found. Please configure AZURE_STORAGE_CONNECTION_STRING or AZURE_STORAGE_ACCOUNT_NAME/AZURE_STORAGE_ACCOUNT_KEY")
            
            # Test connection and create container if it doesn't exist
            self._ensure_container_exists()
            
        except Exception as e:
            raise ValueError(f"Failed to initialize Azure Blob Storage: {e}")
    
    def _extract_account_name_from_connection_string(self) -> str:
        """Extract account name from connection string."""
        conn_str = settings.azure_storage_connection_string
        for part in conn_str.split(';'):
            if part.startswith('AccountName='):
                return part.split('=', 1)[1]
        raise ValueError("AccountName not found in connection string")
    
    def _extract_account_key_from_connection_string(self) -> str:
        """Extract account key from connection string."""
        conn_str = settings.azure_storage_connection_string
        for part in conn_str.split(';'):
            if part.startswith('AccountKey='):
                return part.split('=', 1)[1]
        raise ValueError("AccountKey not found in connection string")
    
    def _ensure_container_exists(self):
        """Ensure the Azure container exists, create if it doesn't."""
        try:
            container_client = self.blob_service_client.get_container_client(self.container_name)
            container_client.get_container_properties()
        except ResourceNotFoundError:
            # Container doesn't exist, create it
            try:
                self.blob_service_client.create_container(self.container_name)
            except ResourceExistsError:
                # Container was created by another process
                pass
            except Exception as e:
                raise ValueError(f"Failed to create Azure container: {e}")
    
    async def save_file(self, file: UploadFile, file_id: str) -> str:
        """Save uploaded file to Azure Blob Storage."""
        secure_filename = create_secure_filename(file.filename, file_id)
        blob_name = f"uploads/{secure_filename}"
        
        # Read file content
        content = await file.read()
        
        try:
            # Get blob client
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name
            )
            
            # Upload to Azure Blob Storage
            blob_client.upload_blob(
                content,
                content_type=file.content_type or 'application/octet-stream',
                metadata={
                    'original_filename': file.filename,
                    'file_id': file_id,
                    'upload_timestamp': datetime.utcnow().isoformat()
                },
                overwrite=False  # Prevent overwriting existing files
            )
            
            return f"azure://{self.container_name}/{blob_name}"
            
        except ResourceExistsError:
            raise FileExistsError(f"File {secure_filename} already exists")
        except Exception as e:
            raise Exception(f"Failed to upload file to Azure Blob Storage: {e}")
    
    def get_blob_name(self, file_id: str, original_filename: str) -> str:
        """Get the blob name for a file."""
        secure_filename = create_secure_filename(original_filename, file_id)
        return f"uploads/{secure_filename}"
    
    def file_exists(self, file_id: str, original_filename: str) -> bool:
        """Check if a file exists in Azure Blob Storage."""
        blob_name = self.get_blob_name(file_id, original_filename)
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name
            )
            blob_client.get_blob_properties()
            return True
        except ResourceNotFoundError:
            return False
        except Exception:
            return False
    
    def get_file_size(self, file_id: str, original_filename: str) -> Optional[int]:
        """Get the size of a file in Azure Blob Storage."""
        blob_name = self.get_blob_name(file_id, original_filename)
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name
            )
            properties = blob_client.get_blob_properties()
            return properties.size
        except ResourceNotFoundError:
            return None
        except Exception:
            return None
    
    def delete_file(self, file_id: str, original_filename: str) -> bool:
        """Delete a file from Azure Blob Storage."""
        blob_name = self.get_blob_name(file_id, original_filename)
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name
            )
            blob_client.delete_blob()
            return True
        except ResourceNotFoundError:
            return False
        except Exception:
            return False
    
    def download_file_to_temp(self, file_id: str, original_filename: str) -> Optional[str]:
        """Download a file from Azure Blob Storage to a temporary location."""
        blob_name = self.get_blob_name(file_id, original_filename)
        
        try:
            # Create a temporary file
            temp_fd, temp_path = tempfile.mkstemp()
            os.close(temp_fd)
            
            # Download from Azure Blob Storage
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name
            )
            
            with open(temp_path, 'wb') as temp_file:
                download_stream = blob_client.download_blob()
                temp_file.write(download_stream.readall())
            
            return temp_path
            
        except ResourceNotFoundError:
            return None
        except Exception:
            return None
    
    def generate_presigned_url(self, file_id: str, original_filename: str, 
                             expiration: int = 3600) -> Optional[str]:
        """Generate a SAS URL for file download."""
        blob_name = self.get_blob_name(file_id, original_filename)
        
        try:
            # Generate SAS token
            sas_token = generate_blob_sas(
                account_name=self.account_name,
                account_key=self.account_key,
                container_name=self.container_name,
                blob_name=blob_name,
                permission=BlobSasPermissions(read=True),
                expiry=datetime.utcnow() + timedelta(seconds=expiration)
            )
            
            # Construct the full URL
            blob_url = f"https://{self.account_name}.blob.core.windows.net/{self.container_name}/{blob_name}?{sas_token}"
            return blob_url
            
        except Exception:
            return None
    
    def copy_file_from_temp(self, temp_path: str, file_id: str, original_filename: str) -> str:
        """Copy a file from temporary location to Azure Blob Storage."""
        secure_filename = create_secure_filename(original_filename, file_id)
        blob_name = f"uploads/{secure_filename}"
        
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name
            )
            
            with open(temp_path, 'rb') as temp_file:
                blob_client.upload_blob(
                    temp_file,
                    metadata={
                        'original_filename': original_filename,
                        'file_id': file_id,
                        'upload_timestamp': datetime.utcnow().isoformat()
                    },
                    overwrite=True
                )
            
            return f"azure://{self.container_name}/{blob_name}"
            
        except Exception as e:
            raise Exception(f"Failed to upload file to Azure Blob Storage: {e}")
    
    def get_blob_url(self, file_id: str, original_filename: str) -> str:
        """Get the public URL of a blob (without SAS token)."""
        blob_name = self.get_blob_name(file_id, original_filename)
        return f"https://{self.account_name}.blob.core.windows.net/{self.container_name}/{blob_name}" 