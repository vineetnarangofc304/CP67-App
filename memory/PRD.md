# CP67 Mall - Homeland Advantage PWA

## Product Overview
A top-tier mall engagement app for CP67 Mall (Homeland Advantage), consisting of a consumer mobile PWA, an admin backend, a brand/store dashboard, and an AI/analytics engine.

## Core Requirements
- Consumer PWA: Loyalty wallet, bill upload (OCR), tier journey, store directory, referrals, events, mall maps, amenities
- Admin Dashboard: Brand management, bill review, campaign engine, banner management, analytics
- WhatsApp Bot (Karix): OTP, bill upload instructions, points check, redeem, know more, support
- Backend: FastAPI, MongoDB, TagnPay/Fundle loyalty, Gemini Vision OCR, Karix WhatsApp

## Tech Stack
- Frontend: React, PWA, framer-motion, Tailwind-adjacent CSS, Google Fonts (Playfair Display + Outfit)
- Backend: FastAPI (Python), Motor AsyncIOMotorClient (MongoDB)
- Database: MongoDB (DB_NAME: test_database)
- Integrations: TagnPay/Fundle (Loyalty), Karix (WhatsApp), Gemini Vision (OCR)

## Design Theme
- **Kinetic Luxury Dark Theme**: Dark chocolate (#140B00) backgrounds, gold (#C9A55A) accents, glassmorphism panels, Playfair Display headings, Outfit body font, framer-motion animations, shimmer effects, grain texture overlay

## What's Been Implemented

### Phase 1-8 (Previous Sessions)
- Full consumer PWA with all pages (Home, Wallet, Stores, Profile, Tier Journey, Bill Upload, Events, Offers, Rewards, Help, Legal, Mall Map, Amenities, Referrals)
- Admin Dashboard (Brands, Bills, Campaigns, Banners, Dashboard stats)
- WhatsApp Bot (Karix webhooks) with deduplication
- TagnPay loyalty integration
- OCR bill parsing with Gemini Vision
- 1050 brand staff phone numbers blocked

### Phase 9 (Previous Session)
- Kinetic Luxury UI Overhaul (Welcome splash, animated logo, floating particles)
- Banner admin direct image upload
- Bill upload instructions
- T&C and earning slabs (10 Points = INR 1)
- WhatsApp webhook formatting fixes

### Phase 10 (Current Session - March 31, 2026)
- **WhatsApp Bot Formatting Verified**: All 4 responses (My Points, Redeem Points, Know More, Help/Support) confirmed working correctly - no bullets, proper line breaks, Karix 200 Accepted
- **Brand Staff Excel Analyzed**: New file has 1049 valid phones, same as existing 1050 blocked - no new numbers needed
- **Dark Luxury Theme Overhaul (ALL Inner Pages)**: Complete CSS overhaul from light cream (#FAF8F5) to dark chocolate (#140B00) for every consumer page:
  - Home: Dark background, gold points card, glass quick actions, gold accents
  - Wallet: Gold glow aura on balance card, glass stats, gold progress bar with luminous dot
  - Stores: Glass search with gold focus ring, dark store cards, gold active category pills
  - Profile: Gold avatar ring, glass personal info card, gold edit links
  - Tier Journey: Full dark theme, tier-colored icon glows, gold progress line
  - Login/Onboarding: Dark inputs, gold borders, gold gradient buttons
  - Bill Upload: Dark capture zone, gold dashed border
  - Events/Offers/Rewards/Help/Legal/Mall Map/Amenities/Referrals: All updated
  - Bottom Nav: Dark glass pill with gold camera button
  - Side Drawer: Dark background with gold accents
- Testing: 100% pass rate (Iteration 23)

## Pending Issues
- Karix WhatsApp QR Image Not Being Delivered (BLOCKED - external Karix platform issue)

## Upcoming Tasks (P1)
- Campaign-aware bill processing: Auto-apply multipliers during active campaigns
- PWA Installation Guide: Modal for mall visitors on "Add to Home Screen"

## Future Tasks (P2)
- Parking access flow (WhatsApp)
- Automate Footfall Data via Email Parser
- Refactor monolithic server.py (5200+ lines → modular /routes, /services, /models)
- Brand/Store Dashboard (separate brand login)
- Advanced Analytics (RFM, CLV, AI Concierge)

## Key API Endpoints
- POST /api/whatsapp/webhook - Karix WhatsApp entry point
- POST /api/consumer/auth/send-otp & /api/consumer/auth/verify-otp - Consumer auth
- POST /api/admin/banners/{banner_id}/upload-image - Direct banner upload
- GET /api/consumer/home - Home page data
- GET /api/consumer/stores - Store listing

## Database Collections
- brands, whatsapp_dedup (TTL), campaigns, blocked_phones, banners, users, bills, whatsapp_logs

## Code Architecture
```
/app/
├── backend/
│   ├── routes/consumer.py
│   ├── server.py (monolithic - 5200+ lines)
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
