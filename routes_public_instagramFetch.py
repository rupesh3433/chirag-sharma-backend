# routes_public_instagramFetch.py
# ============================================================
# PRODUCTION-GRADE INSTAGRAM FETCH - PROFILE-CENTRIC ARCHITECTURE
# ============================================================
# ✅ Profile-centric architecture (matches TikTok)
# ✅ /profile is single source of truth
# ✅ /reels is READ-ONLY legacy endpoint
# ✅ Atomic refresh locks (unique index enforced)
# ✅ Lock ownership validation
# ✅ Schema versioning
# ✅ Multi-user support (username as parameter)
# ✅ Enhanced retry queue discipline
# ✅ Improved metrics tracking
# ✅ Async-safe Cloudinary cleanup
# ✅ MongoDB cache with logical TTL (2 days)
# ✅ Safe fallback strategies
# ✅ UTC time everywhere
# ✅ Concurrency-safe retry queue
# ✅ TTL math correctness
# ✅ Namespaced Cloudinary IDs
# ✅ Safe cleanup ordering
# ✅ Fixed lock release pattern
# ✅ Async retry queue processing
# ============================================================

from fastapi import APIRouter, Query, BackgroundTasks
import httpx
import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
import cloudinary
import cloudinary.uploader
from pymongo import ReturnDocument

from config import (
    RAPIDAPI_KEY, 
    INSTAGRAM_RAPIDAPI_HOST,
    CLOUDINARY_CLOUD_NAME,
    CLOUDINARY_API_KEY,
    CLOUDINARY_API_SECRET
)

# Import from enhanced database
from database import (
    instagram_reels_collection,
    instagram_refresh_lock_collection,
    instagram_retry_queue_collection,
    instagram_metrics_collection
)

# Import atomic refresh lock
from utils_refresh_lock import RefreshLock

# ------------------------------------------------------------
# LOGGER
# ------------------------------------------------------------
logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# ROUTER
# ------------------------------------------------------------
router = APIRouter(
    prefix="/public/instagram",
    tags=["Instagram"]
)

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------
DEFAULT_INSTAGRAM_USERNAME = "_jinniechiragmua"  # Default username
CACHE_TTL_DAYS = 2  # Refresh every 2 days
CACHE_TTL_SECONDS = CACHE_TTL_DAYS * 86400  # Exact TTL in seconds
MAX_REELS = 20  # Maximum reels per request
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 60
RETRY_RECLAIM_MINUTES = 10  # Reclaim stuck processing items after 10 minutes

# ------------------------------------------------------------
# CLOUDINARY CONFIG
# ------------------------------------------------------------
if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET
    )
    logger.info("✅ Cloudinary configured for Instagram successfully")
else:
    logger.warning("⚠️ Cloudinary not configured - Instagram thumbnails will not be uploaded")

# ------------------------------------------------------------
# LAZY CLOUDINARY EXECUTOR
# ------------------------------------------------------------
_cloudinary_executor = None

def get_cloudinary_executor():
    """Get or create the Cloudinary thread pool executor."""
    global _cloudinary_executor
    if _cloudinary_executor is None:
        _cloudinary_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="cloudinary-instagram")
        logger.info("✅ Instagram Cloudinary executor initialized")
    return _cloudinary_executor

# ------------------------------------------------------------
# METRICS TRACKING
# ------------------------------------------------------------
class MetricsTracker:
    """Track operation metrics for monitoring and debugging."""
    
    @staticmethod
    def log_refresh(
        username: str,
        source: str,
        reels_count: int,
        cloudinary_uploads: int,
        cloudinary_deletes: int,
        failed_deletes: int,
        duration_seconds: float,
        success: bool,
        error: Optional[str] = None
    ):
        """Log a cache refresh operation."""
        try:
            metric = {
                "username": username,
                "operation": "refresh",
                "source": source,
                "reels_count": reels_count,
                "cloudinary_uploads": cloudinary_uploads,
                "cloudinary_deletes": cloudinary_deletes,
                "failed_deletes": failed_deletes,
                "duration_seconds": round(duration_seconds, 2),
                "success": success,
                "error": error,
                "timestamp": datetime.utcnow()
            }
            
            instagram_metrics_collection.insert_one(metric)
            logger.info(f"📊 Instagram Metrics logged: {metric}")
        except Exception as e:
            logger.error(f"❌ Error logging Instagram metrics: {e}")
    
    @staticmethod
    def log_cloudinary_retry(username: str, public_id: str, success: bool, attempts: int):
        """Log a Cloudinary retry operation."""
        try:
            metric = {
                "username": username,
                "operation": "cloudinary_retry",
                "public_id": public_id,
                "success": success,
                "attempts": attempts,
                "timestamp": datetime.utcnow()
            }
            
            instagram_metrics_collection.insert_one(metric)
        except Exception as e:
            logger.error(f"❌ Error logging Instagram retry metric: {e}")

