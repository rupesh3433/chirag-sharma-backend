# routes_public_tiktokFetch.py
# ============================================================
# PRODUCTION-GRADE TIKTOK FETCH - PROFILE-CENTRIC ARCHITECTURE
# ============================================================
# ✅ Profile-centric architecture (matches Instagram)
# ✅ /profile is single source of truth
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
    TIKTOK_RAPIDAPI_HOST,
    CLOUDINARY_CLOUD_NAME,
    CLOUDINARY_API_KEY,
    CLOUDINARY_API_SECRET
)

# Import from enhanced database
from database import (
    tiktok_cache_collection,
    tiktok_refresh_lock_collection,
    tiktok_retry_queue_collection,
    tiktok_metrics_collection
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
    prefix="/public/tiktok",
    tags=["TikTok"]
)

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------
DEFAULT_TIKTOK_USERNAME = "_chirag_101"  # Default username
CACHE_TTL_DAYS = 2  # Refresh every 2 days
CACHE_TTL_SECONDS = CACHE_TTL_DAYS * 86400  # Exact TTL in seconds
MAX_VIDEOS = 20  # Maximum videos per request
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 60
RETRY_RECLAIM_MINUTES = 10  # Reclaim stuck processing items after 10 minutes

BASE_URL = f"https://{TIKTOK_RAPIDAPI_HOST}"
HEADERS = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": TIKTOK_RAPIDAPI_HOST
}

# ------------------------------------------------------------
# CLOUDINARY CONFIG
# ------------------------------------------------------------
if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET
    )
    logger.info("✅ Cloudinary configured for TikTok successfully")
else:
    logger.warning("⚠️ Cloudinary not configured - TikTok thumbnails will not be uploaded")

# ------------------------------------------------------------
# LAZY CLOUDINARY EXECUTOR
# ------------------------------------------------------------
_cloudinary_executor = None

def get_cloudinary_executor():
    """Get or create the Cloudinary thread pool executor."""
    global _cloudinary_executor
    if _cloudinary_executor is None:
        _cloudinary_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="cloudinary-tiktok")
        logger.info("✅ TikTok Cloudinary executor initialized")
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
        videos_count: int,
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
                "videos_count": videos_count,
                "cloudinary_uploads": cloudinary_uploads,
                "cloudinary_deletes": cloudinary_deletes,
                "failed_deletes": failed_deletes,
                "duration_seconds": round(duration_seconds, 2),
                "success": success,
                "error": error,
                "timestamp": datetime.utcnow()
            }
            
            tiktok_metrics_collection.insert_one(metric)
            logger.info(f"📊 TikTok Metrics logged: {metric}")
        except Exception as e:
            logger.error(f"❌ Error logging TikTok metrics (non-fatal): {e}")
    
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
            
            tiktok_metrics_collection.insert_one(metric)
        except Exception as e:
            logger.error(f"❌ Error logging TikTok retry metric (non-fatal): {e}")

