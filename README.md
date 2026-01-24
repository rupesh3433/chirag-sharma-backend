# 🎨 JinniChirag Makeup Artist - Backend API

A comprehensive, **modular** FastAPI backend with **AI-powered FSM chatbot**, intelligent booking agent, and complete admin management system.

---

## 📁 Project Structure

```
chirag-sharma-backend/
│
├── app.py                          # ⚡ Main FastAPI application
├── config.py                       # ⚙️ Configuration & environment variables
├── database.py                     # 🗄️ MongoDB connection & collections
├── models.py                       # 📋 Pydantic request/response models
├── security.py                     # 🔐 JWT authentication & password hashing
├── services.py                     # 📡 External services (Twilio, Email)
├── utils.py                        # 🛠️ Utility functions
├── prompts.py                      # 🤖 AI system prompts (legacy)
│
├── routes_public.py                # 🌐 Public endpoints (no auth)
├── routes_admin_auth.py            # 🔑 Admin authentication
├── routes_admin_bookings.py        # 📅 Booking management
├── routes_admin_knowledge.py       # 📚 Knowledge base CRUD (NEW!)
├── routes_admin_analytics.py       # 📊 Analytics & statistics
│
├── agent/                          # 🤖 MODULAR AGENTIC CHATBOT
│   ├── __init__.py
│   ├── orchestrator.py            # 🎯 Main orchestrator (FSM coordinator)
│   │
│   ├── models/                    # 📋 Data Models
│   │   ├── __init__.py
│   │   ├── intent.py             # BookingIntent model
│   │   ├── memory.py             # ConversationMemory model
│   │   ├── state.py              # BookingState enum
│   │   └── api_models.py         # API request/response models
│   │
│   ├── engine/                    # 🧠 Core FSM Engine
│   │   ├── __init__.py
│   │   ├── fsm.py                # ✅ Finite State Machine (FIXED)
│   │   ├── state_manager.py     # State management utilities
│   │   └── intent_detector.py    # Intent detection logic
│   │
│   ├── handlers/                  # 🎭 State-Specific Handlers
│   │   ├── __init__.py
│   │   ├── base_handler.py       # Base handler class
│   │   ├── greeting_handler.py   # Greeting state
│   │   ├── service_handler.py    # Service selection
│   │   ├── package_handler.py    # Package selection
│   │   ├── details_handler.py    # Details collection
│   │   ├── confirmation_handler.py # Confirmation
│   │   ├── otp_handler.py        # OTP verification
│   │   └── info_handler.py       # Info queries
│   │
│   ├── extractors/                # 🔍 Data Extractors
│   │   ├── __init__.py
│   │   ├── base_extractor.py     # Base extractor class
│   │   ├── phone_extractor.py    # Phone number extraction
│   │   ├── email_extractor.py    # Email extraction
│   │   ├── date_extractor.py     # Date extraction
│   │   ├── name_extractor.py     # Name extraction
│   │   ├── address_extractor.py  # Address extraction
│   │   ├── pincode_extractor.py  # Pincode extraction
│   │   └── country_extractor.py  # Country extraction
│   │
│   ├── validators/                # ✅ Data Validators
│   │   ├── __init__.py
│   │   ├── phone_validator.py    # Phone validation
│   │   ├── email_validator.py    # Email validation
│   │   ├── date_validator.py     # Date validation
│   │   └── pincode_validator.py  # Pincode validation
│   │
│   ├── prompts/                   # 💬 Prompt Templates
│   │   ├── __init__.py
│   │   ├── system_prompts.py     # System prompts
│   │   ├── templates.py          # Message templates
│   │   └── builder.py            # Prompt builder
│   │
│   ├── services/                  # 🛠️ Business Services
│   │   ├── __init__.py
│   │   ├── memory_service.py     # Session memory management
│   │   ├── phone_service.py      # Phone number services
│   │   ├── otp_service.py        # OTP generation/verification
│   │   ├── booking_service.py    # Booking operations
│   │   └── knowledge_base_service.py  # ✅ KB + Groq LLM (NEW!)
│   │
│   ├── utils/                     # 🧰 Utility Functions
│   │   ├── __init__.py
│   │   ├── patterns.py           # Regex patterns
│   │   ├── formatters.py         # Data formatters
│   │   └── helpers.py            # Helper functions
│   │
│   ├── config/                    # ⚙️ Configuration
│   │   ├── __init__.py
│   │   ├── services_config.py    # Services & packages config
│   │   └── settings.py           # General settings
│   │
│   └── api/                       # 🌐 API Layer
│       ├── __init__.py
│       ├── router.py             # Agent router factory
│       └── endpoints.py          # Endpoint handlers
│
├── requirements.txt                # 📦 Python dependencies
├── .env                           # 🔒 Environment secrets (create this)
└── README.md                      # 📖 This file
```

