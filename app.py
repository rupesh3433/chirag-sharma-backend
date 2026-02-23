# app.py

from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import uuid
from typing import Dict, Any
from datetime import datetime
from contextlib import asynccontextmanager
import uvicorn
import os
from config import CORS_ORIGINS

# ----------------------
# Updated Router Imports - Payment integrated into bookings
# ----------------------
# Public Routes
from routes_public_chat import router as chat_router
from routes_public_bookings import router as bookings_router  # Includes payment endpoints
from routes_public_events import router as public_events_router
from routes_public_instagramFetch import router as instagram_router
from routes_public_tiktokFetch import router as tiktok_router
from routes_admin_portfolio import router as admin_portfolio_router
from routes_public_portfolio import router as public_portfolio_router

# Admin Routes
from routes_admin_auth import router as admin_auth_router
from routes_admin_bookings import router as admin_bookings_router  # Includes payment management
from routes_admin_knowledge import router as admin_knowledge_router
from routes_admin_analytics import router as admin_analytics_router
from routes_admin_events import router as admin_events_router
from routes_payment_webhooks import router as payment_webhook_router


# ✅ WebSocket Live Viewer Manager (replaces routes_visitor_heartbeat)
from ws_live import live_manager

# Agent
from agent import AgentOrchestrator, create_agent_router

# ----------------------
# Logging Configuration
# ----------------------
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()

if ENVIRONMENT == "production":
    LOG_LEVEL = logging.WARNING   # warnings + errors + critical
else:
    LOG_LEVEL = logging.INFO     # full visibility locally

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# ----------------------
# Initialize Agent
# ----------------------
orchestrator = None
agent_router = None

# ----------------------
# Background tasks storage (for clean shutdown)
# ----------------------
_background_tasks = []

# ----------------------
# Lifespan Management
# ----------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup & shutdown lifecycle"""
    global orchestrator, agent_router

    # ---------- STARTUP ----------
    logger.info("=" * 60)
    logger.info("🚀 APPLICATION STARTING UP")
    logger.info("=" * 60)
    logger.info("📦 Service: JinniChirag Website Backend v3.0.0")
    logger.info("📸 Image Storage: Cloudinary configured")
    logger.info("💳 Payment Gateways: Razorpay (INR) + Khalti (NPR)")

    try:
        # Initialize Agent Orchestrator
        orchestrator = AgentOrchestrator()
        agent_router = create_agent_router(orchestrator)
        app.include_router(agent_router)
        logger.info("✅ Agent router configured")

        # Verify Razorpay Payment Service
        try:
            from payment.razorpay_payment_service import get_razorpay_service
            get_razorpay_service()
            logger.info("✅ Razorpay payment service initialized")
        except Exception as e:
            logger.warning(f"⚠️ Razorpay service initialization warning: {e}")

        # Verify Khalti Payment Service
        try:
            from payment.khalti_payment_service import get_khalti_service
            get_khalti_service()
            logger.info("✅ Khalti payment service initialized")
        except Exception as e:
            logger.warning(f"⚠️ Khalti service initialization warning: {e}")

        # Database health check
        try:
            from database import check_database_health
            db_health = check_database_health()
            if db_health.get("connected"):
                logger.info("✅ Database connected successfully")
                logger.info(f"📊 Total documents: {db_health.get('total_documents', 0)}")
            else:
                logger.error("❌ Database connection failed")
        except Exception as e:
            logger.warning(f"⚠️ Database health check warning: {e}")

        # ── Start WebSocket cleanup task ────────────────────────────
        # Removes inactive connections every 10 seconds.
        # Connections idle for 30s+ are auto-closed.
        try:
            await live_manager.start_cleanup_task()
            logger.info("✅ WebSocket live viewer manager started")
            logger.info("   ├── Cleanup interval: 10 seconds")
            logger.info("   └── Inactivity timeout: 30 seconds")
        except Exception as e:
            logger.warning(f"⚠️ WebSocket manager startup warning: {e}")

        # ── Start analytics counter cleanup task ───────────────────
        # Removes expired time buckets (hourly > 48h, daily > 30d).
        # Runs every 1 hour. Keeps analytics_counters document bounded.
        try:
            from analytics_counter import start_cleanup_task as start_counter_cleanup
            counter_task = await start_counter_cleanup()
            _background_tasks.append(counter_task)
            logger.info("✅ Analytics counter cleanup task started")
            logger.info("   ├── Cleanup interval: 1 hour")
            logger.info("   ├── Hourly bucket TTL: 48 hours")
            logger.info("   └── Daily bucket TTL: 30 days")
        except Exception as e:
            logger.warning(f"⚠️ Counter cleanup task startup warning: {e}")

        logger.info("=" * 60)
        logger.info("✅ STARTUP COMPLETE")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ Startup failed: {e}", exc_info=True)
        raise

    yield  # Application runs here

    # ---------- SHUTDOWN ----------
    logger.info("🛑 Application shutting down...")

    try:
        # Stop WebSocket cleanup task
        live_manager.stop_cleanup_task()
        logger.info("✅ WebSocket manager stopped")

        # Cancel analytics background tasks
        for task in _background_tasks:
            task.cancel()
        if _background_tasks:
            logger.info(f"✅ Cancelled {len(_background_tasks)} background tasks")

        if orchestrator:
            cleaned = orchestrator.memory_service.cleanup_old_sessions()
            logger.info(f"🧹 Cleaned up {cleaned} sessions")

        logger.info("✅ Cleanup complete")
        logger.info("👋 Application shutdown successful")

    except Exception as e:
        logger.error(f"❌ Shutdown error: {e}", exc_info=True)


