# database.py
# ============================================================
# PRODUCTION-GRADE DATABASE CONFIGURATION - FINAL VERSION
# ============================================================
# ✅ Atomic refresh locks (unique index enforced)
# ✅ Proper TTL strategy (locks + reset tokens + metrics)
# ✅ Consistent naming conventions
# ✅ Performance indexes
# ✅ Retry queue auto-cleanup
# ✅ Connection pooling and error handling
# ✅ Metrics TTL (30 days auto-cleanup)
# ============================================================

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import logging
from datetime import timedelta
from config import MONGODB_URI, MONGODB_DB_NAME

# ------------------------------------------------------------
# LOGGER
# ------------------------------------------------------------
logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# MONGODB CONNECTION
# ------------------------------------------------------------
try:
    # Create MongoDB client with connection pooling
    client = MongoClient(
        MONGODB_URI,
        maxPoolSize=50,  # Max connections in pool
        minPoolSize=10,  # Min connections in pool
        serverSelectionTimeoutMS=5000,  # 5 second timeout
        connectTimeoutMS=10000,  # 10 second connect timeout
        retryWrites=True,  # Retry writes on network errors
        w='majority'  # Write concern: majority of nodes
    )
    
    try:
        client.admin.command("ping")
        logger.info("✅ MongoDB connection successful")
    except Exception as e:
        logger.error(f"❌ MongoDB ping failed (continuing without crash): {e}")

    # Get database
    db = client[MONGODB_DB_NAME]
    logger.info(f"✅ Using database: {MONGODB_DB_NAME}")
    
except (ConnectionFailure, ServerSelectionTimeoutError) as e:
    logger.error(f"❌ MongoDB connection failed: {e}")
    raise
except Exception as e:
    logger.error(f"❌ Unexpected MongoDB error: {e}")
    raise

# ============================================================
# COLLECTION DEFINITIONS
# ============================================================
# All collections follow consistent naming convention:
# - Primary cache: {platform}_cache
# - Refresh locks: {platform}_refresh_locks
# - Retry queues: {platform}_retry_queue
# - Metrics: {platform}_metrics
# ============================================================

#DONOT REMOVE THESE 5
booking_collection = db["bookings"]
admin_collection = db["admins"]
admin_reset_token_collection = db["admin_reset_tokens"]
knowledge_collection = db["knowledge_base"]
event_collection = db["events"]
payments_collection = db["payments"]

# ------------------------------------------------------------
# INSTAGRAM COLLECTIONS
# ------------------------------------------------------------
instagram_reels_collection = db["instagram_cache"]
instagram_refresh_lock_collection = db["instagram_refresh_locks"]
instagram_retry_queue_collection = db["instagram_retry_queue"]
instagram_metrics_collection = db["instagram_metrics"]

# ------------------------------------------------------------
# TIKTOK COLLECTIONS
# ------------------------------------------------------------
tiktok_cache_collection = db["tiktok_cache"]
tiktok_refresh_lock_collection = db["tiktok_refresh_locks"]
tiktok_retry_queue_collection = db["tiktok_retry_queue"]
tiktok_metrics_collection = db["tiktok_metrics"]

# ------------------------------------------------------------
# USER MANAGEMENT COLLECTIONS
# ------------------------------------------------------------
users_collection = db["users"]
reset_tokens_collection = db["reset_tokens"]

# ============================================================
# INDEX CREATION
# ============================================================
# Indexes improve query performance and enable TTL auto-deletion
# CRITICAL: Unique index on refresh locks enables atomic acquisition
# ============================================================

