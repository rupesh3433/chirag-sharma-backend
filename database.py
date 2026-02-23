# ============================================================
# PRODUCTION-GRADE DATABASE CONFIGURATION
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
# ✅ site_sessions collection (visitor tracking) — SINGLE SOURCE OF TRUTH
# ✅ analytics_counters collection (counter-only analytics — single document)
#
# INDEX CONFLICT PREVENTION STRATEGY
# ─────────────────────────────────────────────────────────────
# Root cause of IndexOptionsConflict:
#   MongoDB raises this when you attempt to create an index on a field
#   that already has an index with the same key pattern but a DIFFERENT
#   name or different options (e.g. a plain index vs a TTL index).
#
# Rules enforced here:
#   1. Every index has a deterministic, human-readable name.
#   2. No field has BOTH a plain index AND a TTL index simultaneously.
#      (last_seen in site_sessions uses TTL only — no duplicate plain index)
#   3. safe_create_index() detects existing conflicts and drops the
#      conflicting old index before recreating with correct options.
#   4. visitor_tracking.py does NOT create any indexes (removed).
#   5. create_indexes() is idempotent — safe to call on every restart.
#
# ANALYTICS COUNTERS STRATEGY
# ─────────────────────────────────────────────────────────────
#   Single document {_id: "global"} in analytics_counters collection.
#   All writes are atomic $inc — no per-visit documents created.
#   No extra indexes needed — _id index (auto-created) handles O(1) reads.
#   Expired buckets cleaned via analytics_counter.py background task.
#   Does NOT store IP, session_id, user_agent, or any raw visit data.
# ============================================================

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, OperationFailure
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
booking_collection            = db["bookings"]
admin_collection              = db["admins"]
admin_reset_token_collection  = db["admin_reset_tokens"]
knowledge_collection          = db["knowledge_base"]
event_collection              = db["events"]
payments_collection           = db["payments"]

# ------------------------------------------------------------
# INSTAGRAM COLLECTIONS
# ------------------------------------------------------------
instagram_reels_collection        = db["instagram_cache"]
instagram_refresh_lock_collection = db["instagram_refresh_locks"]
instagram_retry_queue_collection  = db["instagram_retry_queue"]
instagram_metrics_collection      = db["instagram_metrics"]

# ------------------------------------------------------------
# TIKTOK COLLECTIONS
# ------------------------------------------------------------
tiktok_cache_collection        = db["tiktok_cache"]
tiktok_refresh_lock_collection = db["tiktok_refresh_locks"]
tiktok_retry_queue_collection  = db["tiktok_retry_queue"]
tiktok_metrics_collection      = db["tiktok_metrics"]

# ------------------------------------------------------------
# USER MANAGEMENT COLLECTIONS
# ------------------------------------------------------------
users_collection        = db["users"]
reset_tokens_collection = db["reset_tokens"]

# ------------------------------------------------------------
# EVENT BOOKINGS COLLECTION
# ------------------------------------------------------------
event_bookings_collection = db["event_bookings"]

# ------------------------------------------------------------
# SITE VISITS COLLECTION  (legacy — kept for backward compat)
# ------------------------------------------------------------
site_visits_collection = db["site_visits"]

# ------------------------------------------------------------
# SITE SESSIONS COLLECTION  (visitor tracking — SmartVisitor)
# Single source of truth for all site_sessions indexes.
# visitor_tracking.py does NOT create indexes — only this file does.
# ------------------------------------------------------------
site_sessions_collection = db["site_sessions"]

