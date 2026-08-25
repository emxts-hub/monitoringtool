"""
Example integration of Firebase sync into IBM i Monitoring Dashboard.
This demonstrates how to add cloud sync capabilities to your existing code.
"""

import json
import logging
from typing import Optional
from PyQt6.QtCore import QObject, pyqtSignal

try:
    from firebase_sync import FirebaseSyncManager, SyncWorker
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False

logger = logging.getLogger(__name__)


class CloudSyncManager(QObject):
    """
    Qt-based wrapper around Firebase sync for integration with PyQt6 UI.
    Emits signals when new logs are received from other users.
    """
    
    # Signals for UI updates
    sync_status_changed = pyqtSignal(str)  # "connected", "disconnected", "error"
    new_remote_log = pyqtSignal(str, dict)  # (server_name, log_data)
    sync_stats_updated = pyqtSignal(dict)  # Statistics dictionary
    
    def __init__(self):
        super().__init__()
        self.sync_manager = None
        self.worker = None
        self.enabled = False
        
        if not FIREBASE_AVAILABLE:
            logger.warning("Firebase not available - install with: pip install firebase-admin")
    
    def connect_to_firebase(self) -> bool:
        """
        Connect to Firebase cloud sync.
        
        Returns:
            True if connected, False otherwise.
        """
        if not FIREBASE_AVAILABLE:
            self.sync_status_changed.emit("error")
            logger.error("Firebase admin SDK not installed")
            return False
        
        try:
            self.sync_manager = FirebaseSyncManager()
            if self.sync_manager.initialize():
                # Register callback to receive new logs
                self.sync_manager.register_sync_callback(self._on_remote_log_received)
                
                # Start background sync worker
                self.worker = SyncWorker(self.sync_manager, interval_seconds=60)
                self.worker.start()
                
                # Start real-time listener
                self.sync_manager.listen_to_logs(hours=24)
                
                self.enabled = True
                self.sync_status_changed.emit("connected")
                logger.info("Connected to Firebase")
                return True
            else:
                self.sync_status_changed.emit("error")
                logger.error("Failed to initialize Firebase")
                return False
        except Exception as e:
            self.sync_status_changed.emit("error")
            logger.error(f"Error connecting to Firebase: {e}")
            return False
    
    def disconnect(self) -> None:
        """Disconnect from Firebase cloud sync."""
        try:
            if self.worker:
                self.worker.stop()
            if self.sync_manager:
                self.sync_manager.close()
            self.enabled = False
            self.sync_status_changed.emit("disconnected")
            logger.info("Disconnected from Firebase")
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
    
    def upload_log_entry(self, log_entry: dict) -> bool:
        """
        Upload a log entry to the cloud.
        
        Args:
            log_entry: Dictionary with monitoring data
            
        Returns:
            True if uploaded successfully.
        """
        if not self.enabled or not self.sync_manager:
            return False
        
        try:
            result = self.sync_manager.upload_log_entry(log_entry)
            return result is not None
        except Exception as e:
            logger.error(f"Error uploading log: {e}")
            return False
    
    def get_remote_logs(self, hours: int = 24, server: Optional[str] = None) -> list:
        """
        Fetch logs from other users.
        
        Args:
            hours: Look back N hours
            server: Optional server name to filter
            
        Returns:
            List of remote log entries.
        """
        if not self.enabled or not self.sync_manager:
            return []
        
        try:
            return self.sync_manager.fetch_recent_logs(hours=hours, server_filter=server)
        except Exception as e:
            logger.error(f"Error fetching remote logs: {e}")
            return []
    
    def get_sync_stats(self, hours: int = 24) -> dict:
        """Get synchronization statistics."""
        if not self.enabled or not self.sync_manager:
            return {}
        
        try:
            stats = self.sync_manager.get_statistics(hours=hours)
            self.sync_stats_updated.emit(stats)
            return stats
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}
    
    def _on_remote_log_received(self, server: str, log_data: dict) -> None:
        """Internal callback when a new log is received from Firestore."""
        self.new_remote_log.emit(server, log_data)


