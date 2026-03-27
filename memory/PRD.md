# CP67 Mall - Homeland Advantage - Complete Project Documentation

## Project Overview
A comprehensive mall engagement, loyalty, and discovery platform for CP67 Mall, Mohali. The system consists of:
1. **Consumer Mobile PWA** - Premium mobile-first app for shoppers (at `/app/*`)
2. **Admin Dashboard** - Mall management backend (at `/`)
3. **WhatsApp Integration** - Bill upload and loyalty via WhatsApp (Karix)
4. **Fundle/TagnPay Integration** - Points and loyalty engine

## Architecture
```
/app/
├── backend/
│   ├── server.py              # Admin APIs, WhatsApp, Campaign CRUD, Footfall, Analytics
│   ├── routes/
│   │   └── consumer.py        # Consumer app APIs (Map, Amenities, Referral, Wallet, Campaigns, Tiers)
│   └── .env
├── frontend/
│   ├── src/
│   │   ├── consumer/           # Consumer PWA
│   │   │   ├── ConsumerApp.jsx
│   │   │   ├── consumer.css
│   │   │   ├── components/     # BottomNav, SideDrawer
│   │   │   └── pages/          # 20+ screens
│   │   ├── pages/              # Admin dashboard (Campaigns.jsx, Dashboard.jsx, etc.)
│   │   └── App.js
│   └── public/
│       ├── manifest.json       # PWA manifest
│       └── homeland-advantage-logo.jpeg  # Updated app logo
└── memory/PRD.md
```

## What's Implemented

### Phase 1 - Core PWA (Mar 17)
- OTP login, Onboarding, Home, Store directory, Wallet, Bill upload + OCR, Events, Offers, Profile, Notifications

### Phase 2 - Core Loyalty (Mar 21)
- Enhanced Wallet, Transactions, Bill History, Rewards Catalog, Help & Support, Side Drawer, WhatsApp Bot

### Phase 3 - Map, Amenities, Referrals (Mar 21-22)
- Mall Map, Amenities, Referrals, Participating Brands, Admin brand eligibility toggles

### Phase 4 - Campaign Engine & Tier System (Mar 22)
- Campaign CRUD (4 types: multiplier, bonus, spend_threshold, first_visit)
- Tier Journey page (Bronze→Silver→Gold→Platinum progression)
- Explore/Stores fix (brands from DB with floor/category filters)
- Root /health endpoint for production deployment

### Phase 5 - Content & Dashboard Updates (Mar 24)
- **Logo Updated**: New Homeland Advantage gift box logo
- **Points Earning Slab**: 7-tier table (Retail vs Jewellery/Electronics %)
- **10 Points = INR 1**: Conversion note in Wallet and TierJourney
- **Terms & Conditions**: Full 11-clause T&C on Legal page
- **Amenities Updated**: Real CP67 data (Restrooms by floor, Services, Parking & EV, etc.)
- **WhatsApp Messages Updated**: All bot messages per Revised Doc
- **Dashboard Stats**: Total Footfall, Registrations, Bill Uploads with footfall manual entry

## Key API Endpoints

### Consumer (/api/consumer/*)
- Auth: `POST /auth/send-otp`, `POST /auth/verify-otp`
- Content: `GET /home`, `GET /stores`, `GET /offers`, `GET /events`
- Wallet: `GET /wallet`, `GET /wallet/detailed`, `GET /transactions`, `GET /rewards`
- Bills: `POST /bills/upload`, `GET /bills`
- Discovery: `GET /mall-map`, `GET /amenities`, `GET /participating-brands`
- Tiers: `GET /tier-info`, `GET /campaigns`

### Admin (/api/admin/*)
- Brands: `GET/POST /brands`, `PUT/DELETE /brands/{id}`
- Campaigns: `GET/POST /campaigns`, `PUT/DELETE /campaigns/{id}`, `PUT /campaigns/{id}/toggle`
- Footfall: `GET/POST /admin/footfall`
- Analytics: `GET /analytics/dashboard`

## Database Collections
- `users`, `bills`, `brands`, `campaigns`, `footfall`
- `offers`, `events`, `banners`, `notifications`
- `redemptions`, `rewards`, `admin_users`, `qr_analytics`

### Phase 6 - Floor Filter Bug Fix (Mar 24)
- **Floor Filter Sync**: Fixed floor string consistency between Admin and Consumer pages
- **Duplicate Brand Cleanup**: Removed duplicate "Lakmé Salon" entry (one with no floor)
- **All 101 brands now have proper floor assignments**: Ground Floor (23), First Floor (28), Second Floor (27), Food Court (21), Lower Ground (2)
- **Admin FLOORS dropdown**: Includes all valid options (Ground Floor, First Floor, Second Floor, Third Floor, Food Court, Lower Ground)
- **Testing**: 100% pass rate on backend (20/20) and frontend floor filter tests (iteration 19)

### Phase 7 - Security, Banners & UI Updates (Mar 27)
- **Brand Staff Blocking**: 1050 phone numbers from xlsx blocked from loyalty registration (403 on send-otp & verify-otp)
- **Event Banners**: Vipul Goyal & Vivek Samtani comedy show banners added to home carousel and events
- **Admin Banner Management**: Full CRUD page at /banners with image upload support
- **Wallet Button**: "Rewards" renamed to "Redeem", now navigates to /app/redeem (Redeem at Brand section)
- **Floor Filter Cleanup**: Removed "Food Court" and "Third Floor" from consumer floor dropdowns
- **Profile Cleanup**: Removed Referral Code section
- **HA Logo Update**: New white-background logo placed across Login, Welcome, Home, SideDrawer, PWA manifest
- **Testing**: 100% pass rate on backend (14/14) and frontend (iteration 20)

## Known Issues
- **Karix WhatsApp Image Delivery (BLOCKED):** Code correct but images not delivered (external issue)

## Database Collections
- `users`, `bills`, `brands`, `campaigns`, `footfall`
- `offers`, `events`, `banners`, `notifications`
- `redemptions`, `rewards`, `admin_users`, `qr_analytics`
- `blocked_phones` (1050 brand staff numbers, indexed on phone)

## Credentials
- Admin: admin / CP67Admin@2025
- Dev OTP: 1234 (phone: 9876543210)
- Consumer app: /app/welcome | Admin dashboard: /

## Upcoming Tasks
- (P1) Campaign-aware bill processing (auto-apply multipliers during active campaigns)
- (P1) PWA Install Guide modal for mall visitors (iOS & Android instructions)

## Future Tasks (P2-P3)
- Refactor monolithic server.py (5000+ lines) into /routes, /services, /models
- Automate Footfall Data via Email Parser
- Brand/Store Dashboard (separate brand login)
- Advanced Analytics (RFM, CLV, cohort)
- AI Mall Concierge, Push Notifications, CMS
