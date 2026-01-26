"""
Main Application - Enhanced with lifecycle management
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import uuid
from datetime import datetime

from config import CORS_ORIGINS
from routes_public import router as public_router
from routes_admin_auth import router as admin_auth_router
from routes_admin_bookings import router as admin_bookings_router
from routes_admin_knowledge import router as admin_knowledge_router
from routes_admin_analytics import router as admin_analytics_router

# Import new modular agent
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
# App Setup
# ----------------------
app = FastAPI(
    title="JinniChirag Website Backend",
    description="Backend API for JinniChirag booking system with AI agent",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
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
# Initialize Agent
# ----------------------
orchestrator = None
agent_router = None

# ----------------------
# Lifecycle Events
# ----------------------
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global orchestrator, agent_router
    
    logger.info("🚀 Application starting up...")
    logger.info(f"📦 Service: JinniChirag Website Backend v1.0.0")
    
    try:
        # Initialize orchestrator
        orchestrator = AgentOrchestrator()
        
        # Create agent router
        agent_router = create_agent_router(orchestrator)
        app.include_router(agent_router)
        logger.info("✅ Agent router configured")
                
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}", exc_info=True)
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🛑 Application shutting down...")
    
    try:
        if orchestrator:
            # Cleanup sessions and resources
            cleaned = orchestrator.memory_service.cleanup_old_sessions()
            logger.info(f"🧹 Cleaned up {cleaned} sessions")
            
        logger.info("✅ Cleanup complete")
        logger.info("👋 Application shutdown successful")
        
    except Exception as e:
        logger.error(f"❌ Shutdown error: {e}", exc_info=True)

# ----------------------
# Root Endpoints
# ----------------------
@app.get("/")
async def root():
    """Root endpoint - service status"""
    return {
        "service": "JinniChirag Website Backend",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "endpoints": {
            "docs": "/docs",
            "health": "/agent/health",
            "agent_chat": "/agent/chat"
        }
    }

@app.get("/health")
async def health():
    """Quick health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }

# ----------------------
# Include Routers
# ----------------------

# Public Routes
app.include_router(public_router)

# Admin Routes
app.include_router(admin_auth_router)
app.include_router(admin_bookings_router)
app.include_router(admin_knowledge_router)
app.include_router(admin_analytics_router)

# Note: Agent router is included in startup_event()

# ----------------------
# Run Application
# ----------------------
if __name__ == "__main__":
    import uvicorn
    import os

    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    
    logger.info(f"🌐 Starting server on {host}:{port}")
    
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )