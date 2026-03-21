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

### Bug Fix (Mar 19, 2026)

**Camera Fix on Bill Upload Page (P0)**
- Fixed: "Start camera is getting stuck and not opening the camera"
- Root cause: Used unreliable `<input type="file" capture="environment">` which doesn't work in many PWA contexts
- Fix: Replaced with `navigator.mediaDevices.getUserMedia()` API for direct camera access
- New features: Live camera viewfinder, capture button, front/back camera switch, proper error handling
- Tested: 11/11 test cases passed (100% frontend success rate)

**Parking Scanner Camera Fix (P0) — Mar 19, 2026**
- Fixed: Camera on Parking Scanner admin page showing black screen despite "Camera Active" status
- Root cause: Custom `getUserMedia` + video element had no `muted` attribute (required for iOS autoplay) and no QR decoding library
- Fix: Replaced with `html5-qrcode` library which handles camera access, video rendering, and QR code scanning
- Now auto-detects and validates parking QR codes when scanned
- Removed misleading "Camera scanning requires manual code entry" message

### Phase 1 Complete — Core Loyalty Features (Mar 21, 2026)
Per "Homeland Advantage App Requirements Document Version 1.1":

**New Backend Endpoints:**
- `GET /api/consumer/wallet/detailed` — Enhanced wallet with balance, earned, redeemed, expired, tier progress
- `GET /api/consumer/transactions` — Transaction history with filter (all/earn/redeem)
- `GET /api/consumer/rewards` — Rewards catalog (auto-seeded from brands: 4 denominations x 12 stores)
- `POST /api/consumer/rewards/redeem` — One-tap redemption (1 pt = Rs 1)
- `GET /api/consumer/rewards/history` — Redemption history
- Profile update: added DOB, gender, address fields

**New Frontend Pages (8 pages/components):**
- Enhanced Wallet — Points breakdown (earned/redeemed/expired), tier progress bar, quick actions
- Transactions — Full history with All/Earned/Redeemed filter tabs
- Bill History — All bills with status filters (All/Approved/Pending/Rejected), rejection reasons
- Rewards Catalog — Cards grouped by store, Rs 100/250/500/1000 denominations, one-tap redeem
- Help & Support — 4 contact cards, 6 expandable FAQs
- Legal — Terms & Conditions + Privacy Policy
- Side Drawer Menu — 6 items (Profile, Rewards, Transactions, Bill History, Help, Legal) + Logout
- Enhanced Profile — DOB, gender, address, tier display, edit form with save

**Testing:** 32/32 backend tests passed, all frontend UI verified (100% pass rate)

### WhatsApp Bot List Reply Fix + Additional Features (Mar 21, 2026)
**Critical Bug Fix:**
- WhatsApp bot was not responding to menu selections (list message replies)
- Root cause: Webhook only parsed `button_reply.id`, not `list_reply.id` from Karix interactive messages
- Fix: Added `list_reply` parsing + TITLE_TO_ACTION fallback mapping for text messages matching known titles
- All 5 menu actions tested and verified: upload_bill, my_points, redeem_points, customer_support, know_more

**Additional Features Built:**
- Store Favorites — heart toggle on each store card + Favorites filter tab
- Notification Preferences — 6 category toggles (Offers, Points, Events, Bills, Rewards, Promotions)
- Link from Profile → Notification Settings
- Backend: `/api/consumer/favorites`, `/favorites/toggle`, `/notification-preferences`
- Testing: 25/25 backend + all frontend UI tests passed (100%)
Per user-provided document "Revised WhatsApp Bot Journey_18.03.2026":
- **Menu structure:** Changed from 3 buttons to 5-option list message (Upload Bill, Redeem Points, My Points, Help/Support, Know More)
- **My Points:** Separate flow showing Total Earned, Redeemed, Available Balance
- **Redeem Points:** Separate flow showing redemption info at participating brands
- **Know More:** New option linking to `/app/program` landing page
- **Bill upload prompt:** Updated with step-by-step instructions, e-bills accepted
- **Bill success message:** Simplified to "Thank you for uploading your bill of {Brand} with Homeland Advantage"
- **All rejection messages:** Updated (non-CP67, >15 days, >30K under review)
- **Help/Support:** Reformatted with email, phone, support desk info
- **Emoji cleanup:** All emoji characters removed from every WhatsApp message template
- **New landing page:** Created at `/app/program` — Homeland Advantage program overview, participating brands (50 from API), How It Works, T&C, support contacts
- Tested: 12/12 backend tests passed, landing page verified with 50 brands loading

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

## Known Issues
- **Karix WhatsApp Image Delivery (BLOCKED):** Code is correct but images not delivered. External Karix platform issue - needs escalation to Karix support with message IDs.

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

## Technical Debt
- **server.py refactoring** - Monolithic file needs to be broken into routes, services, models

## Credentials
- Admin: admin / CP67Admin@2025
- Dev OTP: 1234 (phone: 9876543210)
- Consumer app: /app/welcome
- Admin dashboard: /
