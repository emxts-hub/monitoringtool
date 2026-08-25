# Firebase Cloud Sync Setup Guide

## Overview
This module enables your IBM i Monitoring Dashboard to:
- ☁️ **Upload logs** to Firebase Firestore in real-time
- 📥 **Download logs** from other users' machines
- 🔄 **Sync automatically** in the background
- 📊 **View centralized statistics** across all monitoring sources

## Prerequisites

### 1. Install Firebase Admin SDK
```bash
pip install firebase-admin
```

### 2. Create Firebase Project
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Click "Add Project"
3. Name it (e.g., "IBMi-Monitoring")
4. Accept default settings
5. Create project

### 3. Create Firestore Database
1. In Firebase Console, go to "Firestore Database"
2. Click "Create Database"
3. Select "Start in test mode" (for development)
4. Choose your region (recommend closest to your location)
5. Click "Enable"

### 4. Get Credentials
1. Go to Project Settings → Service Accounts
2. Click "Generate New Private Key"
3. Save the JSON file as `firebase_credentials.json`
4. Move file to: `C:\Users\[YourUsername]\AppData\Local\IBMi_Dashboard\`

### 5. Set Up Firestore Security Rules (IMPORTANT!)
Replace default rules with this for team-based access:

```
rules_version = "2";
service cloud.firestore {
  match /databases/{database}/documents {
    // Only authenticated users can read/write
    match /logs/{document=**} {
      allow read, write: if request.auth != null;
    }
    match /sync_metadata/{document=**} {
      allow read, write: if request.auth != null;
    }
  }
}
```

**⚠️ IMPORTANT**: Use **double quotes** for `rules_version = "2";` (not single quotes)

For production, use stronger authentication (see Firebase Auth docs).

## Usage Examples

### Basic Setup
```python
from firebase_sync import FirebaseSyncManager, SyncWorker

# Initialize
sync_mgr = FirebaseSyncManager()
if sync_mgr.initialize():
    print("✓ Firebase connected")
else:
    print("✗ Failed to connect")
    exit(1)
```

### Upload Logs Manually
```python
log_entry = {
    "server": "JDAP04",
    "cpu": 65.2,
    "asp": 88.5,
    "jobs": 953,
    "status": "ONLINE"
}

doc_id = sync_mgr.upload_log_entry(log_entry)
print(f"Uploaded: {doc_id}")
```

### Batch Upload (Multiple Entries)
```python
import json

# Load local JSON logs
with open("logs/lpar_history_2026-08-25.json") as f:
    log_entries = json.load(f)

# Upload all
count = sync_mgr.upload_logs_batch(log_entries)
print(f"Uploaded {count} entries")
```

### Start Background Sync Worker
```python
worker = SyncWorker(sync_mgr, interval_seconds=30)
worker.start()  # Automatically syncs local logs every 30 seconds

# Later, when shutting down:
worker.stop()
```

### Listen for Real-Time Updates
```python
def on_new_log(server, log_data):
    print(f"New log from {server}: CPU={log_data.get('cpu')}%")

sync_mgr.register_sync_callback(on_new_log)
sync_mgr.listen_to_logs(hours=24)  # Listen to logs from last 24 hours
```

### Fetch Recent Logs
```python
# Get all logs from last 24 hours
recent_logs = sync_mgr.fetch_recent_logs(hours=24)
for log in recent_logs:
    print(f"{log['timestamp']}: {log['server']} - CPU: {log['cpu']}%")

# Get logs from specific server
server_logs = sync_mgr.fetch_recent_logs(
    hours=24,
    server_filter="JDAP04"
)
```

### View Statistics
```python
stats = sync_mgr.get_statistics(hours=24)
print(f"Total entries: {stats['total_entries']}")
print(f"Servers: {stats['servers']}")
print(f"Average CPU: {stats['average_cpu']:.2f}%")
print(f"Average ASP: {stats['average_asp']:.2f}%")
```

## Integration with Existing Code

### Option 1: Modify worker.py to auto-sync
```python
# At the top of worker.py
from firebase_sync import FirebaseSyncManager, SyncWorker

# In your main initialization:
sync_mgr = FirebaseSyncManager()
if sync_mgr.initialize():
    worker = SyncWorker(sync_mgr, interval_seconds=60)
    worker.start()
```

### Option 2: Add UI Button to Upload
```python
# In your UI code
from firebase_sync import FirebaseSyncManager

def on_upload_button_clicked():
    sync_mgr = FirebaseSyncManager()
    if sync_mgr.initialize():
        logs = sync_mgr.fetch_recent_logs(hours=24)
        show_message(f"Synced {len(logs)} logs")
```

### Option 3: Create Sync Settings Tab
Add to `config.json`:
```json
{
  "CLOUD_SYNC": {
    "enabled": true,
    "provider": "firebase",
    "auto_sync_interval": 60,
    "upload_on_startup": true,
    "listen_for_updates": true
  }
}
```

## Troubleshooting

### Firebase Connection Fails
- ✓ Check credentials JSON file exists in correct location
- ✓ Verify Firestore database is created and active
- ✓ Ensure internet connection
- ✓ Check firewall/proxy settings

### Logs Not Uploading
- ✓ Check `firebase_sync.log` for error messages
- ✓ Verify Firestore security rules allow writes
- ✓ Ensure log JSON structure matches expected format

### Real-time Updates Not Working
- ✓ Check that listeners are properly registered
- ✓ Verify internet connection is stable
- ✓ Check Firestore quota (test mode has limits)

## Cost Considerations

Firebase Firestore pricing (as of 2026):
- **Free Tier**: 1 GB storage, 50K read/write operations per day
- **Pay as you go**: ~$0.06 per 100K write operations

For continuous monitoring:
- 1 server, 1 entry/minute: ~1.4M writes/month ≈ $8-10/month
- 10 servers, 1 entry/minute: ~14M writes/month ≈ $80-100/month

**Optimization**: Batch writes and use longer sync intervals to reduce costs.

## Next Steps

1. ✓ Create Firebase project and get credentials
2. ✓ Install firebase-admin package
3. ✓ Test `sync_mgr.initialize()` in Python REPL
4. ✓ Try uploading a test log entry
5. ✓ Integrate background worker into main application
6. ✓ Add UI elements for monitoring sync status
7. ✓ Set up proper authentication (production)

## Alternative Cloud Providers

If you prefer other providers:

| Provider | Pros | Cons |
|----------|------|------|
| **Firebase** (current) | Easy setup, real-time | Google ecosystem, costs at scale |
| **MongoDB Atlas** | Flexible, popular | Requires backend API |
| **AWS DynamoDB** | Scalable, enterprise | More complex setup |
| **Supabase** | Open source, PostgreSQL | Smaller community |
| **REST API** (custom) | Full control | Build & maintain backend |

For questions or issues, check Firebase Admin SDK docs:
https://firebase.google.com/docs/database/admin/start
