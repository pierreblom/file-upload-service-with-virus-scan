import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from typing import Optional
from fastapi import UploadFile
from datetime import datetime, timedelta
import tempfile
import os

from app.config import settings
from app.utils.helpers import create_secure_filename


class S3Storage:
    """AWS S3 storage implementation."""
    
    def __init__(self):
        self.bucket_name = settings.s3_bucket_name
        
        # Initialize S3 client
        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region
            )
            # Test connection and create bucket if it doesn't exist
            self._ensure_bucket_exists()
        except NoCredentialsError:
            raise ValueError("AWS credentials not found. Please configure AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
    
    def _ensure_bucket_exists(self):
        """Ensure the S3 bucket exists, create if it doesn't."""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                # Bucket doesn't exist, create it
                try:
                    if settings.aws_region == 'us-east-1':
                        self.s3_client.create_bucket(Bucket=self.bucket_name)
                    else:
                        self.s3_client.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': settings.aws_region}
                        )
                except ClientError as create_error:
                    raise ValueError(f"Failed to create S3 bucket: {create_error}")
            else:
                raise ValueError(f"Failed to access S3 bucket: {e}")
    
    async def save_file(self, file: UploadFile, file_id: str) -> str:
        """Save uploaded file to S3."""
        secure_filename = create_secure_filename(file.filename, file_id)
        s3_key = f"uploads/{secure_filename}"
        
        # Read file content
        content = await file.read()
        
        try:
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=content,
                ContentType=file.content_type or 'application/octet-stream',
                Metadata={
                    'original_filename': file.filename,
                    'file_id': file_id,
                    'upload_timestamp': datetime.utcnow().isoformat()
                }
            )
            
            return f"s3://{self.bucket_name}/{s3_key}"
            
        except ClientError as e:
            raise Exception(f"Failed to upload file to S3: {e}")
    
    def get_s3_key(self, file_id: str, original_filename: str) -> str:
        """Get the S3 key for a file."""
        secure_filename = create_secure_filename(original_filename, file_id)
        return f"uploads/{secure_filename}"
    
    def file_exists(self, file_id: str, original_filename: str) -> bool:
        """Check if a file exists in S3."""
        s3_key = self.get_s3_key(file_id, original_filename)
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except ClientError:
            return False
    
    def get_file_size(self, file_id: str, original_filename: str) -> Optional[int]:
        """Get the size of a file in S3."""
        s3_key = self.get_s3_key(file_id, original_filename)
        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return response['ContentLength']
        except ClientError:
            return None
    
    def delete_file(self, file_id: str, original_filename: str) -> bool:
        """Delete a file from S3."""
        s3_key = self.get_s3_key(file_id, original_filename)
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except ClientError:
            return False
    
    def download_file_to_temp(self, file_id: str, original_filename: str) -> Optional[str]:
        """Download a file from S3 to a temporary location."""
        s3_key = self.get_s3_key(file_id, original_filename)
        
        try:
            # Create a temporary file
            temp_fd, temp_path = tempfile.mkstemp()
            os.close(temp_fd)
            
            # Download from S3
            self.s3_client.download_file(self.bucket_name, s3_key, temp_path)
            return temp_path
            
        except ClientError:
            return None
    
    def generate_presigned_url(self, file_id: str, original_filename: str, 
                             expiration: int = 3600) -> Optional[str]:
        """Generate a presigned URL for file download."""
        s3_key = self.get_s3_key(file_id, original_filename)
        
        try:
            response = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=expiration
            )
            return response
        except ClientError:
            return None
    
    def copy_file_from_temp(self, temp_path: str, file_id: str, original_filename: str) -> str:
        """Copy a file from temporary location to S3."""
        secure_filename = create_secure_filename(original_filename, file_id)
        s3_key = f"uploads/{secure_filename}"
        
        try:
            self.s3_client.upload_file(
                temp_path, 
                self.bucket_name, 
                s3_key,
                ExtraArgs={
                    'Metadata': {
                        'original_filename': original_filename,
                        'file_id': file_id,
                        'upload_timestamp': datetime.utcnow().isoformat()
                    }
                }
            )
            return f"s3://{self.bucket_name}/{s3_key}"
        except ClientError as e:
            raise Exception(f"Failed to upload file to S3: {e}") 