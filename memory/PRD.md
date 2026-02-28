# CP67 Mall WhatsApp Loyalty System - Complete Project Documentation

## Project Overview
A WhatsApp-based loyalty onboarding and bill-scan rewards system for CP67 Mall. Customers scan area-specific QR codes, which opens WhatsApp with a pre-filled, source-tracked message. The system handles user registration, bill uploads via image, point calculation, and balance viewing.

## Recent Updates (Feb 2026)

### Karix Image Sending (Feb 27, 2026)
- **Fixed:** WhatsApp QR code image sending now works using `ATTACHMENT` type with `attachmentData` field
- Parking entry flow sends QR image directly to customer's WhatsApp
- Fall-back to text message if image fails

### Reprocess Button (Feb 27, 2026)
- **Fixed:** Reprocess button now visible for ALL pending bills (not just Brand-related)
- Added Reprocess button to "All Bills" tab for pending_review/manual_review bills
- Added "Pending Review" option to status filter dropdown

### Chunked CSV Upload (Feb 28, 2026)
- **Implemented:** Large file upload with chunking for 30k+ phone numbers
- Client-side CSV parsing to extract phone numbers
- Uploads in chunks of 5,000 numbers at a time
- Progress indicator showing chunk progress (e.g., "Uploading 3/6")
- Supports CSV format (recommended for large files)

### Bill Processing Rules
- **15-Day Limit:** Bills older than 15 days are auto-rejected with friendly message
- **High Value Review:** Bills > ₹30,000 go to pending_review for manual verification
- **Mobile from Bill:** If bill contains customer mobile, points go to that number (not WhatsApp sender)

### WhatsApp Messaging
- **Select Menu:** When >3 options, automatically switches to WhatsApp List message
- **Admin Alerts:** Admin receives WhatsApp notification for brand not found & high-value bills

### Analytics
- **Custom Date Filter:** Analytics page supports custom from-to date range in addition to presets

## Core Architecture

### Tech Stack
- **Backend:** FastAPI (Python)
- **Frontend:** React with Tailwind CSS + Shadcn UI
- **Database:** MongoDB
- **Integrations:**
  - Karix (WhatsApp Business API)
  - Fundle/TagnPay (Loyalty Points API)
  - Gemini Vision (OCR for bill scanning)

### Key Components

#### 1. WhatsApp Flow (via Karix)
```
QR Code Scan → WhatsApp Opens with Pre-filled Message → Webhook Receives Message
→ User Registration (if new) → Menu Options (Upload Bill / Check Points)
→ Bill Image Processing (OCR) → Points Credit via Fundle API → Response to User
```

#### 2. QR Code System
- 7 unique QR codes with immutable source attribution (6 loyalty + 1 parking)
- Each QR opens WhatsApp with source-tracked pre-filled message
- Format: `wa.me/{WHATSAPP_NUMBER}?text={message}%20%7C%20{source_code}`
- Sources: Brands, Food Court, Parking, Entertainment, Main Entrance, Website, Parking Payment

#### 3. Bill Processing Pipeline
```
Image Upload → OCR (Gemini Vision) → Extract: Store, Bill No, Date, Amount, Customer Mobile
→ 15-day check → Amount check (>30K) → CP67 validation → Fundle earn-points API
→ Points credited → WhatsApp confirmation to user
```

#### 4. Admin Dashboard
- Login authentication (JWT)
- Dashboard with stats (Users, Bills, QR Scans, Points)
- QR Code performance analytics
- User management with detailed views
- Bill review system (Approve/Reject/Reprocess)
- WhatsApp conversation logs
- Parking Scanner & Report

## API Integrations

### Karix WhatsApp API
```python
# Send Text Message
POST https://rcmapi.instaalerts.zone/services/rcm/sendMessage
Headers: { "Authentication": "Bearer {API_KEY}" }
Body: {
  "message": {
    "channel": "WABA",
    "content": { "type": "TEXT", "text": "message" },
    "recipient": { "to": "91XXXXXXXXXX" },
    "sender": { "from": "{WHATSAPP_NUMBER}" }
  }
}

# Send Interactive Buttons
Same endpoint, content type: "INTERACTIVE" with buttons array

# Send Image (ATTACHMENT type - base64)
Body: {
  "message": {
    "channel": "WABA",
    "content": {
      "type": "ATTACHMENT",
      "attachment": {
        "type": "image",
        "caption": "Caption text",
        "mimeType": "image/png",
        "attachmentData": "base64_encoded_image_string"
      }
    },
    "recipient": { "to": "91XXXXXXXXXX" },
    "sender": { "from": "{WHATSAPP_NUMBER}" }
  }
}
```

