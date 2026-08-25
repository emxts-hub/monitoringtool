"""
Firebase Firestore synchronization module for IBM i Monitoring Dashboard.
Handles uploading local monitoring logs to Firestore and receiving logs from other users.
"""

import os
import json
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
import logging

try:
    import firebase_admin
    from firebase_admin import initialize_app, credentials, firestore
    from firebase_admin.exceptions import FirebaseError
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False

from config import get_logs_dir, get_app_data_dir


logger = logging.getLogger(__name__)


class FirebaseSyncManager:
    """Manages uploading and downloading monitoring logs from Firestore."""

    def __init__(self, credentials_path: Optional[str] = None):
        """
        Initialize Firebase sync manager.
        
        Args:
            credentials_path: Path to Firebase service account JSON key.
                             If None, looks in app data directory.
        """
        if not FIREBASE_AVAILABLE:
            raise ImportError("firebase-admin not installed. Run: pip install firebase-admin")
        
        self.credentials_path = credentials_path or os.path.join(
            get_app_data_dir(), "firebase_credentials.json"
        )
        self.db = None
        self.app = None
        self.is_initialized = False
        self.sync_lock = threading.Lock()
        self.listeners = {}  # Store Firestore listener references
        self._sync_callbacks = []
        
    def initialize(self) -> bool:
        """
        Initialize Firebase connection using service account credentials.
        
        Returns:
            True if initialized successfully, False otherwise.
        """
        if self.is_initialized:
            return True
        
        if not os.path.exists(self.credentials_path):
            logger.error(f"Firebase credentials not found at {self.credentials_path}")
            return False
        
        try:
            cred = credentials.Certificate(self.credentials_path)

            try:
                self.app = firebase_admin.get_app()
            except ValueError:
                self.app = initialize_app(cred)

            # For the default Firestore database, do not pass a database ID.
            # Passing "(default)" gets URL-encoded as %28default%29 and is rejected.
            self.db = firestore.client(self.app)
            self.is_initialized = True
            logger.info("Firebase initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            self.is_initialized = False
            return False
    
    def register_sync_callback(self, callback: Callable) -> None:
        """
        Register a callback to be called when new logs are received from other users.
        
        Args:
            callback: Function that takes (server_name, log_entry) as arguments.
        """
        self._sync_callbacks.append(callback)
    
    def upload_log_entry(self, log_entry: Dict, collection: str = "logs") -> Optional[str]:
        """
        Upload a single monitoring log entry to Firestore.
        
        Args:
            log_entry: Dictionary containing monitoring data
            collection: Firestore collection name
            
        Returns:
            Document ID if successful, None otherwise.
        """
        if not self.is_initialized:
            logger.warning("Firebase not initialized, skipping upload")
            return None
        
        try:
            with self.sync_lock:
                # Add timestamp if not present
                if "timestamp" not in log_entry:
                    log_entry["timestamp"] = datetime.now().isoformat()
                
                # Add server identifier if not present
                if "server" not in log_entry and "lpar" in log_entry:
                    log_entry["server"] = log_entry["lpar"]
                
                # Add upload timestamp for tracking
                log_entry["uploaded_at"] = datetime.now().isoformat()
                
                # Use server name as collection path for organization
                server = log_entry.get("server", "unknown")
                doc_ref = self.db.collection(collection).document()
                doc_ref.set(log_entry)
                
                logger.info(f"Uploaded log entry from {server}: {doc_ref.id}")
                return doc_ref.id
        except FirebaseError as e:
            logger.error(f"Firebase error uploading log: {e}")
            return None
        except Exception as e:
            logger.error(f"Error uploading log entry: {e}")
            return None
    
    def upload_logs_batch(self, log_entries: List[Dict], collection: str = "logs") -> int:
        """
        Upload multiple log entries as a batch operation.
        
        Args:
            log_entries: List of log entry dictionaries
            collection: Firestore collection name
            
        Returns:
            Number of successfully uploaded entries.
        """
        if not self.is_initialized:
            return 0
        
        uploaded_count = 0
        try:
            with self.sync_lock:
                batch = self.db.batch()
                
                for entry in log_entries:
                    if "timestamp" not in entry:
                        entry["timestamp"] = datetime.now().isoformat()
                    if "server" not in entry and "lpar" in entry:
                        entry["server"] = entry["lpar"]
                    entry["uploaded_at"] = datetime.now().isoformat()
                    
                    doc_ref = self.db.collection(collection).document()
                    batch.set(doc_ref, entry)
                    uploaded_count += 1
                
                batch.commit()
                logger.info(f"Uploaded batch of {uploaded_count} log entries")
        except Exception as e:
            logger.error(f"Error in batch upload: {e}")
        
        return uploaded_count
    
    def fetch_recent_logs(
        self,
        hours: int = 24,
        collection: str = "logs",
        server_filter: Optional[str] = None,
    ) -> List[Dict]:
        """
        Fetch recent logs from Firestore.
        
        Args:
            hours: Number of hours to look back
            collection: Firestore collection name
            server_filter: Optional server name to filter by
            
        Returns:
            List of log entries sorted by timestamp (newest first).
        """
        if not self.is_initialized:
            return []
        
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            query = self.db.collection(collection).where(
                "timestamp", ">=", cutoff_time.isoformat()
            )
            
            if server_filter:
                query = query.where("server", "==", server_filter)
            
            docs = query.order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
            
            logs = []
            for doc in docs:
                log_data = doc.to_dict()
                log_data["_id"] = doc.id
                logs.append(log_data)
            
            logger.info(f"Fetched {len(logs)} recent logs")
            return logs
        except Exception as e:
            logger.error(f"Error fetching logs: {e}")
            return []
    
    def listen_to_logs(
        self,
        collection: str = "logs",
        hours: int = 24,
        server_filter: Optional[str] = None,
    ) -> None:
        """
        Set up a real-time listener for new logs from Firestore.
        Changes are passed to registered callbacks.
        
        Args:
            collection: Firestore collection name
            hours: Only listen to logs from last N hours
            server_filter: Optional server name to filter by
        """
        if not self.is_initialized:
            logger.warning("Firebase not initialized, cannot set up listener")
            return
        
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            query = self.db.collection(collection).where(
                "timestamp", ">=", cutoff_time.isoformat()
            )
            
            if server_filter:
                query = query.where("server", "==", server_filter)
            
            def on_snapshot(docs, changes, read_time):
                """Handle real-time updates from Firestore."""
                for change in changes:
                    if change.type.name == "ADDED":
                        doc_data = change.document.to_dict()
                        server = doc_data.get("server", "unknown")
                        
                        # Trigger callbacks for each registered listener
                        for callback in self._sync_callbacks:
                            try:
                                callback(server, doc_data)
                            except Exception as e:
                                logger.error(f"Error in sync callback: {e}")
            
            listener = query.on_snapshot(on_snapshot)
            self.listeners["default"] = listener
            logger.info("Real-time listener started")
        except Exception as e:
            logger.error(f"Error setting up listener: {e}")
    
    def stop_listening(self, listener_name: str = "default") -> None:
        """Stop a real-time listener."""
        if listener_name in self.listeners:
            try:
                self.listeners[listener_name].unsubscribe()
                del self.listeners[listener_name]
                logger.info(f"Stopped listener: {listener_name}")
            except Exception as e:
                logger.error(f"Error stopping listener: {e}")
    
    def get_statistics(self, hours: int = 24, collection: str = "logs") -> Dict:
        """
        Get statistics about uploaded logs.
        
        Args:
            hours: Number of hours to analyze
            collection: Firestore collection name
            
        Returns:
            Dictionary with statistics (server_count, total_entries, etc.)
        """
        if not self.is_initialized:
            return {}
        
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            docs = self.db.collection(collection).where(
                "timestamp", ">=", cutoff_time.isoformat()
            ).stream()
            
            stats = {
                "total_entries": 0,
                "servers": {},
                "average_cpu": 0,
                "average_asp": 0,
                "highest_cpu": 0,
                "highest_asp": 0,
            }
            
            cpu_values = []
            asp_values = []
            
            for doc in docs:
                data = doc.to_dict()
                stats["total_entries"] += 1
                
                server = data.get("server", "unknown")
                if server not in stats["servers"]:
                    stats["servers"][server] = 0
                stats["servers"][server] += 1
                
                if "cpu" in data:
                    cpu_values.append(data["cpu"])
                    stats["highest_cpu"] = max(stats["highest_cpu"], data["cpu"])
                
                if "asp" in data:
                    asp_values.append(data["asp"])
                    stats["highest_asp"] = max(stats["highest_asp"], data["asp"])
            
            if cpu_values:
                stats["average_cpu"] = sum(cpu_values) / len(cpu_values)
            if asp_values:
                stats["average_asp"] = sum(asp_values) / len(asp_values)
            
            return stats
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {}
    
    def close(self) -> None:
        """Close Firebase connection and cleanup."""
        try:
            # Stop all listeners
            for listener_name in list(self.listeners.keys()):
                self.stop_listening(listener_name)
            
            if self.app:
                # Note: firebase_admin doesn't have a built-in close method
                # The connection will be closed when app is garbage collected
                self.app = None
                self.db = None
                self.is_initialized = False
                logger.info("Firebase connection closed")
        except Exception as e:
            logger.error(f"Error closing Firebase: {e}")


class SyncWorker:
    """Background worker for continuous log synchronization."""
    
    def __init__(self, sync_manager: FirebaseSyncManager, interval_seconds: int = 30):
        """
        Initialize sync worker.
        
        Args:
            sync_manager: FirebaseSyncManager instance
            interval_seconds: Sync interval in seconds
        """
        self.sync_manager = sync_manager
        self.interval = interval_seconds
        self.running = False
        self.thread = None
    
    def start(self, local_log_dir: Optional[str] = None) -> None:
        """
        Start the background sync worker.
        
        Args:
            local_log_dir: Directory containing local JSON logs to sync.
                          Defaults to application logs directory.
        """
        if self.running:
            return
        
        self.running = True
        self.local_log_dir = local_log_dir or get_logs_dir()
        self.thread = threading.Thread(target=self._sync_loop, daemon=True)
        self.thread.start()
        logger.info("Sync worker started")
    
    def stop(self) -> None:
        """Stop the background sync worker."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Sync worker stopped")
    
    def _sync_loop(self) -> None:
        """Main sync loop that periodically uploads local logs."""
        synced_files = set()
        
        while self.running:
            try:
                # Find new JSON log files
                if os.path.exists(self.local_log_dir):
                    for filename in os.listdir(self.local_log_dir):
                        if not filename.endswith(".json"):
                            continue
                        
                        filepath = os.path.join(self.local_log_dir, filename)
                        
                        # Skip temporary files and already synced files
                        if filename.endswith(".tmp") or filepath in synced_files:
                            continue
                        
                        try:
                            with open(filepath, "r", encoding="utf-8") as f:
                                log_data = json.load(f)
                            
                            # Handle both single entry and list of entries
                            entries = log_data if isinstance(log_data, list) else [log_data]
                            
                            # Upload batch
                            uploaded = self.sync_manager.upload_logs_batch(entries)
                            if uploaded > 0:
                                synced_files.add(filepath)
                                logger.info(f"Synced {uploaded} entries from {filename}")
                        except json.JSONDecodeError as e:
                            logger.warning(f"Invalid JSON in {filename}: {e}")
                        except Exception as e:
                            logger.error(f"Error syncing {filename}: {e}")
                
                time.sleep(self.interval)
            except Exception as e:
                logger.error(f"Error in sync loop: {e}")
                time.sleep(self.interval)
