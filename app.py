from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import uuid
from typing import Dict, Any
from datetime import datetime
from contextlib import asynccontextmanager

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

# Admin Routes
from routes_admin_auth import router as admin_auth_router
from routes_admin_bookings import router as admin_bookings_router  # Includes payment management
from routes_admin_knowledge import router as admin_knowledge_router
from routes_admin_analytics import router as admin_analytics_router
from routes_admin_events import router as admin_events_router
from routes_payment_webhooks import router as payment_webhook_router


# Agent
from agent import AgentOrchestrator, create_agent_router

# ----------------------
# Logging Configuration
# ----------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ----------------------
# Initialize Agent
# ----------------------
orchestrator = None
agent_router = None

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
    logger.info("📦 Service: JinniChirag Website Backend v2.0.0")
    logger.info("📸 Image Storage: Cloudinary configured")
    logger.info("💳 Payment Gateway: Razorpay (India - Default)")

    try:
        # Initialize Agent Orchestrator
        orchestrator = AgentOrchestrator()
        agent_router = create_agent_router(orchestrator)
        app.include_router(agent_router)
        logger.info("✅ Agent router configured")

        # Verify Payment Service
        try:
            from payment.razorpay_payment_service import get_razorpay_service
            razorpay_service = get_razorpay_service()
            logger.info("✅ Razorpay payment service initialized")
        except Exception as e:
            logger.warning(f"⚠️ Payment service initialization warning: {e}")

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
    description="Backend API for JinniChirag booking system with AI agent, Event Management, and Integrated Payment Processing",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

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

