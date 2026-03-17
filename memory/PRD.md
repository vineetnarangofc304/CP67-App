# CP67 Mall - Complete Project Documentation

## Project Overview
A comprehensive mall engagement, loyalty, and discovery platform for CP67 Mall, Mohali. The system consists of:
1. **Consumer Mobile PWA** - Premium mobile-first app for shoppers (at `/app/*`)
2. **Admin Dashboard** - Mall management backend (at `/`)
3. **WhatsApp Integration** - Bill upload and loyalty via WhatsApp
4. **Fundle/TagnPay Integration** - Points and loyalty engine

## Architecture
```
/app/
├── backend/
│   ├── server.py              # Admin + WhatsApp APIs
│   ├── routes/
│   │   ├── __init__.py
│   │   └── consumer.py        # Consumer app APIs
│   ├── uploads/
│   │   └── brands/            # Brand logos & cover images
│   ├── tests/
│   │   ├── test_cp67_loyalty.py
│   │   ├── test_consumer_app.py
│   │   └── test_brand_management.py
│   └── .env
├── frontend/
│   ├── src/
│   │   ├── consumer/           # Consumer PWA
│   │   │   ├── ConsumerApp.jsx
│   │   │   ├── consumer.css
│   │   │   ├── components/BottomNav.jsx
│   │   │   └── pages/ (12 screens)
│   │   ├── pages/              # Admin dashboard
│   │   │   ├── Brands.jsx      # Enhanced with store management
│   │   │   └── ...
│   │   └── App.js
│   └── package.json
└── memory/PRD.md
```

## What's Implemented

### Phase 1 Complete (Mar 17, 2026)

**Consumer Mobile PWA (12 screens)**
- OTP login via TagnPay (dev OTP: 1234)
- Onboarding (name, gender, interests)
- Home screen (points card, banners, offers, featured stores, events)
- Store directory (16+ stores, search, category filters)
- Store detail with offers
- Loyalty wallet (Fundle-powered, tier system)
- Bill upload with camera/gallery + Gemini OCR
- Events listing + registration
- Offers page
- Profile management
- Notifications
- Bottom navigation with center scan button

**Brand & Store Management (Admin)**
- 102 brands loaded from ATV sheet
- Full store management with tabbed edit (Basic Info, Store Details, Images)
- Image upload: logo + cover (stored in /uploads/brands/)
- Auto-sync brands → consumer stores collection
- App-Ready status tracking in table
- Bulk sync to app button

**Consumer Entry Points**
- App Download QR code (GET /api/app-download-qr)
- WhatsApp messages include app download link
- QR codes for mall entrances, parking, in-store

**ATV Data Leak Fix (P0)**
- Customer WhatsApp messages no longer expose brand ATV

### Previously Implemented
- WhatsApp bill upload + OCR
- Fundle customer sync
- Parking validation flow
- Export reports
- Multi-admin system
- Bill approval workflow
- Brand ATV rules

## Key API Endpoints

### Consumer App (/api/consumer/*)
- `POST /auth/send-otp`, `POST /auth/verify-otp`
- `GET /profile`, `PUT /profile`
- `GET /home`, `GET /stores`, `GET /stores/{id}`
- `GET /offers`, `GET /events`, `POST /events/{id}/register`
- `GET /wallet`, `POST /bills/upload`, `GET /bills`
- `GET /notifications`, `PUT /notifications/{id}/read`

### Admin (/api/admin/*)
- `GET/POST /brands`, `PUT /brands/{id}`, `DELETE /brands/{id}`
- `POST /brands/{id}/upload-image` (logo/cover)
- `POST /brands/sync-to-stores`
- `GET /app-download-qr`

## Database Collections
- `users`, `bills`, `brands`, `stores`, `offers`, `events`, `banners`
- `notifications`, `event_registrations`, `fundle_customers`
- `brand_upload_history`, `admin_users`, `qr_analytics`

## Upcoming Tasks (Phase 2)
- Loyalty engine: earn/burn rules, campaigns, multipliers, referral
- Campaign builder: 2X/3X points, first visit, highest spender
- Points expiry, voucher redemptions
- AI mall concierge

## Future Tasks (Phase 3-4)
- Brand/store dashboard with analytics
- CMS for banners, offers, events
- Push notifications
- RFM analysis, CLV, cohort analytics
- Sponsored placements, media inventory
- Mall admin CRM + segmentation

## Credentials
- Admin: admin / CP67Admin@2025
- Dev OTP: 1234 (phone: 9876543210)
- Consumer app: /app/welcome
- Admin dashboard: /
