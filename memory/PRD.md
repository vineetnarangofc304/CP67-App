# CP67 Mall - Homeland Advantage PWA

## Product Overview
A top-tier mall engagement app for CP67 Mall (Homeland Advantage), consisting of a consumer mobile PWA, an admin backend, a brand/store dashboard, and an AI/analytics engine.

## Core Requirements
- Consumer PWA: Loyalty wallet, bill upload (OCR), tier journey, store directory, referrals, events, mall maps, amenities
- Admin Dashboard: Brand management, bill review, campaign engine, banner management, analytics
- WhatsApp Bot (Karix): OTP, bill upload instructions, points check, redeem, know more, support, parking
- Backend: FastAPI, MongoDB, TagnPay/Fundle loyalty, Gemini Vision OCR, Karix WhatsApp

## Tech Stack
- Frontend: React, PWA, framer-motion, CSS, Google Fonts (Playfair Display + Outfit)
- Backend: FastAPI (Python), Motor AsyncIOMotorClient (MongoDB)
- Database: MongoDB (DB_NAME: test_database)
- Integrations: TagnPay/Fundle (Loyalty), Karix (WhatsApp), Gemini Vision (OCR)

## Design Theme
- Light cream (#FAF8F5) backgrounds with luxury gold accents
- Gold-tinted card borders, luxury shadows, shimmer effects
- Breathing glow on center nav button
- Gold gradient CTAs, gold avatar rings, gold dividers

## What's Been Implemented

### Phase 1-8 (Previous Sessions)
- Full consumer PWA with all pages
- Admin Dashboard (Brands, Bills, Campaigns, Banners, Dashboard stats)
- WhatsApp Bot (Karix webhooks) with deduplication
- TagnPay loyalty integration, OCR bill parsing
- 1050 brand staff phone numbers blocked

### Phase 9 (Previous Session)
- Kinetic Luxury UI Overhaul (Welcome splash)
- Banner admin direct image upload
- Bill upload instructions, T&C updates
- WhatsApp webhook formatting fixes

### Phase 10 (Current Session - April 3, 2026)
- **Dark theme reverted**: Client rejected full dark overhaul; reverted to original light cream design
- **Luxury design gimmicks added**: Gold-tinted card borders, premium shadows, shimmer sweep, breathing glow on nav, gold progress dot, gold avatar ring, gold dividers, gold focus ring on search, gold active category pills, gold gradient CTAs, image zoom on tap, gold dashed bill upload zone
- **Parking QR Flow (SRC_PARKING)**: 
  - QR code in mall parking links to WhatsApp: `wa.me/917347576767?text=Hi! Sign me up for CP67 Rewards | SRC_PARKING`
  - NEW customer: Registers WITHOUT 1000 bonus points, generates unique parking coupon (PARK-XXXXXXXX), creates QR image, sends via WhatsApp (valid 24 hours)
  - EXISTING customer: "Free parking only for new members" + menu
  - BLOCKED staff: "Not eligible" message
  - Parking coupons stored in `parking_coupons` collection
  - QR image endpoint: `/api/parking/coupon-qr/{coupon_code}`
- **WhatsApp text parsing fix**: Fixed `text` field handling for both string and dict formats

## Pending Issues
- Karix WhatsApp QR Image delivery to actual devices (Karix platform issue — API returns 200 but image may not render on some devices)

## Recently Fixed (April 3, 2026 - Session 2)
- **Parking times now in IST**: All entry/exit times in Parking Report and Scanner validation converted from UTC to IST (UTC+5:30)
- **PARK- coupon validation fixed**: Exit scanner now supports both `PKG-` and `PARK-` codes; response format normalized with `entry_time_display`/`exit_time_display`
- **Scanner QR regex updated**: ParkingScanner now extracts both `PKG-` and `PARK-` prefixes from QR scans
- **completed_today stats fixed**: Uses IST midnight for daily exit count
- **Parking Staff Login**: Added `parking` / `Parking@2025` role with access restricted to only Parking Scanner and Parking Report. Auto-redirects to Parking Scanner on login. All other admin pages blocked.
- **Existing customer free parking bug fixed**: `process_parking_registration` now checks Fundle API for existing customers and denies free parking (sends "already registered" message instead of coupon)
- **Parking Report shows PARK- coupons**: Report now merges `parking_sessions` + `parking_coupons` collections, with Type column (Session / Free Coupon)
- **PK001 location code**: Parking QR registrations now use `loc_id: PK001` for TagnPay/Fundle registration
- **Two-Gate Exit System**: Two separate logins (`parking1`/`parking2`) each assigned to Gate 1 / Gate 2. Validations auto-tagged with exit gate. Reports filtered by gate. Admin sees all. QR codes available at `/api/parking/exit-qr/gate1` and `/api/parking/exit-qr/gate2`.

## Recently Fixed (April 13, 2026 - Session 3)
- **Font**: Changed to Antique Olive everywhere (heading + body)
- **Login**: Shows "Welcome to Homeland Advantage"
- **Wallet Card**: Tier-specific slab colours (Bronze=Copper, Silver=Metallic Grey, Gold=Rich Gold, Platinum=Cool Light Grey, Titanium=Dark Grey, Diamond=Ice Blue, Privilege=Royal Purple & Gold) with coin decorations
- **Hot Deals & Events Admin**: Full CRUD with image upload in admin panel; consumer app pulls from DB
- **Profile**: Added pincode auto-fill (city/state via India Post API), house_no, landmark fields
- **Tier Journey**: Replaced old benefits with earning rates table (Retail % / Jewellery & Electronics % per purchase range)
- **Transactions**: Added "Expired" filter tab
- **Bottom Nav**: Now visible on ALL inner pages (wallet, upload, tier, transactions, amenities, help, profile, etc.)
- **Amenities**: Removed ATM & Banking category
- **Help & Support**: Removed "bill above 30,000" FAQ
- **Logo Syncing**: Admin-uploaded logos (data: URLs) no longer overwritten by startup migration
- **Brands Filtering**: Featured stores only show eligible, active brands

## Upcoming Tasks (P1)
- Campaign-aware bill processing: Auto-apply multipliers during active campaigns
- PWA Installation Guide: Modal for mall visitors on "Add to Home Screen"

## Future Tasks (P2)
- Automate Footfall Data via Email Parser
- Refactor monolithic server.py (5400+ lines → modular /routes, /services, /models)
- Brand/Store Dashboard (separate brand login)
- Advanced Analytics (RFM, CLV, AI Concierge)

## Key API Endpoints
- POST /api/whatsapp/webhook - Karix WhatsApp entry point (handles SRC_PARKING)
- GET /api/parking/coupon-qr/{coupon_code} - Serves parking coupon QR image
- POST /api/consumer/auth/send-otp & verify-otp - Consumer auth
- POST /api/admin/banners/{banner_id}/upload-image - Direct banner upload

## Database Collections
- brands, whatsapp_dedup (TTL), campaigns, blocked_phones, banners, users, bills, whatsapp_logs, parking_coupons (NEW)

## Code Architecture
```
/app/
├── backend/
│   ├── routes/consumer.py
│   ├── server.py (monolithic - 5400+ lines)
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── consumer/ (PWA: components/, pages/, consumer.css)
│   │   ├── pages/ (Admin dashboard)
│   │   └── App.js
└── memory/
    ├── PRD.md
    └── test_credentials.md
```
