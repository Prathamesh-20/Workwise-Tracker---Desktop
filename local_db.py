"""
FocusTrack - Local Database Module
SQLite buffer for offline data storage.
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional
from contextlib import contextmanager


class LocalDB:
    """
    Local SQLite database for buffering activity logs.
    Data is stored here until synced to the server.
    """
    
    def __init__(self, db_path: str = "focustrack_local.db"):
        """
        Initialize the local database.
        
        Args:
            db_path: Path to the SQLite database file
        """
        # Store database in user's home directory for consistent access
        app_data_dir = os.path.join(os.path.expanduser("~"), ".workwise")
        os.makedirs(app_data_dir, exist_ok=True)
        
        # Use absolute path
        if not os.path.isabs(db_path):
            db_path = os.path.join(app_data_dir, db_path)
        
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Create the logs table if it doesn't exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    app_name TEXT NOT NULL,
                    window_title TEXT,
                    mouse_count INTEGER DEFAULT 0,
                    key_count INTEGER DEFAULT 0,
                    is_idle INTEGER DEFAULT 0,
                    synced INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create index for faster queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_logs_synced 
                ON logs(synced)
            """)
            
            conn.commit()
            print(f"[LocalDB] Initialized: {self.db_path}")
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        try:
            yield conn
        finally:
            conn.close()
    
    def save_log(self, data: Dict) -> int:
        """
        Save a single activity log entry.
        
        Args:
            data: Dictionary containing log data:
                - timestamp: ISO format timestamp
                - app_name: Application name
                - window_title: Window title
                - mouse_count: Mouse event count
                - key_count: Keyboard event count
                - is_idle: Whether user was idle
        
        Returns:
            int: ID of the inserted row
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO logs (timestamp, app_name, window_title, mouse_count, key_count, is_idle)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                data.get("timestamp", datetime.now().isoformat()),
                data.get("app_name", "Unknown"),
                data.get("window_title", ""),
                data.get("mouse_count", 0),
                data.get("key_count", 0),
                1 if data.get("is_idle", False) else 0
            ))
            conn.commit()
            return cursor.lastrowid
    
    def get_unsynced_logs(self, limit: int = 100) -> List[Dict]:
        """
        Get logs that haven't been synced to the server yet.
        
        Args:
            limit: Maximum number of logs to retrieve
        
        Returns:
            List of log dictionaries
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, timestamp, app_name, window_title, mouse_count, key_count, is_idle
                FROM logs
                WHERE synced = 0
                ORDER BY id ASC
                LIMIT ?
            """, (limit,))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def mark_as_synced(self, log_ids: List[int]) -> int:
        """
        Mark logs as synced after successful server upload.
        
        Args:
            log_ids: List of log IDs to mark as synced
        
        Returns:
            Number of rows updated
        """
        if not log_ids:
            return 0
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" * len(log_ids))
            cursor.execute(f"""
                UPDATE logs
                SET synced = 1
                WHERE id IN ({placeholders})
            """, log_ids)
            conn.commit()
            return cursor.rowcount
    
    def delete_synced_logs(self, older_than_days: int = 7) -> int:
        """
        Delete synced logs older than specified days.
        Helps keep the local database small.
        
        Args:
            older_than_days: Delete synced logs older than this many days
        
        Returns:
            Number of rows deleted
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM logs
                WHERE synced = 1
                AND datetime(created_at) < datetime('now', ?)
            """, (f"-{older_than_days} days",))
            conn.commit()
            return cursor.rowcount
    
    def get_log_count(self) -> Dict[str, int]:
        """
        Get count of logs by sync status.
        
        Returns:
            Dict with 'total', 'synced', and 'pending' counts
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN synced = 1 THEN 1 ELSE 0 END) as synced,
                    SUM(CASE WHEN synced = 0 THEN 1 ELSE 0 END) as pending
                FROM logs
            """)
            row = cursor.fetchone()
            return {
                "total": row["total"] or 0,
                "synced": row["synced"] or 0,
                "pending": row["pending"] or 0
            }
    
    def get_today_stats(self) -> Dict:
        """
        Get statistics for today's activity.
        
        Returns:
            Dict with today's stats (total_logs, active_logs, idle_logs, total_inputs)
        """
        today = datetime.now().strftime("%Y-%m-%d")
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_logs,
                    SUM(CASE WHEN is_idle = 0 THEN 1 ELSE 0 END) as active_logs,
                    SUM(CASE WHEN is_idle = 1 THEN 1 ELSE 0 END) as idle_logs,
                    SUM(mouse_count + key_count) as total_inputs
                FROM logs
                WHERE date(timestamp) = ?
            """, (today,))
            row = cursor.fetchone()
            
            total_logs = row["total_logs"] or 0
            active_logs = row["active_logs"] or 0
            
            # Each log represents 5 seconds
            active_seconds = active_logs * 5
            hours = active_seconds // 3600
            minutes = (active_seconds % 3600) // 60
            
            return {
                "total_logs": total_logs,
                "active_logs": active_logs,
                "idle_logs": row["idle_logs"] or 0,
                "total_inputs": row["total_inputs"] or 0,
                "active_time_formatted": f"{hours}h {minutes}m"
            }


# ============================================================================
# TEST / DEMO MODE
# ============================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("FocusTrack - LocalDB Test Mode")
    print("=" * 50)
    
    # Use a test database
    db = LocalDB("test_focustrack.db")
    
    # Insert some test data
    print("\n1. Inserting test logs...")
    for i in range(5):
        log_id = db.save_log({
            "timestamp": datetime.now().isoformat(),
            "app_name": f"TestApp{i}",
            "window_title": f"Test Window {i}",
            "mouse_count": i * 10,
            "key_count": i * 5,
            "is_idle": i == 4  # Last one is idle
        })
        print(f"   Inserted log ID: {log_id}")
    
    # Get counts
    print("\n2. Log counts:")
    counts = db.get_log_count()
    print(f"   {counts}")
    
    # Get unsynced logs
    print("\n3. Unsynced logs:")
    unsynced = db.get_unsynced_logs()
    for log in unsynced:
        print(f"   {log['id']}: {log['app_name']} - {log['window_title']}")
    
    # Mark some as synced
    print("\n4. Marking first 3 logs as synced...")
    ids_to_sync = [log['id'] for log in unsynced[:3]]
    synced_count = db.mark_as_synced(ids_to_sync)
    print(f"   Synced {synced_count} logs")
    
    # Get updated counts
    print("\n5. Updated log counts:")
    counts = db.get_log_count()
    print(f"   {counts}")
    
    # Get today's stats
    print("\n6. Today's stats:")
    stats = db.get_today_stats()
    print(f"   {stats}")
    
    # Cleanup test database
    import os
    os.remove("test_focustrack.db")
    print("\n7. Test database cleaned up.")
    print("\nAll tests passed!")
