"""
FocusTrack - Sync Module
Handles syncing local SQLite data to the server API.
"""

import time
import threading
from datetime import datetime
from typing import Optional, Callable
import requests

from local_db import LocalDB


class SyncManager:
    """
    Manages syncing local activity logs to the server.
    Runs in background, syncing every 60 seconds.
    """
    
    def __init__(
        self, 
        db: LocalDB,
        api_base_url: str = "http://localhost:8000",
        sync_interval: int = 60
    ):
        """
        Initialize the sync manager.
        
        Args:
            db: LocalDB instance
            api_base_url: Base URL of the API server
            sync_interval: Seconds between sync attempts
        """
        self.db = db
        self.api_base_url = api_base_url.rstrip("/")
        self.sync_interval = sync_interval
        
        # Authentication
        self.auth_token: Optional[str] = None
        
        # State
        self._running = False
        self._sync_thread: Optional[threading.Thread] = None
        self._last_sync: Optional[datetime] = None
        self._last_error: Optional[str] = None
        
        # Callbacks
        self.on_sync_success: Optional[Callable[[int], None]] = None
        self.on_sync_error: Optional[Callable[[str], None]] = None
    
    def set_token(self, token: str):
        """Set the authentication token."""
        self.auth_token = token
        print(f"[Sync] Token set")
    
    def login(self, email: str, password: str) -> bool:
        """
        Login to get authentication token.
        
        Args:
            email: User email
            password: User password
        
        Returns:
            bool: True if login successful
        """
        try:
            response = requests.post(
                f"{self.api_base_url}/api/auth/login",
                json={"email": email, "password": password},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.auth_token = data.get("access_token")
                print(f"[Sync] Login successful")
                return True
            else:
                error = response.json().get("detail", "Login failed")
                print(f"[Sync] Login failed: {error}")
                return False
                
        except requests.RequestException as e:
            print(f"[Sync] Login error: {e}")
            return False
    
    def sync_data(self) -> tuple[bool, int]:
        """
        Sync unsynced logs to the server.
        
        CRITICAL: Only delete local logs after receiving 200 OK from server.
        
        Returns:
            tuple: (success: bool, synced_count: int)
        """
        if not self.auth_token:
            self._last_error = "Not authenticated"
            print(f"[Sync] Error: {self._last_error}")
            return False, 0
        
        # Get unsynced logs from local database
        unsynced_logs = self.db.get_unsynced_logs(limit=100)
        
        if not unsynced_logs:
            print("[Sync] No logs to sync")
            return True, 0
        
        print(f"[Sync] Syncing {len(unsynced_logs)} logs...")
        
        # Prepare logs for API (convert to expected format)
        logs_payload = []
        log_ids = []
        
        for log in unsynced_logs:
            logs_payload.append({
                "timestamp": log["timestamp"],
                "app_name": log["app_name"],
                "window_title": log["window_title"] or "",
                "mouse_count": log["mouse_count"],
                "key_count": log["key_count"],
                "is_idle": bool(log["is_idle"])
            })
            log_ids.append(log["id"])
        
        # Send to server
        try:
            response = requests.post(
                f"{self.api_base_url}/api/sync-logs",
                json={"logs": logs_payload},
                headers={"Authorization": f"Bearer {self.auth_token}"},
                timeout=30
            )
            
            if response.status_code == 200:
                # SUCCESS - Now safe to mark as synced
                data = response.json()
                synced_count = data.get("synced_count", len(log_ids))
                
                # Mark logs as synced in local database
                self.db.mark_as_synced(log_ids)
                
                self._last_sync = datetime.now()
                self._last_error = None
                
                print(f"[Sync] Success: {synced_count} logs synced")
                
                if self.on_sync_success:
                    self.on_sync_success(synced_count)
                
                return True, synced_count
            else:
                # Server returned error
                error_detail = response.json().get("detail", f"HTTP {response.status_code}")
                self._last_error = error_detail
                print(f"[Sync] Server error: {error_detail}")
                
                if self.on_sync_error:
                    self.on_sync_error(error_detail)
                
                return False, 0
                
        except requests.RequestException as e:
            # Network error - logs remain in local database
            self._last_error = str(e)
            print(f"[Sync] Network error: {e}")
            
            if self.on_sync_error:
                self.on_sync_error(str(e))
            
            return False, 0
    
    def _sync_loop(self):
        """Background sync loop."""
        print(f"[Sync] Background sync started (interval: {self.sync_interval}s)")
        
        while self._running:
            # Wait for the interval
            time.sleep(self.sync_interval)
            
            if not self._running:
                break
            
            # Attempt sync
            self.sync_data()
        
        print("[Sync] Background sync stopped")
    
    def start_background_sync(self):
        """Start the background sync thread."""
        if self._running:
            print("[Sync] Already running")
            return
        
        self._running = True
        self._sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._sync_thread.start()
        
        print("[Sync] Background sync started")
    
    def stop_background_sync(self):
        """Stop the background sync thread."""
        self._running = False
        
        # Do one final sync before stopping
        if self.auth_token:
            print("[Sync] Final sync before stopping...")
            self.sync_data()
        
        print("[Sync] Background sync stopped")
    
    def get_status(self) -> dict:
        """Get current sync status."""
        counts = self.db.get_log_count()
        
        return {
            "is_running": self._running,
            "is_authenticated": self.auth_token is not None,
            "pending_logs": counts["pending"],
            "synced_logs": counts["synced"],
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
            "last_error": self._last_error
        }


# ============================================================================
# CONFIGURATION
# ============================================================================

class SyncConfig:
    """Configuration for sync settings. Supports bundled PyInstaller builds."""
    
    def __init__(self, config_file: str = "sync_config.json"):
        import sys
        import os
        
        # Determine paths based on whether we're frozen (PyInstaller bundle)
        if getattr(sys, 'frozen', False):
            # Running as PyInstaller bundle
            bundle_dir = sys._MEIPASS
            self._bundled_config = os.path.join(bundle_dir, config_file)
            # User data saved to home directory
            self._user_data_file = os.path.join(os.path.expanduser("~"), ".workwise_user.json")
        else:
            # Running as script
            self._bundled_config = config_file
            self._user_data_file = config_file
        
        self.api_url: str = "http://localhost:8000"
        self.email: Optional[str] = None
        self.token: Optional[str] = None
        
        self._load_config()
    
    def _load_config(self):
        """Load configuration from bundled file and user data."""
        import json
        import os
        
        # 1. Load bundled config (API URL)
        if os.path.exists(self._bundled_config):
            try:
                with open(self._bundled_config, "r") as f:
                    data = json.load(f)
                    self.api_url = data.get("api_url", self.api_url)
                print(f"[Config] Loaded API URL from bundle")
            except Exception as e:
                print(f"[Config] Error loading bundled config: {e}")
        
        # 2. Load user data (email, token) from home directory
        if os.path.exists(self._user_data_file):
            try:
                with open(self._user_data_file, "r") as f:
                    data = json.load(f)
                    self.email = data.get("email")
                    self.token = data.get("token")
                print(f"[Config] Loaded user data")
            except Exception as e:
                print(f"[Config] Error loading user data: {e}")
    
    def save_config(self):
        """Save user data (email, token) to home directory."""
        import json
        
        data = {
            "email": self.email,
            "token": self.token
        }
        
        try:
            with open(self._user_data_file, "w") as f:
                json.dump(data, f, indent=2)
            print(f"[Config] User data saved")
        except Exception as e:
            print(f"[Config] Error saving: {e}")


# ============================================================================
# TEST / DEMO MODE
# ============================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("FocusTrack - Sync Manager Test")
    print("=" * 50)
    
    # Create test database
    db = LocalDB("test_sync.db")
    
    # Insert some test data
    print("\n1. Inserting test logs...")
    for i in range(5):
        db.save_log({
            "timestamp": datetime.now().isoformat(),
            "app_name": f"TestApp{i}",
            "window_title": f"Window {i}",
            "mouse_count": i * 10,
            "key_count": i * 5,
            "is_idle": False
        })
    
    # Create sync manager
    sync = SyncManager(db, api_base_url="http://localhost:8000")
    
    # Check status
    print("\n2. Sync status (before sync):")
    status = sync.get_status()
    print(f"   {status}")
    
    # Attempt sync without auth (should fail)
    print("\n3. Attempting sync without auth...")
    success, count = sync.sync_data()
    print(f"   Success: {success}, Count: {count}")
    
    # Note about authentication
    print("\n" + "=" * 50)
    print("To complete the test, start the backend server and")
    print("provide valid credentials:")
    print("  sync.login('user@example.com', 'password')")
    print("  sync.sync_data()")
    print("=" * 50)
    
    # Cleanup
    import os
    os.remove("test_sync.db")
    print("\nTest database cleaned up.")