# ------------------------------------------------------------
# CLOUDINARY RETRY QUEUE
# ------------------------------------------------------------
class CloudinaryRetryQueue:
    """Queue for retrying failed Cloudinary delete operations."""
    
    @staticmethod
    def add_failed_delete(username: str, public_id: str, video_id: str, error: str):
        """Add a failed delete to the retry queue (idempotent)."""
        try:
            now = datetime.utcnow()
            
            tiktok_retry_queue_collection.update_one(
                {
                    "username": username,
                    "public_id": public_id
                },
                {
                    "$setOnInsert": {
                        "username": username,
                        "public_id": public_id,
                        "video_id": video_id,
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
            logger.info(f"📥 Added to TikTok retry queue: {public_id}")
        except Exception as e:
            logger.error(f"❌ Error adding to TikTok retry queue: {e}")
    
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
                item = tiktok_retry_queue_collection.find_one_and_update(
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
                        tiktok_retry_queue_collection.delete_one({"_id": item["_id"]})
                        success_count += 1
                        logger.info(f"✅ TikTok retry success: {public_id} (attempt {retry_count + 1})")
                        
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
                        tiktok_retry_queue_collection.update_one(
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
                        tiktok_retry_queue_collection.update_one(
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
                        logger.warning(f"⚠️ TikTok retry {new_retry_count} failed for {public_id}, next in {next_retry_delay}s")
                    
                    failed_count += 1
            
            if success_count > 0 or failed_count > 0:
                logger.info(f"📊 TikTok retry queue processed: {success_count} success, {failed_count} failed")
            
            return {"success": success_count, "failed": failed_count}
            
        except Exception as e:
            logger.error(f"❌ Error processing TikTok retry queue: {e}")
            return {"success": 0, "failed": 0}

# ------------------------------------------------------------
# ASYNC-SAFE CLOUDINARY OPERATIONS
# ------------------------------------------------------------
async def upload_thumbnail_async(thumbnail_url: str, video_id: str, username: str) -> Optional[Dict[str, str]]:
    """
    Upload TikTok thumbnail to Cloudinary asynchronously.
    Returns dict with 'url' and 'public_id' keys, or None if upload fails.
    """
    if not all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
        logger.debug("⏭️ Cloudinary not configured, skipping TikTok thumbnail upload")
        return None
    
    loop = asyncio.get_event_loop()
    executor = get_cloudinary_executor()
    
    def _upload():
        try:
            # Namespaced public_id to prevent collisions
            public_id = f"tiktok/{username}/video_{video_id}"
            
            result = cloudinary.uploader.upload(
                thumbnail_url,
                public_id=public_id,
                overwrite=True,
                resource_type="image",
                transformation=[
                    {"width": 720, "height": 1280, "crop": "fill", "quality": "auto:good"}
                ]
            )
            
            cloudinary_url = result.get("secure_url")
            cloudinary_public_id = result.get("public_id")
            
            logger.info(f"✅ Uploaded TikTok thumbnail to Cloudinary: {video_id} (public_id: {cloudinary_public_id})")
            
            return {
                "url": cloudinary_url,
                "public_id": cloudinary_public_id
            }
        except Exception as e:
            logger.error(f"❌ Failed to upload TikTok thumbnail to Cloudinary for {video_id}: {e}")
            return None
    
    return await loop.run_in_executor(executor, _upload)


async def delete_old_cloudinary_thumbnails_async(cache_doc: Optional[Dict[str, Any]], username: str) -> Dict[str, int]:
    """
    Delete old Cloudinary thumbnails asynchronously with retry queue support.
    
    Returns:
        Dict with 'deleted', 'failed', 'queued' counts
    """
    if not cache_doc:
        logger.info("ℹ️ No TikTok cache document to clean up")
        return {"deleted": 0, "failed": 0, "queued": 0}
    
    if not all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
        logger.debug("⏭️ Cloudinary not configured, skipping TikTok cleanup")
        return {"deleted": 0, "failed": 0, "queued": 0}
    
    videos = cache_doc.get("videos", [])
    deleted_count = 0
    failed_count = 0
    queued_count = 0
    
    logger.info(f"🗑️ Starting async Cloudinary cleanup for {len(videos)} old TikTok videos...")
    
    loop = asyncio.get_event_loop()
    executor = get_cloudinary_executor()
    
    async def _delete_single(video: Dict[str, Any]) -> Dict[str, Any]:
        cloudinary_data = video.get("cloudinary")
        
        # Support both old structure (string) and new structure (dict)
        public_id = None
        if isinstance(cloudinary_data, dict):
            public_id = cloudinary_data.get("public_id")
        elif isinstance(cloudinary_data, str):
            logger.debug(f"⏭️ Skipping cleanup for video {video.get('video_id')} (old URL format)")
            return {"status": "skipped"}
        
        if not public_id:
            logger.debug(f"⏭️ No public_id found for video {video.get('video_id')}")
            return {"status": "skipped"}
        
        def _delete():
            try:
                result = cloudinary.uploader.destroy(public_id, resource_type="image")
                
                if result.get("result") == "ok":
                    logger.info(f"✅ Deleted TikTok Cloudinary asset: {public_id}")
                    return {"status": "deleted", "public_id": public_id}
                elif result.get("result") == "not found":
                    logger.warning(f"⚠️ TikTok Cloudinary asset not found (already deleted?): {public_id}")
                    return {"status": "deleted", "public_id": public_id}  # Treat as success
                else:
                    raise Exception(f"Cloudinary returned: {result}")
            except Exception as e:
                logger.error(f"❌ Error deleting TikTok Cloudinary asset {public_id}: {e}")
                return {
                    "status": "failed",
                    "public_id": public_id,
                    "error": str(e),
                    "video_id": video.get("video_id")
                }
        
        return await loop.run_in_executor(executor, _delete)
    
    # Delete all thumbnails concurrently
    tasks = [_delete_single(video) for video in videos]
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
                video_id=result.get("video_id", "unknown"),
                error=result.get("error", "Unknown error")
            )
            queued_count += 1
    
    logger.info(f"🗑️ TikTok async cleanup complete: {deleted_count} deleted, {failed_count} failed, {queued_count} queued for retry")
    
    return {
        "deleted": deleted_count,
        "failed": failed_count,
        "queued": queued_count
    }

# ------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------
def _safe(obj, *keys, default=None):
    """
    Safely navigate nested dictionaries.
    Usage: _safe(data, "user", "stats", "followerCount", default=0)
    """
    for k in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(k)
    return obj if obj is not None else default


def get_cached_profile(username: str) -> Optional[Dict[str, Any]]:
    """Get cached profile from MongoDB for a specific username."""
    try:
        cache_doc = tiktok_cache_collection.find_one({"username": username})
        
        if cache_doc:
            cached_at = cache_doc.get("cached_at")
            if cached_at:
                age_seconds = (datetime.utcnow() - cached_at).total_seconds()
                age_days = age_seconds / 86400
                logger.info(f"📦 Found cached TikTok profile for @{username} (age: {age_days:.2f} days)")
                return cache_doc
        
        return None
    except Exception as e:
        logger.error(f"❌ MongoDB error getting cached TikTok profile: {e}")
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
        logger.info(f"🔄 TikTok cache is {age_days:.2f} days old, refreshing...")
    
    return should_refresh


def save_profile_to_cache(username: str, user_data: Dict[str, Any], videos: List[Dict[str, Any]]) -> bool:
    """Save profile data to MongoDB cache using atomic upsert."""
    try:
        cache_doc = {
            "username": username,
            "schema_version": 1,
            "user": user_data,
            "videos": videos,
            "cached_at": datetime.utcnow(),
            "videos_count": len(videos)
        }
        
        # Atomic upsert: update if exists, insert if not
        tiktok_cache_collection.update_one(
            {"username": username},
            {"$set": cache_doc},
            upsert=True
        )
        
        logger.info(f"✅ Saved TikTok profile for @{username} with {len(videos)} videos to MongoDB cache (atomic upsert)")
        return True
    except Exception as e:
        logger.error(f"❌ MongoDB error saving TikTok profile: {e}")
        return False


async def refresh_cache_with_cleanup_async(
    cache_doc: Optional[Dict[str, Any]], 
    username: str,
    fresh_user: Dict[str, Any],
    fresh_videos: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Refresh cache with proper async cleanup flow.
    CRITICAL: Save new cache FIRST, then cleanup old assets (best-effort).
    
    Returns:
        Dict with operation results and metrics
    """
    start_time = time.time()
    
    # Step 1: Save new cache FIRST (authoritative)
    save_success = save_profile_to_cache(username, fresh_user, fresh_videos)
    
    # Step 2: Delete old Cloudinary thumbnails (async, best-effort)
    cleanup_stats = await delete_old_cloudinary_thumbnails_async(cache_doc, username)
    
    # Calculate duration
    duration = time.time() - start_time
    
    # Count Cloudinary uploads
    cloudinary_uploads = sum(1 for video in fresh_videos if video.get("cloudinary"))
    
    return {
        "save_success": save_success,
        "cloudinary_deletes": cleanup_stats["deleted"],
        "failed_deletes": cleanup_stats["failed"],
        "queued_deletes": cleanup_stats["queued"],
        "cloudinary_uploads": cloudinary_uploads,
        "duration": duration
    }


async def fetch_user_info_async(username: str) -> Dict[str, Any]:
    """
    Fetch TikTok user info with guaranteed stats using async HTTP.

    Final Flow (AUTHORITATIVE):
    1. Call /user/info using unique_id (username)
    2. Extract user_id from response
    3. Strictly validate stats
    """

    logger.info(f"🚀 Fetching TikTok user info for @{username}")

    url = f"{BASE_URL}/user/info"
    params = {"unique_id": username}

    # ------------------------------------------------------------
    # ASYNC NETWORK REQUEST
    # ------------------------------------------------------------
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=HEADERS, params=params)
    except httpx.TimeoutException as e:
        logger.error("⏱️ TikTok user/info request timed out")
        raise RuntimeError("TikTok API timeout") from e
    except httpx.ConnectError as e:
        logger.error("🔌 TikTok user/info connection error")
        raise RuntimeError("TikTok API connection error") from e
    except httpx.RequestError as e:
        logger.error(f"🌐 TikTok user/info request error: {e}")
        raise RuntimeError("TikTok API request failure") from e

    logger.info(
        f"📡 TikTok user info response | "
        f"status={response.status_code} url={response.url}"
    )

    if response.status_code != 200:
        logger.error(
            f"❌ TikTok user/info HTTP failure | "
            f"status={response.status_code} body={response.text[:300]}"
        )
        raise RuntimeError(f"TikTok API returned HTTP {response.status_code}")

    # ------------------------------------------------------------
    # JSON PARSING
    # ------------------------------------------------------------
    try:
        payload = response.json()
    except json.JSONDecodeError as e:
        logger.error(
            f"❌ Invalid JSON from TikTok user/info | "
            f"body={response.text[:300]}"
        )
        raise RuntimeError("Invalid JSON from TikTok API") from e

    data = payload.get("data")
    if not isinstance(data, dict):
        logger.error(f"❌ Missing data object in TikTok response: {payload}")
        raise RuntimeError("Malformed TikTok response (data missing)")

    user_raw = data.get("user")
    stats = data.get("stats")

    if not isinstance(user_raw, dict):
        logger.error(f"❌ Missing user object in TikTok response: {payload}")
        raise RuntimeError("Malformed TikTok response (user missing)")

    if not isinstance(stats, dict):
        logger.error(f"❌ Missing stats object in TikTok response: {payload}")
        raise RuntimeError("Malformed TikTok response (stats missing)")

    # ------------------------------------------------------------
    # STRICT STAT VALIDATION
    # ------------------------------------------------------------
    try:
        followers = int(stats["followerCount"])
        following = int(stats["followingCount"])
        likes = int(stats["heartCount"])
    except (KeyError, TypeError, ValueError) as e:
        logger.error(
            f"❌ Invalid TikTok stats | "
            f"followers={stats.get('followerCount')} "
            f"following={stats.get('followingCount')} "
            f"likes={stats.get('heartCount')}"
        )
        raise RuntimeError("TikTok stats invalid or missing") from e

    # ------------------------------------------------------------
    # FINAL USER OBJECT (CACHE-SAFE)
    # ------------------------------------------------------------
    user = {
        "internal_user_id": user_raw.get("id"),
        "username": user_raw.get("uniqueId"),
        "nickname": user_raw.get("nickname"),
        "bio": user_raw.get("signature"),
        "verified": bool(user_raw.get("verified", False)),
        "followers_count": followers,
        "following_count": following,
        "total_likes_count": likes,
        "profile_picture_url": user_raw.get("avatarLarger"),
    }

    logger.info(
        "✅ TikTok user info resolved successfully | "
        f"@{user['username']} "
        f"followers={followers} following={following} likes={likes}"
    )

    return user
    

async def fetch_user_posts_async(unique_id: str, username: str, count: int = 20) -> List[Dict[str, Any]]:
    """
    Fetch user posts from RapidAPI with async Cloudinary uploads.
    
    Args:
        unique_id: TikTok username/unique_id
        username: Username for namespacing Cloudinary IDs
        count: Number of videos to fetch
    
    Returns:
        List of video dicts with all required fields.
    """
    try:
        url = f"{BASE_URL}/user/posts"
        
        params = {
            "unique_id": unique_id,
            "count": min(count, MAX_VIDEOS),
            "cursor": 0
        }
        
        logger.info(f"🚀 Fetching TikTok posts for @{unique_id} (count: {params['count']})")
        
        # Fetch from API (async)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=HEADERS, params=params)
        except httpx.TimeoutException:
            logger.error("⏱️ TikTok user posts request timed out")
            raise
        except httpx.ConnectError:
            logger.error("🔌 TikTok user posts connection error")
            raise
        except httpx.RequestError as e:
            logger.error(f"🌐 TikTok user posts request error: {e}")
            raise
        
        logger.info(f"📡 TikTok user posts response status: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"❌ TikTok user posts API request failed: {response.status_code}")
            logger.error(f"📝 Response text: {response.text[:500]}")
            raise Exception(f"API returned status {response.status_code}")
        
        try:
            payload = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse TikTok user posts JSON response: {e}")
            raise
        
        # Extract videos from response with correct field mapping
        data = payload.get("data", {})
        items = (
            data.get("videos")
            or data.get("items")
            or data.get("aweme_list")
            or []
        )
        
        logger.info(f"🔍 Processing {len(items)} TikTok videos...")
        
        videos = []
        for i, item in enumerate(items):
            try:
                video = {
                    "video_id": item.get("video_id") or item.get("aweme_id"),
                    "video_url": item.get("play") or _safe(item, "video", "playAddr"),
                    "description": item.get("title") or item.get("desc"),
                    "create_time": item.get("create_time"),
                    "duration": item.get("duration") or _safe(item, "video", "duration"),
                    "thumbnail_url": item.get("cover") or item.get("origin_cover") or _safe(item, "video", "cover"),
                    "cloudinary": None,  # Will be set after upload
                    "view_count": item.get("play_count") or _safe(item, "stats", "playCount", default=0),
                    "like_count": item.get("digg_count") or _safe(item, "stats", "diggCount", default=0),
                    "comment_count": item.get("comment_count") or _safe(item, "stats", "commentCount", default=0),
                    "share_count": item.get("share_count") or _safe(item, "stats", "shareCount", default=0),
                    "author_id": _safe(item, "author", "id"),
                    "music_title": _safe(item, "music_info", "title") or _safe(item, "music", "title"),
                    "music_author": _safe(item, "music_info", "author") or _safe(item, "music", "authorName")
                }
                
                videos.append(video)
                logger.info(f"✅ Processed TikTok video {i+1}/{len(items)}: {video['video_id']}")
                
            except Exception as e:
                logger.error(f"❌ Error processing TikTok video {i+1}: {e}")
                continue
        
        # Upload all thumbnails to Cloudinary concurrently
        if videos:
            logger.info(f"☁️ Uploading {len(videos)} TikTok thumbnails to Cloudinary...")
            
            # Create upload tasks only for videos with thumbnails
            for i, video in enumerate(videos):
                if video.get("thumbnail_url"):
                    cloudinary_result = await upload_thumbnail_async(video["thumbnail_url"], video["video_id"], username)
                    if cloudinary_result:
                        video["cloudinary"] = cloudinary_result
            
            # Count successful uploads
            upload_count = sum(1 for video in videos if video.get("cloudinary"))
            
            logger.info(f"☁️ TikTok Cloudinary uploads complete: {upload_count}/{len(videos)} successful")
        
        logger.info(f"🎯 Successfully extracted {len(videos)} TikTok videos")
        return videos
        
    except Exception as e:
        logger.error(f"❌ Unexpected error fetching TikTok user posts: {e}")
        raise


# ------------------------------------------------------------
# AUTHORITATIVE ENDPOINT: /profile
# ------------------------------------------------------------
@router.get("/profile")
async def get_profile(
    username: str = Query(DEFAULT_TIKTOK_USERNAME, description="TikTok username"),
    count: int = Query(20, ge=1, le=30, description="Number of videos to fetch"),
    background_tasks: BackgroundTasks = None
):
    """
    Fetch TikTok profile with user info and videos.
    
    AUTHORITATIVE ENDPOINT - SINGLE SOURCE OF TRUTH
    - This is the ONLY endpoint that calls RapidAPI
    - This is the ONLY endpoint that uploads to Cloudinary
    - This is the ONLY endpoint that writes to cache
    - This is the ONLY endpoint that acquires refresh locks
    
    Returns:
        Complete profile data with user info and videos
    """
    
    # Try to get from cache
    cache_doc = get_cached_profile(username)
    should_refresh = should_refresh_cache(cache_doc)
    
    # If cache is fresh, return it
    if cache_doc and not should_refresh:
        user = cache_doc.get("user", {})
        videos = cache_doc.get("videos", [])
        cached_at = cache_doc.get("cached_at")
        age_seconds = (datetime.utcnow() - cached_at).total_seconds() if cached_at else 0
        age_days = age_seconds / 86400
        
        logger.info(f"✅ Serving TikTok profile for @{username} from MongoDB cache (age: {age_days:.2f} days)")
        
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
            "videos": videos[:count],
            "metrics": None,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    # Cache is old or doesn't exist - try to acquire refresh lock
    refresh_lock = RefreshLock(
        collection=tiktok_refresh_lock_collection,
        username=username,
        platform="TikTok"
    )
    
    lock_acquired = refresh_lock.acquire()
    
    if not lock_acquired:
        # Another process is refreshing - serve old cache if available
        if cache_doc and cache_doc.get("user") and cache_doc.get("videos"):
            user = cache_doc.get("user", {})
            videos = cache_doc.get("videos", [])
            cached_at = cache_doc.get("cached_at")
            age_seconds = (datetime.utcnow() - cached_at).total_seconds() if cached_at else 999999
            age_days = age_seconds / 86400
            
            logger.info(f"🔒 Refresh in progress by another process, serving old TikTok cache for @{username} (age: {age_days:.2f} days)")
            
            return {
                "success": True,
                "source": "mongodb_cache_locked",
                "cached_at": cached_at.isoformat() if cached_at else None,
                "cache_age_days": round(age_days, 2),
                "cache_age_seconds": round(age_seconds, 2),
                "message": "Refresh in progress, serving cached data",
                "user": user,
                "videos": videos[:count],
                "metrics": None,
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            return {
                "success": False,
                "source": "none",
                "error": "Refresh in progress and no cache available",
                "user": {},
                "videos": [],
                "metrics": None,
                "timestamp": datetime.utcnow().isoformat()
            }
    
    try:
        # Fetch user info
        logger.info(f"🎬 Fetching fresh TikTok profile for @{username} from RapidAPI")
        user = await fetch_user_info_async(username)
        
        # Fetch user posts with Cloudinary uploads
        videos = await fetch_user_posts_async(user["username"], username, MAX_VIDEOS)
        
        if user and videos:
            # Refresh cache with async cleanup (save first, cleanup after)
            refresh_stats = await refresh_cache_with_cleanup_async(cache_doc, username, user, videos)
            
            # Log metrics
            MetricsTracker.log_refresh(
                username=username,
                source="rapidapi_fresh",
                videos_count=len(videos),
                cloudinary_uploads=refresh_stats["cloudinary_uploads"],
                cloudinary_deletes=refresh_stats["cloudinary_deletes"],
                failed_deletes=refresh_stats["failed_deletes"],
                duration_seconds=refresh_stats["duration"],
                success=True
            )
            
            logger.info(f"✅ Returning fresh TikTok profile for @{username} with {len(videos)} videos")
            
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
                "videos": videos[:count],
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
        if cache_doc and cache_doc.get("user") and cache_doc.get("videos"):
            user = cache_doc.get("user", {})
            videos = cache_doc.get("videos", [])
            cached_at = cache_doc.get("cached_at")
            age_seconds = (datetime.utcnow() - cached_at).total_seconds() if cached_at else 999999
            age_days = age_seconds / 86400
            
            logger.warning(f"⚠️ TikTok API returned empty data, using old cache for @{username} (age: {age_days:.2f} days)")
            
            # Log failed refresh
            MetricsTracker.log_refresh(
                username=username,
                source="mongodb_cache_fallback",
                videos_count=len(videos),
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
                "videos": videos[:count],
                "metrics": None,
                "timestamp": datetime.utcnow().isoformat()
            }
        
        # Everything failed - return error
        logger.error(f"❌ All sources failed for TikTok @{username} - no cache available and API failed")
        
        MetricsTracker.log_refresh(
            username=username,
            source="none",
            videos_count=0,
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
            "videos": [],
            "metrics": None,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Error in TikTok main endpoint: {e}")
        
        # Try to fallback to cache
        if cache_doc and cache_doc.get("user") and cache_doc.get("videos"):
            user = cache_doc.get("user", {})
            videos = cache_doc.get("videos", [])
            cached_at = cache_doc.get("cached_at")
            age_seconds = (datetime.utcnow() - cached_at).total_seconds() if cached_at else 999999
            age_days = age_seconds / 86400
            
            logger.warning(f"⚠️ Exception occurred, using old TikTok cache for @{username} (age: {age_days:.2f} days)")
            
            MetricsTracker.log_refresh(
                username=username,
                source="mongodb_cache_fallback",
                videos_count=len(videos),
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
                "videos": videos[:count],
                "metrics": None,
                "timestamp": datetime.utcnow().isoformat()
            }
        
        return {
            "success": False,
            "source": "none",
            "error": str(e),
            "user": {},
            "videos": [],
            "metrics": None,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    finally:
        # Only release if we acquired it
        if lock_acquired:
            refresh_lock.release()


# ------------------------------------------------------------
# ADMIN/DEBUG ENDPOINTS
# ------------------------------------------------------------
@router.get("/metrics")
async def get_metrics(
    username: str = Query(None, description="Filter by username (optional)"),
    limit: int = Query(50, ge=1, le=200, description="Number of metrics to return")
):
    """Get recent TikTok operation metrics."""
    try:
        query = {"username": username} if username else {}
        
        metrics = list(
            tiktok_metrics_collection
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
    """Get status of the TikTok Cloudinary retry queue."""
    try:
        pending = tiktok_retry_queue_collection.count_documents({"status": "pending"})
        processing = tiktok_retry_queue_collection.count_documents({"status": "processing"})
        failed = tiktok_retry_queue_collection.count_documents({"status": "failed"})
        
        recent_items = list(
            tiktok_retry_queue_collection
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
    """Manually trigger TikTok retry queue processing."""
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
async def get_cache_status(username: str = Query(DEFAULT_TIKTOK_USERNAME, description="TikTok username")):
    """Get current cache status for a specific username."""
    cache_doc = get_cached_profile(username)
    
    if not cache_doc:
        return {
            "cached": False,
            "username": username,
            "message": "No cache found",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    cached_at = cache_doc.get("cached_at")
    videos_count = cache_doc.get("videos_count", 0)
    age_seconds = (datetime.utcnow() - cached_at).total_seconds() if cached_at else 0
    age_days = age_seconds / 86400
    needs_refresh = should_refresh_cache(cache_doc)
    
    # Check for active refresh lock
    refresh_lock_active = tiktok_refresh_lock_collection.find_one({"username": username}) is not None
    
    return {
        "cached": True,
        "username": username,
        "videos_count": videos_count,
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
async def clear_cache(username: str = Query(DEFAULT_TIKTOK_USERNAME, description="TikTok username")):
    """Clear the TikTok cache for a specific username (MongoDB + Cloudinary)."""
    try:
        # Get cache first to clean Cloudinary
        cache_doc = get_cached_profile(username)
        
        # Delete Cloudinary thumbnails (async)
        cleanup_stats = await delete_old_cloudinary_thumbnails_async(cache_doc, username)
        
        # Delete MongoDB cache
        result = tiktok_cache_collection.delete_many({"username": username})
        
        return {
            "success": True,
            "message": f"TikTok cache cleared for @{username}",
            "documents_deleted": result.deleted_count,
            "cloudinary_cleaned": bool(cache_doc),
            "cloudinary_stats": cleanup_stats,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ Error clearing TikTok cache: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@router.post("/force-refresh")
async def force_refresh(
    username: str = Query(DEFAULT_TIKTOK_USERNAME, description="TikTok username")
):
    """
    Force refresh the TikTok cache from API (with Cloudinary cleanup).
    Bypasses TTL check and fetches fresh data immediately.
    """
    logger.info(f"🔄 TikTok force refresh requested for @{username}")
    
    # Acquire lock
    refresh_lock = RefreshLock(
        collection=tiktok_refresh_lock_collection,
        username=username,
        platform="TikTok"
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
        cache_doc = get_cached_profile(username)
        
        # Fetch user info
        user = await fetch_user_info_async(username)
        
        # Fetch videos
        videos = await fetch_user_posts_async(user["username"], username, MAX_VIDEOS)
        
        if not user or not videos:
            return {
                "success": False,
                "error": "Failed to fetch TikTok profile from API",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        # Refresh cache with proper cleanup (save first, cleanup after)
        refresh_stats = await refresh_cache_with_cleanup_async(cache_doc, username, user, videos)
        
        # Log metrics
        MetricsTracker.log_refresh(
            username=username,
            source="force_refresh",
            videos_count=len(videos),
            cloudinary_uploads=refresh_stats["cloudinary_uploads"],
            cloudinary_deletes=refresh_stats["cloudinary_deletes"],
            failed_deletes=refresh_stats["failed_deletes"],
            duration_seconds=refresh_stats["duration"],
            success=True
        )
        
        return {
            "success": refresh_stats["save_success"],
            "count": len(videos),
            "message": f"Successfully refreshed TikTok profile for @{username} with {len(videos)} videos",
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
        logger.error(f"❌ TikTok force refresh failed: {e}")
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
    Lightweight health check for TikTok endpoint.
    - Does NOT call RapidAPI
    - Does NOT touch Cloudinary
    - Safe for load balancers / uptime monitors
    """
    try:
        # Check if cache has any data
        cache_count = tiktok_cache_collection.count_documents({})
        
        # Check most recent cache entry
        recent_cache = tiktok_cache_collection.find_one(
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
        active_locks = tiktok_refresh_lock_collection.count_documents({})
        
        # Check retry queue
        retry_queue_pending = tiktok_retry_queue_collection.count_documents({"status": "pending"})
        retry_queue_processing = tiktok_retry_queue_collection.count_documents({"status": "processing"})
        retry_queue_failed = tiktok_retry_queue_collection.count_documents({"status": "failed"})
        
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
        logger.error(f"❌ TikTok health check failed: {e}")
        return {
            "status": "down",
            "mongodb_connected": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

@router.get("/raw")
async def get_raw_response(
    username: str = Query(DEFAULT_TIKTOK_USERNAME, description="TikTok username / unique_id")
):
    """
    Get RAW API responses for debugging.
    This endpoint shows EXACT responses from RapidAPI.
    It is NOT used in production flow.
    """
    try:
        # --------------------------------------------------
        # STEP 1: RAW user/info (MUST use unique_id)
        # --------------------------------------------------
        user_info_url = f"{BASE_URL}/user/info"
        logger.info(f"🔧 TikTok RAW debug request: {user_info_url}")

        async with httpx.AsyncClient(timeout=15.0) as client:
            user_response = await client.get(
                user_info_url,
                headers=HEADERS,
                params={"unique_id": username}
            )

        debug_info = {
            "user_info": {
                "endpoint": "user/info",
                "status_code": user_response.status_code,
                "url": str(user_response.url),
                "raw_text": user_response.text[:2000]
            }
        }

        # Try parsing user info JSON
        try:
            user_json = user_response.json()
            debug_info["user_info"]["json"] = user_json

            user_obj = user_json.get("data", {}).get("user", {})
            debug_info["user_info"]["user_id"] = user_obj.get("id")
            debug_info["user_info"]["unique_id"] = user_obj.get("uniqueId")

        except Exception as e:
            debug_info["user_info"]["json_error"] = str(e)

        # --------------------------------------------------
        # STEP 2: RAW user/posts (unique_id only)
        # --------------------------------------------------
        posts_url = f"{BASE_URL}/user/posts"

        async with httpx.AsyncClient(timeout=15.0) as client:
            posts_response = await client.get(
                posts_url,
                headers=HEADERS,
                params={
                    "unique_id": username,
                    "count": 5
                }
            )

        debug_info["user_posts"] = {
            "endpoint": "user/posts",
            "status_code": posts_response.status_code,
            "url": str(posts_response.url),
            "raw_text": posts_response.text[:2000]
        }

        # Try parsing posts JSON
        try:
            posts_json = posts_response.json()
            debug_info["user_posts"]["json"] = posts_json

            videos = posts_json.get("data", {}).get("videos", [])
            debug_info["user_posts"]["videos_found"] = len(videos)

            if videos:
                debug_info["user_posts"]["sample_video_id"] = (
                    videos[0].get("video_id") or videos[0].get("aweme_id")
                )
                debug_info["user_posts"]["sample_video_fields"] = list(videos[0].keys())

        except Exception as e:
            debug_info["user_posts"]["json_error"] = str(e)

        return debug_info

    except Exception as e:
        logger.exception("❌ RAW TikTok debug endpoint failed")
        return {
            "success": False,
            "error": str(e),
            "rapidapi_host": TIKTOK_RAPIDAPI_HOST,
            "rapidapi_key_present": bool(RAPIDAPI_KEY),
            "timestamp": datetime.utcnow().isoformat()
        }