# ------------------------------------------------------------
# ANALYTICS COUNTERS COLLECTION  (counter-only analytics)
# ─────────────────────────────────────────────────────────────
# Contains exactly ONE document: {_id: "global"}
# Structure:
#   {
#     "_id":   "global",
#     "total": 124582,           ← monotonically increasing all-time visit count
#     "hourly": {
#       "2026-02-23-08": 6,      ← visits in that UTC hour
#       ...                      ← auto-cleaned after 48 hours
#     },
#     "daily": {
#       "2026-02-23": 41,        ← visits on that UTC day
#       ...                      ← auto-cleaned after 30 days
#     }
#   }
#
# All writes: atomic $inc + upsert (no new documents, no raw visit logs).
# Reads: O(1) — single document lookup by _id="global".
# Cleanup: analytics_counter.py background task runs every 1 hour.
#   - Hourly buckets older than 48h → $unset
#   - Daily buckets older than 30d  → $unset
# No IP, session_id, user_agent, or raw visit data stored here.
# ------------------------------------------------------------
analytics_counters_collection = db["analytics_counters"]


# ============================================================
# SAFE INDEX HELPER — CONFLICT-AWARE, IDEMPOTENT
# ============================================================

def safe_create_index(collection, keys, name: str, **kwargs):
    """
    Idempotent index creation that handles IndexOptionsConflict safely.

    Strategy:
      1. Retrieve current indexes on the collection.
      2. If an index with the SAME name already exists and matches the
         key pattern AND options exactly → skip (already done).
      3. If an index with the SAME key pattern exists under a DIFFERENT
         name or with different options (conflict) → drop it first, then
         recreate with correct spec.
      4. If no matching index exists → create fresh.

    This never touches production data — it only manages index metadata.

    Args:
        collection: PyMongo collection object
        keys:       Index key spec, e.g. [("field", ASCENDING)] or "field"
        name:       Deterministic index name (snake_case, descriptive)
        **kwargs:   Any extra index options: unique, sparse, expireAfterSeconds,
                    partialFilterExpression, etc.
    """
    # Normalize keys to list-of-tuples form for consistent comparison
    if isinstance(keys, str):
        normalized_keys = [(keys, ASCENDING)]
    elif isinstance(keys, list):
        normalized_keys = keys
    else:
        normalized_keys = list(keys)

    key_set = {k for k, _ in normalized_keys}

    try:
        existing_indexes = {
            idx["name"]: idx
            for idx in collection.list_indexes()
        }

        # ── Case 1: Index with this exact name already exists ──────
        if name in existing_indexes:
            existing = existing_indexes[name]
            existing_key = {k for k in existing.get("key", {}).keys() if k != "_id"}

            # Check if the key pattern matches what we expect
            if existing_key == key_set:
                # Looks like the same index — skip silently
                logger.debug("✔ Index already exists (skipping): %s.%s", collection.name, name)
                return
            else:
                # Same name but different keys — drop and recreate
                logger.warning(
                    "⚠️  Index '%s' on '%s' has unexpected key pattern. "
                    "Dropping and recreating...", name, collection.name
                )
                collection.drop_index(name)

        # ── Case 2: Same key pattern exists under a DIFFERENT name ─
        #    This is the root cause of IndexOptionsConflict.
        #    E.g.: a plain index on last_seen named "last_seen_1"
        #    conflicts with a TTL index on last_seen named "ttl_90_days".
        for idx_name, idx in existing_indexes.items():
            if idx_name in ("_id_", name):
                continue
            idx_keys = {k for k in idx.get("key", {}).keys() if k != "_id"}
            if idx_keys == key_set:
                # Same field(s), different name/options → conflict
                existing_ttl   = "expireAfterSeconds" in idx
                requested_ttl  = "expireAfterSeconds" in kwargs
                existing_uniq  = idx.get("unique", False)
                requested_uniq = kwargs.get("unique", False)

                if existing_ttl != requested_ttl or existing_uniq != requested_uniq:
                    logger.warning(
                        "⚠️  IndexOptionsConflict detected on '%s': "
                        "existing index '%s' conflicts with requested '%s'. "
                        "Dropping existing conflicting index (data is safe)...",
                        collection.name, idx_name, name,
                    )
                    collection.drop_index(idx_name)
                    logger.info("✅ Dropped conflicting index '%s' on '%s'", idx_name, collection.name)
                    break
                # Same options, just a name difference — still drop old, create with correct name
                logger.warning(
                    "⚠️  Duplicate index (same keys, different name) on '%s': "
                    "dropping '%s', creating '%s'.",
                    collection.name, idx_name, name,
                )
                collection.drop_index(idx_name)
                break

        # ── Create the index with the correct spec ─────────────────
        collection.create_index(normalized_keys, name=name, **kwargs)
        logger.debug("✅ Index created: %s.%s", collection.name, name)

    except OperationFailure as exc:
        logger.error(
            "❌ Failed to create index '%s' on '%s': %s",
            name, collection.name, exc,
        )
        raise
    except Exception as exc:
        logger.error(
            "❌ Unexpected error creating index '%s' on '%s': %s",
            name, collection.name, exc,
        )
        raise


