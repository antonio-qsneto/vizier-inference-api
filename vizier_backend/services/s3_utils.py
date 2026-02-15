"""
AWS S3 utilities for file storage and signed URLs.
Supports both S3 (production) and local storage (development).
"""

import os
import shutil
from pathlib import Path
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

# Try to import boto3, but it's optional for dev mode
try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    ClientError = Exception


class S3Utils:
    """
    Utility class for file storage operations.
    
    In production (with AWS credentials): uses S3
    In development (without AWS credentials): uses local filesystem
    """
    
    def __init__(self):
        self.bucket = settings.S3_BUCKET
        self.region = settings.AWS_REGION
        
        # Check if we're in dev mode (no AWS credentials)
        self.is_dev_mode = not (
            settings.AWS_ACCESS_KEY_ID and 
            settings.AWS_SECRET_ACCESS_KEY
        )
        
        if self.is_dev_mode:
            # Development mode: use local storage
            self.storage_root = Path('/tmp/vizier-med')
            self.storage_root.mkdir(parents=True, exist_ok=True)
            logger.info(f"S3Utils initialized in DEV MODE (local storage): {self.storage_root}")
            self.s3_client = None
        else:
            # Production mode: use S3
            if not BOTO3_AVAILABLE:
                raise ImportError("boto3 is required for S3 storage. Install with: pip install boto3")
            
            self.s3_client = boto3.client(
                's3',
                region_name=self.region,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            )
            logger.info(f"S3Utils initialized in PRODUCTION MODE (S3): {self.bucket}")
    
    def upload_file(self, file_path: str, s3_key: str, content_type: str = 'application/octet-stream') -> bool:
        """
        Upload file to S3 (production) or local storage (development).
        
        Args:
            file_path: Local file path
            s3_key: S3 object key (or relative path in dev mode)
            content_type: MIME type (ignored in dev mode)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if self.is_dev_mode:
                # Development: copy to local storage
                local_path = self.storage_root / s3_key
                local_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, local_path)
                logger.info(f"[DEV] Uploaded file to local storage: {local_path}")
                return True
            else:
                # Production: upload to S3
                self.s3_client.upload_file(
                    file_path,
                    self.bucket,
                    s3_key,
                    ExtraArgs={'ContentType': content_type}
                )
                logger.info(f"[PROD] Uploaded file to S3: s3://{self.bucket}/{s3_key}")
                return True
        except Exception as e:
            logger.error(f"Failed to upload file: {e}")
            return False
    
    def download_file(self, s3_key: str, file_path: str) -> bool:
        """
        Download file from S3 (production) or local storage (development).
        
        Args:
            s3_key: S3 object key (or relative path in dev mode)
            file_path: Local file path to save to
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if self.is_dev_mode:
                # Development: copy from local storage
                local_path = self.storage_root / s3_key
                if not local_path.exists():
                    logger.warning(f"[DEV] File not found for download: {local_path}")
                    return False
                
                # Ensure parent directory exists
                Path(file_path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(local_path, file_path)
                logger.info(f"[DEV] Downloaded file from local storage: {local_path} -> {file_path}")
                return True
            else:
                # Production: download from S3
                # Ensure parent directory exists
                Path(file_path).parent.mkdir(parents=True, exist_ok=True)
                self.s3_client.download_file(self.bucket, s3_key, file_path)
                logger.info(f"[PROD] Downloaded file from S3: s3://{self.bucket}/{s3_key} -> {file_path}")
                return True
        except Exception as e:
            logger.error(f"Failed to download file: {e}")
            return False
    
    def generate_presigned_url(self, s3_key: str, expires_in: int = 3600) -> str:
        """
        Generate presigned URL for S3 object (production) or local file URL (development).
        
        Args:
            s3_key: S3 object key (or relative path in dev mode)
            expires_in: URL expiration time in seconds (ignored in dev mode)
        
        Returns:
            Presigned URL (S3) or file path (dev mode)
        
        Raises:
            Exception: If URL generation fails
        """
        try:
            if self.is_dev_mode:
                # Development: return local file path
                local_path = self.storage_root / s3_key
                if not local_path.exists():
                    raise FileNotFoundError(f"File not found: {local_path}")
                
                # Return file:// URL for dev mode
                file_url = f"file://{local_path}"
                logger.info(f"[DEV] Generated file URL: {file_url}")
                return file_url
            else:
                # Production: generate S3 presigned URL
                url = self.s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': self.bucket, 'Key': s3_key},
                    ExpiresIn=expires_in
                )
                logger.info(f"[PROD] Generated presigned URL for: s3://{self.bucket}/{s3_key}")
                return url
        except Exception as e:
            logger.error(f"Failed to generate URL: {e}")
            raise
    
    def delete_object(self, s3_key: str) -> bool:
        """
        Delete object from S3 (production) or local storage (development).
        
        Args:
            s3_key: S3 object key (or relative path in dev mode)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if self.is_dev_mode:
                # Development: delete local file
                local_path = self.storage_root / s3_key
                if local_path.exists():
                    os.remove(local_path)
                    logger.info(f"[DEV] Deleted local file: {local_path}")
                return True
            else:
                # Production: delete from S3
                self.s3_client.delete_object(Bucket=self.bucket, Key=s3_key)
                logger.info(f"[PROD] Deleted S3 object: s3://{self.bucket}/{s3_key}")
                return True
        except Exception as e:
            logger.error(f"Failed to delete object: {e}")
            return False
    
    def object_exists(self, s3_key: str) -> bool:
        """
        Check if object exists in S3 (production) or local storage (development).
        
        Args:
            s3_key: S3 object key (or relative path in dev mode)
        
        Returns:
            True if object exists, False otherwise
        """
        try:
            if self.is_dev_mode:
                # Development: check local file
                local_path = self.storage_root / s3_key
                exists = local_path.exists()
                logger.debug(f"[DEV] Checking file exists: {local_path} -> {exists}")
                return exists
            else:
                # Production: check S3
                self.s3_client.head_object(Bucket=self.bucket, Key=s3_key)
                return True
        except Exception as e:
            if self.is_dev_mode:
                return False
            if hasattr(e, 'response') and e.response.get('Error', {}).get('Code') == '404':
                return False
            logger.error(f"Error checking object: {e}")
            raise
    
    def get_storage_info(self) -> dict:
        """
        Get information about current storage configuration.
        
        Returns:
            Dictionary with storage info
        """
        if self.is_dev_mode:
            return {
                'mode': 'development',
                'storage_type': 'local',
                'storage_root': str(self.storage_root),
                'bucket': self.bucket,
            }
        else:
            return {
                'mode': 'production',
                'storage_type': 's3',
                'bucket': self.bucket,
                'region': self.region,
            }