# ----------------------
# App Setup
# ----------------------
app = FastAPI(
    title="JinniChirag Website Backend",
    description="Backend API for JinniChirag booking system with AI agent, Event Management, Multi-Provider Payment (Razorpay INR + Khalti NPR), WebSocket Live Viewers, and Counter Analytics",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# ----------------------
# Visitor Tracking Middleware
# Registers SmartVisitorMiddleware which:
#   1. Upserts site_sessions (1 per IP per hour)
#   2. Atomically increments analytics_counters (total/hourly/daily)
# ----------------------
from visitor_tracking import setup_visitor_tracking
setup_visitor_tracking(app)
logger.info("✅ Visitor Tracking Middleware Registered")
logger.info("   ├── Session dedup: 1 doc per IP per hour")
logger.info("   └── Counter increment: atomic $inc per request")


# ----------------------
# CORS Middleware
# ----------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------
# Request ID Middleware
# ----------------------
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add unique request ID for tracking"""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id

    return response

# ----------------------
# Global Exception Handler
# ----------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions gracefully"""
    request_id = getattr(request.state, "request_id", "unknown")

    logger.error(
        f"❌ Unhandled exception [Request ID: {request_id}]: {exc}",
        exc_info=True
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred",
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


# ============================================================
# WEBSOCKET — REAL-TIME LIVE VIEWERS
# ============================================================

VSID_COOKIE = "__vsid"   # Must match visitor_tracking.COOKIE_NAME


@app.websocket("/ws/live")
async def websocket_live_viewers(websocket: WebSocket):
    """
    Public-only WebSocket endpoint for real-time live viewer tracking.

    Qualification rules (enforced in ws_live.py LiveViewerManager):
      - Must stay connected ≥ 8 seconds to count as live
      - session_id deduplication: multi-tab from same session = 1 viewer
      - Reconnect-safe: same session_id in same hour = not re-counted in hourly

    Admin users are NEVER counted:
      - Authorization header present → reject
      - admin_token cookie present   → reject
    """

    # ── Block admin users ─────────────────────────────────────────

    auth_header = websocket.headers.get("authorization")
    if auth_header:
        await websocket.close(code=1008)
        return

    admin_cookie = websocket.cookies.get("admin_token")
    if admin_cookie:
        await websocket.close(code=1008)
        return

    # ── Extract session_id from __vsid cookie ─────────────────────
    # visitor_tracking.py sets this cookie on every tracked page request.
    # Format: sha256(ip_hash + ":" + hour_bucket)[:32]
    # If cookie is missing (direct WS connect, bot, etc.) use conn_id
    # as fallback — it will still work but won't dedup across tabs.

    vsid       = websocket.cookies.get(VSID_COOKIE, "").strip()
    conn_id    = str(uuid.uuid4())
    session_id = vsid if vsid else f"anon-{conn_id}"

    # ✅ live_manager.connect() calls websocket.accept() internally
    await live_manager.connect(websocket, conn_id, session_id)

    try:
        while True:
            msg = await websocket.receive_text()

            # Any message is treated as a keepalive ping
            await live_manager.ping(conn_id)

            # Send pong with current live count
            await websocket.send_json({
                "type":  "pong",
                "count": live_manager.get_live_count(),
            })

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("WS error [%s]: %s", conn_id[:8], exc)
    finally:
        await live_manager.disconnect(conn_id)


# ============================================================
# ROOT ENDPOINTS
# ============================================================

@app.get("/")
async def root():
    """Root endpoint - service status"""
    return {
        "service": "JinniChirag Website Backend",
        "version": "3.0.0",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "endpoints": {
            "docs": "/docs",
            "redoc": "/redoc",
            "health": "/health",
            "chat": "/chat",
            "bookings": "/bookings (includes payment)",
            "admin": "/admin",
            "ws_live": "/ws/live (WebSocket - real-time live viewers)",
        },
        "features": [
            "AI Chatbot (Multi-language)",
            "Service Bookings with OTP",
            "Multi-Provider Payment Processing (Razorpay + Khalti)",
            "Admin Approval with Payment Options Link",
            "Event Management",
            "WhatsApp Notifications",
            "WebSocket-based Real-Time Live Viewers (/ws/live)",
            "Counter-Only Analytics (analytics_counters — no raw visit logs)",
            "Auto-cleanup of Expired Time Buckets",
        ],
        "analytics": {
            "live_viewers": "WebSocket /ws/live (real-time push)",
            "counters": "GET /admin/analytics/counter-stats (total/today/hour/24h/30d)",
            "visitors": "GET /admin/analytics/visitors (session-based detail)",
            "cleanup": "Automatic — hourly buckets 48h TTL, daily buckets 30d TTL",
        },
        "payment": {
            "providers": {
                "razorpay": "INR (India)",
                "khalti": "NPR (Nepal)"
            },
            "webhooks": {
                "razorpay": "/razorpay/webhook",
                "khalti": "/khalti/webhook"
            },
            "approval_flow": "Admin approves → WhatsApp payment-options link → User selects provider → Pays → Webhook confirms"
        }
    }


@app.get("/health")
async def health():
    """Comprehensive health check endpoint"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {}
    }

    # Check Database
    try:
        from database import check_database_health
        db_health = check_database_health()
        health_status["services"]["database"] = {
            "status": "healthy" if db_health.get("connected") else "unhealthy",
            "connected": db_health.get("connected", False),
            "total_documents": db_health.get("total_documents", 0)
        }
    except Exception as e:
        health_status["services"]["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "degraded"

    # Check WebSocket Live Manager
    try:
        health_status["services"]["websocket_live"] = {
            "status": "healthy",
            "live_connections": live_manager.get_live_count(),
            "cleanup_running": (
                live_manager._cleanup_task is not None
                and not live_manager._cleanup_task.done()
            ),
        }
    except Exception as e:
        health_status["services"]["websocket_live"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "degraded"

    # Check Analytics Counter
    try:
        from analytics_counter import get_counters
        doc = get_counters()
        health_status["services"]["analytics_counters"] = {
            "status": "healthy",
            "total_visits": doc.get("total", 0),
            "hourly_buckets": len(doc.get("hourly", {})),
            "daily_buckets": len(doc.get("daily", {})),
        }
    except Exception as e:
        health_status["services"]["analytics_counters"] = {
            "status": "unhealthy",
            "error": str(e)
        }

    # Check Razorpay Payment Service
    try:
        from payment.razorpay_payment_service import get_razorpay_service
        get_razorpay_service()
        health_status["services"]["razorpay"] = {
            "status": "healthy",
            "provider": "razorpay",
            "currency": "INR"
        }
    except Exception as e:
        health_status["services"]["razorpay"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "degraded"

    # Check Khalti Payment Service
    try:
        from payment.khalti_payment_service import get_khalti_service
        get_khalti_service()
        health_status["services"]["khalti"] = {
            "status": "healthy",
            "provider": "khalti",
            "currency": "NPR"
        }
    except Exception as e:
        health_status["services"]["khalti"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "degraded"

    # Check Agent
    if orchestrator:
        health_status["services"]["agent"] = {
            "status": "healthy",
            "type": "AI Agent"
        }
    else:
        health_status["services"]["agent"] = {
            "status": "unhealthy",
            "error": "Agent not initialized"
        }
        health_status["status"] = "degraded"

    return health_status


# ============================================================
# PUBLIC ROUTES
# ============================================================

# Chat Service (AI Chatbot)
app.include_router(chat_router, tags=["Public - Chat"])
logger.info("✅ Loaded: Public Chat Routes (/chat)")

# Booking Service (Includes Multi-Provider Payment Endpoints)
app.include_router(bookings_router, tags=["Public - Bookings & Payments"])

# Portfolio pages to See Images and Videos
app.include_router(public_portfolio_router, tags=["Public - Portfolio"])


# Payment Webhooks (Global - No Prefix)
app.include_router(payment_webhook_router, tags=["Public - Payment Webhooks"])
logger.info("✅ Loaded: Payment Webhook Routes")
logger.info("   ├── POST /razorpay/webhook")
logger.info("   └── POST /khalti/webhook")

logger.info("✅ Loaded: Public Booking Routes with Multi-Provider Payment (/bookings)")
logger.info("   ├── POST /bookings/request")
logger.info("   ├── POST /bookings/verify-otp")
logger.info("   ├── POST /bookings/{id}/create-payment  ← razorpay|khalti")
logger.info("   ├── POST /bookings/razorpay/verify-payment")
logger.info("   ├── POST /bookings/khalti/verify-payment")
logger.info("   ├── POST /bookings/payment-failed")
logger.info("   ├── GET  /bookings/{id}/payment-status")
logger.info("   └── POST /bookings/{id}/cancel")

# Event Service (Public Events)
app.include_router(public_events_router, tags=["Public - Events"])
logger.info("✅ Loaded: Public Event Routes")

# Social Media Fetching
app.include_router(instagram_router, tags=["Public - Instagram"])
logger.info("✅ Loaded: Instagram Routes")

app.include_router(tiktok_router, tags=["Public - TikTok"])
logger.info("✅ Loaded: TikTok Routes")


# ============================================================
# ADMIN ROUTES (Protected)
# ============================================================

# Admin Authentication
app.include_router(admin_auth_router, tags=["Admin - Auth"])
logger.info("✅ Loaded: Admin Auth Routes")


# Admin Booking Management
app.include_router(admin_bookings_router, tags=["Admin - Bookings & Payments"])
logger.info("✅ Loaded: Admin Booking Routes with Multi-Provider Payment")
logger.info("   ├── PATCH /admin/bookings/{id}/status")
logger.info("   ├── POST  /admin/bookings/{id}/refund")
logger.info("   ├── GET   /admin/bookings/{id}/payment-history")
logger.info("   └── GET   /admin/bookings/payments/analytics")


# Admin Events
app.include_router(admin_events_router, tags=["Admin - Events"])
logger.info("✅ Loaded: Admin Event Routes")


# Portfolio pages Images Upload + Video Upload(unlisted) from admin sides
app.include_router(admin_portfolio_router, tags=["Admin - Portfolio"])


# Admin Analytics
app.include_router(admin_analytics_router, tags=["Admin - Analytics"])
logger.info("✅ Loaded: Admin Analytics Routes")
logger.info("   ├── GET  /admin/analytics/counter-stats  ← NEW (counter-only, O(1))")
logger.info("   ├── GET  /admin/analytics/live-viewers   ← UPDATED (WebSocket-based)")
logger.info("   ├── GET  /admin/analytics/overview")
logger.info("   ├── GET  /admin/analytics/visitors")
logger.info("   ├── POST /admin/analytics/counter-cleanup ← NEW (manual trigger)")
logger.info("   ├── GET  /admin/analytics/by-service")
logger.info("   ├── GET  /admin/analytics/by-month")
logger.info("   ├── GET  /admin/analytics/service-bookings/stats")
logger.info("   ├── GET  /admin/analytics/event-bookings/stats")
logger.info("   ├── GET  /admin/analytics/export/service-bookings")
logger.info("   └── GET  /admin/analytics/export/event-bookings")

# ============================================================
# WEBSOCKET LOGS
# ============================================================
logger.info("✅ Loaded: WebSocket Live Viewers (WS /ws/live)")
logger.info("   ├── On connect  → register + broadcast count")
logger.info("   ├── On message  → ping (update last_activity)")
logger.info("   ├── On disconnect → remove + broadcast count")
logger.info("   └── Cleanup task → remove inactive (>30s) every 10s")


# Admin Knowledge Base
app.include_router(admin_knowledge_router, tags=["Admin - Knowledge"])
logger.info("✅ Loaded: Admin Knowledge Routes")


# ============================================================
# AGENT ROUTER (Injected during lifespan startup)
# ============================================================
logger.info("ℹ️ Agent router will be loaded during startup")


# ----------------------
# API Documentation Enhancement
# ----------------------
@app.get("/api/info")
async def api_info():
    """Get comprehensive API information"""
    return {
        "api_version": "3.0.0",
        "service": "JinniChirag Website Backend",
        "documentation": {
            "swagger": "/docs",
            "redoc": "/redoc"
        },
        "analytics_architecture": {
            "live_viewers": {
                "method": "WebSocket (/ws/live)",
                "mechanism": "Each connected browser tab = 1 live viewer",
                "inactivity_timeout": "30 seconds",
                "cleanup_interval": "10 seconds",
                "broadcast": "Count pushed to all clients on every change",
            },
            "counters": {
                "collection": "analytics_counters",
                "document": "_id='global' (single document, always)",
                "fields": ["total", "hourly.{YYYY-MM-DD-HH}", "daily.{YYYY-MM-DD}"],
                "writes": "Atomic $inc — no raw visit documents",
                "reads": "O(1) — no aggregation pipelines",
                "cleanup": "Hourly buckets 48h TTL, daily 30d TTL, runs every 1h",
            },
            "sessions": {
                "collection": "site_sessions",
                "document": "1 per IP per hour (NOT a raw visit log)",
                "used_for": "Detailed analytics: top pages, referrers, quality metrics",
                "ttl": "90 days (MongoDB TTL index on last_seen)",
            },
        },
        "endpoint_groups": {
            "public": {
                "chat": "/chat (AI Chatbot)",
                "bookings": "/bookings (Bookings + Multi-Provider Payment)",
                "events": "/events (Public Events)",
                "websocket_live": "WS /ws/live (Real-time live viewer count)",
            },
            "admin": {
                "auth": "/admin/auth (Admin Authentication)",
                "bookings": "/admin/bookings (Booking + Payment Management)",
                "knowledge": "/admin/knowledge (Knowledge Base)",
                "analytics": "/admin/analytics (Analytics Dashboard)",
                "events": "/admin/events (Event Management)"
            },
        },
    }


# ----------------------
# Run Application
# ----------------------
if __name__ == "__main__":

    ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()

    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")

    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=(ENVIRONMENT == "development"),
        log_level="debug" if ENVIRONMENT == "development" else "warning",
        access_log=(ENVIRONMENT == "development"),
    )