# ------------------------------------------------------------
# CLOUDINARY RETRY QUEUE
# ------------------------------------------------------------
class CloudinaryRetryQueue:
    """Queue for retrying failed Cloudinary delete operations."""
    
    @staticmethod
    def add_failed_delete(username: str, public_id: str, reel_code: str, error: str):
        """Add a failed delete to the retry queue (idempotent)."""
        try:
            now = datetime.utcnow()
            
            instagram_retry_queue_collection.update_one(
                {
                    "username": username,
                    "public_id": public_id
                },
                {
                    "$setOnInsert": {
                        "username": username,
                        "public_id": public_id,
                        "reel_code": reel_code,
                        "status": "pending",
                        "retry_count": 0,
                        "created_at": now
                    },
                    "$set": {
                        "last_error": error,
                        "next_retry_at": now + timedelta(seconds=RETRY_DELAY_SECONDS)
                    }
                },
                upsert=True
            )
            logger.info(f"📥 Added to Instagram retry queue: {public_id}")
        except Exception as e:
            logger.error(f"❌ Error adding to Instagram retry queue: {e}")
    
    @staticmethod
    async def process_retry_queue_async() -> Dict[str, int]:
        """
        Process pending items in the retry queue with atomic operations (ASYNC).
        Returns dict with success/failure counts.
        """
        try:
            success_count = 0
            failed_count = 0
            
            loop = asyncio.get_event_loop()
            executor = get_cloudinary_executor()
            
            # Process items one-by-one using atomic findOneAndUpdate
            while True:
                now = datetime.utcnow()
                reclaim_threshold = now - timedelta(minutes=RETRY_RECLAIM_MINUTES)
                
                # Atomic claim: find pending item OR stuck processing item
                item = instagram_retry_queue_collection.find_one_and_update(
                    {
                        "$or": [
                            {
                                "status": "pending",
                                "retry_count": {"$lt": MAX_RETRY_ATTEMPTS},
                                "next_retry_at": {"$lte": now}
                            },
                            {
                                "status": "processing",
                                "processing_at": {"$lt": reclaim_threshold}
                            }
                        ]
                    },
                    {
                        "$set": {
                            "status": "processing",
                            "processing_at": now
                        }
                    },
                    return_document=ReturnDocument.AFTER
                )
                
                if not item:
                    # No more items to process
                    break
                
                public_id = item["public_id"]
                retry_count = item["retry_count"]
                
                try:
                    # Attempt to delete (run in executor to avoid blocking)
                    def _delete():
                        return cloudinary.uploader.destroy(public_id, resource_type="image")
                    
                    result = await loop.run_in_executor(executor, _delete)
                    
                    if result.get("result") in ["ok", "not found"]:
                        # Success - remove from queue
                        instagram_retry_queue_collection.delete_one({"_id": item["_id"]})
                        success_count += 1
                        logger.info(f"✅ Instagram retry success: {public_id} (attempt {retry_count + 1})")
                        
                        MetricsTracker.log_cloudinary_retry(
                            item["username"],
                            public_id,
                            success=True,
                            attempts=retry_count + 1
                        )
                    else:
                        raise Exception(f"Cloudinary returned: {result}")
                
                except Exception as e:
                    # Failed - update retry count
                    new_retry_count = retry_count + 1
                    
                    if new_retry_count >= MAX_RETRY_ATTEMPTS:
                        # Max retries reached - mark as failed
                        instagram_retry_queue_collection.update_one(
                            {"_id": item["_id"]},
                            {
                                "$set": {
                                    "status": "failed",
                                    "retry_count": new_retry_count,
                                    "last_error": str(e),
                                    "failed_at": datetime.utcnow()
                                }
                            }
                        )
                        logger.error(f"❌ Max retries reached for {public_id}: {e}")
                        
                        MetricsTracker.log_cloudinary_retry(
                            item["username"],
                            public_id,
                            success=False,
                            attempts=new_retry_count
                        )
                    else:
                        # Schedule next retry with exponential backoff
                        next_retry_delay = RETRY_DELAY_SECONDS * (2 ** new_retry_count)
                        instagram_retry_queue_collection.update_one(
                            {"_id": item["_id"]},
                            {
                                "$set": {
                                    "status": "pending",
                                    "retry_count": new_retry_count,
                                    "last_error": str(e),
                                    "next_retry_at": datetime.utcnow() + timedelta(seconds=next_retry_delay)
                                }
                            }
                        )
                        logger.warning(f"⚠️ Instagram retry {new_retry_count} failed for {public_id}, next in {next_retry_delay}s")
                    
                    failed_count += 1
            
            if success_count > 0 or failed_count > 0:
                logger.info(f"📊 Instagram retry queue processed: {success_count} success, {failed_count} failed")
            
            return {"success": success_count, "failed": failed_count}
            
        except Exception as e:
            logger.error(f"❌ Error processing Instagram retry queue: {e}")
            return {"success": 0, "failed": 0}

# ------------------------------------------------------------
# ASYNC-SAFE CLOUDINARY OPERATIONS
# ------------------------------------------------------------
async def upload_thumbnail_async(thumbnail_url: str, reel_code: str, username: str) -> Optional[Dict[str, str]]:
    """
    Upload Instagram thumbnail to Cloudinary asynchronously.
    Returns dict with 'url' and 'public_id' keys, or None if upload fails.
    """
    if not all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
        logger.debug("⏭️ Cloudinary not configured, skipping Instagram thumbnail upload")
        return None
    
    loop = asyncio.get_event_loop()
    executor = get_cloudinary_executor()
    
    def _upload():
        try:
            # Namespaced public_id to prevent collisions
            public_id = f"instagram/{username}/reel_{reel_code}"
            
            result = cloudinary.uploader.upload(
                thumbnail_url,
                public_id=public_id,
                overwrite=True,
                resource_type="image",
                transformation=[
                    {"width": 600, "height": 1067, "crop": "fill", "quality": "auto:good"}
                ]
            )
            
            cloudinary_url = result.get("secure_url")
            cloudinary_public_id = result.get("public_id")
            
            logger.info(f"✅ Uploaded Instagram thumbnail to Cloudinary: {reel_code} (public_id: {cloudinary_public_id})")
            
            return {
                "url": cloudinary_url,
                "public_id": cloudinary_public_id
            }
        except Exception as e:
            logger.error(f"❌ Failed to upload Instagram thumbnail to Cloudinary for {reel_code}: {e}")
            return None
    
    return await loop.run_in_executor(executor, _upload)


async def delete_old_cloudinary_thumbnails_async(cache_doc: Optional[Dict[str, Any]], username: str) -> Dict[str, int]:
    """
    Delete old Cloudinary thumbnails asynchronously with retry queue support.
    
    Returns:
        Dict with 'deleted', 'failed', 'queued' counts
    """
    if not cache_doc:
        logger.info("ℹ️ No Instagram cache document to clean up")
        return {"deleted": 0, "failed": 0, "queued": 0}
    
    if not all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
        logger.debug("⏭️ Cloudinary not configured, skipping Instagram cleanup")
        return {"deleted": 0, "failed": 0, "queued": 0}
    
    reels = cache_doc.get("reels", [])
    deleted_count = 0
    failed_count = 0
    queued_count = 0
    
    logger.info(f"🗑️ Starting async Cloudinary cleanup for {len(reels)} old Instagram reels...")
    
    loop = asyncio.get_event_loop()
    executor = get_cloudinary_executor()
    
    async def _delete_single(reel: Dict[str, Any]) -> Dict[str, Any]:
        cloudinary_data = reel.get("cloudinary")
        
        # Support both old structure (string) and new structure (dict)
        public_id = None
        if isinstance(cloudinary_data, dict):
            public_id = cloudinary_data.get("public_id")
        elif isinstance(cloudinary_data, str):
            logger.debug(f"⏭️ Skipping cleanup for reel {reel.get('code')} (old URL format)")
            return {"status": "skipped"}
        
        if not public_id:
            logger.debug(f"⏭️ No public_id found for reel {reel.get('code')}")
            return {"status": "skipped"}
        
        def _delete():
            try:
                result = cloudinary.uploader.destroy(public_id, resource_type="image")
                
                if result.get("result") == "ok":
                    logger.info(f"✅ Deleted Instagram Cloudinary asset: {public_id}")
                    return {"status": "deleted", "public_id": public_id}
                elif result.get("result") == "not found":
                    logger.warning(f"⚠️ Instagram Cloudinary asset not found (already deleted?): {public_id}")
                    return {"status": "deleted", "public_id": public_id}  # Treat as success
                else:
                    raise Exception(f"Cloudinary returned: {result}")
            except Exception as e:
                logger.error(f"❌ Error deleting Instagram Cloudinary asset {public_id}: {e}")
                return {
                    "status": "failed",
                    "public_id": public_id,
                    "error": str(e),
                    "reel_code": reel.get("code")
                }
        
        return await loop.run_in_executor(executor, _delete)
    
    # Delete all thumbnails concurrently
    tasks = [_delete_single(reel) for reel in reels]
    results = await asyncio.gather(*tasks)
    
    # Process results
    for result in results:
        if result["status"] == "deleted":
            deleted_count += 1
        elif result["status"] == "failed":
            failed_count += 1
            # Add to retry queue
            CloudinaryRetryQueue.add_failed_delete(
                username=username,
                public_id=result["public_id"],
                reel_code=result.get("reel_code", "unknown"),
                error=result.get("error", "Unknown error")
            )
            queued_count += 1
    
    logger.info(f"🗑️ Instagram async cleanup complete: {deleted_count} deleted, {failed_count} failed, {queued_count} queued for retry")
    
    return {
        "deleted": deleted_count,
        "failed": failed_count,
        "queued": queued_count
    }

