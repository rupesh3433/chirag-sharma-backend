# routes_public_instagramFetch.py
# ============================================================
# PRODUCTION-GRADE VERSION
# - Refresh lock (prevents race conditions)
# - Retry queue for failed Cloudinary deletes
# - Metrics collection (cleanup stats, orphan tracking)
# - Async-safe Cloudinary cleanup
# ============================================================

from fastapi import APIRouter, Query, BackgroundTasks
import requests
import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
import cloudinary
import cloudinary.uploader

from config import (
    RAPIDAPI_KEY, 
    RAPIDAPI_HOST,
    CLOUDINARY_CLOUD_NAME,
    CLOUDINARY_API_KEY,
    CLOUDINARY_API_SECRET
)

# Import from existing database connection
from database import (
    instagram_reels_collection,
    db  # We'll use this to create new collections
)

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
INSTAGRAM_USERNAME = "_jinniechiragmua"
CACHE_TTL_DAYS = 2  # Refresh every 2 days
REFRESH_LOCK_TTL_SECONDS = 300  # 5 minutes max lock time
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 60

# ------------------------------------------------------------
# NEW COLLECTIONS FOR PRODUCTION FEATURES
# ------------------------------------------------------------
# Refresh lock collection
refresh_lock_collection = db["instagram_refresh_locks"]

# Cloudinary retry queue collection
cloudinary_retry_queue_collection = db["cloudinary_retry_queue"]

# Metrics collection
instagram_metrics_collection = db["instagram_metrics"]

# ------------------------------------------------------------
# SETUP INDEXES
# ------------------------------------------------------------
def setup_production_indexes():
    """Create indexes for production collections."""
    try:
        # Refresh locks - auto-expire
        refresh_lock_collection.create_index("locked_at", expireAfterSeconds=REFRESH_LOCK_TTL_SECONDS)
        refresh_lock_collection.create_index("username")
        
        # Retry queue - common queries
        cloudinary_retry_queue_collection.create_index("username")
        cloudinary_retry_queue_collection.create_index("status")
        cloudinary_retry_queue_collection.create_index("retry_count")
        cloudinary_retry_queue_collection.create_index("created_at")
        cloudinary_retry_queue_collection.create_index([("status", 1), ("retry_count", 1)])
        
        # Metrics - queries by date
        instagram_metrics_collection.create_index("username")
        instagram_metrics_collection.create_index("timestamp")
        instagram_metrics_collection.create_index([("username", 1), ("timestamp", -1)])
        
        logger.info("✅ Production indexes created successfully")
    except Exception as e:
        logger.error(f"❌ Error creating production indexes: {e}")

# Initialize indexes
setup_production_indexes()

# ------------------------------------------------------------
# CLOUDINARY CONFIG
# ------------------------------------------------------------
if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET
    )
    logger.info("✅ Cloudinary configured successfully")
else:
    logger.warning("⚠️ Cloudinary not configured - thumbnails will not be uploaded")

# Thread pool for async Cloudinary operations
cloudinary_executor = ThreadPoolExecutor(max_workers=5)

