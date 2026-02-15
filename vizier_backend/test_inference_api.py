#!/usr/bin/env python
"""
Test script to verify inference API connection and endpoints.

Usage:
    python test_inference_api.py

Or from Docker:
    docker-compose exec web python test_inference_api.py
"""

import os
import sys
import requests
import json
from datetime import datetime

# Get API URL from environment
API_URL = os.getenv('INFERENCE_API_URL', 'http://localhost:8001')
TIMEOUT = int(os.getenv('INFERENCE_API_TIMEOUT', 300))

def print_header(text):
    """Print a formatted header."""
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")

def test_connection():
    """Test basic connection to inference API."""
    print_header("1. Testing Connection")
    
    try:
        response = requests.get(f"{API_URL}/", timeout=5)
        print(f"✓ API is reachable at: {API_URL}")
        print(f"  Status Code: {response.status_code}")
        return True
    except requests.exceptions.ConnectionError:
        print(f"✗ Cannot connect to API at: {API_URL}")
        print(f"  Make sure your inference API is running")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_submit_endpoint():
    """Test job submission endpoint."""
    print_header("2. Testing Job Submission Endpoint")
    
    try:
        # Create a dummy NPZ file for testing
        import numpy as np
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix='.npz', delete=False) as f:
            # Create dummy data
            data = {
                'image': np.random.rand(512, 512, 64).astype(np.float32),
                'metadata': {
                    'patient_id': 'TEST-001',
                    'study_date': datetime.now().isoformat()
                }
            }
            np.savez(f.name, **data)
            temp_file = f.name
        
        # Submit job
        with open(temp_file, 'rb') as f:
            files = {'file': f}
            response = requests.post(
                f"{API_URL}/jobs/submit",
                files=files,
                timeout=TIMEOUT
            )
        
        # Clean up
        os.unlink(temp_file)
        
        if response.status_code == 200:
            data = response.json()
            job_id = data.get('job_id')
            print(f"✓ Job submitted successfully")
            print(f"  Job ID: {job_id}")
            print(f"  Status: {data.get('status')}")
            return job_id
        else:
            print(f"✗ Failed to submit job")
            print(f"  Status Code: {response.status_code}")
            print(f"  Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"✗ Error: {e}")
        return None

def test_status_endpoint(job_id):
    """Test job status endpoint."""
    print_header("3. Testing Job Status Endpoint")
    
    if not job_id:
        print("⊘ Skipping (no job ID from submission)")
        return False
    
    try:
        response = requests.get(
            f"{API_URL}/jobs/{job_id}/status",
            timeout=TIMEOUT
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Status retrieved successfully")
            print(f"  Job ID: {data.get('job_id')}")
            print(f"  Status: {data.get('status')}")
            print(f"  Progress: {data.get('progress', 'N/A')}%")
            return True
        else:
            print(f"✗ Failed to get status")
            print(f"  Status Code: {response.status_code}")
            print(f"  Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_results_endpoint(job_id):
    """Test job results endpoint."""
    print_header("4. Testing Job Results Endpoint")
    
    if not job_id:
        print("⊘ Skipping (no job ID from submission)")
        return False
    
    try:
        response = requests.get(
            f"{API_URL}/jobs/{job_id}/results",
            timeout=TIMEOUT,
            stream=True
        )
        
        if response.status_code == 200:
            content_length = len(response.content)
            print(f"✓ Results retrieved successfully")
            print(f"  Content Length: {content_length} bytes")
            print(f"  Content Type: {response.headers.get('content-type')}")
            return True
        else:
            print(f"✗ Failed to get results")
            print(f"  Status Code: {response.status_code}")
            print(f"  Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_django_integration():
    """Test Django integration with inference API."""
    print_header("5. Testing Django Integration")
    
    try:
        # Import Django settings
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vizier_backend.settings')
        import django
        django.setup()
        
        from apps.inference.client import InferenceClient
        
        client = InferenceClient()
        print(f"✓ InferenceClient initialized")
        print(f"  API URL: {client.base_url}")
        print(f"  Timeout: {client.timeout}s")
        
        # Try to get status (will fail if job doesn't exist, but that's OK)
        try:
            client.get_status('test-job-id')
        except Exception as e:
            # Expected to fail, just testing connectivity
            if "404" in str(e) or "Not found" in str(e):
                print(f"✓ API responded (job not found, as expected)")
                return True
            else:
                print(f"✗ Unexpected error: {e}")
                return False
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def print_summary(results):
    """Print test summary."""
    print_header("Test Summary")
    
    tests = [
        ("Connection", results[0]),
        ("Job Submission", results[1]),
        ("Job Status", results[2]),
        ("Job Results", results[3]),
        ("Django Integration", results[4]),
    ]
    
    passed = sum(1 for _, result in tests if result)
    total = len(tests)
    
    for test_name, result in tests:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8} - {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All tests passed! Your inference API is properly configured.")
        return 0
    else:
        print("\n✗ Some tests failed. Check the errors above.")
        return 1

def main():
    """Run all tests."""
    print("\n")
    print("╔" + "="*58 + "╗")
    print("║" + " "*58 + "║")
    print("║" + "  Vizier Med - Inference API Test Suite".center(58) + "║")
    print("║" + " "*58 + "║")
    print("╚" + "="*58 + "╝")
    
    print(f"\nAPI URL: {API_URL}")
    print(f"Timeout: {TIMEOUT}s")
    
    # Run tests
    results = []
    
    # Test 1: Connection
    results.append(test_connection())
    
    if not results[0]:
        print("\n✗ Cannot proceed without API connection")
        return 1
    
    # Test 2: Submit endpoint
    job_id = test_submit_endpoint()
    results.append(job_id is not None)
    
    # Test 3: Status endpoint
    results.append(test_status_endpoint(job_id))
    
    # Test 4: Results endpoint
    results.append(test_results_endpoint(job_id))
    
    # Test 5: Django integration
    results.append(test_django_integration())
    
    # Print summary
    return print_summary(results)

if __name__ == '__main__':
    sys.exit(main())
