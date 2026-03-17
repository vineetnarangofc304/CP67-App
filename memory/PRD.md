# CP67 Mall - Complete Project Documentation

## Project Overview
A comprehensive mall engagement, loyalty, and discovery platform for CP67 Mall, Mohali. The system consists of:
1. **Consumer Mobile PWA** - Premium mobile-first app for shoppers
2. **Admin Dashboard** - Mall management backend
3. **WhatsApp Integration** - Bill upload and loyalty via WhatsApp
4. **Fundle/TagnPay Integration** - Points and loyalty engine

## Architecture
```
/app/
├── backend/
│   ├── server.py           # Admin + WhatsApp APIs (monolithic, 4800+ lines)
│   ├── routes/
│   │   ├── __init__.py
│   │   └── consumer.py     # Consumer app APIs (modular, ~600 lines)
│   ├── tests/
│   │   ├── test_cp67_loyalty.py
│   │   └── test_consumer_app.py
│   └── .env
├── frontend/
│   ├── src/
│   │   ├── consumer/           # Consumer PWA
│   │   │   ├── ConsumerApp.jsx # Shell with auth context + routing
│   │   │   ├── consumer.css    # Premium mobile-first styles
│   │   │   ├── components/
│   │   │   │   └── BottomNav.jsx
│   │   │   └── pages/
│   │   │       ├── Welcome.jsx
│   │   │       ├── Login.jsx (OTP)
│   │   │       ├── Onboarding.jsx
│   │   │       ├── Home.jsx
│   │   │       ├── Stores.jsx
│   │   │       ├── StoreDetail.jsx
│   │   │       ├── Wallet.jsx
│   │   │       ├── BillUpload.jsx
│   │   │       ├── Events.jsx
│   │   │       ├── Offers.jsx
│   │   │       ├── Profile.jsx
│   │   │       └── Notifications.jsx
│   │   ├── pages/              # Admin dashboard pages
│   │   ├── components/         # Admin components
│   │   └── App.js              # Main router
│   └── package.json
└── memory/
    └── PRD.md
```

## Consumer App Routes (/app/*)
- `/app/welcome` - Splash/onboarding screen
- `/app/login` - Phone + OTP login
- `/app/onboarding` - Profile setup (name, gender, interests)
- `/app/home` - Main home (banners, points, offers, stores, events)
- `/app/stores` - Store directory with search + category filters
- `/app/stores/:id` - Store detail with offers
- `/app/wallet` - Points balance, tier progress, transaction history
- `/app/upload` - Bill upload with camera/gallery
- `/app/events` - Events listing + registration
- `/app/offers` - Offers and deals
- `/app/profile` - User profile + settings
- `/app/notifications` - In-app notifications

## Consumer API Endpoints (/api/consumer/*)
- `POST /auth/send-otp` - Send OTP via TagnPay
- `POST /auth/verify-otp` - Verify OTP, return JWT (dev: 1234)
- `GET /profile` - Get user profile with points
- `PUT /profile` - Update profile
- `GET /home` - Aggregated home screen data
- `GET /stores` - Store directory
- `GET /stores/{id}` - Store detail with offers
- `GET /offers` - Active offers
- `GET /events` - Events listing
- `POST /events/{id}/register` - Event registration
- `GET /wallet` - Points balance + tier + transactions
- `POST /bills/upload` - Upload bill (OCR processing)
- `GET /bills` - User's bill history
- `GET /notifications` - User notifications
- `PUT /notifications/{id}/read` - Mark notification read
- `POST /seed` - Seed initial data

## Database Collections
- `users` - All users (WhatsApp + App, extended with app fields)
- `bills` - Bill uploads and OCR results
- `brands` - Brand/ATV configuration
- `stores` - Consumer-facing store directory (16 stores seeded)
- `offers` - Active offers (8 seeded)
- `events` - Mall events (4 seeded)
- `banners` - Homepage banners (4 seeded)
- `notifications` - User notifications
- `event_registrations` - Event sign-ups
- `fundle_customers` - Imported Fundle customer list

## Key Technical Details
- **Auth:** JWT tokens with `type: "consumer"` vs `type: "admin"`
- **OTP:** TagnPay API for real OTP, dev bypass with OTP=1234
- **Points:** Fundle/TagnPay API (balance, earn, registration)
- **OCR:** Gemini Vision API via Emergent LLM Key
- **Tiers:** Bronze (0-1999), Silver (2000-4999), Gold (5000-9999), Platinum (10000+)
- **Design:** Premium mobile-first, gold/amber accents, glassmorphism, 480px max-width

## What's Implemented (Phase 1) - Mar 17, 2026
- Full consumer app with 12 screens
- OTP authentication flow
- Personalized home screen with dynamic data
- Store directory with 16 stores, search, category filters
- Loyalty wallet with Fundle integration
- Bill upload with camera/gallery + Gemini OCR
- Events with registration
- Offers listing
- Profile management with onboarding
- In-app notifications system
- Premium bottom navigation
- 100% test pass rate (34 tests)

## Upcoming Tasks (Phase 2)
- Loyalty engine: Earn/burn rules, campaign multipliers, referral rewards
- Campaign builder: 2X/3X points, first visit, highest spender
- Points expiry logic
- Voucher redemptions
- AI mall concierge for recommendations

## Future Tasks (Phase 3-4)
- Brand/store dashboard with analytics
- CMS for banners, offers, events
- Mall admin CRM and segmentation
- Push notifications
- RFM analysis, cohort analytics, CLV
- Sponsored placements, media inventory
- Advanced fraud detection
- SMS fallback notifications
- Refactor server.py into modular routers

## 3rd Party Integrations
- **Fundle/TagnPay** - Loyalty API (live)
- **Karix** - WhatsApp messaging (live)
- **Gemini Vision** - OCR (via Emergent LLM Key)

## Credentials
- Admin: admin / CP67Admin@2025
- Dev OTP: 1234
- Test phone: 9876543210
