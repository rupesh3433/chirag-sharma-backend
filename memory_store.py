from typing import Dict, Optional
from datetime import datetime, timedelta
from agent_models import ConversationMemory, BookingIntent
import secrets
import logging

logger = logging.getLogger(__name__)

# In-memory storage for conversation states
_memory_store: Dict[str, ConversationMemory] = {}

# Cleanup old sessions periodically
MEMORY_TTL_HOURS = 2

def create_session(language: str) -> str:
    """Create a new conversation session"""
    session_id = secrets.token_urlsafe(16)
    
    memory = ConversationMemory(
        session_id=session_id,
        language=language,
        intent=BookingIntent(),
        stage="greeting",
        last_updated=datetime.utcnow()
    )
    
    _memory_store[session_id] = memory
    logger.info(f"Created new session: {session_id} for language: {language}")
    return session_id

def get_memory(session_id: str) -> Optional[ConversationMemory]:
    """Retrieve conversation memory by session ID"""
    if not session_id:
        return None
    
    memory = _memory_store.get(session_id)
    
    if memory:
        # Check if expired
        if datetime.utcnow() - memory.last_updated > timedelta(hours=MEMORY_TTL_HOURS):
            logger.info(f"Session expired: {session_id}")
            del _memory_store[session_id]
            return None
        
        # Update last accessed time
        memory.last_updated = datetime.utcnow()
    
    return memory

def update_memory(session_id: str, memory: ConversationMemory) -> None:
    """Update conversation memory"""
    if session_id:
        memory.last_updated = datetime.utcnow()
        _memory_store[session_id] = memory
        logger.debug(f"Updated session: {session_id}, stage: {memory.stage}")

def delete_memory(session_id: str) -> None:
    """Delete conversation memory"""
    if session_id in _memory_store:
        del _memory_store[session_id]
        logger.info(f"Deleted session: {session_id}")

def cleanup_old_sessions() -> int:
    """Remove expired sessions. Returns count of cleaned sessions."""
    cutoff_time = datetime.utcnow() - timedelta(hours=MEMORY_TTL_HOURS)
    
    expired_sessions = [
        sid for sid, memory in _memory_store.items()
        if memory.last_updated < cutoff_time
    ]
    
    for sid in expired_sessions:
        del _memory_store[sid]
    
    if expired_sessions:
        logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
    
    return len(expired_sessions)

def get_all_sessions() -> Dict[str, ConversationMemory]:
    """Get all active sessions (for debugging/admin)"""
    return _memory_store.copy()