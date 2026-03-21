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
│   │   └── consumer.py        # Consumer app APIs (Map, Amenities, Referral, Wallet, etc.)
│   ├── uploads/
│   │   └── brands/            # Brand logos & cover images
│   ├── tests/
│   │   ├── test_new_features.py
│   │   ├── test_cp67_loyalty.py
│   │   ├── test_consumer_app.py
│   │   └── test_brand_management.py
│   └── .env
├── frontend/
│   ├── src/
│   │   ├── consumer/           # Consumer PWA
│   │   │   ├── ConsumerApp.jsx
│   │   │   ├── consumer.css
│   │   │   ├── components/
│   │   │   │   ├── BottomNav.jsx
│   │   │   │   └── SideDrawer.jsx (9 menu items)
│   │   │   └── pages/ (18 screens)
│   │   │       ├── Home.jsx, Login.jsx, Welcome.jsx, Onboarding.jsx
│   │   │       ├── Stores.jsx, StoreDetail.jsx, Wallet.jsx
│   │   │       ├── Offers.jsx (enhanced: Flash Sales + filters)
│   │   │       ├── Events.jsx (enhanced: Featured hero + countdown)
│   │   │       ├── BillUpload.jsx, BillHistory.jsx
│   │   │       ├── Profile.jsx, Notifications.jsx, NotificationPrefs.jsx
│   │   │       ├── Transactions.jsx, Rewards.jsx
│   │   │       ├── HelpSupport.jsx, Legal.jsx, ProgramInfo.jsx
│   │   │       ├── MallMap.jsx (NEW)
│   │   │       ├── Amenities.jsx (NEW)
│   │   │       └── Referrals.jsx (NEW)
│   │   ├── pages/              # Admin dashboard
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
- Full store management with tabbed edit
- Image upload: logo + cover
- Auto-sync brands to consumer stores collection
- App-Ready status tracking

**Camera Fixes (Mar 19, 2026)**
- Bill Upload camera: replaced with getUserMedia for PWA robustness
- Parking Scanner camera: replaced with html5-qrcode

### Phase 2 Complete — Core Loyalty Features (Mar 21, 2026)

**New Backend Endpoints:**
- `GET /api/consumer/wallet/detailed` — Enhanced wallet
- `GET /api/consumer/transactions` — Transaction history with filters
- `GET /api/consumer/rewards` — Rewards catalog
- `POST /api/consumer/rewards/redeem` — One-tap redemption
- Profile update: DOB, gender, address fields

**New Frontend Pages (8 pages):**
- Enhanced Wallet, Transactions, Bill History, Rewards Catalog
- Help & Support, Legal, Side Drawer Menu, Enhanced Profile

**WhatsApp Bot (Mar 21, 2026):**
- 5-option list message menu
- All message flows updated per revised journey doc
- List reply + button reply webhook parsing

**Additional Features:**
- Store Favorites with heart toggle
- Notification Preferences (6 category toggles)

### Phase 3 — Map, Amenities, Referrals, Enhanced UX (Feb 2026)

**New Backend Endpoints:**
- `GET /api/consumer/mall-map` — Floor-wise brand locations
- `GET /api/consumer/amenities` — 6-category amenities directory (18 facilities)
- `GET /api/consumer/referral` — User referral info & stats
- `POST /api/consumer/referral/apply` — Apply referral code
- `GET /api/consumer/tier-info` — Tier system details

**3 New Frontend Pages:**
- **Mall Map** (`/app/mall-map`) — Floor-wise accordion, search by store/category, store logos
- **Amenities** (`/app/amenities`) — 6 category quick-grid, expandable sections with locations
- **Referrals** (`/app/referrals`) — Referral code card with copy/share, stats dashboard, how-it-works, apply code form

**Enhanced Existing Pages:**
- **Offers** — Filter tabs (All Offers / Hot Deals), horizontal Flash Sales scroll section
- **Events** — Filter tabs (All Events / Featured), featured hero banner with countdown, event countdown tags

**SideDrawer Updated:** 9 menu items (added Mall Map, Amenities, Refer & Earn)

**Testing:** 100% backend (15/15), 100% frontend — all verified

## Key API Endpoints

### Consumer App (/api/consumer/*)
- `POST /auth/send-otp`, `POST /auth/verify-otp`
- `GET /profile`, `PUT /profile`
- `GET /home`, `GET /stores`, `GET /stores/{id}`
- `GET /offers`, `GET /events`, `POST /events/{id}/register`
- `GET /wallet`, `GET /wallet/detailed`
- `POST /bills/upload`, `GET /bills`
- `GET /transactions`, `GET /rewards`, `POST /rewards/redeem`
- `GET /favorites`, `POST /favorites/toggle`
- `GET /notification-preferences`, `PUT /notification-preferences`
- `GET /mall-map`, `GET /amenities`
- `GET /referral`, `POST /referral/apply`
- `GET /tier-info`

### Admin (/api/admin/*)
- `GET/POST /brands`, `PUT /brands/{id}`, `DELETE /brands/{id}`
- `POST /brands/{id}/upload-image`
- `POST /brands/sync-to-stores`

## Database Collections
- `users`, `bills`, `brands`, `stores`, `offers`, `events`, `banners`
- `notifications`, `event_registrations`, `fundle_customers`
- `brand_upload_history`, `admin_users`, `qr_analytics`

## Known Issues
- **Karix WhatsApp Image Delivery (BLOCKED):** Code correct but images not delivered. External Karix platform issue.

## Upcoming Tasks (P1)
- Campaign Engine: Admin campaign builder (2X/3X points, multipliers, first visit, highest spender)
- Tier System Visual UI: Bronze -> Silver -> Gold -> Platinum progression journey

## Future Tasks (P2-P3)
- **TECH DEBT**: Refactor monolithic server.py into /routes, /services, /models
- Brand/Store Dashboard: Separate login for brands, self-manage offers
- Advanced Analytics: RFM, CLV, cohort analysis
- AI Mall Concierge
- Push Notifications, CMS for banners/offers/events
- Sponsored placements, media inventory

## Credentials
- Admin: admin / CP67Admin@2025
- Dev OTP: 1234 (phone: 9876543210)
- Consumer app: /app/welcome
- Admin dashboard: /