# Example: Add this to your main_window.py to integrate with UI

class CloudSyncUI:
    """
    Example UI components for cloud sync integration.
    Add these methods to your IBMiDashboard class.
    """
    
    def setup_cloud_sync(self):
        """Initialize cloud sync in your main window."""
        self.cloud_sync = CloudSyncManager()
        
        # Connect signals to UI updates
        self.cloud_sync.sync_status_changed.connect(self.on_sync_status_changed)
        self.cloud_sync.new_remote_log.connect(self.on_new_remote_log)
        self.cloud_sync.sync_stats_updated.connect(self.on_sync_stats_updated)
        
        # Auto-connect on startup
        self.cloud_sync.connect_to_firebase()
    
    def on_sync_status_changed(self, status: str):
        """Handle sync status changes."""
        status_icon = "🟢" if status == "connected" else "🔴"
        print(f"{status_icon} Cloud Sync: {status}")
        
        # Update UI (e.g., status bar, indicator light)
        # self.sync_status_label.setText(f"Sync: {status}")
    
    def on_new_remote_log(self, server: str, log_data: dict):
        """Handle incoming logs from other users."""
        print(f"📥 New log from {server}: CPU={log_data.get('cpu')}%")
        
        # Update UI tables, charts, etc.
        # Could merge with local data for comparison
    
    def on_sync_stats_updated(self, stats: dict):
        """Handle sync statistics updates."""
        print(f"📊 Sync Stats: {stats['total_entries']} entries from {len(stats['servers'])} servers")
        
        # Update dashboard with aggregate metrics


# Example: Modify your worker.py to auto-sync logs

def example_worker_modification():
    """
    This shows how to modify your existing worker.py to include cloud sync.
    """
    example_code = '''
# Add to top of worker.py:
from firebase_sync import FirebaseSyncManager, SyncWorker

# In your monitoring loop where you save JSON logs:
def log_monitoring_data(entry):
    """Original function that saves logs locally."""
    # ... existing local logging code ...
    save_to_json(entry)  # existing function
    
    # NEW: Also upload to cloud
    try:
        # Get the sync manager (global or passed through)
        if cloud_sync_manager and cloud_sync_manager.is_initialized:
            cloud_sync_manager.upload_log_entry(entry)
    except Exception as e:
        logger.debug(f"Cloud sync failed (non-critical): {e}")
    '''
    print(example_code)


# Example: Configuration for cloud sync in config.json

def example_config():
    """Example cloud sync settings for config.json"""
    example_config = {
        "CLOUD_SYNC": {
            "enabled": True,
            "provider": "firebase",
            "credentials_path": "firebase_credentials.json",
            "auto_sync_interval": 60,  # seconds
            "upload_on_startup": True,
            "listen_for_updates": True,
            "batch_upload_size": 50,
            "retention_days": 30,  # Only keep 30 days of cloud logs
        }
    }
    return example_config


if __name__ == "__main__":
    # Quick test of cloud sync
    import time
    
    # Initialize
    sync_mgr = CloudSyncManager()
    print("Connecting to Firebase...")
    
    if sync_mgr.connect_to_firebase():
        print("✓ Connected!")
        
        # Test upload
        test_log = {
            "server": "JDAP04",
            "cpu": 45.5,
            "asp": 72.3,
            "jobs": 850,
            "status": "ONLINE"
        }
        
        if sync_mgr.upload_log_entry(test_log):
            print("✓ Test log uploaded")
        
        # Get stats
        stats = sync_mgr.get_sync_stats()
        print(f"✓ Cloud stats: {stats}")
        
        # Keep running for 10 seconds to receive real-time updates
        print("Listening for incoming logs...")
        time.sleep(10)
        
        # Cleanup
        sync_mgr.disconnect()
        print("✓ Disconnected")
    else:
        print("✗ Failed to connect to Firebase")
