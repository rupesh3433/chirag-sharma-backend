"""
Memory Service - Session management
"""

import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List
from collections import OrderedDict
import logging
import threading

from ..models.memory import ConversationMemory
from ..models.intent import BookingIntent

logger = logging.getLogger(__name__)


class MemoryService:
    """In-memory session store with TTL and LRU cleanup"""
    
    def __init__(self, ttl_hours: int = 2, max_sessions: int = 1000):
        """Initialize memory service"""
        self.ttl_hours = ttl_hours
        self.max_sessions = max_sessions
        self.sessions: Dict[str, ConversationMemory] = OrderedDict()
        self.lock = threading.RLock()
        self.stats = {
            'created': 0,
            'accessed': 0,
            'expired': 0,
            'evicted': 0,
            'last_cleanup': None
        }
        
        # Start cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
        self.cleanup_thread.start()
        
        logger.info(f"MemoryService initialized: TTL={ttl_hours}h, Max={max_sessions}")
    
    def create_session(self, language: str = "en") -> str:
        """Create new session"""
        with self.lock:
            # Generate unique session ID
            session_id = secrets.token_urlsafe(16)
            
            # Create new memory
            memory = ConversationMemory(
                session_id=session_id,
                language=language
            )
            
            # Add to sessions
            self.sessions[session_id] = memory
            self.sessions.move_to_end(session_id)  # Mark as recently used
            
            # Update stats
            self.stats['created'] += 1
            
            logger.info(f"Created new session: {session_id} (lang: {language})")
            
            return session_id
    
    def get_session(self, session_id: str) -> Optional[ConversationMemory]:
        """Get session by ID"""
        with self.lock:
            if session_id not in self.sessions:
                return None
            
            memory = self.sessions[session_id]
            
            # Check if expired
            if self._is_expired(memory):
                del self.sessions[session_id]
                self.stats['expired'] += 1
                logger.info(f"Session expired: {session_id}")
                return None
            
            # Move to end (recently used)
            self.sessions.move_to_end(session_id)
            
            # Update stats
            self.stats['accessed'] += 1
            
            return memory
    
    def update_session(self, session_id: str, memory: ConversationMemory) -> None:
        """Update session"""
        with self.lock:
            if session_id not in self.sessions:
                return
            
            # Update memory and move to end
            self.sessions[session_id] = memory
            self.sessions.move_to_end(session_id)
            
            # Update last_updated
            memory.last_updated = datetime.utcnow()
            
            logger.debug(f"Updated session: {session_id}")
    
    def delete_session(self, session_id: str) -> bool:
        """Delete session"""
        with self.lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
                logger.info(f"Deleted session: {session_id}")
                return True
            return False
    
    def reset_session(self, session_id: str) -> Optional[ConversationMemory]:
        """Reset session for new booking"""
        with self.lock:
            memory = self.get_session(session_id)
            if not memory:
                return None
            
            # Reset memory but keep session ID and language
            memory.reset()
            self.update_session(session_id, memory)
            
            logger.info(f"Reset session: {session_id}")
            
            return memory
    
    def update_last_shown_list(self, session_id: str, list_type: str) -> Optional[ConversationMemory]:
        """Update last shown list context"""
        with self.lock:
            memory = self.get_session(session_id)
            if not memory:
                return None
            
            memory.last_shown_list = list_type
            self.update_session(session_id, memory)
            
            return memory
    
    def cleanup_old_sessions(self) -> int:
        """Cleanup expired sessions"""
        with self.lock:
            expired_count = 0
            current_time = datetime.utcnow()
            
            # Find expired sessions
            expired_sessions = []
            for session_id, memory in list(self.sessions.items()):
                if self._is_expired(memory):
                    expired_sessions.append(session_id)
            
            # Remove expired sessions
            for session_id in expired_sessions:
                del self.sessions[session_id]
                expired_count += 1
            
            # LRU cleanup if still over limit
            if len(self.sessions) > self.max_sessions:
                overflow = len(self.sessions) - self.max_sessions
                for _ in range(overflow):
                    # Remove oldest (least recently used)
                    session_id, _ = self.sessions.popitem(last=False)
                    self.stats['evicted'] += 1
            
            # Update stats
            self.stats['expired'] += expired_count
            self.stats['last_cleanup'] = current_time
            
            if expired_count > 0:
                logger.info(f"Cleaned up {expired_count} expired sessions")
            
            return expired_count
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory store statistics"""
        with self.lock:
            stats = self.stats.copy()
            stats.update({
                'active_sessions': len(self.sessions),
                'max_sessions': self.max_sessions,
                'ttl_hours': self.ttl_hours,
                'timestamp': datetime.utcnow().isoformat()
            })
            return stats
    
    def _is_expired(self, memory: ConversationMemory) -> bool:
        """Check if session is expired"""
        expiration_time = memory.last_updated + timedelta(hours=self.ttl_hours)
        return datetime.utcnow() > expiration_time
    
    def _cleanup_worker(self):
        """Background cleanup worker"""
        import time
        
        while True:
            try:
                time.sleep(300)  # Run every 5 minutes
                cleaned = self.cleanup_old_sessions()
                if cleaned > 0:
                    logger.debug(f"Background cleanup removed {cleaned} sessions")
            except Exception as e:
                logger.error(f"Cleanup worker error: {e}")
    
    def _cleanup_lru(self, force: bool = False):
        """LRU cleanup if store is too large"""
        with self.lock:
            if len(self.sessions) > self.max_sessions or force:
                overflow = len(self.sessions) - self.max_sessions
                if overflow > 0:
                    for _ in range(overflow):
                        session_id, _ = self.sessions.popitem(last=False)
                        self.stats['evicted'] += 1
                    logger.info(f"LRU cleanup removed {overflow} sessions")