# ------------------------------------------------------------
# REFRESH LOCK MECHANISM
# ------------------------------------------------------------
class RefreshLock:
    """Distributed lock for preventing concurrent cache refreshes."""
    
    def __init__(self, username: str):
        self.username = username
        self.lock_acquired = False
    
    def acquire(self) -> bool:
        """
        Try to acquire refresh lock.
        Returns True if lock acquired, False if already locked.
        """
        try:
            existing_lock = refresh_lock_collection.find_one({"username": self.username})
            
            if existing_lock:
                locked_at = existing_lock.get("locked_at")
                if locked_at:
                    age = datetime.now() - locked_at
                    logger.info(f"🔒 Refresh already in progress (locked {age.seconds}s ago)")
                return False
            
            # Create lock
            refresh_lock_collection.insert_one({
                "username": self.username,
                "locked_at": datetime.now(),
                "locked_by": f"process_{id(self)}"
            })
            
            self.lock_acquired = True
            logger.info(f"🔓 Refresh lock acquired for {self.username}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error acquiring refresh lock: {e}")
            return False
    
    def release(self):
        """Release the refresh lock."""
        if not self.lock_acquired:
            return
        
        try:
            refresh_lock_collection.delete_many({"username": self.username})
            logger.info(f"🔓 Refresh lock released for {self.username}")
        except Exception as e:
            logger.error(f"❌ Error releasing refresh lock: {e}")
    
    def __enter__(self):
        return self.acquire()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

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
                "timestamp": datetime.now()
            }
            
            instagram_metrics_collection.insert_one(metric)
            logger.info(f"📊 Metrics logged: {metric}")
        except Exception as e:
            logger.error(f"❌ Error logging metrics: {e}")
    
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
                "timestamp": datetime.now()
            }
            
            instagram_metrics_collection.insert_one(metric)
        except Exception as e:
            logger.error(f"❌ Error logging retry metric: {e}")

