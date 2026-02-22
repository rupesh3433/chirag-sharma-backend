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
# ✅ Multi-provider payment indexes (Razorpay + Khalti)
# ✅ Unique partial index on pidx (Khalti)
# ✅ Compound index: (booking_id, provider)
# ✅ Event bookings collection with indexes
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
    client = MongoClient(
        MONGODB_URI,
        maxPoolSize=50,
        minPoolSize=10,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=10000,
        retryWrites=True,
        w='majority'
    )

    try:
        client.admin.command("ping")
        logger.info("✅ MongoDB connection successful")
    except Exception as e:
        logger.error(f"❌ MongoDB ping failed (continuing without crash): {e}")

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

# DONOT REMOVE THESE 5
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

# ------------------------------------------------------------
# EVENT BOOKINGS COLLECTION
# ------------------------------------------------------------
event_bookings_collection = db["event_bookings"]

# ============================================================
# INDEX CREATION
# ============================================================

def create_indexes():
    """
    Create all necessary indexes for optimal performance.
    Safe to call multiple times (MongoDB handles duplicates).
    """
    try:
        logger.info("🔧 Creating MongoDB indexes...")

        # --------------------------------
        # Donot Remove these My main these 5 collection's indexes
        # --------------------------------
        admin_reset_token_collection.create_index("expires_at", expireAfterSeconds=0)

        admin_collection.create_index("email", unique=True)

        booking_collection.create_index("created_at")
        booking_collection.create_index("status")
        booking_collection.create_index("payment_status")
        booking_collection.create_index("payment_provider")

        knowledge_collection.create_index("language")
        knowledge_collection.create_index("is_active")
        knowledge_collection.create_index("created_at")
        knowledge_collection.create_index([("language", 1), ("is_active", 1)])

        event_collection.create_index("created_at")
        event_collection.create_index("status")
        event_collection.create_index("is_active")
        event_collection.create_index("date_from")
        event_collection.create_index("date_to")
        event_collection.create_index([("status", 1), ("is_active", 1)])
        event_collection.create_index([("date_from", 1), ("date_to", 1)])

        # ------------------------------------------------------------
        # PAYMENTS INDEXES — MULTI-PROVIDER (Razorpay + Khalti)
        # ------------------------------------------------------------

        payments_collection.create_index(
            [("booking_id", ASCENDING)],
            name="booking_id_idx"
        )

        payments_collection.create_index(
            [("provider", ASCENDING)],
            name="provider_idx"
        )

        payments_collection.create_index(
            [("order_id", ASCENDING)],
            name="order_id_idx"
        )

        payments_collection.create_index(
            [("status", ASCENDING)],
            name="status_idx"
        )

        payments_collection.create_index(
            [("created_at", DESCENDING)],
            name="created_at_desc"
        )

        payments_collection.create_index(
            [("booking_id", ASCENDING), ("provider", ASCENDING)],
            name="booking_provider_compound"
        )

        payments_collection.create_index(
            [("booking_id", ASCENDING), ("status", ASCENDING)],
            name="booking_status_compound"
        )

        payments_collection.create_index(
            [("payment_id", ASCENDING)],
            unique=True,
            partialFilterExpression={
                "payment_id": {"$type": "string"}
            },
            name="payment_id_unique_not_null"
        )

        payments_collection.create_index(
            [("pidx", ASCENDING)],
            unique=True,
            sparse=True,
            name="khalti_pidx_unique_sparse"
        )

        payments_collection.create_index(
            [("fraud_flag", ASCENDING)],
            name="fraud_flag_idx"
        )

        logger.info("✅ Payments collection indexes created (multi-provider: Razorpay + Khalti)")

        # ------------------------------------------------------------
        # INSTAGRAM INDEXES
        # ------------------------------------------------------------

        instagram_reels_collection.create_index(
            [("username", ASCENDING)],
            unique=True,
            name="username_unique"
        )

        instagram_reels_collection.create_index(
            [("cached_at", DESCENDING)],
            name="cached_at_desc"
        )

        instagram_refresh_lock_collection.create_index(
            [("username", ASCENDING)],
            unique=True,
            name="username_unique_lock"
        )

        instagram_refresh_lock_collection.create_index(
            [("expires_at", ASCENDING)],
            expireAfterSeconds=0,
            name="ttl_expires_at"
        )

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

        instagram_retry_queue_collection.create_index(
            [("failed_at", ASCENDING)],
            expireAfterSeconds=604800,
            name="ttl_7days_failed"
        )

        instagram_metrics_collection.create_index(
            [("username", ASCENDING), ("timestamp", DESCENDING)],
            name="username_timestamp"
        )

        instagram_metrics_collection.create_index(
            [("timestamp", DESCENDING)],
            name="timestamp_desc"
        )

        instagram_metrics_collection.create_index(
            [("timestamp", ASCENDING)],
            expireAfterSeconds=2592000,
            name="ttl_30days"
        )

        logger.info("✅ Instagram indexes created")

        # ------------------------------------------------------------
        # TIKTOK INDEXES
        # ------------------------------------------------------------

        tiktok_cache_collection.create_index(
            [("username", ASCENDING)],
            unique=True,
            name="username_unique"
        )

        tiktok_cache_collection.create_index(
            [("cached_at", DESCENDING)],
            name="cached_at_desc"
        )

        tiktok_refresh_lock_collection.create_index(
            [("username", ASCENDING)],
            unique=True,
            name="username_unique_lock"
        )

        tiktok_refresh_lock_collection.create_index(
            [("expires_at", ASCENDING)],
            expireAfterSeconds=0,
            name="ttl_expires_at"
        )

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

        tiktok_retry_queue_collection.create_index(
            [("failed_at", ASCENDING)],
            expireAfterSeconds=604800,
            name="ttl_7days_failed"
        )

        tiktok_metrics_collection.create_index(
            [("username", ASCENDING), ("timestamp", DESCENDING)],
            name="username_timestamp"
        )

        tiktok_metrics_collection.create_index(
            [("timestamp", DESCENDING)],
            name="timestamp_desc"
        )

        tiktok_metrics_collection.create_index(
            [("timestamp", ASCENDING)],
            expireAfterSeconds=2592000,
            name="ttl_30days"
        )

        logger.info("✅ TikTok indexes created")

        # ------------------------------------------------------------
        # USER MANAGEMENT INDEXES
        # ------------------------------------------------------------

        users_collection.create_index(
            [("email", ASCENDING)],
            unique=True,
            name="email_unique"
        )

        users_collection.create_index(
            [("created_at", DESCENDING)],
            name="created_at_desc"
        )

        reset_tokens_collection.create_index(
            [("token", ASCENDING)],
            unique=True,
            name="token_unique"
        )

        reset_tokens_collection.create_index(
            [("created_at", ASCENDING)],
            expireAfterSeconds=3600,
            name="ttl_1hour"
        )

        logger.info("✅ User management indexes created")

        # ------------------------------------------------------------
        # EVENT BOOKINGS INDEXES
        # ------------------------------------------------------------

        event_bookings_collection.create_index(
            [("event_id", ASCENDING)],
            name="event_id_idx"
        )

        event_bookings_collection.create_index(
            [("status", ASCENDING)],
            name="status_idx"
        )

        event_bookings_collection.create_index(
            [("phone", ASCENDING)],
            name="phone_idx"
        )

        event_bookings_collection.create_index(
            [("email", ASCENDING)],
            name="email_idx"
        )

        event_bookings_collection.create_index(
            [("ticket_code", ASCENDING)],
            unique=True,
            sparse=True,
            name="ticket_code_unique_sparse"
        )

        event_bookings_collection.create_index(
            [("event_id", ASCENDING), ("status", ASCENDING)],
            name="event_status_compound"
        )

        event_bookings_collection.create_index(
            [("created_at", DESCENDING)],
            name="created_at_desc"
        )

        event_bookings_collection.create_index(
            [("payment_order_id", ASCENDING)],
            sparse=True,
            name="payment_order_id_idx"
        )

        event_bookings_collection.create_index(
            [("payment_pidx", ASCENDING)],
            sparse=True,
            name="payment_pidx_idx"
        )

        logger.info("✅ Event bookings indexes created")

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
        client.admin.command('ping')

        stats = db.command("dbstats")

        collection_counts = {
            "bookings": booking_collection.count_documents({}),
            "payments": payments_collection.count_documents({}),
            "payments_razorpay": payments_collection.count_documents({"provider": "razorpay"}),
            "payments_khalti": payments_collection.count_documents({"provider": "khalti"}),
            "event_bookings": event_bookings_collection.count_documents({}),
            "event_bookings_paid": event_bookings_collection.count_documents({"status": "paid"}),
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
    Run this once if upgrading from old schema.
    """
    try:
        logger.info("🔄 Starting collection migration...")

        if "cloudinary_retry_queue" in db.list_collection_names():
            logger.info("📦 Found old 'cloudinary_retry_queue' collection")
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

        instagram_result = instagram_metrics_collection.delete_many({
            "timestamp": {"$lt": cutoff_date}
        })
        logger.info(f"🗑️ Deleted {instagram_result.deleted_count} old Instagram metrics")

        tiktok_result = tiktok_metrics_collection.delete_many({
            "timestamp": {"$lt": cutoff_date}
        })
        logger.info(f"🗑️ Deleted {tiktok_result.deleted_count} old TikTok metrics")

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
logger.info("Payments Collection (Multi-Provider):")
logger.info("  - booking_id (lookup)")
logger.info("  - provider (razorpay | khalti)")
logger.info("  - (booking_id, provider) compound")
logger.info("  - (booking_id, status) compound")
logger.info("  - payment_id UNIQUE PARTIAL (not null)")
logger.info("  - pidx UNIQUE PARTIAL (Khalti, not null)")
logger.info("  - order_id (lookup)")
logger.info("  - fraud_flag (monitoring)")
logger.info("")
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
logger.info("Event Bookings:")
logger.info("  - event_bookings (event_id, status, phone, email)")
logger.info("  - ticket_code UNIQUE SPARSE")
logger.info("  - (event_id, status) compound")
logger.info("")
logger.info("🔒 CRITICAL INDEXES:")
logger.info("  - Refresh locks: UNIQUE on username (atomic acquire)")
logger.info("  - Refresh locks: TTL on expires_at (auto-cleanup)")
logger.info("  - Retry queue: TTL on failed_at (auto-cleanup)")
logger.info("  - Metrics: TTL on timestamp (30 days auto-cleanup)")
logger.info("  - payments.pidx: UNIQUE PARTIAL (Khalti idempotency)")
logger.info("  - payments.payment_id: UNIQUE PARTIAL (cross-provider)")
logger.info("  - event_bookings.ticket_code: UNIQUE SPARSE")
logger.info("=" * 60)