### Fundle/TagnPay API
```python
# Generate Token
POST {BASE_URL}/api/generate-token/
Body: { "username": "", "password": "" }

# Register Customer
POST {BASE_URL}/api/customer-registration/
Body: { "mobile_number": "", "name": "", "loc_id": "", ... }

# Get Points
POST {BASE_URL}/api/get-customer-points/
Body: { "mobile_number": "" }

# Earn Points (Bill Upload)
POST {BASE_URL}/api/earn-points/
Body: { 
  "mobile_number": "", "bill_amount": 0, "bill_number": "",
  "bill_date": "YYYY-MM-DD", "brand_name": "", "bill_image": "base64..."
}
```

### Gemini Vision OCR
```python
from emergentintegrations.llm.gemini import GeminiClient
client = GeminiClient(api_key=EMERGENT_LLM_KEY)
response = await client.analyze_image(
    image_base64=image_data,
    prompt="Extract store name, bill number, date, amount from this receipt..."
)
```

## Database Schema

### Users Collection
```javascript
{
  id: "uuid",
  phone: "91XXXXXXXXXX",
  name: "Customer Name",
  kyc_status: true/false,
  registration_time: "ISO datetime",
  first_touch_source: "SRC_BRANDS",
  first_touch_qr: "QR0124001",
  balance_points: 0,
  total_earned_points: 0
}
```

### Bills Collection
```javascript
{
  id: "uuid",
  user_id: "user_uuid",
  user_phone: "91XXXXXXXXXX",
  store_name: "Store Name",
  bill_no: "BILL123",
  bill_date: "2025-01-24",
  amount: 1000.0,
  status: "auto_approved|manual_review|pending_review|approved|rejected",
  points_issued: 100,
  image_url: "data:image/jpeg;base64,...",
  image_hash: "md5hash",
  ocr_confidence: 0.95,
  ocr_raw_data: {},
  rejection_reason: "Optional reason",
  processed_at: "ISO datetime",
  processed_by: "system|admin|admin_reprocess"
}
```

### WhatsApp Logs Collection
```javascript
{
  id: "uuid",
  user_id: "user_uuid",
  user_phone: "91XXXXXXXXXX",
  direction: "inbound|outbound",
  message_type: "text|interactive|image",
  content: "Message content",
  source_code: "SRC_BRANDS",
  timestamp: "ISO datetime"
}
```

### QR Analytics Collection
```javascript
{
  qr_code_id: "QR0124001",
  scans: 100,
  registrations: 50,
  bill_uploads: 30
}
```

## Key Backend Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/whatsapp/webhook` | POST | Karix webhook for incoming messages |
| `/api/admin/login` | POST | Admin authentication |
| `/api/admin/me` | GET | Get current admin info |
| `/api/users` | GET | List all users |
| `/api/users/{id}` | GET | Get user details |
| `/api/bills` | GET | List all bills |
| `/api/bills/pending-review` | GET | Get bills needing review |
| `/api/bills/{id}/process` | POST | Approve/reject bill |
| `/api/bills/{id}/reprocess` | POST | Retry failed bill |
| `/api/analytics/dashboard` | GET | Dashboard stats |
| `/api/analytics/qr-performance` | GET | QR code analytics |
| `/api/qr-codes` | GET | List QR codes |

## Environment Variables

### Backend (.env)
```
MONGO_URL=mongodb://localhost:27017
DB_NAME=cp67_loyalty
CORS_ORIGINS=*
EMERGENT_LLM_KEY=sk-emergent-xxx
TAGNPAY_API_URL=https://cp67.fundlezone.com
TAGNPAY_USERNAME=xxx
TAGNPAY_PASSWORD=xxx
LOCATION_CODE=WAPP001
ADMIN_USERNAME=admin
ADMIN_PASSWORD=xxx
WHATSAPP_API_KEY=xxx
ADMIN_PHONE=91XXXXXXXXXX
WHATSAPP_NUMBER=91XXXXXXXXXX
```