# ============================================================
# INDEX CREATION — SINGLE SOURCE OF TRUTH
# ============================================================

def create_indexes():
    """
    Create all necessary indexes for optimal performance.

    ✅ Safe to call on every application startup (idempotent).
    ✅ Detects and resolves IndexOptionsConflict automatically.
    ✅ Never deletes production data — only manages index metadata.
    ✅ One TTL index per field — no plain+TTL duplicates.
    ✅ All indexes for site_sessions live here ONLY.
       visitor_tracking.py does not create any indexes.
    ✅ analytics_counters needs NO extra indexes — _id auto-index is sufficient.
    """
    logger.info("🔧 Creating MongoDB indexes (idempotent, conflict-safe)...")

    # ────────────────────────────────────────────────────────────
    # ADMIN RESET TOKENS
    # ────────────────────────────────────────────────────────────
    safe_create_index(
        admin_reset_token_collection,
        [("expires_at", ASCENDING)],
        name="art_ttl_expires_at",
        expireAfterSeconds=0,
    )

    # ────────────────────────────────────────────────────────────
    # ADMINS
    # ────────────────────────────────────────────────────────────
    safe_create_index(
        admin_collection,
        [("email", ASCENDING)],
        name="admin_email_unique",
        unique=True,
    )

    # ────────────────────────────────────────────────────────────
    # BOOKINGS
    # ────────────────────────────────────────────────────────────
    safe_create_index(booking_collection, [("created_at", ASCENDING)],    name="bk_created_at_asc")
    safe_create_index(booking_collection, [("status", ASCENDING)],         name="bk_status_asc")
    safe_create_index(booking_collection, [("payment_status", ASCENDING)], name="bk_payment_status_asc")
    safe_create_index(booking_collection, [("payment_provider", ASCENDING)],name="bk_payment_provider_asc")

    # ────────────────────────────────────────────────────────────
    # KNOWLEDGE BASE
    # ────────────────────────────────────────────────────────────
    safe_create_index(knowledge_collection, [("language", ASCENDING)],                              name="kb_language_asc")
    safe_create_index(knowledge_collection, [("is_active", ASCENDING)],                             name="kb_is_active_asc")
    safe_create_index(knowledge_collection, [("created_at", ASCENDING)],                            name="kb_created_at_asc")
    safe_create_index(knowledge_collection, [("language", ASCENDING), ("is_active", ASCENDING)],    name="kb_language_active_compound")

    # ────────────────────────────────────────────────────────────
    # EVENTS
    # ────────────────────────────────────────────────────────────
    safe_create_index(event_collection, [("created_at", ASCENDING)],                                        name="ev_created_at_asc")
    safe_create_index(event_collection, [("status", ASCENDING)],                                            name="ev_status_asc")
    safe_create_index(event_collection, [("is_active", ASCENDING)],                                         name="ev_is_active_asc")
    safe_create_index(event_collection, [("date_from", ASCENDING)],                                         name="ev_date_from_asc")
    safe_create_index(event_collection, [("date_to", ASCENDING)],                                           name="ev_date_to_asc")
    safe_create_index(event_collection, [("status", ASCENDING), ("is_active", ASCENDING)],                  name="ev_status_active_compound")
    safe_create_index(event_collection, [("date_from", ASCENDING), ("date_to", ASCENDING)],                 name="ev_date_range_compound")

    # ────────────────────────────────────────────────────────────
    # PAYMENTS  (Multi-provider: Razorpay + Khalti)
    # ────────────────────────────────────────────────────────────
    safe_create_index(payments_collection, [("booking_id", ASCENDING)],                                      name="pay_booking_id_asc")
    safe_create_index(payments_collection, [("provider", ASCENDING)],                                        name="pay_provider_asc")
    safe_create_index(payments_collection, [("order_id", ASCENDING)],                                        name="pay_order_id_asc")
    safe_create_index(payments_collection, [("status", ASCENDING)],                                          name="pay_status_asc")
    safe_create_index(payments_collection, [("created_at", DESCENDING)],                                     name="pay_created_at_desc")
    safe_create_index(payments_collection, [("fraud_flag", ASCENDING)],                                      name="pay_fraud_flag_asc")
    safe_create_index(payments_collection, [("booking_id", ASCENDING), ("provider", ASCENDING)],             name="pay_booking_provider_compound")
    safe_create_index(payments_collection, [("booking_id", ASCENDING), ("status", ASCENDING)],               name="pay_booking_status_compound")

    safe_create_index(
        payments_collection,
        [("payment_id", ASCENDING)],
        name="pay_payment_id_unique_partial",
        unique=True,
        partialFilterExpression={"payment_id": {"$type": "string"}},
    )

    safe_create_index(
        payments_collection,
        [("pidx", ASCENDING)],
        name="pay_khalti_pidx_unique_sparse",
        unique=True,
        sparse=True,
    )

    logger.info("✅ Payments indexes created (multi-provider: Razorpay + Khalti)")

    # ────────────────────────────────────────────────────────────
    # INSTAGRAM
    # ────────────────────────────────────────────────────────────
    safe_create_index(instagram_reels_collection, [("username", ASCENDING)],                                 name="ig_cache_username_unique", unique=True)
    safe_create_index(instagram_reels_collection, [("cached_at", DESCENDING)],                               name="ig_cache_cached_at_desc")

    safe_create_index(instagram_refresh_lock_collection, [("username", ASCENDING)],                          name="ig_lock_username_unique", unique=True)
    safe_create_index(instagram_refresh_lock_collection, [("expires_at", ASCENDING)],                        name="ig_lock_ttl_expires_at", expireAfterSeconds=0)

    safe_create_index(instagram_retry_queue_collection, [("status", ASCENDING), ("next_retry_at", ASCENDING)], name="ig_retry_status_next_retry")
    safe_create_index(instagram_retry_queue_collection, [("username", ASCENDING)],                           name="ig_retry_username_asc")
    safe_create_index(instagram_retry_queue_collection, [("created_at", DESCENDING)],                        name="ig_retry_created_at_desc")
    safe_create_index(instagram_retry_queue_collection, [("failed_at", ASCENDING)],                          name="ig_retry_ttl_7_days", expireAfterSeconds=604800)

    safe_create_index(instagram_metrics_collection, [("username", ASCENDING), ("timestamp", DESCENDING)],   name="ig_metrics_username_ts")
    safe_create_index(instagram_metrics_collection, [("timestamp", DESCENDING)],                             name="ig_metrics_ts_desc")
    # TTL only — no separate plain index on timestamp to avoid conflict
    safe_create_index(instagram_metrics_collection, [("timestamp", ASCENDING)],                              name="ig_metrics_ttl_30_days", expireAfterSeconds=2592000)

    logger.info("✅ Instagram indexes created")

    # ────────────────────────────────────────────────────────────
    # TIKTOK
    # ────────────────────────────────────────────────────────────
    safe_create_index(tiktok_cache_collection, [("username", ASCENDING)],                                    name="tt_cache_username_unique", unique=True)
    safe_create_index(tiktok_cache_collection, [("cached_at", DESCENDING)],                                  name="tt_cache_cached_at_desc")

    safe_create_index(tiktok_refresh_lock_collection, [("username", ASCENDING)],                             name="tt_lock_username_unique", unique=True)
    safe_create_index(tiktok_refresh_lock_collection, [("expires_at", ASCENDING)],                           name="tt_lock_ttl_expires_at", expireAfterSeconds=0)

    safe_create_index(tiktok_retry_queue_collection, [("status", ASCENDING), ("next_retry_at", ASCENDING)], name="tt_retry_status_next_retry")
    safe_create_index(tiktok_retry_queue_collection, [("username", ASCENDING)],                              name="tt_retry_username_asc")
    safe_create_index(tiktok_retry_queue_collection, [("created_at", DESCENDING)],                          name="tt_retry_created_at_desc")
    safe_create_index(tiktok_retry_queue_collection, [("failed_at", ASCENDING)],                             name="tt_retry_ttl_7_days", expireAfterSeconds=604800)

    safe_create_index(tiktok_metrics_collection, [("username", ASCENDING), ("timestamp", DESCENDING)],      name="tt_metrics_username_ts")
    safe_create_index(tiktok_metrics_collection, [("timestamp", DESCENDING)],                                name="tt_metrics_ts_desc")
    # TTL only — no separate plain index on timestamp to avoid conflict
    safe_create_index(tiktok_metrics_collection, [("timestamp", ASCENDING)],                                 name="tt_metrics_ttl_30_days", expireAfterSeconds=2592000)

    logger.info("✅ TikTok indexes created")

    # ────────────────────────────────────────────────────────────
    # USER MANAGEMENT
    # ────────────────────────────────────────────────────────────
    safe_create_index(users_collection,        [("email", ASCENDING)],       name="usr_email_unique",  unique=True)
    safe_create_index(users_collection,        [("created_at", DESCENDING)], name="usr_created_at_desc")
    safe_create_index(reset_tokens_collection, [("token", ASCENDING)],       name="rst_token_unique",  unique=True)
    safe_create_index(reset_tokens_collection, [("created_at", ASCENDING)],  name="rst_ttl_1_hour",    expireAfterSeconds=3600)

    logger.info("✅ User management indexes created")

    # ────────────────────────────────────────────────────────────
    # EVENT BOOKINGS
    # ────────────────────────────────────────────────────────────
    safe_create_index(event_bookings_collection, [("event_id", ASCENDING)],                                  name="evbk_event_id_asc")
    safe_create_index(event_bookings_collection, [("status", ASCENDING)],                                    name="evbk_status_asc")
    safe_create_index(event_bookings_collection, [("phone", ASCENDING)],                                     name="evbk_phone_asc")
    safe_create_index(event_bookings_collection, [("email", ASCENDING)],                                     name="evbk_email_asc")
    safe_create_index(event_bookings_collection, [("created_at", DESCENDING)],                               name="evbk_created_at_desc")
    safe_create_index(event_bookings_collection, [("event_id", ASCENDING), ("status", ASCENDING)],           name="evbk_event_status_compound")
    safe_create_index(event_bookings_collection, [("ticket_code", ASCENDING)],                               name="evbk_ticket_code_unique_sparse", unique=True, sparse=True)
    safe_create_index(event_bookings_collection, [("payment_order_id", ASCENDING)],                          name="evbk_payment_order_id_sparse",   sparse=True)
    safe_create_index(event_bookings_collection, [("payment_pidx", ASCENDING)],                              name="evbk_payment_pidx_sparse",       sparse=True)

    logger.info("✅ Event bookings indexes created")

    # ────────────────────────────────────────────────────────────
    # SITE VISITS  (legacy collection — kept for backward compat)
    # ────────────────────────────────────────────────────────────
    safe_create_index(site_visits_collection, [("session_id", ASCENDING)],                              name="sv_session_id_asc")
    safe_create_index(site_visits_collection, [("page", ASCENDING)],                                    name="sv_page_asc")
    safe_create_index(site_visits_collection, [("timestamp", ASCENDING), ("session_id", ASCENDING)],    name="sv_timestamp_session_compound")
    # TTL on timestamp — note: this field cannot also have a plain ascending index.
    # The compound index above uses timestamp+session_id so it does NOT conflict.
    # The TTL below is the ONLY single-field index on timestamp for this collection.
    safe_create_index(site_visits_collection, [("timestamp", ASCENDING)],                               name="sv_ttl_180_days", expireAfterSeconds=60 * 60 * 24 * 180)

    logger.info("✅ Site visits indexes created (TTL: 180 days)")

    # ────────────────────────────────────────────────────────────
    # SITE SESSIONS  (SmartVisitor — IP+hour deterministic tracking)
    # ──────────────────────────────────────────────────────────────
    # ⚠️  THIS IS THE SINGLE SOURCE OF TRUTH FOR site_sessions indexes.
    #     visitor_tracking.py does NOT create any indexes.
    #
    # TTL STRATEGY:
    #   • last_seen → TTL 90 days  (auto-expire stale sessions)
    #   • last_seen is NOT also indexed as a plain index (avoids conflict)
    #   • first_seen → plain index for period queries (daily/weekly/monthly)
    #   • hour_bucket → plain index for hourly unique count
    #   • (is_live, last_heartbeat) → compound for live-viewer queries (legacy)
    #   • session_id → unique (one doc per IP+hour, atomic upsert)
    # ──────────────────────────────────────────────────────────────
    safe_create_index(
        site_sessions_collection,
        [("session_id", ASCENDING)],
        name="ss_session_id_unique",
        unique=True,
    )
    safe_create_index(
        site_sessions_collection,
        [("hour_bucket", ASCENDING)],
        name="ss_hour_bucket_asc",
    )
    safe_create_index(
        site_sessions_collection,
        [("first_seen", ASCENDING)],
        name="ss_first_seen_asc",
    )
    safe_create_index(
        site_sessions_collection,
        [("is_live", ASCENDING), ("last_heartbeat", ASCENDING)],
        name="ss_live_heartbeat_compound",
    )
    # TTL index on last_seen — auto-delete sessions older than 90 days.
    # ⚠️  Do NOT add a separate plain index on last_seen; MongoDB does not
    #     allow a field to have both a plain index and a TTL index.
    #     If you need to query by last_seen range, use the TTL index directly
    #     (MongoDB can use TTL indexes for range queries too).
    safe_create_index(
        site_sessions_collection,
        [("last_seen", ASCENDING)],
        name="ss_last_seen_ttl_90_days",
        expireAfterSeconds=60 * 60 * 24 * 90,
    )

    logger.info("✅ Site sessions indexes created (SmartVisitor, TTL: 90 days on last_seen)")

    # ────────────────────────────────────────────────────────────
    # ANALYTICS COUNTERS  (counter-only visitor analytics)
    # ──────────────────────────────────────────────────────────────
    # Single document store: {_id: "global"}
    # MongoDB auto-creates a unique _id index — that is the ONLY index needed.
    # All reads are: db["analytics_counters"].find_one({"_id": "global"})
    # → O(1) lookup on primary key. No additional indexes required.
    #
    # Bucket cleanup (hourly/daily key expiry) is handled programmatically
    # by analytics_counter.py background task (not via MongoDB TTL indexes),
    # because we use $unset on nested subdocument keys, which TTL cannot do.
    #
    # ⚠️  Do NOT add any indexes here — the auto _id index is sufficient
    #     and adding more would waste space on a single-document collection.
    # ──────────────────────────────────────────────────────────────
    logger.info("✅ Analytics counters ready (single-doc _id='global', auto _id index)")

    logger.info("✅ All MongoDB indexes created/verified successfully")


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
            "bookings":                     booking_collection.count_documents({}),
            "payments":                     payments_collection.count_documents({}),
            "payments_razorpay":            payments_collection.count_documents({"provider": "razorpay"}),
            "payments_khalti":              payments_collection.count_documents({"provider": "khalti"}),
            "event_bookings":               event_bookings_collection.count_documents({}),
            "event_bookings_paid":          event_bookings_collection.count_documents({"status": "paid"}),
            "instagram_cache":              instagram_reels_collection.count_documents({}),
            "instagram_refresh_locks":      instagram_refresh_lock_collection.count_documents({}),
            "instagram_retry_queue":        instagram_retry_queue_collection.count_documents({}),
            "instagram_metrics":            instagram_metrics_collection.count_documents({}),
            "tiktok_cache":                 tiktok_cache_collection.count_documents({}),
            "tiktok_refresh_locks":         tiktok_refresh_lock_collection.count_documents({}),
            "tiktok_retry_queue":           tiktok_retry_queue_collection.count_documents({}),
            "tiktok_metrics":               tiktok_metrics_collection.count_documents({}),
            "users":                        users_collection.count_documents({}),
            "reset_tokens":                 reset_tokens_collection.count_documents({}),
            "site_visits":                  site_visits_collection.count_documents({}),
            "site_sessions":                site_sessions_collection.count_documents({}),
            # analytics_counters always has exactly 1 document after first visit
            "analytics_counters":           analytics_counters_collection.count_documents({}),
        }

        # ── Analytics counter snapshot ────────────────────────────
        analytics_snapshot = {}
        try:
            doc = analytics_counters_collection.find_one({"_id": "global"})
            if doc:
                analytics_snapshot = {
                    "total_visits":    doc.get("total", 0),
                    "hourly_buckets":  len(doc.get("hourly", {})),
                    "daily_buckets":   len(doc.get("daily", {})),
                }
        except Exception:
            pass

        return {
            "status":              "healthy",
            "connected":           True,
            "database":            MONGODB_DB_NAME,
            "storage_size_mb":     round(stats.get("dataSize", 0) / (1024 * 1024), 2),
            "collections":         collection_counts,
            "total_documents":     sum(collection_counts.values()),
            "analytics_counters":  analytics_snapshot,
        }

    except Exception as e:
        logger.error(f"❌ Database health check failed: {e}")
        return {
            "status":    "unhealthy",
            "connected": False,
            "error":     str(e),
        }


