# ============================================================
# ADMIN PORTFOLIO ROUTES
# ============================================================
# Handles:
#   - Upload portfolio images (Cloudinary)
#   - Add YouTube video URLs (unlisted supported)
#   - CRUD for images and videos
#   - Reordering, bulk delete, visibility toggle
#   - Categories management
#   - Stats endpoint
# ============================================================

from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Form
from fastapi.responses import JSONResponse
from typing import Optional, List
from datetime import datetime
from bson import ObjectId
from bson.errors import InvalidId
import logging
import re
import cloudinary
import cloudinary.uploader

from database import db
from routes_admin_auth import get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/portfolio", tags=["Admin - Portfolio"])

# ── Collections ───────────────────────────────────────────────────────────────
portfolio_images_collection = db["portfolio_images"]
portfolio_videos_collection = db["portfolio_videos"]
portfolio_categories_collection = db["portfolio_categories"]

# ── Indexes (called from database.py create_indexes ideally, but safe here too)
from pymongo import ASCENDING, DESCENDING
try:
    portfolio_images_collection.create_index([("order", ASCENDING)], name="pi_order_asc")
    portfolio_images_collection.create_index([("category", ASCENDING)], name="pi_category_asc")
    portfolio_images_collection.create_index([("is_visible", ASCENDING)], name="pi_is_visible_asc")
    portfolio_images_collection.create_index([("created_at", DESCENDING)], name="pi_created_at_desc")
    portfolio_images_collection.create_index([("is_visible", ASCENDING), ("category", ASCENDING)], name="pi_visible_category_compound")

    portfolio_videos_collection.create_index([("order", ASCENDING)], name="pv_order_asc")
    portfolio_videos_collection.create_index([("category", ASCENDING)], name="pv_category_asc")
    portfolio_videos_collection.create_index([("is_visible", ASCENDING)], name="pv_is_visible_asc")
    portfolio_videos_collection.create_index([("created_at", DESCENDING)], name="pv_created_at_desc")
    portfolio_videos_collection.create_index([("youtube_id", ASCENDING)], name="pv_youtube_id_asc")
    portfolio_videos_collection.create_index([("is_visible", ASCENDING), ("category", ASCENDING)], name="pv_visible_category_compound")

    portfolio_categories_collection.create_index([("slug", ASCENDING)], name="pc_slug_unique", unique=True)
    portfolio_categories_collection.create_index([("order", ASCENDING)], name="pc_order_asc")
except Exception as e:
    logger.warning(f"⚠️ Portfolio index creation warning: {e}")


# ============================================================
# HELPERS
# ============================================================

def _oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except (InvalidId, Exception):
        raise HTTPException(status_code=400, detail="Invalid ID format")


def _serialize(doc: dict) -> dict:
    if doc is None:
        return None
    doc["id"] = str(doc.pop("_id"))
    return doc


