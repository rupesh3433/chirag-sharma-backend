import logging
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from collections import OrderedDict

from agent_models import ConversationMemory, BookingIntent

logger = logging.getLogger(__name__)

class MemoryStore:
    """In-memory session store with TTL and LRU cleanup"""
    
    def __init__(self, ttl_hours: int = 2, max_sessions: int = 1000):
        self.ttl_hours = ttl_hours
        self.max_sessions = max_sessions
        self._store: Dict[str, ConversationMemory] = OrderedDict()
        self._cleanup_interval = 300  # Clean every 5 minutes
        self._last_cleanup = datetime.utcnow()
    
    def create_session(self, language: str) -> str:
        """Create new session with unique ID"""
        session_id = secrets.token_urlsafe(16)
        
        memory = ConversationMemory(
            session_id=session_id,
            language=language,
            intent=BookingIntent(),
            stage="greeting",
            last_updated=datetime.utcnow()
        )
        
        self._store[session_id] = memory
        self._store.move_to_end(session_id)
        
        # Cleanup if too many sessions
        if len(self._store) > self.max_sessions:
            self._cleanup(force=True)
        
        logger.info(f"Created session: {session_id[:8]}... for language: {language}")
        return session_id
    
    def get_memory(self, session_id: str) -> Optional[ConversationMemory]:
        """Retrieve memory by session ID"""
        if not session_id:
            return None
        
        # Auto cleanup
        self._auto_cleanup()
        
        memory = self._store.get(session_id)
        if memory:
            # Check if expired
            if self._is_expired(memory):
                del self._store[session_id]
                logger.info(f"Session expired: {session_id[:8]}...")
                return None
            
            # Update access time
            memory.last_updated = datetime.utcnow()
            self._store.move_to_end(session_id)
        
        return memory
    
    def update_memory(self, session_id: str, memory: ConversationMemory) -> None:
        """Update memory in store"""
        if session_id:
            memory.last_updated = datetime.utcnow()
            self._store[session_id] = memory
            self._store.move_to_end(session_id)
            
            logger.debug(f"Updated session {session_id[:8]}..., stage: {memory.stage}")
    
    def delete_memory(self, session_id: str) -> bool:
        """Delete memory from store"""
        if session_id in self._store:
            del self._store[session_id]
            logger.info(f"Deleted session: {session_id[:8]}...")
            return True
        return False
    
    def reset_memory(self, session_id: str) -> Optional[ConversationMemory]:
        """Reset memory for new booking"""
        memory = self.get_memory(session_id)
        if memory:
            memory.reset()
            self.update_memory(session_id, memory)
            logger.info(f"Reset session: {session_id[:8]}...")
        return memory
    
    def cleanup_old_sessions(self) -> int:
        """Cleanup expired sessions"""
        expired = []
        
        for session_id, memory in self._store.items():
            if self._is_expired(memory):
                expired.append(session_id)
        
        for session_id in expired:
            del self._store[session_id]
        
        if expired:
            logger.info(f"Cleaned {len(expired)} expired sessions")
        
        return len(expired)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get store statistics"""
        active_sessions = 0
        by_stage = {}
        by_language = {}
        
        for memory in self._store.values():
            if not self._is_expired(memory):
                active_sessions += 1
                by_stage[memory.stage] = by_stage.get(memory.stage, 0) + 1
                by_language[memory.language] = by_language.get(memory.language, 0) + 1
        
        return {
            "total_sessions": len(self._store),
            "active_sessions": active_sessions,
            "expired_sessions": len(self._store) - active_sessions,
            "sessions_by_stage": by_stage,
            "sessions_by_language": by_language,
            "ttl_hours": self.ttl_hours,
            "max_sessions": self.max_sessions,
            "last_cleanup": self._last_cleanup.isoformat()
        }
    
    # Private methods
    def _is_expired(self, memory: ConversationMemory) -> bool:
        """Check if memory is expired"""
        elapsed = datetime.utcnow() - memory.last_updated
        return elapsed > timedelta(hours=self.ttl_hours)
    
    def _auto_cleanup(self):
        """Auto cleanup if interval passed"""
        now = datetime.utcnow()
        if (now - self._last_cleanup).total_seconds() >= self._cleanup_interval:
            self.cleanup_old_sessions()
            self._last_cleanup = now
    
    def _cleanup(self, force: bool = False):
        """LRU cleanup if store is too large"""
        if force or len(self._store) > self.max_sessions * 0.9:
            remove_count = int(len(self._store) * 0.1)
            for _ in range(remove_count):
                self._store.popitem(last=False)  # Remove oldest
            logger.info(f"LRU cleanup removed {remove_count} sessions")

# Global instance
memory_store = MemoryStore(ttl_hours=2, max_sessions=1000)