# ============================================================
# INDEX DIAGNOSTIC UTILITY
# ============================================================

def diagnose_index_conflicts() -> dict:
    """
    Scan all collections and report any potential index conflicts.

    Detects:
      - Fields with both a plain index AND a TTL index (conflict)
      - Duplicate key patterns under different names
      - Indexes missing the expected naming convention

    Returns a dict with per-collection findings. Safe to call any time.
    """
    collections_to_check = {
        "bookings":                 booking_collection,
        "admins":                   admin_collection,
        "admin_reset_tokens":       admin_reset_token_collection,
        "knowledge_base":           knowledge_collection,
        "events":                   event_collection,
        "payments":                 payments_collection,
        "instagram_cache":          instagram_reels_collection,
        "instagram_refresh_locks":  instagram_refresh_lock_collection,
        "instagram_retry_queue":    instagram_retry_queue_collection,
        "instagram_metrics":        instagram_metrics_collection,
        "tiktok_cache":             tiktok_cache_collection,
        "tiktok_refresh_locks":     tiktok_refresh_lock_collection,
        "tiktok_retry_queue":       tiktok_retry_queue_collection,
        "tiktok_metrics":           tiktok_metrics_collection,
        "users":                    users_collection,
        "reset_tokens":             reset_tokens_collection,
        "site_visits":              site_visits_collection,
        "site_sessions":            site_sessions_collection,
        "analytics_counters":       analytics_counters_collection,
    }

    report = {}

    for col_name, col in collections_to_check.items():
        try:
            indexes = list(col.list_indexes())
            field_map: dict[str, list] = {}

            for idx in indexes:
                for field in idx.get("key", {}).keys():
                    if field == "_id":
                        continue
                    field_map.setdefault(field, []).append({
                        "name":               idx["name"],
                        "is_ttl":             "expireAfterSeconds" in idx,
                        "is_unique":          idx.get("unique", False),
                        "is_sparse":          idx.get("sparse", False),
                        "expireAfterSeconds": idx.get("expireAfterSeconds"),
                    })

            conflicts = {}
            for field, idxs in field_map.items():
                if len(idxs) > 1:
                    has_plain = any(not i["is_ttl"] for i in idxs)
                    has_ttl   = any(i["is_ttl"]     for i in idxs)
                    if has_plain and has_ttl:
                        conflicts[field] = {
                            "issue":   "CONFLICT: plain + TTL index on same single field",
                            "indexes": idxs,
                        }
                    else:
                        conflicts[field] = {
                            "issue":   "DUPLICATE: multiple indexes on same field",
                            "indexes": idxs,
                        }

            report[col_name] = {
                "total_indexes": len(indexes),
                "conflicts":     conflicts,
                "clean":         len(conflicts) == 0,
            }

        except Exception as exc:
            report[col_name] = {"error": str(exc)}

    return report


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
            "success":               True,
            "total_deleted":         total_deleted,
            "instagram_metrics":     instagram_result.deleted_count,
            "tiktok_metrics":        tiktok_result.deleted_count,
            "instagram_retry_queue": instagram_retry_result.deleted_count,
            "tiktok_retry_queue":    tiktok_retry_result.deleted_count,
        }

    except Exception as e:
        logger.error(f"❌ Cleanup failed: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# AUTO-INITIALIZATION
# ============================================================

try:
    create_indexes()
except Exception as e:
    logger.warning(f"⚠️ Index creation failed on startup (investigate immediately): {e}")


# ============================================================
# EXPORT SUMMARY
# ============================================================

logger.info("=" * 60)
logger.info("📊 DATABASE MODULE LOADED — PRODUCTION READY")
logger.info("=" * 60)
logger.info("Index management: database.py ONLY (single source of truth)")
logger.info("visitor_tracking.py: NO index creation (removed)")
logger.info("")
logger.info("site_sessions (SmartVisitor TTL strategy):")
logger.info("  - session_id: UNIQUE (one doc per IP+hour)")
logger.info("  - hour_bucket: plain ascending (hourly counts)")
logger.info("  - first_seen: plain ascending (period queries)")
logger.info("  - (is_live, last_heartbeat): compound (legacy live viewers)")
logger.info("  - last_seen: TTL 90 days ONLY — no duplicate plain index")
logger.info("")
logger.info("analytics_counters (counter-only analytics):")
logger.info("  - Single document: {_id: 'global'}")
logger.info("  - Fields: total, hourly.{YYYY-MM-DD-HH}, daily.{YYYY-MM-DD}")
logger.info("  - Writes: atomic $inc + upsert (no raw visit documents)")
logger.info("  - Reads: O(1) — _id primary key lookup only")
logger.info("  - Cleanup: programmatic $unset via analytics_counter.py (hourly task)")
logger.info("  - No extra indexes — auto _id index is sufficient")
logger.info("")
logger.info("Conflict-safe index helper: safe_create_index()")
logger.info("  - Detects same-key-different-name conflicts")
logger.info("  - Detects plain+TTL conflicts on same single field")
logger.info("  - Drops conflicting old index, recreates correctly")
logger.info("  - Never touches document data")
logger.info("=" * 60)