---

## 🚀 Quick Start

### 1️⃣ Install Dependencies
```bash
pip install -r requirements.txt
```

### 2️⃣ Configure Environment
Create `.env` file:
```env
# Database
MONGODB_URL=mongodb+srv://user:pass@cluster.mongodb.net/db?retryWrites=true&w=majority

# AI Services
GROQ_API_KEY=gsk_your_groq_api_key_here
ANTHROPIC_API_KEY=sk-ant-api03-your_key_here  # Optional

# Authentication
JWT_SECRET_KEY=your_super_secret_jwt_key_change_this_in_production
ADMIN_USERNAME=admin
ADMIN_PASSWORD=secure_password_here

# Twilio WhatsApp
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886

# Email Service (Brevo for production)
BREVO_API_KEY=xkeysib-your_brevo_api_key
BREVO_SENDER_EMAIL=noreply@yourdomain.com
BREVO_SENDER_NAME=JinniChirag

# Email Service (SMTP for development)
SMTP_EMAIL=your_email@gmail.com
SMTP_PASSWORD=your_app_specific_password
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587

# Frontend
FRONTEND_URL=https://yourdomain.com
```

### 3️⃣ Initialize Database
```python
# Run once to create admin user
python -c "
from database import admins_collection
from security import get_password_hash
import os

admins_collection.insert_one({
    'email': os.getenv('ADMIN_USERNAME', 'admin@example.com'),
    'password': get_password_hash(os.getenv('ADMIN_PASSWORD', 'admin123')),
    'role': 'admin'
})
print('✅ Admin user created!')
"
```

### 4️⃣ Run Server
```bash
# Development with auto-reload
uvicorn app:app --reload --port 8000

# Production
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4
```

### 5️⃣ Test API
```bash
curl http://localhost:8000/health
```

---

## 🤖 Modular Agent Architecture

### 🎯 How It Works

```mermaid
graph TD
    A[User Message] --> B[API Endpoint]
    B --> C[Orchestrator]
    C --> D{FSM Process}
    D -->|Understood| E[Update State]
    D -->|Not Understood| F[Knowledge Base]
    E --> G[Extractors]
    G --> H[Validators]
    H --> I[Next State]
    F --> J[Groq LLM]
    J --> K[Answer + Continue Flow]
    I --> L[Response]
    K --> L
    L --> M[User]
```

### 📦 Module Breakdown

#### 1. **Orchestrator** (`agent/orchestrator.py`)
- **Role**: Main coordinator - routes messages through FSM
- **Features**:
  - Session management
  - Off-track counter (switches to chat mode after 6 attempts)
  - Knowledge base integration
  - OTP handling
  - Flow state maintenance

#### 2. **FSM Engine** (`agent/engine/fsm.py`)
- **Role**: Finite State Machine - determines next state
- **States**: 
  - `greeting` → `selecting_service` → `selecting_package` → `collecting_details` → `confirming` → `otp_sent` → `completed`
- **Features**:
  - Intent detection
  - Service/package selection (supports "1", "2", "3")
  - Multi-field extraction
  - Returns `understood: True/False` flag

#### 3. **Extractors** (`agent/extractors/`)
- **Phone**: Detects phone numbers with country codes
- **Email**: Validates and extracts emails
- **Date**: Parses natural language dates
- **Name**: Extracts person names
- **Address**: Detects addresses
- **Pincode**: Validates PIN/postal codes
- **Country**: Detects countries from text

#### 4. **Validators** (`agent/validators/`)
- Validates extracted data
- Ensures data quality before saving

#### 5. **Services** (`agent/services/`)
- **Memory Service**: Session management (2-hour TTL)
- **OTP Service**: Generate, send, verify OTP
- **Booking Service**: Save to MongoDB, send confirmations
- **Knowledge Base Service**: ✅ **Groq LLM integration** for answering questions

#### 6. **Knowledge Base Service** (`agent/services/knowledge_base_service.py`)
- **Features**:
  - Loads knowledge from MongoDB
  - 4-language support (English, Hindi, Nepali, Marathi)
  - Groq LLM for natural responses
  - Context-aware (knows current booking state)
  - Short, concise answers (2-4 sentences)

---

## 📚 Complete API Reference

### 🌐 Public Endpoints (No Authentication)

#### Health Check
```http
GET /health
```
**Response:**
```json
{
  "status": "ok",
  "timestamp": "2024-01-21T10:30:00.000Z"
}
```

---

### 🤖 Agent Chatbot - Conversational Booking

#### Start/Continue Conversation
```http
POST /agent/chat
Content-Type: application/json

{
  "message": "I want bridal makeup for December 25",
  "session_id": "optional_session_id",
  "language": "en"
}
```

**Languages:** `en` (English), `hi` (Hindi), `ne` (Nepali), `mr` (Marathi)

**Response:**
```json
{
  "reply": "Wonderful! Which package would you like? 1) Basic (₹15,999) 2) Premium (₹49,999) 3) Luxury (₹99,999)",
  "session_id": "abc123xyz",
  "stage": "selecting_package",
  "action": "continue",
  "missing_fields": ["package", "name", "email", "phone", "address", "pincode", "service_country"],
  "collected_info": {
    "service": "Bridal Makeup Services",
    "event_date": "2024-12-25"
  },
  "booking_id": null,
  "off_track_count": 0
}
```

#### Complete Flow Example

**Step 1: Initial Intent**
```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I want bridal makeup",
    "language": "en"
  }'
```
Response: Shows service options

**Step 2: Select Service**
```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "1",
    "session_id": "abc123xyz",
    "language": "en"
  }'
```
Response: Shows package options

**Step 3: Ask Question (Off-Track)**
```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is your Instagram?",
    "session_id": "abc123xyz",
    "language": "en"
  }'
```
Response: 
```json
{
  "reply": "You can follow us on Instagram @chiragsharma_makeupartist.\n\n📦 Please select your package (1-3):\n1. Basic - ₹15,999\n2. Premium - ₹49,999\n3. Luxury - ₹99,999",
  "off_track_count": 1
}
```
✅ **Answers question AND maintains booking flow!**

**Step 4: Continue Booking**
```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "2",
    "session_id": "abc123xyz",
    "language": "en"
  }'
```
Response: Asks for name

**Step 5-9: Provide Details**
- Name: "Priya Sharma"
- Email: "priya@example.com"
- Phone: "+977-9876543210"
- Address: "Thamel, Kathmandu"
- Pincode: "44600"
- Country: "Nepal"

**Step 10: OTP Sent**
```json
{
  "reply": "Perfect! I've sent a 6-digit OTP to +977-98****3210. Please enter it here.",
  "stage": "otp_sent",
  "action": "send_otp",
  "booking_id": "xyz789"
}
```

**Step 11: Verify OTP**
```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "123456",
    "session_id": "abc123xyz",
    "language": "en"
  }'
```
Response:
```json
{
  "reply": "🎉 Congratulations Priya! Your booking is confirmed!",
  "stage": "greeting",
  "action": "booking_confirmed",
  "booking_id": "507f1f77bcf86cd799439011"
}
```

---

#### Agent Management Endpoints

**Get Active Sessions**
```http
GET /agent/sessions
```
**Response:**
```json
{
  "sessions": [
    {
      "session_id": "abc123xyz",
      "language": "en",
      "stage": "collecting_details",
      "created_at": "2024-01-21T10:30:00Z",
      "updated_at": "2024-01-21T10:35:00Z"
    }
  ],
  "count": 1
}
```

**Delete Session**
```http
DELETE /agent/sessions/{session_id}
```

**Manual Cleanup**
```http
POST /agent/cleanup
```

**Agent Health Check**
```http
GET /agent/health
```

---

### 🔑 Admin Authentication

#### Login
```http
POST /admin/login
Content-Type: application/json

{
  "email": "admin@example.com",
  "password": "securepassword123"
}
```
**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "email": "admin@example.com",
  "role": "admin"
}
```

#### Forgot Password
```http
POST /admin/forgot-password
Content-Type: application/json

{
  "email": "admin@example.com"
}
```

#### Reset Password
```http
POST /admin/reset-password
Content-Type: application/json

{
  "token": "reset_token_from_email",
  "new_password": "newSecurePass123"
}
```

#### Verify Token
```http
GET /admin/verify-token
Authorization: Bearer <jwt_token>
```

---

### 📅 Admin Booking Management

**All endpoints require:** `Authorization: Bearer <jwt_token>`

#### List All Bookings
```http
GET /admin/bookings?status=pending&limit=50&skip=0
Authorization: Bearer <jwt_token>
```

#### Search Bookings
```http
POST /admin/bookings/search
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "search": "Priya",
  "status": "pending",
  "date_from": "2024-01-01",
  "date_to": "2024-12-31"
}
```

#### Get Booking Details
```http
GET /admin/bookings/{booking_id}
Authorization: Bearer <jwt_token>
```

#### Update Booking Status
```http
PATCH /admin/bookings/{booking_id}/status
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "status": "approved"
}
```

**Status Options:** `pending`, `approved`, `completed`, `cancelled`

**WhatsApp Notifications:**
- `approved` → Confirmation sent
- `cancelled` → Apology sent
- `completed` → Thank you sent

#### Delete Booking
```http
DELETE /admin/bookings/{booking_id}
Authorization: Bearer <jwt_token>
```

---

### 📚 Admin Knowledge Base Management

**All endpoints require:** `Authorization: Bearer <jwt_token>`

#### Create Knowledge Entry
```http
POST /admin/knowledge
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "title": "Bridal Makeup Packages",
  "content": "We offer 3 bridal packages: Basic (₹15,999), Premium (₹49,999), and Luxury (₹99,999). All packages include professional makeup, premium products, and on-site service.",
  "category": "Services",
  "language": "en",
  "is_active": true
}
```

**Response:**
```json
{
  "message": "Knowledge entry created",
  "id": "507f1f77bcf86cd799439011"
}
```

#### List Knowledge Entries
```http
GET /admin/knowledge?language=en&is_active=true&limit=50&skip=0
Authorization: Bearer <jwt_token>
```

**Response:**
```json
{
  "entries": [
    {
      "_id": "507f1f77bcf86cd799439011",
      "title": "Bridal Makeup Packages",
      "content": "We offer 3 bridal packages...",
      "category": "Services",
      "language": "en",
      "is_active": true,
      "created_at": "2024-01-21T10:00:00Z"
    }
  ],
  "total": 15,
  "limit": 50,
  "skip": 0
}
```

#### Get Single Entry
```http
GET /admin/knowledge/{entry_id}
Authorization: Bearer <jwt_token>
```

#### Update Entry
```http
PATCH /admin/knowledge/{entry_id}
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "content": "Updated package information...",
  "is_active": true
}
```

#### Delete Entry
```http
DELETE /admin/knowledge/{entry_id}
Authorization: Bearer <jwt_token>
```

---

### 📊 Admin Analytics

**All endpoints require:** `Authorization: Bearer <jwt_token>`

#### Overview Statistics
```http
GET /admin/analytics/overview
Authorization: Bearer <jwt_token>
```

**Response:**
```json
{
  "total_bookings": 150,
  "pending_bookings": 12,
  "approved_bookings": 45,
  "completed_bookings": 85,
  "cancelled_bookings": 8,
  "recent_bookings_7_days": 23,
  "today_bookings": 5
}
```

#### Bookings by Service
```http
GET /admin/analytics/by-service
Authorization: Bearer <jwt_token>
```

#### Monthly Trends
```http
GET /admin/analytics/by-month
Authorization: Bearer <jwt_token>
```

---

## 🧠 Agent Intelligence Features

### ✅ What Makes It Smart

1. **Natural Language Understanding**
   - Understands "I want bridal makeup for my wedding next month"
   - Extracts: service=Bridal, date=next month

2. **Context Maintenance**
   - Remembers entire conversation
   - Doesn't ask for information twice

3. **Off-Track Handling**
   - User asks "What's your Instagram?" → Answers AND continues booking
   - Maintains booking state perfectly
   - Switches to chat mode after 6 off-track questions

4. **Multi-Field Extraction**
   - "My name is Priya, email priya@example.com, phone +977-9876543210"
   - Extracts all 3 fields at once

5. **Flexible Input**
   - Accepts "1" or "Bridal Makeup" or "I want bridal package"
   - Understands natural variations

6. **Smart Prompting**
   - Asks for ONE thing at a time
   - Shows progress
   - Contextual hints

7. **Knowledge Base Integration**
   - Powered by Groq LLM (llama-3.1-8b-instant)
   - 4-language support
   - Short, natural responses
   - Doesn't repeat "according to knowledge base"

---

## 🌍 Multi-Language Support

### Supported Languages

| Language | Code | Example |
|----------|------|---------|
| 🇬🇧 English | `en` | "I want bridal makeup" |
| 🇮🇳 Hindi | `hi` | "मुझे ब्राइडल मेकअप चाहिए" |
| 🇳🇵 Nepali | `ne` | "मलाई ब्राइडल मेकअप चाहिन्छ" |
| 🇮🇳 Marathi | `mr` | "मला ब्राइडल मेकअप हवा आहे" |

### Language Features

✅ **AI Responses** - Groq responds in selected language
✅ **Knowledge Base** - Separate content per language
✅ **Prompts** - Localized templates
✅ **WhatsApp** - Messages in user's language
✅ **Error Messages** - Translated

---

## 📦 Database Schema

### Collections

#### `bookings`
```javascript
{
  _id: ObjectId,
  service: String,
  package: String,
  name: String,
  email: String,
  phone: String,
  phone_country: String,
  service_country: String,
  address: String,
  pincode: String,
  date: String,
  message: String,
  status: "pending" | "approved" | "completed" | "cancelled",
  otp_verified: Boolean,
  source: "agent_chat" | undefined,
  created_at: DateTime,
  updated_at: DateTime
}
```

**Indexes:** `created_at`, `status`

#### `knowledge_base` ✅ NEW!
```javascript
{
  _id: ObjectId,
  title: String,
  content: String,
  category: String,
  language: "en" | "hi" | "ne" | "mr",
  is_active: Boolean,
  created_at: DateTime,
  updated_at: DateTime
}
```

**Indexes:** `language`, `is_active`, `created_at`

#### `admins`
```javascript
{
  _id: ObjectId,
  email: String (unique),
  password: String (bcrypt),
  role: "admin",
  created_at: DateTime
}
```

**Indexes:** `email` (unique)

#### `reset_tokens`
```javascript
{
  _id: ObjectId,
  email: String,
  token: String (bcrypt),
  used: Boolean,
  expires_at: DateTime (TTL)
}
```

**Indexes:** `expires_at` (TTL auto-delete)

---

## 🔐 Security Features

### Authentication
- **JWT Tokens**: 24-hour expiration
- **Password Hashing**: Bcrypt with salt
- **Admin-Only Routes**: Protected by dependency injection
- **Email Enumeration Prevention**: Same response for valid/invalid

### Data Protection
- **Environment Variables**: Secrets in `.env`
- **CORS**: Configured origins
- **Input Validation**: Pydantic models
- **Rate Limiting**: Can be added via middleware

### OTP Security
- **6-digit codes**: Randomly generated
- **5-minute expiry**: Auto-cleanup
- **3 attempts max**: Prevents brute force
- **WhatsApp delivery**: Secure channel

---

## 🛠️ Development Guide

### Adding Knowledge Base Content

```python
# Via API (recommended)
curl -X POST http://localhost:8000/admin/knowledge \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Social Media Links",
    "content": "Instagram: @chiragsharma_makeupartist, Facebook: Chirag Sharma Makeup, YouTube: Chirag Sharma Official",
    "category": "Contact",
    "language": "en",
    "is_active": true
  }'

# Via MongoDB (direct)
use jinnichirag_db
db.knowledge_base.insertOne({
  title: "Social Media Links",
  content: "Instagram: @chiragsharma_makeupartist...",
  category: "Contact",
  language: "en",
  is_active: true,
  created_at: new Date()
})
```

### Testing Agent Locally

```bash
# Test booking flow
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I want bridal makeup", "language": "en"}'

# Test question during booking
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is your Instagram?",
    "session_id": "test123",
    "language": "en"
  }'

# Should answer AND continue booking flow ✅
```

---

## 📈 Performance & Scaling

### Current Architecture
- **In-Memory Sessions**: 2-hour TTL, auto-cleanup
- **MongoDB**: Single connection, indexed queries
- **Groq API**: Rate limited (adjust max_tokens if needed)

### Production Recommendations

1. **Redis for Sessions**
   ```python
   # Replace memory_service.py with Redis backend
   import redis
   redis_client = redis.Redis(host='localhost', port=6379)
   ```

2. **Connection Pooling**
   ```python
   # database.py
   client = MongoClient(
       MONGODB_URL,
       maxPoolSize=50,
       minPoolSize=10
   )
   ```

3. **Rate Limiting**
   ```python
   from fastapi_limiter import FastAPILimiter
   from fastapi_limiter.depends import RateLimiter
   
   @app.post("/agent/chat", dependencies=[Depends(RateLimiter(times=10, seconds=60))])
   ```

4. **Caching**
   ```python
   # Cache knowledge base in Redis
   @lru_cache(maxsize=100)
   def get_knowledge(language: str):
       ...
   ```

5. **Load Balancing**
   ```bash
   # Use Nginx or similar
   upstream backend {
       server 127.0.0.1:8000;
       server 127.0.0.1:8001;
       server 127.0.0.1:8002;
   }
   ```

---

## 🚨 Troubleshooting

### Agent Not Detecting "1", "2", "3"

**Issue:** User types "1" but agent doesn't select service

**Solution:** Ensure you're using the FIXED `agent/engine/fsm.py`:
```python
# In _extract_service_selection()
num_match = re.search(r'\b([1-4])\b', message)  # ✅ This should be present
```

### Knowledge Base Not Loading

**Issue:** Agent gives fallback message instead of KB content

**Check:**
1. MongoDB has entries: `db.knowledge_base.find()`
2. Language matches: `{"language": "en", "is_active": true}`
3. Groq API key is set: `echo $GROQ_API_KEY`

### Agent Losing Booking State

**Issue:** Agent forgets what was collected

**Solution:** Ensure `orchestrator.py` has `_get_exact_next_step()` method that checks current state and missing fields

### OTP Not Sending

**Check:**
1. Twilio credentials in `.env`
2. Phone format: `+977-9876543210` (with country code)
3. Twilio console for errors
4. WhatsApp sandbox (if testing)

---

## 📄 License

Proprietary software for JinniChirag Makeup Artist. All rights reserved.

---

## 👨‍💻 Support & Contact

For issues:
1. Check logs: `tail -f app.log`
2. Verify environment: `python -c "import os; print(os.getenv('GROQ_API_KEY')[:10])"`
3. Test endpoints with curl commands above

---

**Built with ❤️ using FastAPI, MongoDB, Groq AI, and Twilio**

**Modular Architecture** | **FSM-Based** | **4 Languages** | **Smart Booking Flow**