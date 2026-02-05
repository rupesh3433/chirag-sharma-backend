from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
from datetime import datetime
from database import event_collection

router = APIRouter(prefix="/public/events", tags=["Public Events"])

# ----------------------
# Helper Functions
# ----------------------
def serialize_dates(obj):
    """Recursively convert date/datetime objects to ISO strings"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: serialize_dates(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [serialize_dates(item) for item in obj]
    return obj

def format_event(event_dict):
    """Format event document for response with proper JSON serialization"""
    event_dict["_id"] = str(event_dict["_id"])
    
    # Serialize all dates recursively
    event_dict = serialize_dates(event_dict)
    
    return event_dict

# ----------------------
# Public Event Endpoints
# ----------------------
@router.get("/", response_model=dict)
async def get_public_events(
    status: Optional[str] = None,
    is_active: Optional[bool] = True,  # Default to active events only
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = None,
):
    """
    Get all public events (no authentication required)
    - Only returns active events by default
    - Excludes draft events automatically
    """
    try:
        # Build filter query
        filter_query = {
            "is_active": True,  # Always filter for active events
            "status": {"$ne": "draft"}  # Exclude drafts
        }
        
        # Add additional filters if provided
        if status and status != 'all' and status != 'draft':
            filter_query["status"] = status
            
        if search:
            filter_query["$or"] = [
                {"title": {"$regex": search, "$options": "i"}},
                {"location": {"$regex": search, "$options": "i"}},
                {"bio": {"$regex": search, "$options": "i"}}
            ]
        
        # Calculate skip
        skip = (page - 1) * limit
        
        # Get total count
        total = event_collection.count_documents(filter_query)
        
        # Get events
        events_cursor = event_collection.find(filter_query).sort("date_from", 1).skip(skip).limit(limit)
        events = []
        for event in events_cursor:
            events.append(format_event(event))
        
        return {
            "events": events,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if total > 0 else 1
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch events: {str(e)}")


@router.get("/{event_id}", response_model=dict)
async def get_public_event_by_id(event_id: str):
    """
    Get a single public event by ID (no authentication required)
    - Only returns active, non-draft events
    """
    try:
        from bson import ObjectId
        
        if not ObjectId.is_valid(event_id):
            raise HTTPException(status_code=400, detail="Invalid event ID")
        
        event = event_collection.find_one({
            "_id": ObjectId(event_id),
            "is_active": True,
            "status": {"$ne": "draft"}
        })
        
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        
        return format_event(event)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch event: {str(e)}")


@router.get("/status/{status}", response_model=dict)
async def get_events_by_status(
    status: str,
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=100),
):
    """
    Get events by status (published, cancelled, completed)
    - Excludes draft events
    - Only returns active events
    """
    try:
        valid_statuses = ["published", "cancelled", "completed"]
        if status not in valid_statuses:
            raise HTTPException(
                status_code=400, 
                detail=f"Status must be one of: {', '.join(valid_statuses)}"
            )
        
        filter_query = {
            "status": status,
            "is_active": True,
            "status": {"$ne": "draft"}
        }
        
        skip = (page - 1) * limit
        total = event_collection.count_documents(filter_query)
        
        events_cursor = event_collection.find(filter_query).sort("date_from", 1).skip(skip).limit(limit)
        events = [format_event(event) for event in events_cursor]
        
        return {
            "events": events,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if total > 0 else 1
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch events: {str(e)}")