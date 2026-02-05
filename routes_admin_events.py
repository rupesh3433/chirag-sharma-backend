from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse
from typing import List, Optional
import cloudinary
import cloudinary.uploader
from datetime import datetime, date
import os
import json
import uuid

from models import EventCreate, EventUpdate, EventStatus, PriceCategory
from security import get_current_admin
from database import event_collection
from config import CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET

router = APIRouter(prefix="/admin/events", tags=["Admin Events"])

# Configure Cloudinary
cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET
)

# ----------------------
# Helper Functions
# ----------------------
def serialize_dates(obj):
    """Recursively convert date/datetime objects to ISO strings"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, date):
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

def validate_price_categories(price_details):
    """Validate price categories"""
    for category in price_details:
        if category["price"] < 0:
            raise HTTPException(status_code=400, detail="Price cannot be negative")
        if category.get("available_seats", 0) < 0:
            raise HTTPException(status_code=400, detail="Available seats cannot be negative")
    return price_details

def parse_date_to_datetime(date_str):
    """Parse date string and convert to datetime for MongoDB compatibility"""
    try:
        # Try parsing as date (YYYY-MM-DD)
        parsed_date = datetime.strptime(date_str, '%Y-%m-%d')
        return parsed_date  # Return as datetime, not date
    except ValueError:
        try:
            # Try parsing as ISO string
            parsed_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return parsed_date
        except:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {date_str}")

# ----------------------
# Image Upload Endpoints
# ----------------------
@router.post("/upload-image")
async def upload_event_image(
    file: UploadFile = File(...),
    folder: str = "events",
    current_admin: dict = Depends(get_current_admin)
):
    """Upload image to Cloudinary - scales down while preserving aspect ratio"""
    try:
        # Validate file type
        allowed_types = ["image/jpeg", "image/png", "image/jpg", "image/webp", "image/gif"]
        if file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="Only JPEG, PNG, JPG, WebP, and GIF images are allowed")
        
        # Check file size (max 10MB)
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        
        if file_size > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size must be less than 10MB")
        
        # Upload to Cloudinary - scale down while preserving aspect ratio
        result = cloudinary.uploader.upload(
            file.file,
            folder=f"jinnichirag/{folder}",
            resource_type="image",
            transformation=[
                {"width": 1920, "crop": "limit"},  # Max width 1920, maintains aspect ratio
                {"quality": "auto"}
            ]
        )
        
        return {
            "url": result["secure_url"],
            "public_id": result["public_id"],
            "width": result["width"],
            "height": result["height"],
            "format": result["format"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")


@router.delete("/delete-image/{public_id}")
async def delete_event_image(
    public_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """Delete image from Cloudinary"""
    try:
        result = cloudinary.uploader.destroy(public_id)
        return {"success": result.get("result") == "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image deletion failed: {str(e)}")

# ----------------------
# Event CRUD Endpoints
# ----------------------
@router.post("/", response_model=dict)
async def create_event(
    event_data: str = Form(...),
    main_poster: UploadFile = File(...),
    gallery_images: List[UploadFile] = File([]),
    current_admin: dict = Depends(get_current_admin)
):
    """Create a new event with images - scales images while preserving aspect ratio"""
    try:
        # Parse event data
        event_dict = json.loads(event_data)
        
        # Validate required fields
        required_fields = ["title", "bio", "date_from", "date_to", 
                          "time_from", "time_to", "location", "total_seats"]
        for field in required_fields:
            if field not in event_dict or not event_dict[field]:
                raise HTTPException(status_code=400, detail=f"{field.replace('_', ' ').title()} is required")
        
        # Validate and parse dates - CONVERT TO DATETIME FOR MONGODB
        try:
            event_dict["date_from"] = parse_date_to_datetime(event_dict["date_from"])
            event_dict["date_to"] = parse_date_to_datetime(event_dict["date_to"])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
        
        # Validate price details
        if "price_details" not in event_dict or not event_dict["price_details"]:
            raise HTTPException(status_code=400, detail="At least one price category is required")
        
        price_details = validate_price_categories(event_dict["price_details"])
        
        # Upload main poster - scale down while preserving aspect ratio
        main_poster_result = cloudinary.uploader.upload(
            main_poster.file,
            folder="jinnichirag/events/main",
            resource_type="image",
            transformation=[
                {"width": 1920, "crop": "limit"},  # Max width 1920, maintains aspect ratio
                {"quality": "auto"}
            ]
        )
        
        # Upload gallery images - scale down while preserving aspect ratio
        gallery_urls = []
        gallery_public_ids = []
        for image in gallery_images:
            result = cloudinary.uploader.upload(
                image.file,
                folder="jinnichirag/events/gallery",
                resource_type="image",
                transformation=[
                    {"width": 1920, "crop": "limit"},  # Max width 1920, maintains aspect ratio
                    {"quality": "auto"}
                ]
            )
            gallery_urls.append(result["secure_url"])
            gallery_public_ids.append(result["public_id"])
        
        # Prepare event document
        event_doc = {
            **event_dict,
            "price_details": price_details,
            "main_poster_url": main_poster_result["secure_url"],
            "main_poster_public_id": main_poster_result["public_id"],
            "gallery_images": gallery_urls,
            "gallery_public_ids": gallery_public_ids,
            "created_by": current_admin["email"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_active": event_dict.get("is_active", True),
            "status": event_dict.get("status", "draft")
        }
        
        # Insert into database
        result = event_collection.insert_one(event_doc)
        event = event_collection.find_one({"_id": result.inserted_id})
        
        return JSONResponse(
            status_code=201,
            content={
                "message": "Event created successfully",
                "event": format_event(event)
            }
        )
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON data: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create event: {str(e)}")

@router.get("/", response_model=dict)
async def get_all_events(
    status: Optional[str] = None,
    is_active: Optional[bool] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = None,
    current_admin: dict = Depends(get_current_admin)
):
    """Get all events with pagination and filtering"""
    try:
        # Build filter query
        filter_query = {}
        
        if status and status != 'all':
            filter_query["status"] = status
        if is_active is not None:
            filter_query["is_active"] = is_active
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
        events_cursor = event_collection.find(filter_query).sort("created_at", -1).skip(skip).limit(limit)
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
async def get_event_by_id(
    event_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """Get a single event by ID"""
    try:
        from bson import ObjectId
        
        if not ObjectId.is_valid(event_id):
            raise HTTPException(status_code=400, detail="Invalid event ID")
        
        event = event_collection.find_one({"_id": ObjectId(event_id)})
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        
        return format_event(event)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch event: {str(e)}")

@router.put("/{event_id}", response_model=dict)
async def update_event(
    event_id: str,
    event_data: str = Form(...),
    main_poster: Optional[UploadFile] = File(None),
    gallery_images: List[UploadFile] = File([]),
    current_admin: dict = Depends(get_current_admin)
):
    """Update event with optional new images"""
    try:
        from bson import ObjectId
        
        if not ObjectId.is_valid(event_id):
            raise HTTPException(status_code=400, detail="Invalid event ID")
        
        # Check if event exists
        event = event_collection.find_one({"_id": ObjectId(event_id)})
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        
        # Parse event data
        event_dict = json.loads(event_data)
        
        # Prepare update data
        update_data = {}
        
        # Handle basic fields
        if 'title' in event_dict:
            update_data['title'] = event_dict['title']
        if 'bio' in event_dict:
            update_data['bio'] = event_dict['bio']
        if 'time_from' in event_dict:
            update_data['time_from'] = event_dict['time_from']
        if 'time_to' in event_dict:
            update_data['time_to'] = event_dict['time_to']
        if 'location' in event_dict:
            update_data['location'] = event_dict['location']
        if 'location_coords' in event_dict:
            update_data['location_coords'] = event_dict['location_coords']
        if 'total_seats' in event_dict:
            update_data['total_seats'] = event_dict['total_seats']
        if 'is_active' in event_dict:
            update_data['is_active'] = event_dict['is_active']
        if 'status' in event_dict:
            update_data['status'] = event_dict['status']
        
        # Handle date parsing
        if 'date_from' in event_dict:
            update_data['date_from'] = parse_date_to_datetime(event_dict['date_from'])
        if 'date_to' in event_dict:
            update_data['date_to'] = parse_date_to_datetime(event_dict['date_to'])
        
        # Validate and update price details
        if 'price_details' in event_dict:
            update_data['price_details'] = validate_price_categories(event_dict['price_details'])
        
        # Handle main poster update
        if main_poster:
            # Delete old main poster if exists
            if event.get('main_poster_public_id'):
                try:
                    cloudinary.uploader.destroy(event['main_poster_public_id'])
                except Exception as e:
                    print(f"Warning: Failed to delete old main poster: {e}")
            
            # Upload new main poster
            main_poster_result = cloudinary.uploader.upload(
                main_poster.file,
                folder="jinnichirag/events/main",
                resource_type="image",
                transformation=[
                    {"width": 1920, "crop": "limit"},
                    {"quality": "auto"}
                ]
            )
            
            update_data['main_poster_url'] = main_poster_result["secure_url"]
            update_data['main_poster_public_id'] = main_poster_result["public_id"]
        elif 'main_poster_url' in event_dict:
            # Keep existing main poster URL from event_data
            update_data['main_poster_url'] = event_dict['main_poster_url']
        
        # Handle gallery images
        existing_gallery = event_dict.get('gallery_images', [])
        new_gallery_urls = list(existing_gallery)
        new_gallery_public_ids = event.get('gallery_public_ids', [])[:len(existing_gallery)]
        
        # Upload new gallery images
        for image in gallery_images:
            result = cloudinary.uploader.upload(
                image.file,
                folder="jinnichirag/events/gallery",
                resource_type="image",
                transformation=[
                    {"width": 1920, "crop": "limit"},
                    {"quality": "auto"}
                ]
            )
            new_gallery_urls.append(result["secure_url"])
            new_gallery_public_ids.append(result["public_id"])
        
        # Delete removed gallery images from Cloudinary
        old_gallery_urls = event.get('gallery_images', [])
        old_gallery_public_ids = event.get('gallery_public_ids', [])
        for i, old_url in enumerate(old_gallery_urls):
            if old_url not in existing_gallery and i < len(old_gallery_public_ids):
                try:
                    cloudinary.uploader.destroy(old_gallery_public_ids[i])
                except Exception as e:
                    print(f"Warning: Failed to delete gallery image: {e}")
        
        update_data['gallery_images'] = new_gallery_urls
        update_data['gallery_public_ids'] = new_gallery_public_ids
        
        # Add metadata
        update_data['updated_at'] = datetime.utcnow()
        update_data['updated_by'] = current_admin["email"]
        
        # Update in database
        result = event_collection.update_one(
            {"_id": ObjectId(event_id)},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Event not found")
        
        # Fetch updated event
        updated_event = event_collection.find_one({"_id": ObjectId(event_id)})
        
        return {
            "message": "Event updated successfully",
            "event": format_event(updated_event)
        }
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON data: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update event: {str(e)}")


@router.delete("/{event_id}")
async def delete_event(
    event_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """Delete an event and its images"""
    try:
        from bson import ObjectId
        
        if not ObjectId.is_valid(event_id):
            raise HTTPException(status_code=400, detail="Invalid event ID")
        
        # Find event first to get image URLs for cleanup
        event = event_collection.find_one({"_id": ObjectId(event_id)})
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        
        # Delete images from Cloudinary
        try:
            # Delete main poster
            if event.get("main_poster_public_id"):
                cloudinary.uploader.destroy(event["main_poster_public_id"])
            
            # Delete gallery images
            if event.get("gallery_public_ids"):
                for public_id in event["gallery_public_ids"]:
                    cloudinary.uploader.destroy(public_id)
        except Exception as e:
            # Log but don't fail if image deletion fails
            print(f"Warning: Failed to delete images: {e}")
        
        # Delete from database
        result = event_collection.delete_one({"_id": ObjectId(event_id)})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Event not found")
        
        return {"message": "Event deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{event_id}/upload-gallery")
async def upload_gallery_images(
    event_id: str,
    images: List[UploadFile] = File(...),
    current_admin: dict = Depends(get_current_admin)
):
    """Upload additional gallery images to event - scales while preserving aspect ratio"""
    try:
        from bson import ObjectId
        
        if not ObjectId.is_valid(event_id):
            raise HTTPException(status_code=400, detail="Invalid event ID")
        
        # Check if event exists
        event = event_collection.find_one({"_id": ObjectId(event_id)})
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        
        # Upload new images - scale down while preserving aspect ratio
        new_urls = []
        new_public_ids = []
        
        for image in images:
            result = cloudinary.uploader.upload(
                image.file,
                folder="jinnichirag/events/gallery",
                resource_type="image",
                transformation=[
                    {"width": 1920, "crop": "limit"},  # Max width 1920, maintains aspect ratio
                    {"quality": "auto"}
                ]
            )
            new_urls.append(result["secure_url"])
            new_public_ids.append(result["public_id"])
        
        # Update event with new gallery images
        event_collection.update_one(
            {"_id": ObjectId(event_id)},
            {
                "$push": {
                    "gallery_images": {"$each": new_urls},
                    "gallery_public_ids": {"$each": new_public_ids}
                },
                "$set": {
                    "updated_at": datetime.utcnow(),
                    "updated_by": current_admin["email"]
                }
            }
        )
        
        return {
            "message": "Images uploaded successfully",
            "new_images": new_urls
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{event_id}/gallery/{image_index}")
async def delete_gallery_image(
    event_id: str,
    image_index: int,
    current_admin: dict = Depends(get_current_admin)
):
    """Delete a specific gallery image from event"""
    try:
        from bson import ObjectId
        
        if not ObjectId.is_valid(event_id):
            raise HTTPException(status_code=400, detail="Invalid event ID")
        
        # Find event
        event = event_collection.find_one({"_id": ObjectId(event_id)})
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        
        # Check if index is valid
        gallery_images = event.get("gallery_images", [])
        gallery_public_ids = event.get("gallery_public_ids", [])
        
        if image_index < 0 or image_index >= len(gallery_images):
            raise HTTPException(status_code=400, detail="Invalid image index")
        
        # Delete image from Cloudinary
        try:
            if image_index < len(gallery_public_ids):
                cloudinary.uploader.destroy(gallery_public_ids[image_index])
        except Exception as e:
            print(f"Warning: Failed to delete image from Cloudinary: {e}")
        
        # Remove from arrays
        gallery_images.pop(image_index)
        if image_index < len(gallery_public_ids):
            gallery_public_ids.pop(image_index)
        
        # Update event
        event_collection.update_one(
            {"_id": ObjectId(event_id)},
            {
                "$set": {
                    "gallery_images": gallery_images,
                    "gallery_public_ids": gallery_public_ids,
                    "updated_at": datetime.utcnow(),
                    "updated_by": current_admin["email"]
                }
            }
        )
        
        return {"message": "Image deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{event_id}/status")
async def update_event_status(
    event_id: str,
    status: str,
    current_admin: dict = Depends(get_current_admin)
):
    """Update event status"""
    try:
        from bson import ObjectId
        
        if not ObjectId.is_valid(event_id):
            raise HTTPException(status_code=400, detail="Invalid event ID")
        
        # Validate status
        valid_statuses = ["draft", "published", "cancelled", "completed"]
        if status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(valid_statuses)}")
        
        # Update status
        result = event_collection.update_one(
            {"_id": ObjectId(event_id)},
            {
                "$set": {
                    "status": status,
                    "updated_at": datetime.utcnow(),
                    "updated_by": current_admin["email"]
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Event not found")
        
        return {"message": "Event status updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{event_id}/toggle-active")
async def toggle_event_active(
    event_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """Toggle event active status"""
    try:
        from bson import ObjectId
        
        if not ObjectId.is_valid(event_id):
            raise HTTPException(status_code=400, detail="Invalid event ID")
        
        # Find event to get current status
        event = event_collection.find_one({"_id": ObjectId(event_id)})
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        
        # Toggle is_active
        new_status = not event.get("is_active", True)
        
        event_collection.update_one(
            {"_id": ObjectId(event_id)},
            {
                "$set": {
                    "is_active": new_status,
                    "updated_at": datetime.utcnow(),
                    "updated_by": current_admin["email"]
                }
            }
        )
        
        return {
            "message": f"Event {'activated' if new_status else 'deactivated'} successfully",
            "is_active": new_status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))