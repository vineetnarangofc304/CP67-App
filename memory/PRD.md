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
│   ├── server.py              # Admin APIs, WhatsApp, Campaign CRUD, Analytics
│   ├── routes/
│   │   ├── __init__.py
│   │   └── consumer.py        # Consumer app APIs (Map, Amenities, Referral, Wallet, Campaigns, etc.)
│   ├── uploads/brands/
│   ├── tests/
│   └── .env
├── frontend/
│   ├── src/
│   │   ├── consumer/           # Consumer PWA
│   │   │   ├── ConsumerApp.jsx
│   │   │   ├── consumer.css
│   │   │   ├── components/     # BottomNav, SideDrawer (11 items)
│   │   │   └── pages/          # 19 screens incl. TierJourney
│   │   ├── pages/              # Admin dashboard (incl. Campaigns.jsx)
│   │   └── App.js
│   └── public/manifest.json    # PWA manifest
└── memory/PRD.md
```

## What's Implemented

### Phase 1 (Mar 17, 2026) - Core PWA
- OTP login, Onboarding, Home, Store directory, Wallet, Bill upload + OCR, Events, Offers, Profile, Notifications

### Phase 2 (Mar 21, 2026) - Core Loyalty
- Enhanced Wallet, Transactions, Bill History, Rewards Catalog, Help & Support, Side Drawer, WhatsApp Bot

### Phase 3 (Feb 2026) - Map, Amenities, Referrals, Enhanced UX
- Mall Map, Amenities, Referrals, Participating Brands, Offers/Events enhancements, Admin brand eligibility toggles

### Phase 4 (Mar 22, 2026) - Campaign Engine & Tier System
**Explore/Stores Fix:**
- Fixed `/api/consumer/stores` to pull from `brands` collection (not hardcoded)
- Added `_enrich_brands()` startup function to populate floor/category for all 102 brands
- Floor filter, category filter, and search all work against real DB data
- Brand logos via Google Favicon CDN

**Campaign Engine (Admin):**
- Full CRUD: `POST/GET/PUT/DELETE /api/admin/campaigns`
- Toggle endpoint: `PUT /api/admin/campaigns/{id}/toggle`
- Active campaigns: `GET /api/admin/campaigns/active`
- Consumer campaigns: `GET /api/consumer/campaigns`
- 4 campaign types: Points Multiplier, Bonus Points, Spend Threshold, First Visit Reward
- Scoped by floor and category
- Admin UI: Stats cards, Campaign Builder table, Create/Edit dialog with type selectors, multiplier presets (1.5X-5X), date pickers, floor/category chips

**Tier System Visual UI:**
- New page: `/app/tier-journey`
- Hero card with current tier + lifetime points
- Visual progression: Bronze (0) -> Silver (2,500) -> Gold (10,000) -> Platinum (25,000)
- Benefits listed per tier
- Progress bar showing points needed for next tier
- Accessible from Wallet tier badge and SideDrawer

**PWA Enhancements:**
- Added `manifest.json` with app name, icons, theme colors
- Apple mobile web app meta tags
- `start_url: /app/welcome`, `display: standalone`

## Key API Endpoints

### Consumer App (/api/consumer/*)
- Auth: `POST /auth/send-otp`, `POST /auth/verify-otp`
- Profile: `GET /profile`, `PUT /profile`
- Content: `GET /home`, `GET /stores`, `GET /stores/{id}`, `GET /offers`, `GET /events`
- Wallet: `GET /wallet`, `GET /wallet/detailed`, `GET /transactions`, `GET /rewards`
- Bills: `POST /bills/upload`, `GET /bills`
- Social: `GET /favorites`, `POST /favorites/toggle`, `GET /referral`, `POST /referral/apply`
- Discovery: `GET /mall-map`, `GET /amenities`, `GET /participating-brands`
- Tiers: `GET /tier-info`, `GET /campaigns`

### Admin (/api/admin/*)
- Brands: `GET/POST /brands`, `PUT/DELETE /brands/{id}`
- Campaigns: `GET/POST /campaigns`, `PUT/DELETE /campaigns/{id}`, `PUT /campaigns/{id}/toggle`, `GET /campaigns/active`
- Analytics, Bills, Users, Parking, WhatsApp endpoints

## Database Collections
- `users`, `bills`, `brands`, `stores`, `offers`, `events`, `banners`
- `campaigns` (NEW), `notifications`, `event_registrations`, `fundle_customers`
- `redemptions`, `rewards`, `admin_users`, `qr_analytics`

## Known Issues
- **Karix WhatsApp Image Delivery (BLOCKED):** Code correct but images not delivered. External Karix platform issue.

## Upcoming Tasks (P1)
- Campaign-aware bill processing (apply multiplier/bonus when processing bills)
- PWA Install Guide modal for mall visitors

## Future Tasks (P2-P3)
- **TECH DEBT**: Refactor monolithic server.py into /routes, /services, /models
- Brand/Store Dashboard: Separate login for brands, self-manage offers
- Advanced Analytics: RFM, CLV, cohort analysis
- AI Mall Concierge
- Push Notifications, CMS for banners/offers/events

## Credentials
- Admin: admin / CP67Admin@2025
- Dev OTP: 1234 (phone: 9876543210)
- Consumer app: /app/welcome
- Admin dashboard: /
