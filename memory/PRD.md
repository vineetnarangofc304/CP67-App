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

## Recently Fixed (May 14, 2026 - Session 8)
- **Play Store package name fix**: Rebuilt the production AAB with `packageId=com.fundle.cp67` (Google Play Console rejected the previous `com.homelandadvantage.cp67` since the listing was created under `Fundle`). Same signing key reused so future updates work. Updated `assetlinks.json` to match the new package name and republished it under `/app/frontend/public/.well-known/` on preview. **Production needs a redeploy** for the new assetlinks.json + new download files (`/downloads/cp67-mall.aab` and `/downloads/cp67-mall.apk`) to go live at `cp67bot.fundlexperiences.com`.

## Recently Fixed (May 7, 2026 - Session 7)
- **Users CSV Export**: New "Export CSV" button in admin Users page. `GET /api/export/users` now also accepts `source` and `search`, and returns separate `joined_date` / `joined_time` (IST) columns instead of a raw ISO timestamp.
- **Parking CSV Export**: New "Export CSV" button in admin Parking Report. `GET /api/export/parking` now merges `parking_sessions` + `parking_coupons` (matches the live UI report) and outputs separate `entry_date` / `entry_time` / `exit_date` / `exit_time` (IST) columns plus `type` (Session / Free Coupon), `exit_gate`, `scanned_by`. Parking-staff users see only their gate; admin sees both.
- **Bulk Block from Excel/CSV**: New `POST /api/admin/blocked-users/bulk-upload` (multipart) accepts `.xlsx` or `.csv` with auto-detected columns (`Brand Name`, `Staff Name`, `Designation`, `Contact No.`). Phones normalised to last 10 digits, dedupes within file and against existing entries. Admin BlockedUsers page now has an "Upload Excel / CSV" card with file picker + result summary (parsed / unique / newly_blocked / already_blocked / enriched_existing).

## Recently Fixed (April 29, 2026 - Session 6)
- **Brand staff blocklist enrichment + verification**: Re-imported the latest `Brand Staff Details (1).xlsx` (1050 unique 10-digit phones). All numbers were already in `blocked_phones` (carry-over from earlier 1050 import), so no duplicates created. Existing minimal records (`reason: 'brand_staff'`) were enriched with `brand`, `staff_name`, `designation`, `source_file` so the admin BlockedUsers page now shows who each phone belongs to. Confirmed enforcement live on `/api/consumer/auth/send-otp` (HTTP 403 for blocked phone, 200 for unblocked).
- **Admin BlockedUsers UI**: Added "Brand / Staff" column showing brand · staff name · designation. Admin search now matches phone OR brand OR staff name (case-insensitive).

## Recently Fixed (April 28, 2026 - Session 5)
- **Invoice mobile-number mismatch check**: OCR now extracts `customer_mobile` from the bill. If the invoice prints a mobile number that does not match the uploader's WhatsApp/app number (last-10-digit comparison, country codes & spaces stripped), the bill is routed to admin review with `rejection_reason="Mob No not matched with Invoice"` and `invoice_mobile` stored. Applies to both Consumer App (`POST /api/consumer/bills/upload` → `process_bill_ocr`) and WhatsApp (`process_bill_image`). If no customer mobile is on the invoice, processing continues normally with the uploader's number. Admin Bills page shows the mismatch reason with both numbers side-by-side.

## Recently Fixed (April 26, 2026 - Session 4)
- **Android TWA / APK generated**: `/app/twa-build/app-release-signed.apk` & `app-release-bundle.aab` (1.2 MB / 1.3 MB). Package `com.homelandadvantage.cp67`, version 1, signed with `android.keystore` (alias `android`, password `CP67Mall@2025`).
- **Bubblewrap bootstrap**: `/app/twa-build/bootstrap.js` generates `twa-manifest.json`, project files, checksum, and signing key non-interactively. Build via `bubblewrap build --skipPwaValidation` with `BUBBLEWRAP_KEYSTORE_PASSWORD` / `BUBBLEWRAP_KEY_PASSWORD` env vars.
- **ARM64 build host workaround**: Wrapped `aapt`, `aapt2`, `aidl`, `zipalign`, `dexdump`, `split-select`, `bcc_compat`, `llvm-rs-cc` (build-tools/34.0.0) and the gradle-cached `aapt2-8.9.1-12782657-linux/aapt2` with shell scripts that delegate to `qemu-x86_64-static` (`/usr/x86_64-linux-gnu` ld prefix).
- **Digital Asset Links**: SHA-256 fingerprint `32:BF:48:D0:63:E1:4C:64:26:7B:59:1B:45:50:97:AE:46:F1:8F:E9:EE:35:4C:B6:BE:BB:03:23:5C:31:40:5E` published at `/.well-known/assetlinks.json` (frontend public/) — verified live at the preview URL.

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
