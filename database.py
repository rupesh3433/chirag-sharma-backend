from pymongo import MongoClient
from config import MONGO_URI

# ----------------------
# MongoDB Connection
# ----------------------
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["jinnichirag_db"]

# ----------------------
# Collections
# ----------------------
booking_collection = db["bookings"]
admin_collection = db["admins"]
reset_token_collection = db["reset_tokens"]
knowledge_collection = db["knowledge_base"]

# ----------------------
# Create Indexes
# ----------------------
def create_indexes():
    """Create database indexes for better performance"""
    
    # Reset tokens - auto-expire
    reset_token_collection.create_index("expires_at", expireAfterSeconds=0)
    
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
    knowledge_collection.create_index([("language", 1), ("category", 1), ("is_active", 1)])

    print(f"Database connected: {MONGO_URI}")

# Initialize indexes on module import
create_indexes()