def create_indexes():
    """
    Create all necessary indexes for optimal performance.
    Safe to call multiple times (MongoDB handles duplicates).
    """
    try:
        logger.info("🔧 Creating MongoDB indexes...")

        #--------------------------------
        # Donot Remove these My main these 5 collection's indexes
        #--------------------------------
        # Reset tokens - auto-expire
        admin_reset_token_collection.create_index("expires_at", expireAfterSeconds=0)
        
        # Admins - unique email
        admin_collection.create_index("email", unique=True)
        
        # Bookings - common queries
        booking_collection.create_index("created_at")
        booking_collection.create_index("status")
        
        # Knowledge base - common queries
        knowledge_collection.create_index("language")
        knowledge_collection.create_index("is_active")
        knowledge_collection.create_index("created_at")
        knowledge_collection.create_index([("language", 1), ("is_active", 1)])
        
        # Events - common queries
        event_collection.create_index("created_at")
        event_collection.create_index("status")
        event_collection.create_index("is_active")
        event_collection.create_index("date_from")
        event_collection.create_index("date_to")
        event_collection.create_index([("status", 1), ("is_active", 1)])
        event_collection.create_index([("date_from", 1), ("date_to", 1)])


        # ------------------------------------------------------------
        # PAYMENTS INDEXES
        # ------------------------------------------------------------
        payments_collection.create_index("booking_id")
        payments_collection.create_index("provider")
        payments_collection.create_index("order_id")
        payments_collection.create_index(
            [("payment_id", ASCENDING)],
            unique=True,
            partialFilterExpression={
                "payment_id": {"$exists": True}
            },
            name="payment_id_unique_not_null"
        )
        payments_collection.create_index("status")
        payments_collection.create_index("created_at")
                
        # ------------------------------------------------------------
        # INSTAGRAM INDEXES
        # ------------------------------------------------------------
        
        # Instagram Cache - username lookup (unique)
        instagram_reels_collection.create_index(
            [("username", ASCENDING)],
            unique=True,
            name="username_unique"
        )
        
        # Instagram Cache - cached_at for sorting
        instagram_reels_collection.create_index(
            [("cached_at", DESCENDING)],
            name="cached_at_desc"
        )
        
        # Instagram Refresh Locks - username lookup (UNIQUE - CRITICAL FOR ATOMICITY)
        instagram_refresh_lock_collection.create_index(
            [("username", ASCENDING)],
            unique=True,  # ← CRITICAL: Enforces atomic lock acquisition
            name="username_unique_lock"
        )
        
        # Instagram Refresh Locks - TTL cleanup (failsafe)
        instagram_refresh_lock_collection.create_index(
            [("expires_at", ASCENDING)],
            expireAfterSeconds=0,
            name="ttl_expires_at"
        )
        
        # Instagram Retry Queue - status and next_retry_at
        instagram_retry_queue_collection.create_index(
            [("status", ASCENDING), ("next_retry_at", ASCENDING)],
            name="status_next_retry"
        )
        
        instagram_retry_queue_collection.create_index(
            [("username", ASCENDING)],
            name="username_lookup"
        )
        
        instagram_retry_queue_collection.create_index(
            [("created_at", DESCENDING)],
            name="created_at_desc"
        )
        
        # Instagram Retry Queue - TTL for old failed items (auto-cleanup)
        instagram_retry_queue_collection.create_index(
            [("failed_at", ASCENDING)],
            expireAfterSeconds=604800,  # 7 days TTL for failed items
            name="ttl_7days_failed"
        )
        
        # Instagram Metrics - username and timestamp
        instagram_metrics_collection.create_index(
            [("username", ASCENDING), ("timestamp", DESCENDING)],
            name="username_timestamp"
        )
        
        instagram_metrics_collection.create_index(
            [("timestamp", DESCENDING)],
            name="timestamp_desc"
        )
        
        # Instagram Metrics - TTL for auto-cleanup (30 days)
        instagram_metrics_collection.create_index(
            [("timestamp", ASCENDING)],
            expireAfterSeconds=2592000,  # 30 days TTL
            name="ttl_30days"
        )
        
        logger.info("✅ Instagram indexes created")
        
        # ------------------------------------------------------------
        # TIKTOK INDEXES
        # ------------------------------------------------------------
        
        # TikTok Cache - username lookup (unique)
        tiktok_cache_collection.create_index(
            [("username", ASCENDING)],
            unique=True,
            name="username_unique"
        )
        
        # TikTok Cache - cached_at for sorting
        tiktok_cache_collection.create_index(
            [("cached_at", DESCENDING)],
            name="cached_at_desc"
        )
        
        # TikTok Refresh Locks - username lookup (UNIQUE - CRITICAL FOR ATOMICITY)
        tiktok_refresh_lock_collection.create_index(
            [("username", ASCENDING)],
            unique=True,  # ← CRITICAL: Enforces atomic lock acquisition
            name="username_unique_lock"
        )
        
        # TikTok Refresh Locks - TTL cleanup (failsafe)
        tiktok_refresh_lock_collection.create_index(
            [("expires_at", ASCENDING)],
            expireAfterSeconds=0,
            name="ttl_expires_at"
        )
        
        # TikTok Retry Queue - status and next_retry_at
        tiktok_retry_queue_collection.create_index(
            [("status", ASCENDING), ("next_retry_at", ASCENDING)],
            name="status_next_retry"
        )
        
        tiktok_retry_queue_collection.create_index(
            [("username", ASCENDING)],
            name="username_lookup"
        )
        
        tiktok_retry_queue_collection.create_index(
            [("created_at", DESCENDING)],
            name="created_at_desc"
        )
        
        # TikTok Retry Queue - TTL for old failed items (auto-cleanup)
        tiktok_retry_queue_collection.create_index(
            [("failed_at", ASCENDING)],
            expireAfterSeconds=604800,  # 7 days TTL for failed items
            name="ttl_7days_failed"
        )
        
        # TikTok Metrics - username and timestamp
        tiktok_metrics_collection.create_index(
            [("username", ASCENDING), ("timestamp", DESCENDING)],
            name="username_timestamp"
        )
        
        tiktok_metrics_collection.create_index(
            [("timestamp", DESCENDING)],
            name="timestamp_desc"
        )
        
        # TikTok Metrics - TTL for auto-cleanup (30 days)
        tiktok_metrics_collection.create_index(
            [("timestamp", ASCENDING)],
            expireAfterSeconds=2592000,  # 30 days TTL
            name="ttl_30days"
        )
        
        logger.info("✅ TikTok indexes created")
        
        # ------------------------------------------------------------
        # USER MANAGEMENT INDEXES
        # ------------------------------------------------------------
        
        # Users - email lookup (unique)
        users_collection.create_index(
            [("email", ASCENDING)],
            unique=True,
            name="email_unique"
        )
        
        # Users - created_at for sorting
        users_collection.create_index(
            [("created_at", DESCENDING)],
            name="created_at_desc"
        )
        
        # Reset Tokens - token lookup + TTL
        reset_tokens_collection.create_index(
            [("token", ASCENDING)],
            unique=True,
            name="token_unique"
        )
        
        reset_tokens_collection.create_index(
            [("created_at", ASCENDING)],
            expireAfterSeconds=3600,  # 1 hour TTL
            name="ttl_1hour"
        )
        
        logger.info("✅ User management indexes created")
        
        logger.info("✅ All MongoDB indexes created successfully")
        
    except Exception as e:
        logger.error(f"❌ Error creating MongoDB indexes: {e}")
        raise