### Frontend (.env)
```
REACT_APP_BACKEND_URL=https://your-domain.com
```

## Special Handling & Edge Cases

### 1. Brand Not Found in Fundle
- System sends WhatsApp alert to admin with exact brand name to add
- Bill saved as `pending_review` with rejection reason
- Admin can click "Reprocess" button after adding brand to Fundle

### 2. Bill Date > 30 Days
- Fundle API enforces 30-day rule server-side
- System marks as `auto_approved` for testing (configurable)
- User receives appropriate message

### 3. Duplicate Bill Detection
- Hash-based detection using store_name + bill_no
- Prevents same bill from being uploaded twice

### 4. OCR Tampering Detection
- Gemini analyzes bill for inconsistencies
- Flags potential tampering for manual review

### 5. User Name Emoji Stripping
- Fundle API doesn't support 4-byte UTF-8 characters
- System strips emojis from names before API calls

## Webhook URL Configuration
Configure in Karix dashboard:
```
https://your-domain.com/api/whatsapp/webhook
```

## Admin Credentials
- Username: `admin`
- Password: Set in ADMIN_PASSWORD env var

## File Structure
```
/app/
├── backend/
│   ├── server.py          # Main FastAPI application
│   ├── .env               # Environment variables
│   └── requirements.txt   # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── components/    # Reusable components
│   │   │   └── DashboardLayout.jsx
│   │   ├── pages/         # Page components
│   │   │   ├── Login.jsx
│   │   │   ├── Dashboard.jsx
│   │   │   ├── Users.jsx
│   │   │   ├── Bills.jsx
│   │   │   ├── QRCodes.jsx
│   │   │   └── Analytics.jsx
│   │   ├── App.js
│   │   └── index.css
│   ├── public/
│   │   └── qr-codes/      # Generated QR code images
│   ├── .env
│   └── package.json
└── memory/
    └── PRD.md
```

## Deployment Checklist
1. ✅ All secrets in environment variables
2. ✅ CORS configured for production domain
3. ✅ Karix webhook URL updated
4. ✅ DNS configured for custom domain
5. ✅ SSL certificate active
6. ✅ MongoDB connection string updated

## Completed Features
- [x] WhatsApp webhook integration with Karix
- [x] User registration flow
- [x] Bill upload and OCR processing
- [x] Points credit via Fundle API
- [x] Admin dashboard with full CRUD
- [x] QR code management and analytics
- [x] Bill review system (approve/reject/reprocess)
- [x] Brand not found workflow with admin alerts
- [x] Duplicate bill detection
- [x] WhatsApp conversation logging
- [x] Multi-admin system with roles (Super Admin, Admin, Bill Operator, Call Centre, Support Officer)
- [x] WhatsApp conversation logs viewer in dashboard
- [x] Real-time points from Fundle API
- [x] New vs Existing customer tracking
- [x] Website source tracking for WhatsApp onboarding
- [x] **Parking Validation Flow** (Feb 2026):
  - Parking entry API with QR code generation
  - Parking validation API for exit scanning
  - Parking Scanner page for staff
  - Parking Report page with stats and session history

## Parking System
### QR Code
- **QR0124007** - Parking Payment QR (`SRC_PARKING_PAY`)
- Completely isolated from loyalty system
- Does NOT affect loyalty registrations, scans, or bill uploads
- Has its own stats: Total Sessions, Active, Completed

### API Endpoints
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/parking/entry` | POST | No | Create parking session, returns QR code |
| `/api/parking/validate/{code}` | POST | No | Validate parking at exit (public) |
| `/api/parking/sessions` | GET | Yes | Get sessions report with stats |
| `/api/parking/session/{id}` | GET | Yes | Get single session details |

### Session Code Format
`PKG-HHMMSS-XXXXXX` (e.g., PKG-143022-A1B2C3)

## Known Limitations
- Fundle API enforces 30-day bill date rule (server-side)
- Fundle API requires exact brand name match from master list
- Karix requires webhook URL to be publicly accessible
- Parking QR scanning requires manual code entry (camera QR scanning not implemented)

## Technical Debt
- **CRITICAL:** `backend/server.py` is ~4000 lines and needs refactoring into:
  - `/app/backend/routers/` - API route handlers
  - `/app/backend/models/` - Pydantic models
  - `/app/backend/services/` - Business logic
  - `/app/backend/db/` - Database operations
