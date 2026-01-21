from datetime import datetime

def serialize_booking(booking: dict) -> dict:
    """Convert MongoDB booking document to JSON-safe format"""
    booking["_id"] = str(booking["_id"])
    if "otp" in booking:
        del booking["otp"]
    if "created_at" in booking and isinstance(booking["created_at"], datetime):
        booking["created_at"] = booking["created_at"].isoformat()
    if "updated_at" in booking and isinstance(booking["updated_at"], datetime):
        booking["updated_at"] = booking["updated_at"].isoformat()
    return booking

def serialize_knowledge(knowledge: dict) -> dict:
    """Convert knowledge document to JSON-safe format"""
    knowledge["_id"] = str(knowledge["_id"])
    if "created_at" in knowledge and isinstance(knowledge["created_at"], datetime):
        knowledge["created_at"] = knowledge["created_at"].isoformat()
    if "updated_at" in knowledge and isinstance(knowledge["updated_at"], datetime):
        knowledge["updated_at"] = knowledge["updated_at"].isoformat()
    return knowledge