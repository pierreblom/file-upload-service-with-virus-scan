import os
import tempfile
import time
from datetime import datetime
from typing import Dict, Any, Optional
import pyclamd

from celery import Celery
from app.config import settings
from app.models import ScanStatus, VirusScanResult
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage

# Initialize Celery app
celery_app = Celery(
    "virus_scanner",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=['app.tasks.virus_scan']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.virus_scan_timeout,
    task_soft_time_limit=settings.virus_scan_timeout - 30,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_disable_rate_limits=True
)

# Initialize storage
if settings.storage_type == "s3":
    storage = S3Storage()
else:
    storage = LocalStorage()


class ClamAVScanner:
    """ClamAV virus scanner wrapper."""
    
    def __init__(self):
        self.host = settings.clamav_host
        self.port = settings.clamav_port
        self.timeout = settings.clamav_timeout
    
    def connect(self) -> pyclamd.ClamdUnixSocket:
        """Connect to ClamAV daemon."""
        try:
            # Try Unix socket first, then TCP
            if os.path.exists('/var/run/clamav/clamd.ctl'):
                cd = pyclamd.ClamdUnixSocket('/var/run/clamav/clamd.ctl')
            else:
                cd = pyclamd.ClamdNetworkSocket(self.host, self.port)
            
            # Test connection
            if cd.ping():
                return cd
            else:
                raise ConnectionError("ClamAV daemon not responding")
                
        except Exception as e:
            raise ConnectionError(f"Failed to connect to ClamAV: {e}")
    
    def scan_file(self, file_path: str) -> Dict[str, Any]:
        """Scan a file for viruses."""
        cd = self.connect()
        
        try:
            # Get engine version
            version_info = cd.version()
            
            # Scan the file
            scan_result = cd.scan_file(file_path)
            
            # Parse results
            if scan_result is None:
                # File is clean
                return {
                    'status': ScanStatus.CLEAN,
                    'threats_found': [],
                    'engine_version': version_info
                }
            else:
                # File is infected
                filename = list(scan_result.keys())[0]
                threat_info = scan_result[filename]
                
                return {
                    'status': ScanStatus.INFECTED,
                    'threats_found': [threat_info[1]] if isinstance(threat_info, tuple) else [str(threat_info)],
                    'engine_version': version_info
                }
                
        except Exception as e:
            raise Exception(f"Virus scan failed: {e}")


@celery_app.task(bind=True, name='scan_file_for_viruses')
def scan_file_for_viruses(self, file_id: str, filename: str, file_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Celery task to scan a file for viruses.
    
    Args:
        file_id: Unique file identifier
        filename: Original filename
        file_info: Additional file information
    
    Returns:
        VirusScanResult as dictionary
    """
    start_time = time.time()
    scanner = ClamAVScanner()
    temp_file_path = None
    
    try:
        # Update task status
        self.update_state(
            state='SCANNING',
            meta={'file_id': file_id, 'status': 'Scanning file for viruses...'}
        )
        
        # Get file path for scanning
        if settings.storage_type == "s3":
            # Download file from S3 to temporary location
            temp_file_path = storage.download_file_to_temp(file_id, filename)
            if not temp_file_path:
                raise Exception("Failed to download file from S3 for scanning")
            file_path = temp_file_path
        else:
            # Use local file path
            file_path = storage.get_file_path(file_id, filename)
            if not os.path.exists(file_path):
                raise Exception("File not found in local storage")
        
        # Perform virus scan
        scan_result = scanner.scan_file(file_path)
        scan_duration = time.time() - start_time
        
        # Create result object
        result = VirusScanResult(
            file_id=file_id,
            status=scan_result['status'],
            scan_timestamp=datetime.utcnow(),
            scan_duration=scan_duration,
            engine_version=scan_result.get('engine_version'),
            threats_found=scan_result.get('threats_found', [])
        )
        
        # If file is infected, optionally delete it
        if result.status == ScanStatus.INFECTED:
            # Log the threat
            print(f"VIRUS DETECTED in file {file_id}: {result.threats_found}")
            
            # Optionally delete infected files
            # storage.delete_file(file_id, filename)
        
        return result.dict()
        
    except Exception as e:
        scan_duration = time.time() - start_time
        
        # Create error result
        result = VirusScanResult(
            file_id=file_id,
            status=ScanStatus.ERROR,
            scan_timestamp=datetime.utcnow(),
            scan_duration=scan_duration,
            error_message=str(e)
        )
        
        return result.dict()
        
    finally:
        # Clean up temporary file if created
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception:
                pass


@celery_app.task(name='get_scan_status')
def get_scan_status(task_id: str) -> Dict[str, Any]:
    """Get the status of a virus scan task."""
    result = celery_app.AsyncResult(task_id)
    
    return {
        'task_id': task_id,
        'status': result.status,
        'result': result.result if result.ready() else None,
        'traceback': result.traceback if result.failed() else None
    }


@celery_app.task(name='cleanup_temp_files')
def cleanup_temp_files():
    """Periodic task to clean up temporary files."""
    temp_dir = tempfile.gettempdir()
    current_time = time.time()
    
    # Clean files older than 1 hour
    for filename in os.listdir(temp_dir):
        if filename.startswith('tmp'):
            file_path = os.path.join(temp_dir, filename)
            try:
                if current_time - os.path.getctime(file_path) > 3600:  # 1 hour
                    os.unlink(file_path)
            except Exception:
                pass 