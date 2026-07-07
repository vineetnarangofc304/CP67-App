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

## Recently Fixed (Jun 17, 2026 - Session 18) — TWA URL Bar
- **TWA showed Chrome address bar despite earlier assetlinks fix**: Root cause was Google Play App Signing — when you upload the AAB, Google re-signs the installed app with their own signing key. The installed app sends Google's SHA-256, not ours. Added Google's Play App Signing SHA-256 (`30:82:31:A1:0B:C8:3E:AA:CC:9A:8C:5E:E0:4F:CA:77:9D:2F:00:6D:57:15:85:8E:F7:5B:5A:12:EE:E9:74:0A`) to `assetlinks.json` alongside our upload-key SHA. Both fingerprints now in the file — sideloaded APK + Play-Store-installed app both verify. Requires production redeploy + clearing app storage on the test device.

## Recently Fixed (Jun 17, 2026 - Session 17) — Reprocess False-Failure
- **"Failed to reprocess bill" toast was showing even when reprocess succeeded** (Reliance Trends bill in screenshot was already approved with +9532 pts, tagged `admin_reprocess`, but toast still said failed). Two root causes:
  - Backend: reprocess was re-uploading the 180 KB base64 bill image to Fundle on every retry, adding 20–30s of latency on a flaky remote → response often arrived after Cloudflare/ingress cut the connection. **Removed the image attachment from reprocess** — Fundle already has it from the original upload. Request payload drops from ~180 KB → ~1 KB.
  - Frontend: `fetch().json()` would throw → the catch block displayed a generic "Failed to reprocess bill" toast that didn't reflect the actual backend state. **Migrated to XMLHttpRequest** with explicit `onload`/`onerror`/`ontimeout` handlers, 90s timeout, and an "always refresh" pattern — even on a perceived failure, the list refetches to show the real status. Error messages now distinguish "Fundle slow" vs "actual error" vs "network hiccup".

## Recently Fixed (Jun 15, 2026 - Session 16) — PRODUCTION PERF EMERGENCY
- **Bills section + Admin "billion years to reload"** root cause: each bill carried a **180 KB inline base64 `image_url`** in the `/api/bills` and `/api/bills/pending-review` responses. A 50-bill page = ~10 MB transferred. `/pending-review` was returning HTTP 500 on prod (likely BSON 16 MB doc limit blown by `$project` retaining all images).
  - **Backend**: Both list endpoints now exclude `image_url` and `ocr_raw_data`. New `/api/bills/{id}/image` for on-demand fetch. Production responses should drop from ~10 MB → ~50 KB.
  - **Frontend**: Pending bill card and All Bills row thumbnail now show a "Click to view bill image" placeholder. Clicking opens the review dialog which lazy-loads the image via `/bills/{id}/image`.
  - **Result on preview**: `/api/bills?limit=50` = **0.14s** (was 7.5s on prod), `/api/bills/pending-review` = **0.13s** (was 500 on prod).
- **"Failed to reprocess" comes very often** root cause: `/api/bills/{id}/reprocess` made up to 4 sequential TagnPay calls (60s timeout each) → up to 240s wall time → Cloudflare 524 → toast.
  - Tightened `TagnPayClient.earn_points` timeout from 60s → **25s**.
  - Removed the redundant 2nd `get_customer_points` call after a successful `earn_points` (we already know the points earned + the local balance was just incremented).
  - WhatsApp success message moved to background — admin response returns immediately on success.

## Recently Fixed (Jun 11, 2026 - Session 15)
- **OTP input box count fixed (4 → 6)**: Karix SMS sends a 6-digit OTP per the DLT-approved template, but the consumer login UI only had 4 boxes — users could not enter the 6th digit. Expanded `consumer/pages/Login.jsx` to 6 boxes, narrowed the box width (44px) so it fits on small phones, added paste / SMS-autofill handling (paste a 6-digit code into any box and it auto-distributes), kept the 4-digit dev bypass (`1234`) working. CSS updated.

## Recently Fixed (Jun 10, 2026 - Session 14)

Two User-report issues from the screenshot:

