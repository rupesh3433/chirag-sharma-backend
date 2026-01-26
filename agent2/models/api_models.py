"""
API Request/Response Models
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict


class AgentChatRequest(BaseModel):
    """Incoming chat request"""
    
    message: str = Field(..., min_length=1, max_length=1000)
    session_id: Optional[str] = None
    language: str = Field(default="en", pattern="^(en|ne|hi|mr)$")
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "I want to book bridal makeup",
                "session_id": "abc123",
                "language": "en"
            }
        }


class AgentChatResponse(BaseModel):
    """Agent response with state"""
    
    reply: str
    session_id: str
    stage: str
    action: str
    missing_fields: List[str] = Field(default_factory=list)
    collected_info: Dict[str, str] = Field(default_factory=dict)
    booking_id: Optional[str] = None
    chat_mode: str = "agent"
    next_expected: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "reply": "Which service would you like to book?",
                "session_id": "abc123",
                "stage": "selecting_service",
                "action": "ask_service",
                "missing_fields": ["service type"],
                "collected_info": {},
                "chat_mode": "agent",
                "next_expected": "service selection"
            }
        }