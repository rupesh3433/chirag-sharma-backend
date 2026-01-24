"""
Main Application - Updated to use modular agent
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from config import CORS_ORIGINS
from routes_public import router as public_router
from routes_admin_auth import router as admin_auth_router
from routes_admin_bookings import router as admin_bookings_router
from routes_admin_knowledge import router as admin_knowledge_router
from routes_admin_analytics import router as admin_analytics_router

# Import new modular agent
from agent import AgentOrchestrator, create_agent_router

# ----------------------
# Basic Logging
# ----------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----------------------
# App Setup
# ----------------------
app = FastAPI(title="JinniChirag Website Backend")

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
# Initialize Agent
# ----------------------
orchestrator = AgentOrchestrator()
agent_router = create_agent_router(orchestrator)

# ----------------------
# Include Routers
# ----------------------

# Public Routes
app.include_router(public_router)

# Agent Routes (New Modular Agent)
app.include_router(agent_router)

# Admin Routes
app.include_router(admin_auth_router)
app.include_router(admin_bookings_router)
app.include_router(admin_knowledge_router)
app.include_router(admin_analytics_router)

# ----------------------
# Run Application
# ----------------------
if __name__ == "__main__":
    import uvicorn
    import os

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
    
    
    
    
    
    
    



# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
# import logging

# from config import CORS_ORIGINS
# from routes_public import router as public_router
# from routes_admin_auth import router as admin_auth_router
# from routes_admin_bookings import router as admin_bookings_router
# from routes_admin_knowledge import router as admin_knowledge_router
# from routes_admin_analytics import router as admin_analytics_router
# from routes_agent import router as agent_router


# # ----------------------
# # Basic Logging
# # ----------------------
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# # ----------------------
# # App Setup
# # ----------------------
# app = FastAPI(title="JinniChirag Website Backend")

# # ----------------------
# # CORS Middleware
# # ----------------------
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=CORS_ORIGINS,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # ----------------------
# # Include Routers
# # ----------------------

# # Public Routes
# app.include_router(public_router)

# # Agent Routes
# app.include_router(agent_router)

# # Admin Routes
# app.include_router(admin_auth_router)
# app.include_router(admin_bookings_router)
# app.include_router(admin_knowledge_router)
# app.include_router(admin_analytics_router)

# # ----------------------
# # Run Application
# # ----------------------
# if __name__ == "__main__":
#     import uvicorn
#     import os

#     port = int(os.environ.get("PORT", 8000))
#     uvicorn.run("main:app", host="0.0.0.0", port=port)