# ------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------
def extract_reel_data(media_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract reel data from a media item, handling different structures with defensive guards."""
    
    try:
        # Get the actual media data (could be nested or direct)
        media_data = media_item.get("media", media_item)
        
        if not isinstance(media_data, dict):
            logger.debug("⏭️ Media data is not a dict, skipping")
            return None
        
        # Check if this is a video/reel
        media_type = media_data.get("media_type")
        product_type = media_data.get("product_type")
        
        # Accept reels: media_type 2 (video) or product_type "clips"
        is_reel = (
            media_type == 2 or 
            product_type == "clips" or 
            media_data.get("is_video") is True or
            (media_type == 8 and product_type == "clips")  # Carousel with clips
        )
        
        if not is_reel:
            return None
        
        # Get the reel code/shortcode
        code = media_data.get("code") or media_data.get("shortcode")
        
        if not code:
            logger.warning("⚠️ No code/shortcode found for reel")
            return None
        
        # Get caption with defensive guards
        caption = ""
        caption_obj = media_data.get("caption")
        if caption_obj:
            if isinstance(caption_obj, dict):
                caption = caption_obj.get("text", "")
            elif isinstance(caption_obj, str):
                caption = caption_obj
        
        # Truncate caption for title
        title = caption[:120] + "..." if len(caption) > 120 else caption
        if not title:
            title = "Instagram Reel"
        
        # Extract thumbnail - try multiple locations with defensive guards
        thumbnail = None
        
        # Method 1: Try image_versions2.candidates (highest quality first)
        if "image_versions2" in media_data:
            img_versions = media_data["image_versions2"]
            if isinstance(img_versions, dict) and "candidates" in img_versions:
                candidates = img_versions["candidates"]
                if candidates and isinstance(candidates, list) and len(candidates) > 0:
                    for candidate in candidates:
                        if isinstance(candidate, dict) and candidate.get("url"):
                            thumbnail = candidate["url"]
                            break
        
        # Method 2: Try thumbnail_url field
        if not thumbnail:
            thumbnail = media_data.get("thumbnail_url")
        
        # Method 3: Try video_versions (first frame)
        if not thumbnail and "video_versions" in media_data:
            video_versions = media_data["video_versions"]
            if video_versions and isinstance(video_versions, list) and len(video_versions) > 0:
                for version in video_versions:
                    if isinstance(version, dict) and version.get("url"):
                        thumbnail = version["url"]
                        break
        
        # Method 4: Try image_versions (old structure)
        if not thumbnail and "image_versions" in media_data:
            image_versions = media_data["image_versions"]
            if image_versions and isinstance(image_versions, list) and len(image_versions) > 0:
                first_version = image_versions[0]
                if isinstance(first_version, dict):
                    thumbnail = first_version.get("url")
        
        if not thumbnail:
            logger.warning(f"⚠️ No thumbnail found for reel {code}")
            return None
        
        # Get ID with defensive guard
        reel_id = media_data.get("id", f"reel_{code}")
        if isinstance(reel_id, dict):
            reel_id = reel_id.get("id", f"reel_{code}")
        
        # Build URLs
        post_url = f"https://www.instagram.com/reel/{code}/"
        embed_url = f"https://www.instagram.com/reel/{code}/embed"
        
        # Get engagement metrics with defensive guards
        like_count = media_data.get("like_count", 0)
        comment_count = media_data.get("comment_count", 0)
        play_count = media_data.get("play_count", 0)
        
        # If like_count is a dict with "count" key
        if isinstance(like_count, dict):
            like_count = like_count.get("count", 0)
        
        # If comment_count is a dict with "count" key
        if isinstance(comment_count, dict):
            comment_count = comment_count.get("count", 0)
        
        # Ensure counts are integers
        try:
            like_count = int(like_count) if like_count is not None else 0
            comment_count = int(comment_count) if comment_count is not None else 0
            play_count = int(play_count) if play_count is not None else 0
        except (ValueError, TypeError):
            like_count = 0
            comment_count = 0
            play_count = 0
        
        # Create reel object
        reel = {
            "id": str(reel_id),
            "code": code,
            "title": title,
            "caption": caption[:200] + "..." if len(caption) > 200 else caption,
            "thumbnail": thumbnail,
            "cloudinary": None,  # Will be set after upload (dict with url + public_id)
            "postUrl": post_url,
            "embedUrl": embed_url,
            "likeCount": like_count,
            "commentCount": comment_count,
            "playCount": play_count,
            "takenAt": media_data.get("taken_at", 0),
            "mediaType": media_type,
            "productType": product_type
        }
        
        logger.info(f"🎉 Successfully extracted reel: {code} (likes: {like_count}, plays: {play_count})")
        return reel
        
    except Exception as e:
        logger.error(f"❌ Error extracting reel data: {e}")
        return None


async def fetch_reels_from_rapidapi_async(username: str, count: int = 20) -> List[Dict[str, Any]]:
    """Fetch reels from RapidAPI Instagram endpoint with async Cloudinary uploads."""
    
    if not RAPIDAPI_KEY or not INSTAGRAM_RAPIDAPI_HOST:
        logger.error("❌ RapidAPI credentials missing in config")
        return []
    
    url = f"https://{INSTAGRAM_RAPIDAPI_HOST}/userreels/"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": INSTAGRAM_RAPIDAPI_HOST
    }
    params = {"username_or_id": username}
    
    reels = []
    upload_count = 0
    
    try:
        logger.info(f"🚀 Fetching Instagram reels from RapidAPI for @{username}")
        
        # Fetch from API (async)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers, params=params)
        except httpx.TimeoutException:
            logger.error("⏱️ Instagram reels request timed out")
            return []
        except httpx.ConnectError:
            logger.error("🔌 Instagram reels connection error")
            return []
        except httpx.RequestError as e:
            logger.error(f"🌐 Instagram reels request error: {e}")
            return []
        
        logger.info(f"📡 Instagram reels response status: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"❌ Instagram API request failed: {response.status_code}")
            logger.error(f"📝 Response text: {response.text[:500]}")
            return []
        
        # Parse response
        try:
            payload = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse Instagram JSON response: {e}")
            return []
        
        # Handle different response structures with defensive guards
        items = []
        
        if isinstance(payload, dict):
            if "data" in payload:
                data = payload["data"]
                
                if isinstance(data, dict):
                    if "data" in data and isinstance(data["data"], dict):
                        items = data["data"].get("items", [])
                    elif "items" in data:
                        items = data["items"]
                elif isinstance(data, list):
                    items = data
            
            elif "items" in payload and isinstance(payload["items"], list):
                items = payload["items"]
            
            elif "data" in payload and isinstance(payload.get("data"), dict):
                user_data = payload["data"]
                if "user" in user_data and isinstance(user_data["user"], dict):
                    user = user_data["user"]
                    if "edge_owner_to_timeline_media" in user:
                        edges = user["edge_owner_to_timeline_media"].get("edges", [])
                        items = [edge.get("node", {}) for edge in edges if isinstance(edge, dict) and edge.get("node")]
        
        if not isinstance(items, list):
            logger.warning(f"⚠️ Unexpected items structure: {type(items)}")
            items = []
        
        logger.info(f"🔍 Processing {len(items)} Instagram items...")
        
        # Process each item with defensive error handling
        for i, item in enumerate(items[:count]):  # Limit to requested count
            try:
                reel_data = extract_reel_data(item)
                if reel_data:
                    reels.append(reel_data)
                    logger.info(f"✅ Added reel {i+1}/{len(items)}: {reel_data.get('code')}")
            except Exception as e:
                logger.error(f"❌ Error processing Instagram item {i+1}: {e}")
                continue
        
        # Upload all thumbnails to Cloudinary concurrently
        if reels:
            logger.info(f"☁️ Uploading {len(reels)} Instagram thumbnails to Cloudinary...")
            upload_tasks = [
                upload_thumbnail_async(reel["thumbnail"], reel["code"], username)
                for reel in reels
            ]
            upload_results = await asyncio.gather(*upload_tasks)
            
            # Update reels with Cloudinary data
            for reel, cloudinary_result in zip(reels, upload_results):
                if cloudinary_result:
                    reel["cloudinary"] = cloudinary_result
                    upload_count += 1
            
            logger.info(f"☁️ Instagram Cloudinary uploads complete: {upload_count}/{len(reels)} successful")
        
        logger.info(f"🎯 Successfully extracted {len(reels)} Instagram reels")
        
    except Exception as e:
        logger.error(f"❌ Unexpected error fetching Instagram reels: {e}")
    
    return reels


def get_cached_reels(username: str) -> Optional[Dict[str, Any]]:
    """Get cached reels from MongoDB for a specific username."""
    try:
        cache_doc = instagram_reels_collection.find_one({"username": username})
        
        if cache_doc:
            cached_at = cache_doc.get("cached_at")
            if cached_at:
                age_seconds = (datetime.utcnow() - cached_at).total_seconds()
                age_days = age_seconds / 86400
                logger.info(f"📦 Found cached Instagram reels for @{username} (age: {age_days:.2f} days)")
                return cache_doc
        
        return None
    except Exception as e:
        logger.error(f"❌ MongoDB error getting cached Instagram reels: {e}")
        return None


def should_refresh_cache(cache_doc: Optional[Dict[str, Any]]) -> bool:
    """Check if cache should be refreshed (>2 days old)."""
    if not cache_doc:
        return True
    
    cached_at = cache_doc.get("cached_at")
    if not cached_at:
        return True
    
    age_seconds = (datetime.utcnow() - cached_at).total_seconds()
    should_refresh = age_seconds > CACHE_TTL_SECONDS
    
    if should_refresh:
        age_days = age_seconds / 86400
        logger.info(f"🔄 Instagram cache is {age_days:.2f} days old, refreshing...")
    
    return should_refresh


def save_reels_to_cache(username: str, user_data: Dict[str, Any], reels: List[Dict[str, Any]]) -> bool:
    """Save reels and user data to MongoDB cache using atomic upsert."""
    try:
        cache_doc = {
            "username": username,
            "schema_version": 1,
            "user": user_data,
            "reels": reels,
            "cached_at": datetime.utcnow(),
            "count": len(reels)
        }
        
        # Atomic upsert: update if exists, insert if not
        instagram_reels_collection.update_one(
            {"username": username},
            {"$set": cache_doc},
            upsert=True
        )
        
        logger.info(f"✅ Saved {len(reels)} Instagram reels for @{username} to MongoDB cache (atomic upsert)")
        return True
    except Exception as e:
        logger.error(f"❌ MongoDB error saving Instagram reels: {e}")
        return False


async def refresh_cache_with_cleanup_async(
    cache_doc: Optional[Dict[str, Any]], 
    username: str,
    fresh_user: Dict[str, Any],
    fresh_reels: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Refresh cache with proper async cleanup flow.
    CRITICAL: Save new cache FIRST, then cleanup old assets (best-effort).
    
    Returns:
        Dict with operation results and metrics
    """
    start_time = time.time()
    
    # Step 1: Save new cache FIRST (authoritative)
    save_success = save_reels_to_cache(username, fresh_user, fresh_reels)
    
    # Step 2: Delete old Cloudinary thumbnails (async, best-effort)
    cleanup_stats = await delete_old_cloudinary_thumbnails_async(cache_doc, username)
    
    # Calculate duration
    duration = time.time() - start_time
    
    # Count Cloudinary uploads
    cloudinary_uploads = sum(1 for reel in fresh_reels if reel.get("cloudinary"))
    
    return {
        "save_success": save_success,
        "cloudinary_deletes": cleanup_stats["deleted"],
        "failed_deletes": cleanup_stats["failed"],
        "queued_deletes": cleanup_stats["queued"],
        "cloudinary_uploads": cloudinary_uploads,
        "duration": duration
    }


async def fetch_instagram_user_info_async(username: str) -> Dict[str, Any]:
    """
    Fetch Instagram user profile info (bio, followers, following, posts) using async HTTP.

    Uses RapidAPI Instagram user info endpoint.
    Safe, strict, production-ready.
    """

    logger.info(f"🚀 Fetching Instagram user info for @{username}")

    if not INSTAGRAM_RAPIDAPI_HOST or not RAPIDAPI_KEY:
        raise RuntimeError("Instagram RapidAPI credentials not configured")

    url = f"https://{INSTAGRAM_RAPIDAPI_HOST}/userinfo/"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": INSTAGRAM_RAPIDAPI_HOST
    }
    params = {
        "username_or_id": username
    }

    # ------------------------------------------------------------
    # ASYNC REQUEST
    # ------------------------------------------------------------
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=headers, params=params)
    except httpx.TimeoutException as e:
        logger.error("⏱️ Instagram userinfo request timed out")
        raise RuntimeError("Instagram API timeout") from e
    except httpx.ConnectError as e:
        logger.error("🔌 Instagram API connection error")
        raise RuntimeError("Instagram API connection error") from e
    except httpx.RequestError as e:
        logger.error(f"🌐 Instagram API request error: {e}")
        raise RuntimeError("Instagram API request failure") from e

    logger.info(
        f"📡 Instagram userinfo response | "
        f"status={response.status_code} url={response.url}"
    )

    if response.status_code != 200:
        logger.error(
            f"❌ Instagram userinfo HTTP failure | "
            f"status={response.status_code} body={response.text[:300]}"
        )
        raise RuntimeError(f"Instagram API returned HTTP {response.status_code}")

    # ------------------------------------------------------------
    # JSON PARSING
    # ------------------------------------------------------------
    try:
        payload = response.json()
    except json.JSONDecodeError as e:
        logger.error(
            f"❌ Invalid JSON from Instagram userinfo | "
            f"body={response.text[:300]}"
        )
        raise RuntimeError("Invalid JSON from Instagram API") from e

    data = payload.get("data")
    if not isinstance(data, dict):
        logger.error(f"❌ Missing data object in Instagram response: {payload}")
        raise RuntimeError("Malformed Instagram response (data missing)")

    # ------------------------------------------------------------
    # FIELD EXTRACTION (STRICT)
    # ------------------------------------------------------------
    try:
        followers = int(data.get("follower_count"))
        following = int(data.get("following_count"))
        posts = int(data.get("media_count"))
    except (TypeError, ValueError) as e:
        logger.error(
            f"❌ Invalid Instagram stats | "
            f"followers={data.get('follower_count')} "
            f"following={data.get('following_count')} "
            f"posts={data.get('media_count')}"
        )
        raise RuntimeError("Instagram stats missing or invalid") from e

    bio = (
        data.get("biography")
        or data.get("biography_with_entities", {}).get("raw_text")
        or ""
    )

    # ------------------------------------------------------------
    # FINAL USER OBJECT (CACHE-SAFE)
    # ------------------------------------------------------------
    user = {
        "username": data.get("username") or username,
        "full_name": data.get("full_name"),
        "bio": bio,
        "followers_count": followers,
        "following_count": following,
        "posts_count": posts,
        "is_verified": bool(data.get("is_verified", False)),
        "profile_picture_url": (
            data.get("profile_pic_url_hd")
            or data.get("profile_pic_url")
        )
    }

    logger.info(
        "✅ Instagram user info resolved | "
        f"@{user['username']} "
        f"followers={followers} following={following} posts={posts}"
    )

    return user