# ----------------------
# Root Endpoints
# ----------------------
@app.get("/")
async def root():
    """Root endpoint - service status"""
    return {
        "service": "JinniChirag Website Backend",
        "version": "2.0.0",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "endpoints": {
            "docs": "/docs",
            "redoc": "/redoc",
            "health": "/health",
            "chat": "/chat",
            "bookings": "/bookings (includes payment)",
            "admin": "/admin"
        },
        "features": [
            "AI Chatbot (Multi-language)",
            "Service Bookings with OTP",
            "Integrated Payment Processing (Razorpay)",
            "Admin Approval with Payment Link",
            "Event Management",
            "WhatsApp Notifications"
        ],
        "payment": {
            "default_provider": "Razorpay (India)",
            "webhook": "/razorpay/webhook",
            "approval_flow": "Admin approves → Payment link sent via WhatsApp"
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

    # Check Payment Service
    try:
        from payment.razorpay_payment_service import get_razorpay_service
        razorpay_service = get_razorpay_service()
        health_status["services"]["payment"] = {
            "status": "healthy",
            "provider": "razorpay"
        }
    except Exception as e:
        health_status["services"]["payment"] = {
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


# ----------------------
# Include Routers
# ----------------------

# ============================================================
# PUBLIC ROUTES
# ============================================================

# Chat Service (AI Chatbot)
app.include_router(
    chat_router,
    tags=["Public - Chat"]
)
logger.info("✅ Loaded: Public Chat Routes (/chat)")

# Booking Service (Includes Payment Endpoints)
app.include_router(
    bookings_router,
    tags=["Public - Bookings & Payments"]
)

# Payment Webhooks (Global - No Prefix)
app.include_router(
    payment_webhook_router,
    tags=["Public - Payment Webhooks"]
)
logger.info("✅ Loaded: Payment Webhook Routes")
logger.info("   ├── POST /razorpay/webhook")
logger.info("   └── POST /khalti/webhook")


logger.info("✅ Loaded: Public Booking Routes with Payment (/bookings)")
logger.info("   ├── POST /bookings/request")
logger.info("   ├── POST /bookings/verify-otp")
logger.info("   ├── POST /razorpay/webhook")
logger.info("   ├── GET  /bookings/{id}/payment-status")
logger.info("   └── POST /bookings/{id}/cancel")

# Event Service (Public Events)
app.include_router(
    public_events_router,
    tags=["Public - Events"]
)
logger.info("✅ Loaded: Public Event Routes")

# Social Media Fetching
app.include_router(
    instagram_router,
    tags=["Public - Instagram"]
)
logger.info("✅ Loaded: Instagram Routes")

app.include_router(
    tiktok_router,
    tags=["Public - TikTok"]
)
logger.info("✅ Loaded: TikTok Routes")

# ============================================================
# ADMIN ROUTES (Protected)
# ============================================================

# Admin Authentication
app.include_router(
    admin_auth_router,
    tags=["Admin - Auth"]
)
logger.info("✅ Loaded: Admin Auth Routes")

# Admin Booking Management (Includes Payment Management)
app.include_router(
    admin_bookings_router,
    tags=["Admin - Bookings & Payments"]
)
logger.info("✅ Loaded: Admin Booking Routes with Payment")
logger.info("   ├── PATCH /admin/bookings/{id}/status (creates payment link)")
logger.info("   ├── POST  /admin/bookings/{id}/refund")
logger.info("   ├── GET   /admin/bookings/{id}/payment-history")
logger.info("   └── GET   /admin/bookings/payments/analytics")

# Admin Knowledge Base
app.include_router(
    admin_knowledge_router,
    tags=["Admin - Knowledge"]
)
logger.info("✅ Loaded: Admin Knowledge Routes")

# Admin Analytics
app.include_router(
    admin_analytics_router,
    tags=["Admin - Analytics"]
)
logger.info("✅ Loaded: Admin Analytics Routes")

# Admin Events
app.include_router(
    admin_events_router,
    tags=["Admin - Events"]
)
logger.info("✅ Loaded: Admin Event Routes")

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
        "api_version": "2.0.0",
        "service": "JinniChirag Website Backend",
        "documentation": {
            "swagger": "/docs",
            "redoc": "/redoc"
        },
        "architecture": {
            "payment_integration": "Consolidated in booking routes",
            "payment_webhook": "/razorpay/webhook",
            "approval_triggers_payment": True
        },
        "endpoint_groups": {
            "public": {
                "chat": "/chat (AI Chatbot)",
                "bookings": "/bookings (Bookings + Payment)",
                "events": "/events (Public Events)",
                "payment_webhook": "/razorpay/webhook"
            },
            "admin": {
                "auth": "/admin/auth (Admin Authentication)",
                "bookings": "/admin/bookings (Booking + Payment Management)",
                "knowledge": "/admin/knowledge (Knowledge Base)",
                "analytics": "/admin/analytics (Analytics Dashboard)",
                "events": "/admin/events (Event Management)"
            },
            "agent": {
                "chat": "/agent/chat (AI Agent)",
                "health": "/agent/health (Agent Health)"
            }
        },
        "features": {
            "booking_flow": "OTP → Verify → Pending → Admin Approves (creates payment) → User Pays → Confirmed",
            "payment_providers": {
                "india": "Razorpay (Active)",
                "nepal": "Khalti (Coming Soon)",
                "default": "Razorpay"
            },
            "notifications": "WhatsApp (Twilio)",
            "languages": ["English", "Nepali", "Hindi", "Marathi"]
        },
        "approval_workflow": {
            "step_1": "Admin approves booking via PATCH /admin/bookings/{id}/status",
            "step_2": "Payment order created automatically via Razorpay",
            "step_3": "Payment link sent to customer via WhatsApp",
            "step_4": "Customer pays via secure Razorpay checkout",
            "step_5": "Webhook confirms payment → Booking auto-confirmed"
        }
    }

# ----------------------
# Run Application
# ----------------------
if __name__ == "__main__":
    import uvicorn
    import os

    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")

    logger.info("=" * 60)
    logger.info("🌐 STARTING JINNICHIRAG BACKEND SERVER")
    logger.info("=" * 60)
    logger.info(f"📍 Host: {host}")
    logger.info(f"🔌 Port: {port}")
    logger.info(f"📚 Docs: http://{host}:{port}/docs")
    logger.info(f"🔍 ReDoc: http://{host}:{port}/redoc")
    logger.info(f"💳 Payment: Integrated in /bookings routes")
    logger.info("=" * 60)

    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )