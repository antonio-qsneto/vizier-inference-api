"""
Client for external inference API (FastAPI).

Integrates with FastAPI inference service that:
- Accepts NPZ files via POST /jobs/submit
- Returns job_id
- Provides status via GET /jobs/{job_id}/status
- Returns NPZ results via GET /jobs/{job_id}/results
"""

import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class InferenceClient:
    """Client for submitting jobs to external inference API."""
    
    def __init__(self):
        self.base_url = settings.INFERENCE_API_URL.rstrip('/')
        self.timeout = settings.INFERENCE_API_TIMEOUT
    
    def submit_job(self, file_path: str) -> str:
        """
        Submit NPZ file for inference.
        
        Endpoint: POST /jobs/submit
        
        Args:
            file_path: Path to NPZ file
        
        Returns:
            Job ID from inference API
        
        Raises:
            Exception: If submission fails
        """
        try:
            with open(file_path, 'rb') as f:
                files = {'file': f}
                response = requests.post(
                    f"{self.base_url}/jobs/submit",
                    files=files,
                    timeout=self.timeout
                )
            
            response.raise_for_status()
            data = response.json()
            job_id = data.get('job_id')
            
            if not job_id:
                raise ValueError("No job_id in response")
            
            logger.info(f"Submitted job to inference API: {job_id}")
            return job_id
        
        except requests.RequestException as e:
            logger.error(f"Failed to submit job: {e}")
            raise
    
    def get_status(self, job_id: str) -> dict:
        """
        Get job status from inference API.
        
        Endpoint: GET /jobs/{job_id}/status
        
        Args:
            job_id: Job ID
        
        Returns:
            Status dict with 'status' and optional 'progress' keys
        
        Raises:
            Exception: If request fails
        """
        try:
            response = requests.get(
                f"{self.base_url}/jobs/{job_id}/status",
                timeout=self.timeout
            )
            
            response.raise_for_status()
            data = response.json()
            
            logger.debug(f"Job {job_id} status: {data.get('status')}")
            return data
        
        except requests.RequestException as e:
            logger.error(f"Failed to get job status: {e}")
            raise
    
    def get_results(self, job_id: str, output_path: str) -> bool:
        """
        Download job results from inference API.
        API returns NPZ file (binary) or JSON with results.
        
        Endpoint: GET /jobs/{job_id}/results
        
        Args:
            job_id: Job ID
            output_path: Path to save results as NPZ
        
        Returns:
            True if successful, False otherwise
        
        Raises:
            Exception: If download fails or results not ready
        """
        try:
            import numpy as np
            import json
            
            # Endpoint returns NPZ file or JSON
            response = requests.get(
                f"{self.base_url}/jobs/{job_id}/results",
                timeout=self.timeout,
                stream=True
            )
            
            if response.status_code == 404:
                logger.warning(f"Results not ready for job {job_id}")
                raise Exception("Results not ready yet")
            
            response.raise_for_status()
            
            # Check content type
            content_type = response.headers.get('content-type', '')
            logger.info(f"Response content-type: {content_type}")
            
            # Try to parse as JSON first
            try:
                # Read all content
                content = response.content
                
                # Try JSON parsing
                if b'{' in content[:10]:  # JSON starts with {
                    logger.info(f"Parsing response as JSON")
                    data = json.loads(content.decode('utf-8'))
                    
                    # Extract mask/result from JSON
                    # Expected format: {"mask": [...], "spacing": [...]} or similar
                    if 'segs' in data:
                        mask = np.array(data['segs'])
                    elif 'mask' in data:
                        mask = np.array(data['mask'])
                    elif 'result' in data:
                        mask = np.array(data['result'])
                    elif 'imgs' in data:
                        mask = np.array(data['imgs'])
                    else:
                        # Try first array-like value
                        for key, value in data.items():
                            if isinstance(value, (list, dict)):
                                mask = np.array(value)
                                break
                        else:
                            raise ValueError(f"Could not find array data in JSON response")
                    
                    # Get spacing if available
                    spacing = data.get('spacing', None)
                    
                    # Save as NPZ
                    logger.info(f"Saving JSON data as NPZ: {output_path}")
                    if spacing:
                        np.savez(output_path, segs=mask, spacing=spacing)
                    else:
                        np.savez(output_path, segs=mask)
                else:
                    # Binary NPZ file
                    logger.info(f"Saving binary NPZ file: {output_path}")
                    with open(output_path, 'wb') as f:
                        f.write(content)
            
            except (json.JSONDecodeError, ValueError) as e:
                # Not JSON, save as binary NPZ
                logger.info(f"Not JSON, saving as binary NPZ: {e}")
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            
            logger.info(f"Downloaded results for job {job_id} to {output_path}")
            return True
        
        except requests.RequestException as e:
            logger.error(f"Failed to download results: {e}")
            raise
