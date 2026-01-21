from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timedelta
import secrets
import logging
from models import AdminLoginRequest, AdminPasswordResetRequest, AdminPasswordResetConfirm
from security import (
    hash_password,
    verify_password,
    create_jwt_token,
    get_current_admin
)
from services import send_password_reset_email
from database import admin_collection, reset_token_collection
from config import PERMANENT_ADMINS

router = APIRouter(prefix="/admin", tags=["Admin Authentication"])
logger = logging.getLogger(__name__)

# ############################################################
# ADMIN ROUTES - AUTHENTICATION
# ############################################################

@router.post("/login")
async def admin_login(credentials: AdminLoginRequest):
    """Admin login endpoint - returns JWT token"""
    
    admin = admin_collection.find_one({"email": credentials.email})
    
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not verify_password(credentials.password, admin["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_jwt_token(credentials.email, admin["role"])
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "email": admin["email"],
        "role": admin["role"]
    }

@router.post("/forgot-password")
async def admin_forgot_password(request: AdminPasswordResetRequest):
    """Request password reset - sends email with reset token"""
    
    email = request.email.lower()
    
    # Only permanent admins can reset
    if email not in PERMANENT_ADMINS:
        return {
            "message": "If your email is registered, you will receive a password reset link"
        }
    
    reset_token = secrets.token_urlsafe(32)
    hashed_token = hash_password(reset_token)
    
    reset_token_collection.insert_one({
        "email": email,
        "token": hashed_token,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(hours=1),
        "used": False
    })
    
    # FIXED: Never expose SMTP errors (security best practice)
    try:
        send_password_reset_email(email, reset_token)
    except Exception as e:
        logger.error(f"Password reset email failed for {email}: {e}")
        # Still return success to prevent email enumeration
    
    return {
        "message": "If your email is registered, you will receive a password reset link"
    }

@router.post("/reset-password")
async def admin_reset_password(request: AdminPasswordResetConfirm):
    """Reset password using token from email - Auto-creates admin if not exists"""
    
    valid_tokens = reset_token_collection.find({
        "expires_at": {"$gt": datetime.utcnow()},
        "used": False
    })
    
    token_doc = None
    for doc in valid_tokens:
        if verify_password(request.token, doc["token"]):
            token_doc = doc
            break
    
    if not token_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    # Mark token as used
    reset_token_collection.update_one(
        {"_id": token_doc["_id"]},
        {"$set": {"used": True}}
    )
    
    # Check if admin exists
    admin = admin_collection.find_one({"email": token_doc["email"]})
    new_hashed_password = hash_password(request.new_password)
    
    if not admin:
        # Auto-create admin on first reset
        admin_collection.insert_one({
            "email": token_doc["email"],
            "password": new_hashed_password,
            "role": "admin",
            "created_at": datetime.utcnow()
        })
    else:
        # Update existing admin password
        admin_collection.update_one(
            {"email": token_doc["email"]},
            {"$set": {"password": new_hashed_password}}
        )
    
    return {"message": "Password reset successful"}

@router.get("/verify-token")
async def verify_admin_token(admin: dict = Depends(get_current_admin)):
    """Verify if current token is valid"""
    return {
        "valid": True,
        "email": admin["email"],
        "role": admin["role"]
    }