- **Case 1 — Blank Source column fixed (forwards + backwards)**:
  - When users register via WhatsApp **without** a recognised QR-tagged message, the system was storing `first_touch_source=None`. Now defaults to `"SRC_WHATSAPP"` at all 3 user-creation sites (QR registration flow, parking QR flow, generic webhook message creation).
  - Startup backfill upgraded — splits existing blank-source users into `SRC_APP` (if `app_registered=true`) or `SRC_WHATSAPP` otherwise.

- **Case 2 — "Pending" status fixed**:
  - Root cause: `kyc_status` was set to `True` only when TagnPay/Fundle remote registration succeeded. For users with unusual phone formats (e.g. Australian `61...`), Fundle rejected them → `kyc_status=False` → UI showed "Pending" even though the user was fully functional in our system.
  - Decoupled local registration from TagnPay sync: `kyc_status=True` the moment a user engages with CP67. TagnPay sync status now tracked separately in `fundle_registered` field (added to `UserData` model).
  - Startup backfill flips any existing `kyc_status=False/missing` to `True`. All 3 WhatsApp user-creation sites + consumer app verify-otp now set `kyc_status=True` directly.

**Tested on preview**: All 7 users show "Registered", all have non-blank source (`SRC_APP × 6, SRC_MARKETING × 1`). New user via `?src=SRC_BRANDS` correctly tagged.

**Lint clean** (backend & consumer).

## Recently Fixed (Jun 6, 2026 - Session 13)

Three production issues + a critical perf fix:

- **OTP delay during app login fixed (was 20s, now 0.2s)**: Karix SMS endpoint occasionally takes 30+ seconds. Both the Karix SMS send AND the TagnPay sync now run as FastAPI `BackgroundTasks` — the OTP response returns immediately. OTP is still stored in `otp_codes` collection before the response so verify-otp works deterministically even if SMS takes a few extra seconds to land.
- **"Source" column blank in User report fixed**: When users registered through the SMS-OTP App flow (not WhatsApp), `first_touch_source` was never set. Now (a) consumer login accepts `?src=` / `?qr=` query params from the URL (e.g. marketing campaign QR landing pages), preserved in localStorage across the OTP step, (b) defaults to `SRC_APP` if no source provided, (c) one-time backfill on startup tagged 6 existing legacy users with `SRC_APP`. Added internal `SRC_APP` pseudo-QR (`internal: true`, hidden from public QR endpoints).
- **Admin login "body stream already read" error fixed**: On production behind Cloudflare, `fetch()` would mark the response body as already-read for non-200 responses. Migrated admin login + token-validation to `XMLHttpRequest` (same pattern as consumer login). Wrong password now shows clean "Invalid credentials" toast.
- **Cleaned up pre-existing lint debt**: Removed duplicate `Lakme Salon` dict key, unused locals (`current_month`, `not_found`, `pan`, `now`), bare `except:` → `except Exception:`, redefined `get_whatsapp_logs` (deleted the dumber second copy), 4 unused f-strings. Backend lint is now clean.

## Recently Fixed (Jun 4, 2026 - Session 12)
- **Karix SMS DLT entity ID configured**: `KARIX_SMS_DLT_ENTITY_ID=1701172802304667512` (Principal Entity ID) added to `/app/backend/.env`. Karix HTTP API call now passes both `dlt_entity_id` and `dlt_template_id=1707172914885560615` so SMS should land on real handsets via Implicit DLT route. Header `CP67`, template `Your verification OTP is {#var#} Use this at CP67 Mall.`
- **Phone masking for parking gate staff**: In `/api/parking/sessions` and `/api/export/parking`, when the JWT belongs to `parking1` or `parking2` (gate set), `user_phone` is masked as `XXXXXX0001` (last 4 digits visible). Admin still sees full numbers — this is JWT-claim based, no UI changes needed. Tested with both admin and parking1 logins.

## Recently Fixed (Jun 2, 2026 - Session 11)
- **Production backend slowness root-caused & fixed**: Production `/api/analytics/dashboard` was timing out at 20s → HTTP 500. Same for `/api/bills?limit=20`. Cause: 20 sequential `count_documents` queries on un-indexed collections (heavy collection scans at scale).
  - **Parallelised** the analytics dashboard with `asyncio.gather()` — all 22 counts run concurrently
  - **Added 30 DB indexes** via new `ensure_db_indexes()` on startup (idempotent, defensive per-index): `users.phone/phone_10/loyalty_id/created_at/customer_type/first_touch_source/kyc_status`, `bills.created_at/status/user_id/user_phone + compound (status, created_at)`, `whatsapp_logs.{created_at,direction,user_phone}`, `parking_sessions.{entry_time,status,user_phone,exit_gate}`, `parking_coupons.{coupon_code,user_phone,status,created_at,exit_gate}`, `blocked_phones.phone`, `otp_codes.{phone,expires_at}`, `whatsapp_dedup.ts`, `qr_analytics.qr_code_id`, `footfall.date`
  - **Preview results** (small data, expected fast): dashboard 0.12s, bills 0.15s
  - **Production impact** (large data, the actual fix): once redeployed, the indexes will be auto-created on first boot, and the parallel dashboard should drop from 20s+ → under 1s

## Recently Fixed (May 30, 2026 - Session 10)
- **Real SMS OTP via Karix HTTP API**: Consumer login OTP now sends a real SMS instead of relying on TagnPay. Generates a 6-digit OTP locally, stores it in `otp_codes` collection with 5-min expiry + max-5-attempt lockout, and sends via Karix `QueryStringReceiver` endpoint (`https://pod2-japi.instaalerts.zone/httpapi/QueryStringReceiver`) using sender ID `CP67`. DLT-approved template: `Your verification OTP is {OTP} Use this at CP67 Mall.`
- **Dev bypass**: OTP `1234` (`OTP_DEV_BYPASS` env var) still works for QA / testing agent / sideload tests.
- **`/api/consumer/auth/verify-otp`** no longer hits TagnPay for verification — uses the local stored OTP. TagnPay sync still happens in `send-otp` (best-effort, non-blocking).
- **New env vars** in `/app/backend/.env`: `KARIX_SMS_API_URL`, `KARIX_SMS_API_KEY`, `KARIX_SMS_SENDER_ID`, `KARIX_SMS_DLT_ENTITY_ID`, `OTP_DEV_BYPASS`.
- **Tested**: Karix returned `Statuscode=200 & Platform Accepted` for the test sends. Dev OTP `1234` returns JWT token. Wrong OTP returns 400.

## Recently Fixed (May 15, 2026 - Session 9)
- **Marketing Campaign QR**: New QR (`QR0124008`, source `SRC_MARKETING`, location `Marketing Campaign`) with prefilled text `"I want to register in CP 67 Loyalty Program Homeland Advantage"`. Added `clean_text` flag to QR_CODES — when true, the `wa.me` link drops the visible `| SRC_X` tracking suffix so the message users see in WhatsApp is clean for external advertising. Source attribution still works via the existing `MESSAGE_TO_SOURCE` map. Other QRs unchanged (backward-compatible). Added shared `_build_wa_link(qr)` helper to centralise link construction.
- **Bill Management date filter**: `/api/bills` now accepts `start_date` and `end_date` (ISO strings, end inclusive to end-of-day). Admin Bills page "All Bills" tab now has two `<input type="date">` pickers + a "Clear dates" button that works alongside the status filter.

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

## Phase 16 (Current Session - Feb 21, 2026) — CP67 Team Feedback Fixes

### Backend
- **Bulk Reprocess Failed Bills** (`POST /api/admin/bills/bulk-reprocess`): admin-only date-range endpoint that re-runs OCR on stored images for bills stuck in `manual_review`/`pending_review`, re-applies all rules (15-day age, blocklist, mismatch, brand check), pushes to TagnPay, and notifies customers on success. Supports `dry_run=true` for safe preview. Idempotent (no double-credit).
- **Consumer JWT TTL: 30d → 90d** in `routes/consumer.py:create_consumer_token` — addresses CP67 feedback "users have to OTP every reopen".
- **Resilient profile fetch** in ConsumerApp: only clears token on 401/403, NOT on 5xx/network errors (root cause of phantom logouts).
- **Web Push subscription endpoints** (`/api/consumer/push/{subscribe,unsubscribe,status}`): stores Web Push subscriptions for future FCM-based delivery. Idempotent upsert on endpoint.

### Frontend (Admin)
- New "Bulk Reprocess" button on `/bills` opens a dialog with date pickers, "Re-run OCR" + "Send WhatsApp on approval" toggles, "Preview Candidates" (dry-run) and "Run Reprocess" actions, with a result summary panel.

### Frontend (Consumer PWA)
- **Service Worker** (`/public/sw.js`): push + notificationclick handlers ready (delivery requires VAPID/FCM keys).
- **NotificationPrompt** modal: first-launch friendly prompt requesting notification permission; on grant, auto-subscribes the device. Falls back to a PWA install guide modal (iOS Safari + Android Chrome variants) when the user isn't running in standalone mode.

### TWA (Android v1.1)
- AndroidManifest now requests `android.permission.CAMERA`, `android.permission.POST_NOTIFICATIONS`, `android.permission.INTERNET` and declares optional camera features so the in-app bill capture works on Android.
- Bumped `appVersionCode=2`, `appVersionName="1.1"` — requires rebuild via `./gradlew bundleRelease`.

## Phase 17 (Feb 7, 2026 — this session) — Campaign Engine + PWA Install Guide

### Backend — Campaign-Aware Bill Processing
- `apply_campaign_bonus(bill_amount, base_points, store_name, is_first_bill)` helper in `/app/backend/server.py` (~line 503). Reads `db.campaigns` (active, in-date-range, min_spend ok, category/brand filters, campaign_type). Returns `{final_points, bonus_points, applied_campaigns[]}`.
- Wired into every bill-approval path: WhatsApp auto-approve (`process_bill_image`), admin approve (`process_bill`), single reprocess (`reprocess_bill`), and bulk reprocess (`_reprocess_single_bill`). Fundle's base points are the ground truth; multipliers/bonuses are added on top and stored in `bills.campaign_bonus` + `bills.applied_campaigns`. WhatsApp success messages now show `Bonus: +X pts (Campaign Name)` line when applicable.
- Consumer in-app bill upload (`/api/consumer/bills/upload` -> `process_bill_ocr` in `routes/consumer.py`) also applies campaign bonus and increments user balance for the delta.
- New public endpoint `GET /api/consumer/campaigns/active` — filtered date-window active campaigns for consumer UI display (no auth).
- Fixed `/api/admin/campaigns/active`: date-only strings (`YYYY-MM-DD`) are now padded to full-day window for correct comparison (previously excluded a campaign ending today).

### Frontend — PWA Install Guide
- New `/app/frontend/src/consumer/components/PWAInstallGuide.jsx` exporting `PWAInstallGuideModal` + `PWAInstallBanner`.
- **PWAInstallBanner** (mounted from `ConsumerApp.jsx` when `token` is set): a subtle, non-intrusive pill anchored above the bottom nav. Only appears when NOT in standalone mode and localStorage flag not set. 3.5s delay so it doesn't compete with page-load animations. "How" opens the modal; X permanently dismisses.
- **PWAInstallGuideModal**: iOS Safari steps, Android Chrome steps (with native `beforeinstallprompt` "Install Now" button when available), and Desktop steps.
- SideDrawer has a new "Install App" menu item (only visible when not in standalone) that opens the same modal — users can always find the guide from the drawer even after dismissing the banner.
- Admin Bills page now shows "incl. +X campaign" line under points when a bill was boosted by a campaign.

### Testing
- 15/15 backend + 100% frontend PWA install flows passed (iteration_26).
- Test file: `/app/backend/tests/test_iteration26_campaigns_pwa.py`

## Pending / Next
- (P0) BLOCKED: Android WebView camera bug (Point 5) — awaiting user detail on exact symptom.
- (P2) Refactor `server.py` (~7176 lines) into `/routes/admin_bills.py`, `/routes/admin_campaigns.py`, `/services/ocr.py`, `/services/tagnpay.py`, `/utils/campaigns.py` (extract duplicate campaign helper from consumer.py + server.py).
- (P2) Brand/Store separate dashboard.
- (P2) Automate footfall data via email parser.
- (P2) Advanced Analytics: RFM, CLV, AI Concierge.

## Upcoming Tasks (P1)
- Campaign-aware bill processing: Auto-apply multipliers during active campaigns
- Web Push delivery: configure VAPID keypair + Firebase project; add backend send endpoint
- Native "Settings" deep-link from TWA so users access app settings instead of Chrome's

## Future Tasks (P2)
- Automate Footfall Data via Email Parser
- **Refactor monolithic server.py** (6700+ lines → `/routes/admin_bills.py`, `/services/ocr.py`, `/services/tagnpay.py`)
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
