# JinniChirag Backend - Modular Structure

A modular FastAPI backend for JinniChirag Makeup Artist website with AI chatbot, booking system, and admin panel.

---

## 📁 Project Structure

```
app/
├── main.py                      # FastAPI app entry point
├── config.py                    # Configuration & environment variables
├── database.py                  # MongoDB connection & collections
├── models.py                    # Pydantic models
├── security.py                  # Authentication & JWT
├── services.py                  # External services (Twilio, Email, Knowledge)
├── utils.py                     # Utility functions
├── prompts.py                   # AI prompts & system messages
├── routes_public.py             # Public endpoints
├── routes_admin_auth.py         # Admin authentication endpoints
├── routes_admin_bookings.py     # Admin booking management endpoints
├── routes_admin_knowledge.py    # Admin knowledge base endpoints
├── routes_admin_analytics.py    # Admin analytics endpoints
├── requirements.txt             # Python dependencies
└── .env                         # Environment variables (not in repo)
```

---

## 📝 Module Descriptions

### `main.py`
- FastAPI application initialization
- CORS middleware configuration
- Router registration
- Application entry point

### `config.py`
- All environment variables
- API keys (Groq, MongoDB, Twilio, Brevo)
- JWT configuration
- Language mapping
- Permanent admin list
- Country codes
- CORS origins

### `database.py`
- MongoDB client initialization
- Database and collection references
- Index creation for performance optimization

### `models.py`
- **Public Models**: ChatRequest, BookingRequest, OtpVerifyRequest
- **Admin Models**: AdminLoginRequest, AdminPasswordResetRequest, BookingStatusUpdate, BookingSearchQuery
- **Knowledge Base Models**: KnowledgeCreate, KnowledgeUpdate
- Input validation with Pydantic

### `security.py`
- Password hashing (bcrypt)
- Password verification
- JWT token creation
- JWT token verification
- `get_current_admin` dependency for protected routes

### `services.py`
- **WhatsApp Service**: Twilio integration for OTP and notifications
- **Email Service**: Password reset emails via Brevo API or SMTP
- **Knowledge Service**: Load knowledge base content from database

### `utils.py`
- `serialize_booking()`: Convert MongoDB documents to JSON
- `serialize_knowledge()`: Convert knowledge documents to JSON
- DateTime formatting helpers

### `prompts.py`
- `get_base_system_prompt()`: Generate AI system prompt with knowledge base
- `get_language_reset_prompt()`: Generate language control instructions
- All AI prompt templates preserved from original code

### `routes_public.py`
Public endpoints (no authentication required):
- `GET /health` - Health check
- `POST /chat` - AI chatbot (GROQ API)
- `POST /bookings/request` - Request OTP for booking
- `POST /bookings/verify-otp` - Verify OTP and create booking

### `routes_admin_auth.py`
Admin authentication endpoints:
- `POST /admin/login` - Admin login (returns JWT)
- `POST /admin/forgot-password` - Request password reset
- `POST /admin/reset-password` - Reset password with token
- `GET /admin/verify-token` - Verify JWT token validity

### `routes_admin_bookings.py`
Admin booking management (requires authentication):
- `GET /admin/bookings` - List all bookings
- `POST /admin/bookings/search` - Advanced search
- `GET /admin/bookings/{id}` - Get booking details
- `PATCH /admin/bookings/{id}/status` - Update status (sends WhatsApp)
- `DELETE /admin/bookings/{id}` - Delete booking

### `routes_admin_knowledge.py`
Admin knowledge base management (requires authentication):
- `POST /admin/knowledge` - Create knowledge entry
- `GET /admin/knowledge` - List all knowledge entries
- `GET /admin/knowledge/{id}` - Get specific entry
- `PATCH /admin/knowledge/{id}` - Update entry
- `DELETE /admin/knowledge/{id}` - Delete entry

### `routes_admin_analytics.py`
Admin analytics (requires authentication):
- `GET /admin/analytics/overview` - Overall statistics
- `GET /admin/analytics/by-service` - Bookings by service
- `GET /admin/analytics/by-month` - Monthly booking trends

---

## 🚀 Running the Application

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Create a `.env` file with:
```env
GROQ_API_KEY=your_groq_api_key
MONGO_URI=mongodb://localhost:27017
JWT_SECRET=your_secret_key
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
BREVO_API_KEY=your_brevo_key
FRONTEND_URL=https://yourdomain.com
SMTP_EMAIL=your_email@gmail.com
SMTP_PASSWORD=your_app_password
```

### 3. Run the Server
```bash
python main.py
```
Or using uvicorn directly:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## 🔑 Key Features Preserved

### ✅ All original logic preserved
- Chat AI prompts remain identical
- OTP booking flow unchanged
- WhatsApp messaging templates preserved
- Email templates unchanged
- Admin password reset flow intact

### ✅ Security
- JWT authentication
- Password hashing with bcrypt
- Token expiration
- Auto-error disabled for public routes

### ✅ Database
- All indexes created automatically
- Collections properly initialized
- Serialization helpers for JSON conversion

### ✅ Services
- Twilio WhatsApp integration
- Brevo + SMTP email fallback
- Knowledge base loading from MongoDB

---

## 📊 API Endpoints Summary

### Public (No Auth Required)
```
GET  /health
POST /chat
POST /bookings/request
POST /bookings/verify-otp
```

### Admin Authentication
```
POST /admin/login
POST /admin/forgot-password
POST /admin/reset-password
GET  /admin/verify-token
```

### Admin Bookings (Auth Required)
```
GET    /admin/bookings
POST   /admin/bookings/search
GET    /admin/bookings/{id}
PATCH  /admin/bookings/{id}/status
DELETE /admin/bookings/{id}
```

### Admin Knowledge Base (Auth Required)
```
POST   /admin/knowledge
GET    /admin/knowledge
GET    /admin/knowledge/{id}
PATCH  /admin/knowledge/{id}
DELETE /admin/knowledge/{id}
```

### Admin Analytics (Auth Required)
```
GET /admin/analytics/overview
GET /admin/analytics/by-service
GET /admin/analytics/by-month
```

---

## 🎯 Benefits of Modular Structure

1. **Separation of Concerns**: Each module has a single responsibility
2. **Easier Testing**: Can test each module independently
3. **Better Maintainability**: Changes to one module don't affect others
4. **Clearer Code Organization**: Easy to find and modify specific features
5. **Scalability**: Easy to add new routes or services
6. **Reusability**: Services and utilities can be reused across routes

---

## 🔒 Security Notes

- All admin routes require JWT authentication
- Passwords are hashed with bcrypt
- JWT tokens expire after 24 hours
- Password reset tokens expire after 1 hour
- Email enumeration prevention in forgot-password
- Only permanent admins can reset passwords

---

## 📦 Dependencies

```
fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.5.0
pydantic[email]
pymongo==4.6.0
python-dotenv==1.0.0
bcrypt==4.1.1
PyJWT==2.8.0
twilio==8.10.0
requests==2.31.0
```

---

## 🛠️ Technology Stack

- **Framework**: FastAPI
- **Database**: MongoDB
- **Authentication**: JWT + bcrypt
- **AI**: GROQ API (Llama 3.1)
- **Messaging**: Twilio WhatsApp
- **Email**: Brevo API / SMTP
- **Language Support**: English, Nepali, Hindi, Marathi

---

## 📄 License

This project is proprietary software for JinniChirag Makeup Artist.

---

## 👨‍💻 Development

Built with ❤️ for JinniChirag Makeup Artist by the development team.