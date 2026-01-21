from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from typing import Optional
from bson import ObjectId
from models import KnowledgeCreate, KnowledgeUpdate
from security import get_current_admin
from database import knowledge_collection
from config import LANGUAGE_MAP
from utils import serialize_knowledge

router = APIRouter(prefix="/admin/knowledge", tags=["Admin Knowledge Base"])

# ############################################################
# ADMIN ROUTES - KNOWLEDGE BASE MANAGEMENT
# ############################################################

@router.post("")
async def create_knowledge(
    data: KnowledgeCreate,
    admin: dict = Depends(get_current_admin)
):
    """Create new knowledge base entry"""
    
    # Validate language
    if data.language not in LANGUAGE_MAP:
        raise HTTPException(status_code=400, detail="Unsupported language")
    
    knowledge_doc = {
        "title": data.title,
        "content": data.content,
        "language": data.language,
        "is_active": data.is_active,
        "created_at": datetime.utcnow(),
        "updated_at": None
    }
    
    result = knowledge_collection.insert_one(knowledge_doc)
    
    return {
        "message": "Knowledge base entry created successfully",
        "id": str(result.inserted_id)
    }

@router.get("")
async def get_all_knowledge(
    language: Optional[str] = None,
    is_active: Optional[bool] = None,
    admin: dict = Depends(get_current_admin)
):
    """Get all knowledge base entries with optional filtering"""
    
    query = {}
    
    if language:
        if language not in LANGUAGE_MAP:
            raise HTTPException(status_code=400, detail="Unsupported language")
        query["language"] = language
    
    if is_active is not None:
        query["is_active"] = is_active
    
    knowledge_entries = list(
        knowledge_collection
        .find(query)
        .sort("created_at", -1)
    )
    
    return [serialize_knowledge(entry) for entry in knowledge_entries]

@router.get("/{knowledge_id}")
async def get_knowledge_entry(
    knowledge_id: str,
    admin: dict = Depends(get_current_admin)
):
    """Get single knowledge base entry"""
    
    try:
        knowledge = knowledge_collection.find_one({"_id": ObjectId(knowledge_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid knowledge ID")
    
    if not knowledge:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    
    return serialize_knowledge(knowledge)

@router.patch("/{knowledge_id}")
async def update_knowledge_entry(
    knowledge_id: str,
    data: KnowledgeUpdate,
    admin: dict = Depends(get_current_admin)
):
    """Update knowledge base entry"""
    
    try:
        knowledge = knowledge_collection.find_one({"_id": ObjectId(knowledge_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid knowledge ID")
    
    if not knowledge:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    
    # Validate language if provided
    if data.language and data.language not in LANGUAGE_MAP:
        raise HTTPException(status_code=400, detail="Unsupported language")
    
    # Prepare update data
    update_data = {}
    if data.title is not None:
        update_data["title"] = data.title
    if data.content is not None:
        update_data["content"] = data.content
    if data.language is not None:
        update_data["language"] = data.language
    if data.is_active is not None:
        update_data["is_active"] = data.is_active
    
    update_data["updated_at"] = datetime.utcnow()
    
    # Update in database
    result = knowledge_collection.update_one(
        {"_id": ObjectId(knowledge_id)},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    
    return {"message": "Knowledge base entry updated successfully"}

@router.delete("/{knowledge_id}")
async def delete_knowledge_entry(
    knowledge_id: str,
    admin: dict = Depends(get_current_admin)
):
    """Delete knowledge base entry"""
    
    try:
        result = knowledge_collection.delete_one({"_id": ObjectId(knowledge_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid knowledge ID")
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    
    return {"message": "Knowledge base entry deleted successfully"}