# ------------------------------------------------------------
# AUTHORITATIVE ENDPOINT: /profile
# ------------------------------------------------------------
@router.get("/profile")
async def get_profile(
    username: str = Query(DEFAULT_INSTAGRAM_USERNAME, description="Instagram username"),
    count: int = Query(20, ge=1, le=30, description="Number of reels to fetch"),
    background_tasks: BackgroundTasks = None
):
    """
    Fetch Instagram profile with user info and reels.
    
    AUTHORITATIVE ENDPOINT - SINGLE SOURCE OF TRUTH
    - This is the ONLY endpoint that calls RapidAPI
    - This is the ONLY endpoint that uploads to Cloudinary
    - This is the ONLY endpoint that writes to cache
    - This is the ONLY endpoint that acquires refresh locks
    
    Returns:
        Complete profile data with user info and reels
    """
    
    # Try to get from cache
    cache_doc = get_cached_reels(username)
    should_refresh = should_refresh_cache(cache_doc)
    
    # If cache is fresh, return it
    if cache_doc and not should_refresh:
        user = cache_doc.get("user", {})
        reels = cache_doc.get("reels", [])
        cached_at = cache_doc.get("cached_at")
        age_seconds = (datetime.utcnow() - cached_at).total_seconds() if cached_at else 0
        age_days = age_seconds / 86400
        
        logger.info(f"✅ Serving Instagram profile for @{username} from MongoDB cache (age: {age_days:.2f} days)")
        
        # Process retry queue in background
        if background_tasks:
            background_tasks.add_task(CloudinaryRetryQueue.process_retry_queue_async)
        
        return {
            "success": True,
            "source": "mongodb_cache",
            "cached_at": cached_at.isoformat() if cached_at else None,
            "cache_age_days": round(age_days, 2),
            "cache_age_seconds": round(age_seconds, 2),
            "user": user,
            "reels": reels[:count],
            "metrics": None,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    # Cache is old or doesn't exist - try to acquire refresh lock
    refresh_lock = RefreshLock(
        collection=instagram_refresh_lock_collection,
        username=username,
        platform="Instagram"
    )
    
    lock_acquired = refresh_lock.acquire()
    
    if not lock_acquired:
        # Another process is refreshing - serve old cache if available
        if cache_doc and cache_doc.get("user") and cache_doc.get("reels"):
            user = cache_doc.get("user", {})
            reels = cache_doc.get("reels", [])
            cached_at = cache_doc.get("cached_at")
            age_seconds = (datetime.utcnow() - cached_at).total_seconds() if cached_at else 999999
            age_days = age_seconds / 86400
            
            logger.info(f"🔒 Refresh in progress by another process, serving old Instagram cache for @{username} (age: {age_days:.2f} days)")
            
            return {
                "success": True,
                "source": "mongodb_cache_locked",
                "cached_at": cached_at.isoformat() if cached_at else None,
                "cache_age_days": round(age_days, 2),
                "cache_age_seconds": round(age_seconds, 2),
                "message": "Refresh in progress, serving cached data",
                "user": user,
                "reels": reels[:count],
                "metrics": None,
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            return {
                "success": False,
                "source": "none",
                "error": "Refresh in progress and no cache available",
                "user": {},
                "reels": [],
                "metrics": None,
                "timestamp": datetime.utcnow().isoformat()
            }
    
    try:
        # Fetch user info
        logger.info(f"🎬 Fetching fresh Instagram profile for @{username} from RapidAPI")
        user = await fetch_instagram_user_info_async(username)
        
        # Fetch reels with async Cloudinary uploads
        fresh_reels = await fetch_reels_from_rapidapi_async(username, MAX_REELS)
        
        if user and fresh_reels:
            # Sort by taken_at (newest first)
            fresh_reels.sort(key=lambda x: x.get("takenAt", 0), reverse=True)
            
            # Refresh cache with async cleanup (save first, cleanup after)
            refresh_stats = await refresh_cache_with_cleanup_async(cache_doc, username, user, fresh_reels)
            
            # Log metrics
            MetricsTracker.log_refresh(
                username=username,
                source="rapidapi_fresh",
                reels_count=len(fresh_reels),
                cloudinary_uploads=refresh_stats["cloudinary_uploads"],
                cloudinary_deletes=refresh_stats["cloudinary_deletes"],
                failed_deletes=refresh_stats["failed_deletes"],
                duration_seconds=refresh_stats["duration"],
                success=True
            )
            
            logger.info(f"✅ Returning fresh Instagram profile for @{username} with {len(fresh_reels)} reels")
            
            # Process retry queue in background
            if background_tasks:
                background_tasks.add_task(CloudinaryRetryQueue.process_retry_queue_async)
            
            return {
                "success": True,
                "source": "rapidapi_fresh",
                "cached_at": datetime.utcnow().isoformat(),
                "cache_age_days": 0,
                "cache_age_seconds": 0,
                "user": user,
                "reels": fresh_reels[:count],
                "metrics": {
                    "cloudinary_uploads": refresh_stats["cloudinary_uploads"],
                    "cloudinary_deletes": refresh_stats["cloudinary_deletes"],
                    "failed_deletes": refresh_stats["failed_deletes"],
                    "queued_for_retry": refresh_stats["queued_deletes"],
                    "duration_seconds": round(refresh_stats["duration"], 2)
                },
                "timestamp": datetime.utcnow().isoformat()
            }
        
        # API returned empty data - fallback to cache if available
        if cache_doc and cache_doc.get("user") and cache_doc.get("reels"):
            user = cache_doc.get("user", {})
            reels = cache_doc.get("reels", [])
            cached_at = cache_doc.get("cached_at")
            age_seconds = (datetime.utcnow() - cached_at).total_seconds() if cached_at else 999999
            age_days = age_seconds / 86400
            
            logger.warning(f"⚠️ Instagram API returned empty data, using old cache for @{username} (age: {age_days:.2f} days)")
            
            # Log failed refresh
            MetricsTracker.log_refresh(
                username=username,
                source="mongodb_cache_fallback",
                reels_count=len(reels),
                cloudinary_uploads=0,
                cloudinary_deletes=0,
                failed_deletes=0,
                duration_seconds=0,
                success=False,
                error="API returned empty data"
            )
            
            return {
                "success": True,
                "source": "mongodb_cache_fallback",
                "cached_at": cached_at.isoformat() if cached_at else None,
                "cache_age_days": round(age_days, 2),
                "cache_age_seconds": round(age_seconds, 2),
                "warning": "Using old cache - API returned empty data",
                "user": user,
                "reels": reels[:count],
                "metrics": None,
                "timestamp": datetime.utcnow().isoformat()
            }
        
        # Everything failed - return error
        logger.error(f"❌ All sources failed for Instagram @{username} - no cache available and API failed")
        
        MetricsTracker.log_refresh(
            username=username,
            source="none",
            reels_count=0,
            cloudinary_uploads=0,
            cloudinary_deletes=0,
            failed_deletes=0,
            duration_seconds=0,
            success=False,
            error="No cache and API failed"
        )
        
        return {
            "success": False,
            "source": "none",
            "error": "Unable to fetch profile - API unavailable and no cache exists",
            "user": {},
            "reels": [],
            "metrics": None,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Error in Instagram main endpoint: {e}")
        
        # Try to fallback to cache
        if cache_doc and cache_doc.get("user") and cache_doc.get("reels"):
            user = cache_doc.get("user", {})
            reels = cache_doc.get("reels", [])
            cached_at = cache_doc.get("cached_at")
            age_seconds = (datetime.utcnow() - cached_at).total_seconds() if cached_at else 999999
            age_days = age_seconds / 86400
            
            logger.warning(f"⚠️ Exception occurred, using old Instagram cache for @{username} (age: {age_days:.2f} days)")
            
            MetricsTracker.log_refresh(
                username=username,
                source="mongodb_cache_fallback",
                reels_count=len(reels),
                cloudinary_uploads=0,
                cloudinary_deletes=0,
                failed_deletes=0,
                duration_seconds=0,
                success=False,
                error=str(e)
            )
            
            return {
                "success": True,
                "source": "mongodb_cache_fallback",
                "cached_at": cached_at.isoformat() if cached_at else None,
                "cache_age_days": round(age_days, 2),
                "cache_age_seconds": round(age_seconds, 2),
                "warning": f"Using old cache - API error: {str(e)}",
                "user": user,
                "reels": reels[:count],
                "metrics": None,
                "timestamp": datetime.utcnow().isoformat()
            }
        
        return {
            "success": False,
            "source": "none",
            "error": str(e),
            "user": {},
            "reels": [],
            "metrics": None,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    finally:
        # Only release if we acquired it
        if lock_acquired:
            refresh_lock.release()


# ------------------------------------------------------------
# LEGACY ENDPOINT: /reels (READ-ONLY)
# ------------------------------------------------------------
@router.get("/reels")
async def fetch_latest_reels(
    username: str = Query(DEFAULT_INSTAGRAM_USERNAME, description="Instagram username"),
    limit: int = Query(12, ge=1, le=20, description="Number of reels to return"),
    background_tasks: BackgroundTasks = None
):
    """
    LEGACY ENDPOINT - READ-ONLY MODE
    
    This endpoint EXISTS ONLY to avoid breaking existing frontend code.
    It NEVER calls RapidAPI, NEVER touches Cloudinary, NEVER writes to cache.
    It ONLY reads from MongoDB cache.
    
    Frontend should migrate to /profile endpoint.
    """
    
    # Only read from cache - never refresh
    cache_doc = get_cached_reels(username)
    
    if cache_doc:
        reels = cache_doc.get("reels", [])
        cached_at = cache_doc.get("cached_at")
        age_seconds = (datetime.utcnow() - cached_at).total_seconds() if cached_at else 0
        age_days = age_seconds / 86400
        
        logger.info(f"✅ [LEGACY] Serving {len(reels[:limit])} Instagram reels for @{username} from MongoDB cache (age: {age_days:.2f} days)")
        
        # Process retry queue in background
        if background_tasks:
            background_tasks.add_task(CloudinaryRetryQueue.process_retry_queue_async)
        
        return {
            "success": True,
            "count": len(reels[:limit]),
            "reels": reels[:limit],
            "source": "mongodb_cache",
            "cached_at": cached_at.isoformat() if cached_at else None,
            "cache_age_days": round(age_days, 2),
            "cache_age_seconds": round(age_seconds, 2),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    # No cache available - return empty
    logger.warning(f"⚠️ [LEGACY] No cache available for Instagram @{username}")
    
    return {
        "success": False,
        "count": 0,
        "reels": [],
        "source": "none",
        "error": "No cached data available - use /profile endpoint to fetch fresh data",
        "timestamp": datetime.utcnow().isoformat()
    }


# ------------------------------------------------------------
# ADMIN/DEBUG ENDPOINTS
# ------------------------------------------------------------
@router.get("/metrics")
async def get_metrics(
    username: str = Query(None, description="Filter by username (optional)"),
    limit: int = Query(50, ge=1, le=200, description="Number of metrics to return")
):
    """Get recent Instagram operation metrics."""
    try:
        query = {"username": username} if username else {}
        
        metrics = list(
            instagram_metrics_collection
            .find(query)
            .sort("timestamp", -1)
            .limit(limit)
        )
        
        # Convert ObjectId to string
        for metric in metrics:
            metric["_id"] = str(metric["_id"])
            if "timestamp" in metric:
                metric["timestamp"] = metric["timestamp"].isoformat()
        
        return {
            "success": True,
            "count": len(metrics),
            "metrics": metrics,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/retry-queue-status")
async def get_retry_queue_status():
    """Get status of the Instagram Cloudinary retry queue."""
    try:
        pending = instagram_retry_queue_collection.count_documents({"status": "pending"})
        processing = instagram_retry_queue_collection.count_documents({"status": "processing"})
        failed = instagram_retry_queue_collection.count_documents({"status": "failed"})
        
        recent_items = list(
            instagram_retry_queue_collection
            .find()
            .sort("created_at", -1)
            .limit(20)
        )
        
        # Convert ObjectId to string
        for item in recent_items:
            item["_id"] = str(item["_id"])
            for date_field in ["created_at", "next_retry_at", "failed_at", "processing_at"]:
                if date_field in item and item[date_field]:
                    item[date_field] = item[date_field].isoformat()
        
        return {
            "success": True,
            "pending_count": pending,
            "processing_count": processing,
            "failed_count": failed,
            "recent_items": recent_items,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@router.post("/process-retry-queue")
async def process_retry_queue_endpoint():
    """Manually trigger Instagram retry queue processing."""
    try:
        result = await CloudinaryRetryQueue.process_retry_queue_async()
        return {
            "success": True,
            "processed": result["success"] + result["failed"],
            "success_count": result["success"],
            "failed_count": result["failed"],
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/cache-status")
async def get_cache_status(username: str = Query(DEFAULT_INSTAGRAM_USERNAME, description="Instagram username")):
    """Get current cache status for a specific username."""
    cache_doc = get_cached_reels(username)
    
    if not cache_doc:
        return {
            "cached": False,
            "username": username,
            "message": "No cache found",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    cached_at = cache_doc.get("cached_at")
    reels_count = cache_doc.get("count", 0)
    age_seconds = (datetime.utcnow() - cached_at).total_seconds() if cached_at else 0
    age_days = age_seconds / 86400
    needs_refresh = should_refresh_cache(cache_doc)
    
    # Check for active refresh lock
    refresh_lock_active = instagram_refresh_lock_collection.find_one({"username": username}) is not None
    
    return {
        "cached": True,
        "username": username,
        "count": reels_count,
        "cached_at": cached_at.isoformat() if cached_at else None,
        "age_days": round(age_days, 2),
        "age_seconds": round(age_seconds, 2),
        "needs_refresh": needs_refresh,
        "refresh_in_progress": refresh_lock_active,
        "ttl_days": CACHE_TTL_DAYS,
        "ttl_seconds": CACHE_TTL_SECONDS,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/clear-cache")
async def clear_cache(username: str = Query(DEFAULT_INSTAGRAM_USERNAME, description="Instagram username")):
    """Clear the Instagram reels cache for a specific username (MongoDB + Cloudinary)."""
    try:
        # Get cache first to clean Cloudinary
        cache_doc = get_cached_reels(username)
        
        # Delete Cloudinary thumbnails (async)
        cleanup_stats = await delete_old_cloudinary_thumbnails_async(cache_doc, username)
        
        # Delete MongoDB cache
        result = instagram_reels_collection.delete_many({"username": username})
        
        return {
            "success": True,
            "message": f"Instagram cache cleared for @{username}",
            "documents_deleted": result.deleted_count,
            "cloudinary_cleaned": bool(cache_doc),
            "cloudinary_stats": cleanup_stats,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ Error clearing Instagram cache: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@router.post("/force-refresh")
async def force_refresh(
    username: str = Query(DEFAULT_INSTAGRAM_USERNAME, description="Instagram username")
):
    """
    Force refresh the Instagram cache from API (with Cloudinary cleanup).
    Bypasses TTL check and fetches fresh data immediately.
    """
    logger.info(f"🔄 Instagram force refresh requested for @{username}")
    
    # Acquire lock
    refresh_lock = RefreshLock(
        collection=instagram_refresh_lock_collection,
        username=username,
        platform="Instagram"
    )
    
    lock_acquired = refresh_lock.acquire()
    
    if not lock_acquired:
        return {
            "success": False,
            "error": f"Refresh already in progress for @{username}",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    try:
        # Get old cache first for cleanup
        cache_doc = get_cached_reels(username)
        
        # Fetch user info
        user = await fetch_instagram_user_info_async(username)
        
        # Fetch fresh reels
        fresh_reels = await fetch_reels_from_rapidapi_async(username, MAX_REELS)
        
        if not user or not fresh_reels:
            return {
                "success": False,
                "error": "Failed to fetch Instagram profile from API",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        # Sort by taken_at (newest first)
        fresh_reels.sort(key=lambda x: x.get("takenAt", 0), reverse=True)
        
        # Refresh cache with proper cleanup (save first, cleanup after)
        refresh_stats = await refresh_cache_with_cleanup_async(cache_doc, username, user, fresh_reels)
        
        # Log metrics
        MetricsTracker.log_refresh(
            username=username,
            source="force_refresh",
            reels_count=len(fresh_reels),
            cloudinary_uploads=refresh_stats["cloudinary_uploads"],
            cloudinary_deletes=refresh_stats["cloudinary_deletes"],
            failed_deletes=refresh_stats["failed_deletes"],
            duration_seconds=refresh_stats["duration"],
            success=True
        )
        
        return {
            "success": refresh_stats["save_success"],
            "count": len(fresh_reels),
            "message": f"Successfully refreshed Instagram cache for @{username} with {len(fresh_reels)} reels",
            "metrics": {
                "cloudinary_uploads": refresh_stats["cloudinary_uploads"],
                "cloudinary_deletes": refresh_stats["cloudinary_deletes"],
                "failed_deletes": refresh_stats["failed_deletes"],
                "queued_for_retry": refresh_stats["queued_deletes"],
                "duration_seconds": round(refresh_stats["duration"], 2)
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Instagram force refresh failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
    finally:
        # Only release if we acquired it
        if lock_acquired:
            refresh_lock.release()


@router.get("/health")
async def health_check():
    """
    Lightweight health check for Instagram endpoint.
    - Does NOT call RapidAPI
    - Does NOT touch Cloudinary
    - Safe for load balancers / uptime monitors
    """
    try:
        # Check if cache has any data
        cache_count = instagram_reels_collection.count_documents({})
        
        # Check most recent cache entry
        recent_cache = instagram_reels_collection.find_one(
            {},
            sort=[("cached_at", -1)]
        )
        
        if recent_cache and recent_cache.get("cached_at"):
            age_seconds = (datetime.utcnow() - recent_cache["cached_at"]).total_seconds()
            age_days = age_seconds / 86400
            status = "healthy"
        else:
            age_seconds = None
            age_days = None
            status = "degraded" if cache_count == 0 else "healthy"
        
        # Check active locks
        active_locks = instagram_refresh_lock_collection.count_documents({})
        
        # Check retry queue
        retry_queue_pending = instagram_retry_queue_collection.count_documents({"status": "pending"})
        retry_queue_processing = instagram_retry_queue_collection.count_documents({"status": "processing"})
        retry_queue_failed = instagram_retry_queue_collection.count_documents({"status": "failed"})
        
        return {
            "status": status,
            "mongodb_connected": True,
            "cache_entries": cache_count,
            "most_recent_cache_age_days": round(age_days, 2) if age_days is not None else None,
            "most_recent_cache_age_seconds": round(age_seconds, 2) if age_seconds is not None else None,
            "active_refresh_locks": active_locks,
            "retry_queue_pending": retry_queue_pending,
            "retry_queue_processing": retry_queue_processing,
            "retry_queue_failed": retry_queue_failed,
            "ttl_days": CACHE_TTL_DAYS,
            "ttl_seconds": CACHE_TTL_SECONDS,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Instagram health check failed: {e}")
        return {
            "status": "down",
            "mongodb_connected": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/raw")
async def get_raw_response(username: str = Query(DEFAULT_INSTAGRAM_USERNAME, description="Instagram username")):
    """
    Get raw API response for debugging purposes.
    Shows actual response structure from RapidAPI.
    This is Only for Testing.. This is Not Used in this File.
    """
    try:
        url = f"https://{INSTAGRAM_RAPIDAPI_HOST}/userreels/"
        
        headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": INSTAGRAM_RAPIDAPI_HOST
        }
        
        params = {
            "username_or_id": username
        }
        
        logger.info(f"🔧 Instagram debug request to: {url}")
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, headers=headers, params=params)
        
        debug_info = {
            "endpoint": "userreels",
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "url": str(response.url),
            "elapsed": str(response.elapsed)
        }
        
        if response.text:
            try:
                data = response.json()
                debug_info["json_response"] = True
                
                if isinstance(data, dict):
                    debug_info["data_keys"] = list(data.keys())
                    
                    items = []
                    if "data" in data and isinstance(data["data"], dict):
                        if "items" in data["data"]:
                            items = data["data"]["items"]
                        elif "data" in data["data"] and "items" in data["data"]["data"]:
                            items = data["data"]["data"]["items"]
                    
                    if items and len(items) > 0:
                        first_item = items[0]
                        debug_info["first_item_keys"] = list(first_item.keys()) if isinstance(first_item, dict) else str(type(first_item))
                        
                        if isinstance(first_item, dict) and "media" in first_item:
                            media = first_item["media"]
                            debug_info["first_item_media_keys"] = list(media.keys()) if isinstance(media, dict) else str(type(media))
                        
                        debug_info["items_count"] = len(items)
                    
                    # Sample of actual response (first 1000 chars)
                    debug_info["response_sample"] = str(data)[:1000]
                
            except json.JSONDecodeError:
                debug_info["json_response"] = False
                debug_info["response_preview"] = response.text[:1000]
        else:
            debug_info["response"] = "Empty response"
        
        return debug_info
        
    except Exception as e:
        return {
            "error": str(e),
            "rapidapi_url": f"https://{INSTAGRAM_RAPIDAPI_HOST}/userreels/" if INSTAGRAM_RAPIDAPI_HOST else "Not set",
            "rapidapi_key_present": bool(RAPIDAPI_KEY),
            "timestamp": datetime.utcnow().isoformat()
        }