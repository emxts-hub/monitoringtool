#!/usr/bin/env python3
"""
Test Firebase connection and verify credentials are working.
Run this to validate your cloud sync setup before integrating into the app.
"""

import os
import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from config import get_app_data_dir


def check_credentials_file():
    """Check if Firebase credentials file exists."""
    print("\n[1] Checking credentials file...")

    app_data_dir = get_app_data_dir()
    credentials_path = os.path.join(app_data_dir, "firebase_credentials.json")

    print(f"   Expected location: {credentials_path}")

    if os.path.exists(credentials_path):
        print("   [OK] File found!")

        # Try to load and validate JSON
        try:
            with open(credentials_path, 'r') as f:
                creds = json.load(f)

            # Check for required fields
            required_fields = ['type', 'project_id', 'private_key', 'client_email']
            missing = [field for field in required_fields if field not in creds]

            if missing:
                print(f"   [WARN] Missing fields: {missing}")
                return False

            print(f"   [OK] Valid JSON structure")
            print(f"   Project ID: {creds.get('project_id')}")
            print(f"   Service Account: {creds.get('client_email')}")
            return True
        except json.JSONDecodeError as e:
            print(f"   [ERROR] Invalid JSON: {e}")
            return False
    else:
        print(f"   [ERROR] File not found!")
        print(f"\n   Please download credentials from Firebase:")
        print(f"      1. Go to: https://console.firebase.google.com")
        print(f"      2. Select your project")
        print(f"      3. Go to: Settings -> Service Accounts")
        print(f"      4. Click: 'Generate New Private Key'")
        print(f"      5. Save as: firebase_credentials.json")
        print(f"      6. Move to: {credentials_path}")
        return False


def check_firebase_sdk():
    """Check if firebase-admin is installed."""
    print("\n[2] Checking Firebase SDK...")

    try:
        import firebase_admin
        print(f"   [OK] firebase-admin installed (version: {firebase_admin.__version__})")
        return True
    except ImportError:
        print(f"   [ERROR] firebase-admin not installed")
        print(f"\n   To install, run:")
        print(f"      pip install firebase-admin")
        return False


def test_firebase_connection():
    """Test actual connection to Firebase."""
    print("\n[3] Testing Firebase connection...")

    try:
        from firebase_sync import FirebaseSyncManager
    except ImportError as e:
        print(f"   [ERROR] Cannot import firebase_sync: {e}")
        return False

    try:
        sync_mgr = FirebaseSyncManager()

        print(f"   Initializing Firebase...")
        if sync_mgr.initialize():
            print(f"   [OK] Connected to Firebase!")
            print(f"   Firestore database ready")
            return sync_mgr
        else:
            print(f"   [ERROR] Failed to initialize Firebase")
            print(f"   Check your credentials file is valid")
            return None
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
        return None


def test_upload_log():
    """Test uploading a sample log entry."""
    print("\n[4] Testing log upload...")

    sync_mgr = test_firebase_connection()
    if not sync_mgr:
        return False

    try:
        # Create a test log entry matching your actual structure
        test_log = {
            "timestamp": "2026-08-25 16:59:00",
            "lpar": "JDAP04",
            "server": "JDAP04",
            "ip": "192.168.54.30",
            "cpu": 45.5,
            "asp": 72.3,
            "jobs": 850,
            "status": "ONLINE",
            "subsystems_summary": "20 Active",
            "test": True,
        }

        print(f"   Uploading test entry: {test_log['server']}")
        doc_id = sync_mgr.upload_log_entry(test_log)

        if doc_id:
            print(f"   [OK] Upload successful!")
            print(f"   Document ID: {doc_id}")
            return True
        else:
            print(f"   [ERROR] Upload failed")
            return False
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
        return False


def test_fetch_logs():
    """Test fetching recent logs."""
    print("\n[5] Testing log fetch...")

    sync_mgr = test_firebase_connection()
    if not sync_mgr:
        return False

    try:
        print(f"   Fetching recent logs...")
        logs = sync_mgr.fetch_recent_logs(hours=24)

        if logs:
            print(f"   [OK] Fetch successful!")
            print(f"   Found {len(logs)} log entries")

            if logs:
                latest = logs[0]
                print(f"   Latest entry: {latest.get('server')} - CPU: {latest.get('cpu')}%")
            return True
        else:
            print(f"   [INFO] No logs found yet (this is OK on first run)")
            return True
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
        return False


def test_statistics():
    """Test getting sync statistics."""
    print("\n[6] Testing statistics...")

    sync_mgr = test_firebase_connection()
    if not sync_mgr:
        return False

    try:
        print(f"   Gathering statistics...")
        stats = sync_mgr.get_statistics(hours=24)

        if stats:
            print(f"   [OK] Statistics retrieved!")
            print(f"   Total entries: {stats.get('total_entries', 0)}")
            print(f"   Servers: {len(stats.get('servers', {}))}")
            if stats.get('servers'):
                for server, count in stats['servers'].items():
                    print(f"      - {server}: {count} entries")
            return True
        else:
            print(f"   [INFO] No statistics available yet")
            return True
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Firebase Cloud Sync - Connection Test")
    print("=" * 60)

    all_passed = True

    # Step 1: Check credentials
    if not check_credentials_file():
        all_passed = False

    # Step 2: Check SDK
    if not check_firebase_sdk():
        all_passed = False
        print("\n[WARN] Cannot proceed without firebase-admin")
        return False

    # Step 3: Test connection
    if not test_firebase_connection():
        all_passed = False

    # Step 4: Test upload (only if connected)
    if all_passed:
        if not test_upload_log():
            print("\n   Tip: Check Firestore security rules are published")
            all_passed = False

    # Step 5: Test fetch
    if all_passed:
        test_fetch_logs()

    # Step 6: Test stats
    if all_passed:
        test_statistics()

    # Summary
    print("\n" + "=" * 60)
    if all_passed:
        print("[OK] All tests passed! Your cloud sync is ready to use.")
        print("\nNext steps:")
        print("   1. Run: python cloud_sync_integration.py")
        print("   2. Or integrate into: worker.py")
        print("   3. See: cloud_sync_integration.py for UI examples")
    else:
        print("[ERROR] Some tests failed. See above for details.")
        print("\nTroubleshooting:")
        print("   - Verify credentials file location and validity")
        print("   - Check Firebase console - Firestore is enabled")
        print("   - Ensure security rules are published")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
