from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import bcrypt
import jwt
from datetime import datetime, timedelta
from config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRATION_HOURS
from database import admin_collection

# ----------------------
# Security Setup
# ----------------------
security = HTTPBearer(auto_error=False)

# ----------------------
# Password Functions
# ----------------------

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

# ----------------------
# JWT Functions
# ----------------------

def create_jwt_token(email: str, role: str) -> str:
    """Create JWT token for admin"""
    payload = {
        "email": email,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_jwt_token(token: str) -> dict:
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ----------------------
# Authentication Dependency
# ----------------------

def get_current_admin(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> dict:
    """Dependency to get current authenticated admin"""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = credentials.credentials
    payload = verify_jwt_token(token)
    
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    admin = admin_collection.find_one({"email": payload["email"]})
    if not admin:
        raise HTTPException(status_code=403, detail="Admin not found")
    
    return {
        "email": admin["email"],
        "role": admin["role"]
    }