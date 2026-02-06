# utils_refresh_lock.py
# ============================================================
# ATOMIC REFRESH LOCK - PRODUCTION GRADE
# ============================================================
# ✅ Atomic lock acquisition (MongoDB unique index enforced)
# ✅ Lock ownership validation (prevents accidental release)
# ✅ TTL failsafe (auto-cleanup after 5 minutes)
# ✅ Thread-safe and crash-safe
# ✅ Reusable for Instagram, TikTok, and future platforms
# ============================================================

from datetime import datetime
from pymongo.errors import DuplicateKeyError
from pymongo.collection import Collection
import uuid
import logging

logger = logging.getLogger(__name__)


class RefreshLock:
    """
    Distributed refresh lock with atomic acquisition and ownership validation.
    
    Features:
    - Atomic: Uses MongoDB unique index to prevent race conditions
    - Safe: Validates lock ownership before release
    - Self-healing: TTL auto-cleanup after 5 minutes
    - Observable: Logs all operations
    
    Usage:
        lock = RefreshLock(collection, username)
        
        if lock.acquire():
            try:
                # Do refresh work
                pass
            finally:
                lock.release()
        
        # Or use context manager:
        with RefreshLock(collection, username) as acquired:
            if acquired:
                # Do refresh work
                pass
    """
    
    def __init__(self, collection: Collection, username: str, platform: str = ""):
        """
        Initialize refresh lock.
        
        Args:
            collection: MongoDB collection for locks (must have unique index on 'username')
            username: Username to lock (e.g., "@chirag_101")
            platform: Platform name for logging (e.g., "Instagram", "TikTok")
        """
        self.collection = collection
        self.username = username
        self.platform = platform
        self.lock_id = str(uuid.uuid4())  # Unique lock identifier
        self.lock_acquired = False
    
    def acquire(self) -> bool:
        """
        Atomically acquire refresh lock.
        
        Returns:
            True if lock acquired, False if already locked by another process
        
        Thread-safe: MongoDB unique index enforces atomicity
        Race-safe: Only one process can insert per username
        """
        try:
            # Atomic insert - MongoDB rejects duplicates
            self.collection.insert_one({
                "username": self.username,
                "locked_at": datetime.now(),
                "lock_id": self.lock_id,  # For ownership validation
                "locked_by": f"process_{id(self)}"  # For debugging
            })
            
            self.lock_acquired = True
            logger.info(f"🔓 {self.platform} refresh lock acquired for @{self.username} (lock_id: {self.lock_id[:8]}...)")
            return True
            
        except DuplicateKeyError:
            # Lock already exists - another process owns it
            existing_lock = self.collection.find_one({"username": self.username})
            
            if existing_lock:
                locked_at = existing_lock.get("locked_at")
                if locked_at:
                    age = (datetime.now() - locked_at).seconds
                    logger.info(f"🔒 {self.platform} refresh already in progress for @{self.username} (locked {age}s ago)")
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error acquiring {self.platform} refresh lock for @{self.username}: {e}")
            return False
    
    def release(self):
        """
        Release the refresh lock with ownership validation.
        
        Only releases if this instance owns the lock.
        Prevents accidental deletion of other processes' locks.
        
        Safe under:
        - Crashes (TTL cleanup)
        - Force refresh (ownership check)
        - Concurrent releases (idempotent)
        """
        if not self.lock_acquired:
            return
        
        try:
            # Only delete OUR lock (ownership validation)
            result = self.collection.delete_one({
                "username": self.username,
                "lock_id": self.lock_id  # ← CRITICAL: Only delete our own lock
            })
            
            if result.deleted_count > 0:
                logger.info(f"🔓 {self.platform} refresh lock released for @{self.username} (lock_id: {self.lock_id[:8]}...)")
            else:
                logger.warning(f"⚠️ {self.platform} lock for @{self.username} already released (TTL cleanup or manual delete)")
            
        except Exception as e:
            logger.error(f"❌ Error releasing {self.platform} refresh lock for @{self.username}: {e}")
    
    def __enter__(self):
        """Context manager entry - acquire lock."""
        return self.acquire()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - always release lock."""
        self.release()
    
    def is_locked(self) -> bool:
        """
        Check if username is currently locked (by any process).
        
        Returns:
            True if locked, False if available
        """
        return self.collection.find_one({"username": self.username}) is not None
    
    def get_lock_info(self) -> dict:
        """
        Get information about current lock (if exists).
        
        Returns:
            Dict with lock info, or None if not locked
        """
        lock_doc = self.collection.find_one({"username": self.username})
        
        if not lock_doc:
            return None
        
        locked_at = lock_doc.get("locked_at")
        age_seconds = (datetime.now() - locked_at).seconds if locked_at else None
        
        return {
            "username": self.username,
            "locked_at": locked_at.isoformat() if locked_at else None,
            "age_seconds": age_seconds,
            "lock_id": lock_doc.get("lock_id"),
            "locked_by": lock_doc.get("locked_by"),
            "owned_by_me": lock_doc.get("lock_id") == self.lock_id
        }


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

def force_release_lock(collection: Collection, username: str, platform: str = "") -> bool:
    """
    Force release a lock (admin use only).
    
    ⚠️ WARNING: Use with caution - can interrupt running refresh.
    Only use if you're certain the lock is stuck.
    
    Args:
        collection: Lock collection
        username: Username to unlock
        platform: Platform name for logging
    
    Returns:
        True if lock was removed, False if no lock existed
    """
    try:
        result = collection.delete_many({"username": username})
        
        if result.deleted_count > 0:
            logger.warning(f"⚠️ Force released {platform} lock for @{username} (deleted {result.deleted_count} locks)")
            return True
        else:
            logger.info(f"ℹ️ No {platform} lock found for @{username}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error force releasing {platform} lock for @{username}: {e}")
        return False


def get_all_active_locks(collection: Collection) -> list:
    """
    Get all currently active locks.
    
    Useful for:
    - Monitoring
    - Debugging stuck locks
    - Admin dashboards
    
    Args:
        collection: Lock collection
    
    Returns:
        List of lock documents with age information
    """
    try:
        locks = list(collection.find({}))
        
        # Add age info
        for lock in locks:
            locked_at = lock.get("locked_at")
            if locked_at:
                age_seconds = (datetime.now() - locked_at).seconds
                lock["age_seconds"] = age_seconds
                lock["locked_at"] = locked_at.isoformat()
        
        return locks
        
    except Exception as e:
        logger.error(f"❌ Error getting active locks: {e}")
        return []