# ------------------------------------------------------------
# CLOUDINARY RETRY QUEUE
# ------------------------------------------------------------
class CloudinaryRetryQueue:
    """Queue for retrying failed Cloudinary delete operations."""
    
    @staticmethod
    def add_failed_delete(username: str, public_id: str, reel_code: str, error: str):
        """Add a failed delete to the retry queue."""
        try:
            retry_item = {
                "username": username,
                "public_id": public_id,
                "reel_code": reel_code,
                "status": "pending",
                "retry_count": 0,
                "last_error": error,
                "created_at": datetime.now(),
                "next_retry_at": datetime.now() + timedelta(seconds=RETRY_DELAY_SECONDS)
            }
            
            cloudinary_retry_queue_collection.insert_one(retry_item)
            logger.info(f"📥 Added to retry queue: {public_id}")
        except Exception as e:
            logger.error(f"❌ Error adding to retry queue: {e}")
    
    @staticmethod
    def process_retry_queue(background: bool = True) -> Dict[str, int]:
        """
        Process pending items in the retry queue.
        Returns dict with success/failure counts.
        """
        try:
            # Find pending items ready for retry
            pending_items = cloudinary_retry_queue_collection.find({
                "status": "pending",
                "retry_count": {"$lt": MAX_RETRY_ATTEMPTS},
                "next_retry_at": {"$lte": datetime.now()}
            })
            
            success_count = 0
            failed_count = 0
            
            for item in pending_items:
                public_id = item["public_id"]
                retry_count = item["retry_count"]
                
                try:
                    # Attempt to delete
                    result = cloudinary.uploader.destroy(public_id, resource_type="image")
                    
                    if result.get("result") in ["ok", "not found"]:
                        # Success - remove from queue
                        cloudinary_retry_queue_collection.delete_one({"_id": item["_id"]})
                        success_count += 1
                        logger.info(f"✅ Retry success: {public_id} (attempt {retry_count + 1})")
                        
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
                        cloudinary_retry_queue_collection.update_one(
                            {"_id": item["_id"]},
                            {
                                "$set": {
                                    "status": "failed",
                                    "retry_count": new_retry_count,
                                    "last_error": str(e),
                                    "failed_at": datetime.now()
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
                        # Schedule next retry
                        next_retry_delay = RETRY_DELAY_SECONDS * (2 ** new_retry_count)  # Exponential backoff
                        cloudinary_retry_queue_collection.update_one(
                            {"_id": item["_id"]},
                            {
                                "$set": {
                                    "retry_count": new_retry_count,
                                    "last_error": str(e),
                                    "next_retry_at": datetime.now() + timedelta(seconds=next_retry_delay)
                                }
                            }
                        )
                        logger.warning(f"⚠️ Retry {new_retry_count} failed for {public_id}, next in {next_retry_delay}s")
                    
                    failed_count += 1
            
            if success_count > 0 or failed_count > 0:
                logger.info(f"📊 Retry queue processed: {success_count} success, {failed_count} failed")
            
            return {"success": success_count, "failed": failed_count}
            
        except Exception as e:
            logger.error(f"❌ Error processing retry queue: {e}")
            return {"success": 0, "failed": 0}

# ------------------------------------------------------------
# ASYNC-SAFE CLOUDINARY OPERATIONS
# ------------------------------------------------------------
async def upload_thumbnail_async(thumbnail_url: str, reel_code: str) -> Optional[Dict[str, str]]:
    """
    Upload thumbnail to Cloudinary asynchronously.
    Returns dict with 'url' and 'public_id' keys, or None if upload fails.
    """
    if not all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
        logger.debug("⏭️ Cloudinary not configured, skipping upload")
        return None
    
    loop = asyncio.get_event_loop()
    
    def _upload():
        try:
            result = cloudinary.uploader.upload(
                thumbnail_url,
                folder="instagram_reels",
                public_id=f"reel_{reel_code}",
                overwrite=True,
                resource_type="image",
                transformation=[
                    {"width": 600, "height": 1067, "crop": "fill", "quality": "auto:good"}
                ]
            )
            
            cloudinary_url = result.get("secure_url")
            cloudinary_public_id = result.get("public_id")
            
            logger.info(f"✅ Uploaded thumbnail to Cloudinary: {reel_code} (public_id: {cloudinary_public_id})")
            
            return {
                "url": cloudinary_url,
                "public_id": cloudinary_public_id
            }
        except Exception as e:
            logger.error(f"❌ Failed to upload thumbnail to Cloudinary for {reel_code}: {e}")
            return None
    
    return await loop.run_in_executor(cloudinary_executor, _upload)


async def delete_old_cloudinary_thumbnails_async(cache_doc: Optional[Dict[str, Any]], username: str) -> Dict[str, int]:
    """
    Delete old Cloudinary thumbnails asynchronously with retry queue support.
    
    Returns:
        Dict with 'deleted', 'failed', 'queued' counts
    """
    if not cache_doc:
        logger.info("ℹ️ No cache document to clean up")
        return {"deleted": 0, "failed": 0, "queued": 0}
    
    if not all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
        logger.debug("⏭️ Cloudinary not configured, skipping cleanup")
        return {"deleted": 0, "failed": 0, "queued": 0}
    
    reels = cache_doc.get("reels", [])
    deleted_count = 0
    failed_count = 0
    queued_count = 0
    
    logger.info(f"🗑️ Starting async Cloudinary cleanup for {len(reels)} old reels...")
    
    loop = asyncio.get_event_loop()
    
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
                    logger.info(f"✅ Deleted Cloudinary asset: {public_id}")
                    return {"status": "deleted", "public_id": public_id}
                elif result.get("result") == "not found":
                    logger.warning(f"⚠️ Cloudinary asset not found (already deleted?): {public_id}")
                    return {"status": "deleted", "public_id": public_id}  # Treat as success
                else:
                    raise Exception(f"Cloudinary returned: {result}")
            except Exception as e:
                logger.error(f"❌ Error deleting Cloudinary asset {public_id}: {e}")
                return {
                    "status": "failed",
                    "public_id": public_id,
                    "error": str(e),
                    "reel_code": reel.get("code")
                }
        
        return await loop.run_in_executor(cloudinary_executor, _delete)
    
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
    
    logger.info(f"🗑️ Async cleanup complete: {deleted_count} deleted, {failed_count} failed, {queued_count} queued for retry")
    
    return {
        "deleted": deleted_count,
        "failed": failed_count,
        "queued": queued_count
    }

# ------------------------------------------------------------
# HELPER FUNCTIONS (from original)
# ------------------------------------------------------------
def extract_reel_data(media_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract reel data from a media item, handling different structures."""
    
    # Get the actual media data (could be nested or direct)
    media_data = media_item.get("media", media_item)
    
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
    
    # Get caption
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
    
    # Extract thumbnail - try multiple locations
    thumbnail = None
    
    # Method 1: Try image_versions2.candidates (highest quality first)
    if "image_versions2" in media_data:
        img_versions = media_data["image_versions2"]
        if isinstance(img_versions, dict) and "candidates" in img_versions:
            candidates = img_versions["candidates"]
            if candidates and isinstance(candidates, list) and len(candidates) > 0:
                for candidate in candidates:
                    if candidate.get("url"):
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
                if version.get("url"):
                    thumbnail = version["url"]
                    break
    
    # Method 4: Try image_versions (old structure)
    if not thumbnail and "image_versions" in media_data:
        image_versions = media_data["image_versions"]
        if image_versions and isinstance(image_versions, list) and len(image_versions) > 0:
            thumbnail = image_versions[0].get("url")
    
    if not thumbnail:
        logger.warning(f"⚠️ No thumbnail found for reel {code}")
        return None
    
    # Get ID
    reel_id = media_data.get("id", f"reel_{code}")
    if isinstance(reel_id, dict):
        reel_id = reel_id.get("id", f"reel_{code}")
    
    # Build URLs
    post_url = f"https://www.instagram.com/reel/{code}/"
    embed_url = f"https://www.instagram.com/reel/{code}/embed"
    
    # Get engagement metrics
    like_count = media_data.get("like_count", 0)
    comment_count = media_data.get("comment_count", 0)
    play_count = media_data.get("play_count", 0)
    
    # If like_count is a dict with "count" key
    if isinstance(like_count, dict):
        like_count = like_count.get("count", 0)
    
    # If comment_count is a dict with "count" key
    if isinstance(comment_count, dict):
        comment_count = comment_count.get("count", 0)
    
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


async def fetch_reels_from_rapidapi_async() -> List[Dict[str, Any]]:
    """Fetch reels from RapidAPI Instagram endpoint with async Cloudinary uploads."""
    
    if not RAPIDAPI_KEY or not RAPIDAPI_HOST:
        logger.error("❌ RapidAPI credentials missing in config")
        return []
    
    url = f"https://{RAPIDAPI_HOST}/userreels/"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }
    params = {"username_or_id": INSTAGRAM_USERNAME}
    
    reels = []
    upload_count = 0
    
    try:
        logger.info(f"🚀 Fetching reels from RapidAPI for @{INSTAGRAM_USERNAME}")
        
        # Fetch from API (sync)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: requests.get(url, headers=headers, params=params, timeout=30)
        )
        
        logger.info(f"📡 Response status: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"❌ API request failed: {response.status_code}")
            logger.error(f"📝 Response text: {response.text[:500]}")
            return []
        
        # Parse response
        try:
            payload = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse JSON response: {e}")
            return []
        
        # Handle different response structures
        items = []
        
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
        
        elif "data" in payload and "user" in payload["data"]:
            user = payload["data"]["user"]
            if "edge_owner_to_timeline_media" in user:
                edges = user["edge_owner_to_timeline_media"].get("edges", [])
                items = [edge.get("node", {}) for edge in edges if edge.get("node")]
        
        logger.info(f"🔍 Processing {len(items)} items...")
        
        # Process each item
        for i, item in enumerate(items[:20]):  # Limit to first 20
            try:
                reel_data = extract_reel_data(item)
                if reel_data:
                    reels.append(reel_data)
                    logger.info(f"✅ Added reel {i+1}/{len(items)}: {reel_data.get('code')}")
            except Exception as e:
                logger.error(f"❌ Error processing item {i+1}: {e}")
                continue
        
        # Upload all thumbnails to Cloudinary concurrently
        if reels:
            logger.info(f"☁️ Uploading {len(reels)} thumbnails to Cloudinary...")
            upload_tasks = [
                upload_thumbnail_async(reel["thumbnail"], reel["code"])
                for reel in reels
            ]
            upload_results = await asyncio.gather(*upload_tasks)
            
            # Update reels with Cloudinary data
            for reel, cloudinary_result in zip(reels, upload_results):
                if cloudinary_result:
                    reel["cloudinary"] = cloudinary_result
                    upload_count += 1
            
            logger.info(f"☁️ Cloudinary uploads complete: {upload_count}/{len(reels)} successful")
        
        logger.info(f"🎯 Successfully extracted {len(reels)} reels")
        
    except requests.exceptions.Timeout:
        logger.error("⏱️ Request timeout - RapidAPI took too long to respond")
    except requests.exceptions.ConnectionError:
        logger.error("🔌 Connection error - Could not connect to RapidAPI")
    except Exception as e:
        logger.error(f"❌ Unexpected error fetching from RapidAPI: {e}")
    
    return reels


def get_cached_reels() -> Optional[Dict[str, Any]]:
    """Get cached reels from MongoDB."""
    try:
        cache_doc = instagram_reels_collection.find_one({"username": INSTAGRAM_USERNAME})
        
        if cache_doc:
            cached_at = cache_doc.get("cached_at")
            if cached_at:
                age_days = (datetime.now() - cached_at).days
                logger.info(f"📦 Found cached reels (age: {age_days} days)")
                return cache_doc
        
        return None
    except Exception as e:
        logger.error(f"❌ MongoDB error getting cached reels: {e}")
        return None


def save_reels_to_cache(reels: List[Dict[str, Any]]) -> bool:
    """Save reels to MongoDB cache."""
    try:
        # Insert new cache
        cache_doc = {
            "username": INSTAGRAM_USERNAME,
            "reels": reels,
            "cached_at": datetime.now(),
            "count": len(reels)
        }
        
        instagram_reels_collection.insert_one(cache_doc)
        logger.info(f"✅ Saved {len(reels)} reels to MongoDB cache")
        return True
    except Exception as e:
        logger.error(f"❌ MongoDB error saving reels: {e}")
        return False


def should_refresh_cache(cache_doc: Optional[Dict[str, Any]]) -> bool:
    """Check if cache should be refreshed (>2 days old)."""
    if not cache_doc:
        return True
    
    cached_at = cache_doc.get("cached_at")
    if not cached_at:
        return True
    
    age = datetime.now() - cached_at
    should_refresh = age > timedelta(days=CACHE_TTL_DAYS)
    
    if should_refresh:
        logger.info(f"🔄 Cache is {age.days} days old, refreshing...")
    
    return should_refresh


async def refresh_cache_with_cleanup_async(
    cache_doc: Optional[Dict[str, Any]], 
    fresh_reels: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Refresh cache with proper async cleanup flow.
    
    Returns:
        Dict with operation results and metrics
    """
    start_time = time.time()
    
    # Step 1: Delete old Cloudinary thumbnails (async)
    cleanup_stats = await delete_old_cloudinary_thumbnails_async(cache_doc, INSTAGRAM_USERNAME)
    
    # Step 2: Delete old MongoDB cache
    try:
        result = instagram_reels_collection.delete_many({"username": INSTAGRAM_USERNAME})
        logger.info(f"🗑️ Deleted {result.deleted_count} old cache documents from MongoDB")
    except Exception as e:
        logger.error(f"❌ Error deleting old cache: {e}")
    
    # Step 3: Save new cache
    save_success = save_reels_to_cache(fresh_reels)
    
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


# ------------------------------------------------------------
# MAIN ENDPOINT
# ------------------------------------------------------------
@router.get("/reels")
async def fetch_latest_reels(
    limit: int = Query(12, ge=1, le=12),
    background_tasks: BackgroundTasks = None
):
    """Fetch latest Instagram reels for the configured user."""
    
    # Try to get from cache
    cache_doc = get_cached_reels()
    should_refresh = should_refresh_cache(cache_doc)
    
    # If cache is fresh, return it
    if cache_doc and not should_refresh:
        reels = cache_doc.get("reels", [])
        cached_at = cache_doc.get("cached_at")
        age_days = (datetime.now() - cached_at).days if cached_at else 0
        
        logger.info(f"✅ Serving {len(reels[:limit])} reels from MongoDB cache (age: {age_days} days)")
        
        # Process retry queue in background
        if background_tasks:
            background_tasks.add_task(CloudinaryRetryQueue.process_retry_queue)
        
        return {
            "success": True,
            "count": len(reels[:limit]),
            "reels": reels[:limit],
            "source": "mongodb_cache",
            "cached_at": cached_at.isoformat() if cached_at else None,
            "cache_age_days": age_days,
            "timestamp": datetime.now().isoformat()
        }
    
    # Cache is old or doesn't exist - try to acquire refresh lock
    refresh_lock = RefreshLock(INSTAGRAM_USERNAME)
    
    if not refresh_lock.acquire():
        # Another process is refreshing - serve old cache if available
        if cache_doc and cache_doc.get("reels"):
            old_reels = cache_doc.get("reels", [])
            cached_at = cache_doc.get("cached_at")
            age_days = (datetime.now() - cached_at).days if cached_at else 999
            
            logger.info(f"🔒 Refresh in progress by another process, serving old cache (age: {age_days} days)")
            
            return {
                "success": True,
                "count": len(old_reels[:limit]),
                "reels": old_reels[:limit],
                "source": "mongodb_cache_locked",
                "cached_at": cached_at.isoformat() if cached_at else None,
                "cache_age_days": age_days,
                "message": "Refresh in progress, serving cached data",
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "count": 0,
                "reels": [],
                "source": "none",
                "error": "Refresh in progress and no cache available",
                "timestamp": datetime.now().isoformat()
            }
    
    try:
        # Fetch fresh data with async Cloudinary uploads
        logger.info("🎬 Fetching fresh reels from RapidAPI")
        fresh_reels = await fetch_reels_from_rapidapi_async()
        
        if fresh_reels:
            # Sort by taken_at (newest first)
            fresh_reels.sort(key=lambda x: x.get("takenAt", 0), reverse=True)
            
            # Refresh cache with async cleanup
            refresh_stats = await refresh_cache_with_cleanup_async(cache_doc, fresh_reels)
            
            # Log metrics
            MetricsTracker.log_refresh(
                username=INSTAGRAM_USERNAME,
                source="rapidapi_fresh",
                reels_count=len(fresh_reels),
                cloudinary_uploads=refresh_stats["cloudinary_uploads"],
                cloudinary_deletes=refresh_stats["cloudinary_deletes"],
                failed_deletes=refresh_stats["failed_deletes"],
                duration_seconds=refresh_stats["duration"],
                success=True
            )
            
            logger.info(f"✅ Returning {len(fresh_reels[:limit])} fresh reels from API")
            
            # Process retry queue in background
            if background_tasks:
                background_tasks.add_task(CloudinaryRetryQueue.process_retry_queue)
            
            return {
                "success": True,
                "count": len(fresh_reels[:limit]),
                "reels": fresh_reels[:limit],
                "source": "rapidapi_fresh",
                "cached_to_db": refresh_stats["save_success"],
                "metrics": {
                    "cloudinary_uploads": refresh_stats["cloudinary_uploads"],
                    "cloudinary_deletes": refresh_stats["cloudinary_deletes"],
                    "failed_deletes": refresh_stats["failed_deletes"],
                    "queued_for_retry": refresh_stats["queued_deletes"],
                    "duration_seconds": round(refresh_stats["duration"], 2)
                },
                "timestamp": datetime.now().isoformat()
            }
        
        # API failed - try to use old cache anyway
        if cache_doc and cache_doc.get("reels"):
            old_reels = cache_doc.get("reels", [])
            cached_at = cache_doc.get("cached_at")
            age_days = (datetime.now() - cached_at).days if cached_at else 999
            
            logger.warning(f"⚠️ API failed, using old cache (age: {age_days} days)")
            
            # Log failed refresh
            MetricsTracker.log_refresh(
                username=INSTAGRAM_USERNAME,
                source="mongodb_cache_fallback",
                reels_count=len(old_reels),
                cloudinary_uploads=0,
                cloudinary_deletes=0,
                failed_deletes=0,
                duration_seconds=0,
                success=False,
                error="API fetch failed"
            )
            
            return {
                "success": True,
                "count": len(old_reels[:limit]),
                "reels": old_reels[:limit],
                "source": "mongodb_cache_fallback",
                "cached_at": cached_at.isoformat() if cached_at else None,
                "cache_age_days": age_days,
                "warning": "Using old cache - API fetch failed",
                "timestamp": datetime.now().isoformat()
            }
        
        # Everything failed - return error
        logger.error("❌ All sources failed - no cache available and API failed")
        
        MetricsTracker.log_refresh(
            username=INSTAGRAM_USERNAME,
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
            "count": 0,
            "reels": [],
            "source": "none",
            "error": "Unable to fetch reels - API unavailable and no cache exists",
            "timestamp": datetime.now().isoformat()
        }
        
    finally:
        # Always release the lock
        refresh_lock.release()


# ------------------------------------------------------------
# ADMIN/DEBUG ENDPOINTS
# ------------------------------------------------------------
@router.get("/metrics")
async def get_metrics(limit: int = Query(50, ge=1, le=200)):
    """Get recent operation metrics."""
    try:
        metrics = list(
            instagram_metrics_collection
            .find({"username": INSTAGRAM_USERNAME})
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
            "metrics": metrics
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/retry-queue-status")
async def get_retry_queue_status():
    """Get status of the Cloudinary retry queue."""
    try:
        pending = cloudinary_retry_queue_collection.count_documents({"status": "pending"})
        failed = cloudinary_retry_queue_collection.count_documents({"status": "failed"})
        
        recent_items = list(
            cloudinary_retry_queue_collection
            .find()
            .sort("created_at", -1)
            .limit(20)
        )
        
        # Convert ObjectId to string
        for item in recent_items:
            item["_id"] = str(item["_id"])
            for date_field in ["created_at", "next_retry_at", "failed_at"]:
                if date_field in item and item[date_field]:
                    item[date_field] = item[date_field].isoformat()
        
        return {
            "success": True,
            "pending_count": pending,
            "failed_count": failed,
            "recent_items": recent_items
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/process-retry-queue")
async def process_retry_queue_endpoint():
    """Manually trigger retry queue processing."""
    try:
        result = CloudinaryRetryQueue.process_retry_queue(background=False)
        return {
            "success": True,
            "processed": result["success"] + result["failed"],
            "success_count": result["success"],
            "failed_count": result["failed"]
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/cache-status")
async def get_cache_status():
    """Get current cache status."""
    cache_doc = get_cached_reels()
    
    if not cache_doc:
        return {
            "cached": False,
            "message": "No cache found"
        }
    
    cached_at = cache_doc.get("cached_at")
    reels_count = cache_doc.get("count", 0)
    age_days = (datetime.now() - cached_at).days if cached_at else 0
    needs_refresh = should_refresh_cache(cache_doc)
    
    # Check for active refresh lock
    refresh_lock_active = refresh_lock_collection.find_one({"username": INSTAGRAM_USERNAME}) is not None
    
    return {
        "cached": True,
        "count": reels_count,
        "cached_at": cached_at.isoformat() if cached_at else None,
        "age_days": age_days,
        "needs_refresh": needs_refresh,
        "refresh_in_progress": refresh_lock_active,
        "ttl_days": CACHE_TTL_DAYS,
        "timestamp": datetime.now().isoformat()
    }


@router.post("/clear-cache")
async def clear_cache():
    """Clear the Instagram reels cache (MongoDB + Cloudinary)."""
    try:
        # Get cache first to clean Cloudinary
        cache_doc = get_cached_reels()
        
        # Delete Cloudinary thumbnails (async)
        cleanup_stats = await delete_old_cloudinary_thumbnails_async(cache_doc, INSTAGRAM_USERNAME)
        
        # Delete MongoDB cache
        result = instagram_reels_collection.delete_many({"username": INSTAGRAM_USERNAME})
        
        return {
            "success": True,
            "message": f"Cache cleared ({result.deleted_count} documents deleted)",
            "cloudinary_cleaned": bool(cache_doc),
            "cloudinary_stats": cleanup_stats,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ Error clearing cache: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/force-refresh")
async def force_refresh():
    """Force refresh the cache from API (with Cloudinary cleanup)."""
    logger.info("🔄 Force refresh requested")
    
    # Acquire lock
    refresh_lock = RefreshLock(INSTAGRAM_USERNAME)
    if not refresh_lock.acquire():
        return {
            "success": False,
            "error": "Refresh already in progress",
            "timestamp": datetime.now().isoformat()
        }
    
    try:
        # Get old cache first for cleanup
        cache_doc = get_cached_reels()
        
        # Fetch fresh reels
        fresh_reels = await fetch_reels_from_rapidapi_async()
        
        if not fresh_reels:
            return {
                "success": False,
                "error": "Failed to fetch reels from API",
                "timestamp": datetime.now().isoformat()
            }
        
        # Sort by taken_at (newest first)
        fresh_reels.sort(key=lambda x: x.get("takenAt", 0), reverse=True)
        
        # Refresh cache with proper cleanup
        refresh_stats = await refresh_cache_with_cleanup_async(cache_doc, fresh_reels)
        
        # Log metrics
        MetricsTracker.log_refresh(
            username=INSTAGRAM_USERNAME,
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
            "message": f"Successfully refreshed cache with {len(fresh_reels)} reels",
            "metrics": {
                "cloudinary_uploads": refresh_stats["cloudinary_uploads"],
                "cloudinary_deletes": refresh_stats["cloudinary_deletes"],
                "failed_deletes": refresh_stats["failed_deletes"],
                "queued_for_retry": refresh_stats["queued_deletes"],
                "duration_seconds": round(refresh_stats["duration"], 2)
            },
            "timestamp": datetime.now().isoformat()
        }
    finally:
        refresh_lock.release()


@router.get("/health")
async def health_check():
    """
    Lightweight health check.
    - Does NOT call RapidAPI
    - Does NOT touch Cloudinary
    - Safe for load balancers / uptime monitors
    """
    try:
        cache_doc = instagram_reels_collection.find_one(
            {"username": INSTAGRAM_USERNAME},
            {"_id": 0, "cached_at": 1, "count": 1}
        )

        if cache_doc and cache_doc.get("cached_at"):
            age_days = (datetime.now() - cache_doc["cached_at"]).days
            status = "healthy"
        else:
            age_days = None
            status = "degraded"

        # Check retry queue
        retry_queue_size = cloudinary_retry_queue_collection.count_documents({"status": "pending"})

        return {
            "status": status,
            "mongodb_connected": True,
            "cache_exists": bool(cache_doc),
            "cache_count": cache_doc.get("count", 0) if cache_doc else 0,
            "cache_age_days": age_days,
            "retry_queue_size": retry_queue_size,
            "ttl_days": CACHE_TTL_DAYS,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ Health check failed: {e}")
        return {
            "status": "down",
            "mongodb_connected": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# ------------------------------------------------------------
# RAW RESPONSE (unchanged)
# ------------------------------------------------------------
@router.get("/raw")
async def get_raw_response():
    """Get raw API response for debugging purposes."""
    try:
        url = f"https://{RAPIDAPI_HOST}/userreels/"
        
        headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": RAPIDAPI_HOST
        }
        
        params = {
            "username_or_id": INSTAGRAM_USERNAME
        }
        
        logger.info(f"🔧 Debug request to: {url}")
        
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        debug_info = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "url": response.url,
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
                
            except json.JSONDecodeError:
                debug_info["json_response"] = False
                debug_info["response_preview"] = response.text[:1000]
        else:
            debug_info["response"] = "Empty response"
        
        return debug_info
        
    except Exception as e:
        return {
            "error": str(e),
            "rapidapi_url": f"https://{RAPIDAPI_HOST}/userreels/" if RAPIDAPI_HOST else "Not set",
            "rapidapi_key_present": bool(RAPIDAPI_KEY)
        }