# ============================================================
# DATABASE HEALTH CHECK
# ============================================================

def check_database_health() -> dict:
    """
    Check MongoDB connection and collection health.
    Returns dict with status information.
    """
    try:
        # Ping server
        client.admin.command('ping')
        
        # Get database stats
        stats = db.command("dbstats")
        
        # Count documents in each collection
        collection_counts = {
            "instagram_cache": instagram_reels_collection.count_documents({}),
            "instagram_refresh_locks": instagram_refresh_lock_collection.count_documents({}),
            "instagram_retry_queue": instagram_retry_queue_collection.count_documents({}),
            "instagram_metrics": instagram_metrics_collection.count_documents({}),
            "tiktok_cache": tiktok_cache_collection.count_documents({}),
            "tiktok_refresh_locks": tiktok_refresh_lock_collection.count_documents({}),
            "tiktok_retry_queue": tiktok_retry_queue_collection.count_documents({}),
            "tiktok_metrics": tiktok_metrics_collection.count_documents({}),
            "users": users_collection.count_documents({}),
            "reset_tokens": reset_tokens_collection.count_documents({}),
            "payments": payments_collection.count_documents({})
        }
        
        return {
            "status": "healthy",
            "connected": True,
            "database": MONGODB_DB_NAME,
            "storage_size_mb": round(stats.get("dataSize", 0) / (1024 * 1024), 2),
            "collections": collection_counts,
            "total_documents": sum(collection_counts.values())
        }
        
    except Exception as e:
        logger.error(f"❌ Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "connected": False,
            "error": str(e)
        }


# ============================================================
# MIGRATION HELPER (ONE-TIME USE)
# ============================================================

def migrate_old_collection_names():
    """
    Migration helper to rename old collections to new naming convention.
    
    OLD NAMES:
    - cloudinary_retry_queue → instagram_retry_queue
    
    Run this once if upgrading from old schema.
    """
    try:
        logger.info("🔄 Starting collection migration...")
        
        # Check if old collection exists
        if "cloudinary_retry_queue" in db.list_collection_names():
            logger.info("📦 Found old 'cloudinary_retry_queue' collection")
            
            # Rename to new convention
            db["cloudinary_retry_queue"].rename("instagram_retry_queue")
            logger.info("✅ Renamed 'cloudinary_retry_queue' → 'instagram_retry_queue'")
        else:
            logger.info("ℹ️ No old 'cloudinary_retry_queue' collection found (migration not needed)")
        
        logger.info("✅ Collection migration complete")
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise


# ============================================================
# CLEANUP UTILITIES
# ============================================================

def cleanup_old_data(days: int = 30):
    """
    Clean up old data from metrics and completed retry queue items.
    
    Args:
        days: Number of days to keep (default 30)
    """
    try:
        from datetime import datetime, timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        logger.info(f"🧹 Cleaning up data older than {days} days...")
        
        # Clean old Instagram metrics
        instagram_result = instagram_metrics_collection.delete_many({
            "timestamp": {"$lt": cutoff_date}
        })
        logger.info(f"🗑️ Deleted {instagram_result.deleted_count} old Instagram metrics")
        
        # Clean old TikTok metrics
        tiktok_result = tiktok_metrics_collection.delete_many({
            "timestamp": {"$lt": cutoff_date}
        })
        logger.info(f"🗑️ Deleted {tiktok_result.deleted_count} old TikTok metrics")
        
        # Note: Failed retry items auto-clean via TTL (7 days)
        # We only manually clean very old pending items that somehow got stuck
        instagram_retry_result = instagram_retry_queue_collection.delete_many({
            "status": "pending",
            "created_at": {"$lt": cutoff_date}
        })
        logger.info(f"🗑️ Deleted {instagram_retry_result.deleted_count} stuck Instagram retry items")
        
        tiktok_retry_result = tiktok_retry_queue_collection.delete_many({
            "status": "pending",
            "created_at": {"$lt": cutoff_date}
        })
        logger.info(f"🗑️ Deleted {tiktok_retry_result.deleted_count} stuck TikTok retry items")
        
        total_deleted = (
            instagram_result.deleted_count + 
            tiktok_result.deleted_count + 
            instagram_retry_result.deleted_count + 
            tiktok_retry_result.deleted_count
        )
        
        logger.info(f"✅ Cleanup complete: {total_deleted} documents deleted")
        
        return {
            "success": True,
            "total_deleted": total_deleted,
            "instagram_metrics": instagram_result.deleted_count,
            "tiktok_metrics": tiktok_result.deleted_count,
            "instagram_retry_queue": instagram_retry_result.deleted_count,
            "tiktok_retry_queue": tiktok_retry_result.deleted_count
        }
        
    except Exception as e:
        logger.error(f"❌ Cleanup failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================
# AUTO-INITIALIZATION
# ============================================================

# Create indexes on module import (safe to run multiple times)
try:
    create_indexes()
except Exception as e:
    logger.warning(f"⚠️ Index creation failed (may already exist): {e}")


# ============================================================
# EXPORT SUMMARY
# ============================================================

logger.info("=" * 60)
logger.info("📊 DATABASE MODULE LOADED - PRODUCTION READY")
logger.info("=" * 60)
logger.info("Instagram Collections:")
logger.info("  - instagram_cache (NO TTL - logical expiry only)")
logger.info("  - instagram_refresh_locks (TTL: expires_at, UNIQUE)")
logger.info("  - instagram_retry_queue (TTL: 7 days for failed)")
logger.info("  - instagram_metrics (TTL: 30 days auto-cleanup)")
logger.info("")
logger.info("TikTok Collections:")
logger.info("  - tiktok_cache (NO TTL - logical expiry only)")
logger.info("  - tiktok_refresh_locks (TTL: expires_at, UNIQUE)")
logger.info("  - tiktok_retry_queue (TTL: 7 days for failed)")
logger.info("  - tiktok_metrics (TTL: 30 days auto-cleanup)")
logger.info("")
logger.info("User Management:")
logger.info("  - users (user accounts)")
logger.info("  - reset_tokens (TTL: 1 hour)")
logger.info("")
logger.info("🔒 CRITICAL INDEXES:")
logger.info("  - Refresh locks: UNIQUE on username (atomic acquire)")
logger.info("  - Refresh locks: TTL on expires_at (auto-cleanup)")
logger.info("  - Retry queue: TTL on failed_at (auto-cleanup)")
logger.info("  - Metrics: TTL on timestamp (30 days auto-cleanup)")
logger.info("=" * 60)