def _extract_youtube_id(url: str) -> Optional[str]:
    """
    Extract YouTube video ID from various URL formats:
      - https://youtu.be/VIDEO_ID
      - https://www.youtube.com/watch?v=VIDEO_ID
      - https://www.youtube.com/embed/VIDEO_ID
      - https://youtube.com/shorts/VIDEO_ID
    Returns None if URL is not a recognisable YouTube URL.
    """
    patterns = [
        r"youtu\.be/([A-Za-z0-9_\-]{11})",
        r"youtube\.com/watch\?.*v=([A-Za-z0-9_\-]{11})",
        r"youtube\.com/embed/([A-Za-z0-9_\-]{11})",
        r"youtube\.com/shorts/([A-Za-z0-9_\-]{11})",
        r"youtube\.com/v/([A-Za-z0-9_\-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _next_order(collection) -> int:
    last = collection.find_one({}, sort=[("order", DESCENDING)])
    return (last["order"] + 1) if last else 0


# ============================================================
# ── CATEGORY ENDPOINTS ─────────────────────────────────────
# ============================================================

@router.get("/categories", summary="List all portfolio categories")
async def list_categories(admin=Depends(get_current_admin)):
    cats = list(portfolio_categories_collection.find({}).sort("order", 1))
    return {"success": True, "data": [_serialize(c) for c in cats]}


@router.post("/categories", summary="Create a new portfolio category")
async def create_category(
    name: str = Form(...),
    slug: str = Form(...),
    description: Optional[str] = Form(None),
    admin=Depends(get_current_admin)
):
    slug = slug.lower().strip().replace(" ", "-")
    if portfolio_categories_collection.find_one({"slug": slug}):
        raise HTTPException(status_code=409, detail="Category with this slug already exists")

    doc = {
        "name": name.strip(),
        "slug": slug,
        "description": description.strip() if description else None,
        "order": _next_order(portfolio_categories_collection),
        "created_at": datetime.utcnow(),
        "created_by": admin["email"],
    }
    result = portfolio_categories_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    return {"success": True, "message": "Category created", "data": doc}


@router.patch("/categories/{category_id}", summary="Update a portfolio category")
async def update_category(
    category_id: str,
    name: Optional[str] = Form(None),
    slug: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    admin=Depends(get_current_admin)
):
    updates = {"updated_at": datetime.utcnow(), "updated_by": admin["email"]}
    if name:
        updates["name"] = name.strip()
    if slug:
        new_slug = slug.lower().strip().replace(" ", "-")
        existing = portfolio_categories_collection.find_one({"slug": new_slug, "_id": {"$ne": _oid(category_id)}})
        if existing:
            raise HTTPException(status_code=409, detail="Slug already in use")
        updates["slug"] = new_slug
    if description is not None:
        updates["description"] = description.strip()

    result = portfolio_categories_collection.update_one({"_id": _oid(category_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"success": True, "message": "Category updated"}


@router.delete("/categories/{category_id}", summary="Delete a portfolio category")
async def delete_category(category_id: str, admin=Depends(get_current_admin)):
    result = portfolio_categories_collection.delete_one({"_id": _oid(category_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"success": True, "message": "Category deleted"}


@router.patch("/categories/reorder", summary="Reorder categories")
async def reorder_categories(
    ordered_ids: List[str],
    admin=Depends(get_current_admin)
):
    for i, cat_id in enumerate(ordered_ids):
        portfolio_categories_collection.update_one({"_id": _oid(cat_id)}, {"$set": {"order": i}})
    return {"success": True, "message": "Categories reordered"}


# ============================================================
# ── IMAGE ENDPOINTS ────────────────────────────────────────
# ============================================================

@router.get("/images", summary="List all portfolio images (admin view)")
async def list_images_admin(
    category: Optional[str] = Query(None),
    is_visible: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    admin=Depends(get_current_admin)
):
    query = {}
    if category:
        query["category"] = category
    if is_visible is not None:
        query["is_visible"] = is_visible

    total = portfolio_images_collection.count_documents(query)
    images = list(
        portfolio_images_collection
        .find(query)
        .sort("order", 1)
        .skip(skip)
        .limit(limit)
    )
    return {
        "success": True,
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": [_serialize(img) for img in images]
    }


@router.post("/images", summary="Upload a portfolio image to Cloudinary")
async def upload_image(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    category: str = Form("general"),
    is_visible: bool = Form(True),
    admin=Depends(get_current_admin)
):
    allowed_types = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")

    try:
        file_bytes = await file.read()
        upload_result = cloudinary.uploader.upload(
            file_bytes,
            folder="portfolio/images",
            resource_type="image",
            overwrite=False,
        )
    except Exception as e:
        logger.error(f"❌ Cloudinary upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")

    doc = {
        "title": (title or file.filename or "Untitled").strip(),
        "category": category.strip(),
        "cloudinary_public_id": upload_result["public_id"],
        "url": upload_result["secure_url"],
        "width": upload_result.get("width"),
        "height": upload_result.get("height"),
        "format": upload_result.get("format"),
        "bytes": upload_result.get("bytes"),
        "is_visible": is_visible,
        "order": _next_order(portfolio_images_collection),
        "created_at": datetime.utcnow(),
        "created_by": admin["email"],
    }
    result = portfolio_images_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    return {"success": True, "message": "Image uploaded", "data": doc}


@router.post("/images/url", summary="Add a portfolio image via direct URL (no upload)")
async def add_image_by_url(
    url: str = Form(...),
    title: Optional[str] = Form(None),
    category: str = Form("general"),
    is_visible: bool = Form(True),
    admin=Depends(get_current_admin)
):
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid URL")

    doc = {
        "title": (title or "Untitled").strip(),
        "category": category.strip(),
        "cloudinary_public_id": None,
        "url": url.strip(),
        "width": None,
        "height": None,
        "format": None,
        "bytes": None,
        "is_visible": is_visible,
        "order": _next_order(portfolio_images_collection),
        "created_at": datetime.utcnow(),
        "created_by": admin["email"],
    }
    result = portfolio_images_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    return {"success": True, "message": "Image added by URL", "data": doc}


@router.patch("/images/{image_id}", summary="Update a portfolio image's metadata")
async def update_image(
    image_id: str,
    title: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    is_visible: Optional[bool] = Form(None),
    admin=Depends(get_current_admin)
):
    updates = {"updated_at": datetime.utcnow(), "updated_by": admin["email"]}
    if title is not None:
        updates["title"] = title.strip()
    if category is not None:
        updates["category"] = category.strip()
    if is_visible is not None:
        updates["is_visible"] = is_visible

    result = portfolio_images_collection.update_one({"_id": _oid(image_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Image not found")
    return {"success": True, "message": "Image updated"}


@router.patch("/images/{image_id}/toggle-visibility", summary="Toggle image visibility")
async def toggle_image_visibility(image_id: str, admin=Depends(get_current_admin)):
    doc = portfolio_images_collection.find_one({"_id": _oid(image_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Image not found")
    new_val = not doc.get("is_visible", True)
    portfolio_images_collection.update_one(
        {"_id": _oid(image_id)},
        {"$set": {"is_visible": new_val, "updated_at": datetime.utcnow(), "updated_by": admin["email"]}}
    )
    return {"success": True, "is_visible": new_val, "message": f"Image visibility set to {new_val}"}


@router.delete("/images/{image_id}", summary="Delete a portfolio image")
async def delete_image(
    image_id: str,
    delete_from_cloudinary: bool = Query(True),
    admin=Depends(get_current_admin)
):
    doc = portfolio_images_collection.find_one({"_id": _oid(image_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Image not found")

    if delete_from_cloudinary and doc.get("cloudinary_public_id"):
        try:
            cloudinary.uploader.destroy(doc["cloudinary_public_id"])
        except Exception as e:
            logger.warning(f"⚠️ Cloudinary delete warning: {e}")

    portfolio_images_collection.delete_one({"_id": _oid(image_id)})
    return {"success": True, "message": "Image deleted"}


@router.post("/images/bulk-delete", summary="Bulk delete portfolio images")
async def bulk_delete_images(
    image_ids: List[str],
    delete_from_cloudinary: bool = Query(True),
    admin=Depends(get_current_admin)
):
    oids = [_oid(i) for i in image_ids]
    docs = list(portfolio_images_collection.find({"_id": {"$in": oids}}))

    if delete_from_cloudinary:
        for doc in docs:
            if doc.get("cloudinary_public_id"):
                try:
                    cloudinary.uploader.destroy(doc["cloudinary_public_id"])
                except Exception as e:
                    logger.warning(f"⚠️ Cloudinary delete warning for {doc['cloudinary_public_id']}: {e}")

    result = portfolio_images_collection.delete_many({"_id": {"$in": oids}})
    return {"success": True, "deleted_count": result.deleted_count, "message": f"Deleted {result.deleted_count} images"}


@router.patch("/images/reorder", summary="Reorder portfolio images")
async def reorder_images(
    ordered_ids: List[str],
    admin=Depends(get_current_admin)
):
    for i, img_id in enumerate(ordered_ids):
        portfolio_images_collection.update_one({"_id": _oid(img_id)}, {"$set": {"order": i}})
    return {"success": True, "message": "Images reordered"}


@router.patch("/images/bulk-category", summary="Bulk update category for images")
async def bulk_update_image_category(
    image_ids: List[str],
    category: str = Form(...),
    admin=Depends(get_current_admin)
):
    oids = [_oid(i) for i in image_ids]
    result = portfolio_images_collection.update_many(
        {"_id": {"$in": oids}},
        {"$set": {"category": category.strip(), "updated_at": datetime.utcnow(), "updated_by": admin["email"]}}
    )
    return {"success": True, "updated_count": result.modified_count, "message": f"Updated {result.modified_count} images"}


# ============================================================
# ── VIDEO ENDPOINTS ────────────────────────────────────────
# ============================================================

@router.get("/videos", summary="List all portfolio videos (admin view)")
async def list_videos_admin(
    category: Optional[str] = Query(None),
    is_visible: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    admin=Depends(get_current_admin)
):
    query = {}
    if category:
        query["category"] = category
    if is_visible is not None:
        query["is_visible"] = is_visible

    total = portfolio_videos_collection.count_documents(query)
    videos = list(
        portfolio_videos_collection
        .find(query)
        .sort("order", 1)
        .skip(skip)
        .limit(limit)
    )
    return {
        "success": True,
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": [_serialize(v) for v in videos]
    }


@router.post("/videos", summary="Add a YouTube video URL to portfolio")
async def add_video(
    youtube_url: str = Form(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    category: str = Form("general"),
    is_visible: bool = Form(True),
    admin=Depends(get_current_admin)
):
    youtube_id = _extract_youtube_id(youtube_url.strip())
    if not youtube_id:
        raise HTTPException(
            status_code=400,
            detail="Invalid YouTube URL. Supported formats: youtu.be/ID, youtube.com/watch?v=ID, youtube.com/embed/ID, youtube.com/shorts/ID"
        )

    thumbnail_url = f"https://img.youtube.com/vi/{youtube_id}/maxresdefault.jpg"
    embed_url = f"https://www.youtube.com/embed/{youtube_id}"

    doc = {
        "title": (title or f"Video {youtube_id}").strip(),
        "description": description.strip() if description else None,
        "category": category.strip(),
        "youtube_url": youtube_url.strip(),
        "youtube_id": youtube_id,
        "embed_url": embed_url,
        "thumbnail_url": thumbnail_url,
        "is_visible": is_visible,
        "order": _next_order(portfolio_videos_collection),
        "created_at": datetime.utcnow(),
        "created_by": admin["email"],
    }
    result = portfolio_videos_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    return {"success": True, "message": "Video added", "data": doc}


@router.patch("/videos/{video_id}", summary="Update portfolio video metadata")
async def update_video(
    video_id: str,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    youtube_url: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    is_visible: Optional[bool] = Form(None),
    admin=Depends(get_current_admin)
):
    updates = {"updated_at": datetime.utcnow(), "updated_by": admin["email"]}
    if title is not None:
        updates["title"] = title.strip()
    if description is not None:
        updates["description"] = description.strip()
    if category is not None:
        updates["category"] = category.strip()
    if is_visible is not None:
        updates["is_visible"] = is_visible
    if youtube_url is not None:
        youtube_id = _extract_youtube_id(youtube_url.strip())
        if not youtube_id:
            raise HTTPException(status_code=400, detail="Invalid YouTube URL")
        updates["youtube_url"] = youtube_url.strip()
        updates["youtube_id"] = youtube_id
        updates["embed_url"] = f"https://www.youtube.com/embed/{youtube_id}"
        updates["thumbnail_url"] = f"https://img.youtube.com/vi/{youtube_id}/maxresdefault.jpg"

    result = portfolio_videos_collection.update_one({"_id": _oid(video_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"success": True, "message": "Video updated"}


@router.patch("/videos/{video_id}/toggle-visibility", summary="Toggle video visibility")
async def toggle_video_visibility(video_id: str, admin=Depends(get_current_admin)):
    doc = portfolio_videos_collection.find_one({"_id": _oid(video_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Video not found")
    new_val = not doc.get("is_visible", True)
    portfolio_videos_collection.update_one(
        {"_id": _oid(video_id)},
        {"$set": {"is_visible": new_val, "updated_at": datetime.utcnow(), "updated_by": admin["email"]}}
    )
    return {"success": True, "is_visible": new_val, "message": f"Video visibility set to {new_val}"}


@router.delete("/videos/{video_id}", summary="Delete a portfolio video")
async def delete_video(video_id: str, admin=Depends(get_current_admin)):
    result = portfolio_videos_collection.delete_one({"_id": _oid(video_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"success": True, "message": "Video deleted"}


@router.post("/videos/bulk-delete", summary="Bulk delete portfolio videos")
async def bulk_delete_videos(
    video_ids: List[str],
    admin=Depends(get_current_admin)
):
    oids = [_oid(i) for i in video_ids]
    result = portfolio_videos_collection.delete_many({"_id": {"$in": oids}})
    return {"success": True, "deleted_count": result.deleted_count, "message": f"Deleted {result.deleted_count} videos"}


@router.patch("/videos/reorder", summary="Reorder portfolio videos")
async def reorder_videos(
    ordered_ids: List[str],
    admin=Depends(get_current_admin)
):
    for i, vid_id in enumerate(ordered_ids):
        portfolio_videos_collection.update_one({"_id": _oid(vid_id)}, {"$set": {"order": i}})
    return {"success": True, "message": "Videos reordered"}


@router.patch("/videos/bulk-category", summary="Bulk update category for videos")
async def bulk_update_video_category(
    video_ids: List[str],
    category: str = Form(...),
    admin=Depends(get_current_admin)
):
    oids = [_oid(i) for i in video_ids]
    result = portfolio_videos_collection.update_many(
        {"_id": {"$in": oids}},
        {"$set": {"category": category.strip(), "updated_at": datetime.utcnow(), "updated_by": admin["email"]}}
    )
    return {"success": True, "updated_count": result.modified_count}


# ============================================================
# ── STATS ENDPOINT ─────────────────────────────────────────
# ============================================================

@router.get("/stats", summary="Portfolio overall stats for admin dashboard")
async def portfolio_stats(admin=Depends(get_current_admin)):
    total_images = portfolio_images_collection.count_documents({})
    visible_images = portfolio_images_collection.count_documents({"is_visible": True})
    hidden_images = total_images - visible_images

    total_videos = portfolio_videos_collection.count_documents({})
    visible_videos = portfolio_videos_collection.count_documents({"is_visible": True})
    hidden_videos = total_videos - visible_videos

    total_categories = portfolio_categories_collection.count_documents({})

    # Images per category
    image_by_category = list(portfolio_images_collection.aggregate([
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]))
    video_by_category = list(portfolio_videos_collection.aggregate([
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]))

    return {
        "success": True,
        "data": {
            "images": {
                "total": total_images,
                "visible": visible_images,
                "hidden": hidden_images,
                "by_category": [{"category": r["_id"], "count": r["count"]} for r in image_by_category],
            },
            "videos": {
                "total": total_videos,
                "visible": visible_videos,
                "hidden": hidden_videos,
                "by_category": [{"category": r["_id"], "count": r["count"]} for r in video_by_category],
            },
            "categories": {
                "total": total_categories,
            }
        }
    }


# ============================================================
# ── SINGLE ITEM GETTERS (admin detail) ─────────────────────
# ============================================================

@router.get("/images/{image_id}", summary="Get single portfolio image by ID (admin)")
async def get_image_admin(image_id: str, admin=Depends(get_current_admin)):
    doc = portfolio_images_collection.find_one({"_id": _oid(image_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Image not found")
    return {"success": True, "data": _serialize(doc)}


@router.get("/videos/{video_id}", summary="Get single portfolio video by ID (admin)")
async def get_video_admin(video_id: str, admin=Depends(get_current_admin)):
    doc = portfolio_videos_collection.find_one({"_id": _oid(video_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"success": True, "data": _serialize(doc)}