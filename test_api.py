#!/usr/bin/env python3
"""
Simple test script for the File Upload Service API.
"""

import requests
import time
import os
import tempfile

# Configuration
BASE_URL = "http://localhost:8000"
TEST_FILE_CONTENT = b"This is a test file for virus scanning."

def test_health():
    """Test health endpoint."""
    print("🔍 Testing health endpoint...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    return response.status_code == 200

def create_test_file():
    """Create a temporary test file."""
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False) as f:
        f.write(TEST_FILE_CONTENT)
        return f.name

def test_upload():
    """Test file upload."""
    print("\n📤 Testing file upload...")
    
    test_file_path = create_test_file()
    
    try:
        with open(test_file_path, 'rb') as f:
            files = {'file': ('test.txt', f, 'text/plain')}
            response = requests.post(f"{BASE_URL}/upload", files=files)
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"File ID: {data['file_id']}")
            print(f"Filename: {data['filename']}")
            print(f"File Size: {data['file_size']} bytes")
            print(f"Scan Status: {data['scan_status']}")
            return data['file_id']
        else:
            print(f"Error: {response.text}")
            return None
            
    finally:
        os.unlink(test_file_path)

def test_status(file_id):
    """Test file status checking."""
    print(f"\n📊 Testing file status for {file_id}...")
    
    max_attempts = 10
    for attempt in range(max_attempts):
        response = requests.get(f"{BASE_URL}/files/{file_id}/status")
        
        if response.status_code == 200:
            data = response.json()
            file_info = data['file_info']
            scan_status = file_info['scan_status']
            
            print(f"Attempt {attempt + 1}: Status = {scan_status}")
            print(f"Message: {data['message']}")
            
            if scan_status in ['clean', 'infected', 'error']:
                return scan_status
            
            time.sleep(2)  # Wait before checking again
        else:
            print(f"Error: {response.text}")
            return None
    
    print("⚠️ Scan did not complete within timeout")
    return None

def test_download_link(file_id):
    """Test download link generation."""
    print(f"\n🔗 Testing download link generation for {file_id}...")
    
    response = requests.get(f"{BASE_URL}/files/{file_id}/download-link")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Download URL: {data['download_url']}")
        print(f"Expires at: {data['expires_at']}")
        return data['download_url']
    else:
        print(f"Error: {response.text}")
        return None

def test_download(download_url):
    """Test file download."""
    print(f"\n⬇️ Testing file download...")
    
    response = requests.get(f"{BASE_URL}{download_url}")
    
    if response.status_code == 200:
        print(f"Downloaded {len(response.content)} bytes")
        print(f"Content matches: {response.content == TEST_FILE_CONTENT}")
        return True
    else:
        print(f"Error: {response.text}")
        return False

def test_list_files():
    """Test file listing."""
    print(f"\n📋 Testing file listing...")
    
    response = requests.get(f"{BASE_URL}/files")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Total files: {data['total']}")
        print(f"Files in this page: {len(data['files'])}")
        return True
    else:
        print(f"Error: {response.text}")
        return False

def main():
    """Run all tests."""
    print("🚀 Starting File Upload Service API Tests")
    print("=" * 50)
    
    # Test health
    if not test_health():
        print("❌ Health check failed. Is the service running?")
        return
    
    # Test upload
    file_id = test_upload()
    if not file_id:
        print("❌ Upload test failed")
        return
    
    # Test status checking
    scan_status = test_status(file_id)
    if not scan_status:
        print("❌ Status check failed")
        return
    
    # If file is clean, test download
    if scan_status == 'clean':
        download_url = test_download_link(file_id)
        if download_url:
            test_download(download_url)
    else:
        print(f"⚠️ File scan result: {scan_status}")
    
    # Test file listing
    test_list_files()
    
    print("\n✅ All tests completed!")

if __name__ == "__main__":
    main() 