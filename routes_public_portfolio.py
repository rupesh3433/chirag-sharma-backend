import logging
import re
from typing import Optional
from fastapi import APIRouter, Query
from database import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolio", tags=["Public - Portfolio"])


# ── Serializers ───────────────────────────────────────────────

def _serialize_category(doc: dict) -> dict:
    return {
        "id":          str(doc["_id"]),
        "name":        doc.get("name", ""),
        "slug":        doc.get("slug", ""),
        "description": doc.get("description", None),
        "order":       doc.get("order", 0),
    }


def _serialize_image(doc: dict) -> dict:
    created = doc.get("created_at", "")
    return {
        "id":        str(doc["_id"]),
        "title":     doc.get("title", ""),
        "imageUrl":  doc.get("url", ""),
        "category":  doc.get("category", ""),
        "createdAt": created.isoformat() if hasattr(created, "isoformat") else str(created),
    }


def _build_embed_url(doc: dict) -> str:
    embed = doc.get("embed_url", "")
    if embed and "youtube.com/embed/" in embed:
        return embed

    vid_id = doc.get("youtube_id", "")
    if vid_id:
        return f"https://www.youtube.com/embed/{vid_id}"

    raw_url = doc.get("youtube_url", "")
    patterns = [
        r"youtu\.be/([A-Za-z0-9_\-]{11})",
        r"youtube\.com/watch\?.*v=([A-Za-z0-9_\-]{11})",
        r"youtube\.com/embed/([A-Za-z0-9_\-]{11})",
        r"youtube\.com/shorts/([A-Za-z0-9_\-]{11})",
        r"youtube\.com/v/([A-Za-z0-9_\-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_url)
        if match:
            return f"https://www.youtube.com/embed/{match.group(1)}"

    logger.warning(f"Could not build embed URL for video doc _id={doc.get('_id')}")
    return raw_url


def _serialize_video(doc: dict) -> dict:
    created = doc.get("created_at", "")
    return {
        "id":         str(doc["_id"]),
        "title":      doc.get("title", ""),
        "youtubeUrl": _build_embed_url(doc),
        "thumbnail":  doc.get("thumbnail_url", ""),
        "category":   doc.get("category", ""),
        "createdAt":  created.isoformat() if hasattr(created, "isoformat") else str(created),
    }


# ── GET /portfolio/categories ─────────────────────────────────
# Returns all categories EXCEPT "general" (those show only under "All")

@router.get("/categories")
def public_get_categories():
    try:
        cursor = (
            db["portfolio_categories"]
            .find(
                {"slug": {"$ne": "general"}},
                {"_id": 1, "name": 1, "slug": 1, "description": 1, "order": 1},
            )
            .sort("order", 1)
        )
        data = [_serialize_category(doc) for doc in cursor]
        logger.info(f"Public categories: {len(data)} items")
        return {"success": True, "data": data, "total": len(data)}

    except Exception as e:
        logger.error(f"Public categories error: {e}")
        return {"success": False, "data": [], "total": 0, "message": "Failed to load categories."}


# ── GET /portfolio/images ─────────────────────────────────────

@router.get("/images")
def public_get_images(
    category: Optional[str] = Query(None),
):
    try:
        query: dict = {"is_visible": True}
        if category and category != "all":
            query["category"] = category

        cursor = (
            db["portfolio_images"]
            .find(query, {"_id": 1, "title": 1, "url": 1, "category": 1, "created_at": 1})
            .sort([("order", 1), ("created_at", -1)])
        )

        data = [_serialize_image(doc) for doc in cursor]
        logger.info(f"Public images: {len(data)} items (category={category!r})")
        return {"success": True, "data": data, "total": len(data)}

    except Exception as e:
        logger.error(f"Public images error: {e}")
        return {"success": False, "data": [], "total": 0, "message": "Failed to load images."}


# ── GET /portfolio/videos ─────────────────────────────────────

@router.get("/videos")
def public_get_videos(
    category: Optional[str] = Query(None),
):
    try:
        query: dict = {"is_visible": True}
        if category and category not in ("all", "video"):
            query["category"] = category

        cursor = (
            db["portfolio_videos"]
            .find(
                query,
                {
                    "_id": 1,
                    "title": 1,
                    "youtube_url": 1,
                    "youtube_id": 1,
                    "embed_url": 1,
                    "thumbnail_url": 1,
                    "category": 1,
                    "created_at": 1,
                },
            )
            .sort([("order", 1), ("created_at", -1)])
        )

        data = [_serialize_video(doc) for doc in cursor]
        logger.info(f"Public videos: {len(data)} items (category={category!r})")
        return {"success": True, "data": data, "total": len(data)}

    except Exception as e:
        logger.error(f"Public videos error: {e}")
        return {"success": False, "data": [], "total": 0, "message": "Failed to load videos."}