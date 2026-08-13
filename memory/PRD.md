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

## Phase 24 (Aug 1, 2026 — CP67 Doc Pending Points 17-19)

### Point 17 — "Network error while editing brand" ✅
- **Root cause**: `submitFixBrand` in Bills.jsx used `fetch()` — Cloudflare's edge occasionally marks the response body as already-read on production, `res.json()` throws → catch block fired the generic "Network error while editing brand" toast even when the backend had queued the edit successfully.
- **Fix**: Migrated `submitFixBrand` to `XMLHttpRequest` (same pattern as admin login / consumer login fixes in earlier sessions). Explicit `onload`/`ontimeout`/`onerror` handlers with backend-state-honest messaging ("Refreshing the list…" instead of a hard error). Timeout dropped from 20s → 25s and no longer surfaces AbortError.

### Point 18 — "Failed to process Bill" on reject ✅
- **Root cause (backend)**: `process_bill(action='reject')` made TWO synchronous Fundle calls: `log_rejected_bill` (up to 25s) + `get_customer_points` (up to 25s). Combined 50s+ wall time → Cloudflare 524 → "Failed to process bill" toast.
- **Fix (backend)**: Moved `log_rejected_bill` to `background_tasks` and removed the redundant `get_customer_points` — use local `users.balance_points` (already denormalised) for the WhatsApp reject message. Reject latency dropped from **~5s → 0.11s** on preview.
- **Fix (frontend)**: Migrated `processBill()` to XHR — same reasoning as Point 17. Explicit 60s timeout with "your action was submitted — refreshing" instead of a hard error.

### Point 19 — WhatsApp bill not showing in admin panel ✅
- **Root cause**: `process_bill_image` had TWO exit paths that sent "trouble processing your bill" / "unclear image" to the customer but **never inserted a bill record**:
  1. `if not image_base64` branch when Karix's `fileLink` fails to download (auth mismatch, etc.).
  2. The outer `except Exception` handler for any OCR / Fundle / decode error.
- Result: customer got a "manual review" promise, admin panel showed nothing, bill was lost.
- **Fix**: Both branches now `db.bills.insert_one(...)` a `manual_review` stub carrying whatever we have (base64 → data-URL image_url, else the raw Karix URL). Admin sees the bill in Pending Review, can view/reprocess/reject like any other bill. `rejection_reason` field carries the exact backend error for triage.


**Backend** (`/app/backend/routes/staff.py` + wiring in `server.py`)
- **Data models** (Mongo collections): `retail_staff`, `staff_config`, `staff_incentives`, `staff_attributions`, `staff_redemptions`, `staff_otps`.
- **Admin endpoints** (`/api/admin/staff/*`, JWT-protected):
  - `POST /` — onboard staff (name, phone, brand_name, store_location, email) → auto-generates human-readable `staff_code` (HL-XXXX) + `qr_token`.
  - `GET /` — list with `?active_only` and `?brand` filters.
  - `PATCH /{id}` — update or activate/deactivate.
  - `GET /{id}/qr` — returns wa.me deep-link with prefilled `#STAFF:<token>` message + base64 QR PNG.
  - `GET /config/current` + `PUT` — configurable slabs, attribution window, registration validity.
  - `GET /metrics/overview` + `GET /leaderboard?period=daily|weekly|monthly|all`.
  - `GET /redemptions` + `PATCH /redemptions/{id}` — admin lists + settles (`settled`/`rejected`) with payout_ref.
- **Staff endpoints** (`/api/staff/*`, JWT staff-role):
  - `POST /auth/send-otp` — silent success if phone unknown; 6-digit OTP stored + sent via existing Karix SMS (`send_otp_sms`), dev-bypass `1234` from `OTP_DEV_BYPASS`.
  - `POST /auth/verify-otp` → JWT (30-day) with `role=retail_staff`.
  - `GET /me`, `GET /dashboard`, `GET /incentives`, `GET /qr`, `POST /redeem`, `GET /redemptions`.
- **Attribution Engine**:
  - Regex `#STAFF:([A-Z0-9]+)` parsed on every WhatsApp inbound.
  - When customer sends the QR-prefilled message → `open_attribution_window` (15 min).
  - If user is NEW → `create_registration_incentive` (pending; activates on first approved bill).
  - `create_or_activate_bill_incentive` creates a `bill_upload` incentive when a bill is uploaded within the active window.
  - `sync_incentive_on_bill_status_change` syncs status (approved → redeemable, rejected → cancelled).
- **Hooks wired** (5 sites): `process_bill_image` (WhatsApp), `process_bill` (admin approve/reject), `_reprocess_single_bill` (approved + force-credit paths), consumer `process_bill_ocr`.
- **Slab defaults** (admin can tune from UI): Registration 4-tier (₹50/75/100/150), Bill Upload 3-tier (₹20/30/50), 15-min attribution window, 60-day registration validity.

**Frontend Admin** — `/staff-incentives` (`/app/frontend/src/pages/StaffIncentives.jsx`)
- 4 KPI cards + 4 tabs (Staff / Leaderboard / Redemptions / Slabs) with Add Staff dialog and QR modal (base64 PNG viewer).

**Frontend Staff Mini-App** — `/staff-app/*` (`/app/frontend/src/staff/`)
- Fully separate visual identity from consumer (light-cream luxury) and admin (light corporate) — deep navy + amber/violet gradient dark theme with glass topbar and floating tab bar.
- Own `StaffAuthProvider` (isolates from admin auth so `/staff-app` does not redirect to `/login`).
- Pages: `StaffLogin` (phone + 6-OTP with paste-autofill), `StaffDashboard` (Total Earned + Next-slab rate + How-to-earn), `StaffQR` (Share + Copy + prefilled msg), `StaffIncentivesList` (chip-based status), `StaffRedeem` (balance + request + history).

**Testing**
- iteration_33: 12/12 backend + 100% frontend. Files: `/app/backend/tests/test_point19_staff.py`.

## Phase 23 (Feb 8, 2026 — part 7) — Point 19: Retailer Staff Incentive Platform ✅

(moved above; kept anchor here for CHANGELOG legibility)

## Phase 22 (Feb 8, 2026 — part 6) — Point 11 (unified upload) + Point 16 (bill_no dedup)

### Point 11 — Unified base64 bill upload ✅
- **Fix**: `BillUpload.jsx` uses `FileReader.readAsDataURL` → POST JSON `{image_base64}` to `/api/consumer/bills/upload-base64` for ALL clients (browser + WebView).
- Backend `upload_bill_base64` strips optional `data:...;base64,` prefix, decodes, delegates to shared `_handle_bill_upload_bytes`.

### Point 16 — Invoice-number dedup ✅
- `normalize_bill_no(s)` strips `[^A-Za-z0-9]+` and lowercases; `bill_no_normalized` auto-filled on every insert.
- Compound index `(user_id, store_name, bill_no_normalized)` added.
- Consumer OCR path rejects duplicates and notifies user.

## Phase 21 (Feb 8, 2026 — part 5) — Batch: Points 10–15 (iteration_29, 17/17 backend + 100% frontend)

### Point 10 — Bulk June bills auto force-credit ✅
- Added `force_credit_on_fundle_reject` flag to `_reprocess_single_bill` + `BulkReprocessRequest`. When Fundle rejects a bill with brand-mismatch/0-points, the function auto-falls-back to `_compute_auto_points` (tier × amount) and marks `force_credited=true`.
- **Admin UI**: Bulk Reprocess dialog now has "Auto force-credit if Fundle rejects" checkbox (data-testid=bulk-force-on-reject), default CHECKED.

### Point 11 — In-app bill upload fixed ✅
- Root cause: multipart FormData uploads are unreliable in older Android WebViews. Added parallel endpoint `POST /api/consumer/bills/upload-base64` that accepts JSON `{image_base64}` (data-URL OR raw base64).
- **Consumer app**: `BillUpload.jsx` detects Android WebView via `hasNativeCamera` and routes uploads through the JSON endpoint. Browser continues to use multipart.

### Point 12 — WhatsApp bill force-credit fallback ✅
- Global admin toggle `auto_force_credit_on_fundle_reject` in app_settings. When enabled, WhatsApp/in-app auto-approved bills that Fundle rejects with brand-mismatch are automatically credited locally + user balance incremented + WhatsApp success message sent.
- **Admin UI**: `/app-settings` page now has an "Automation: Fundle Rejection Fallback" section with the toggle.

### Point 13 — Nightly Fundle registration sync ✅
- APScheduler (added to `requirements.txt`) runs `run_registration_sync_job` daily at **1:00 AM IST** (`Asia/Kolkata`). Idempotent — skips users already on Fundle. Logs each run to `db.sync_jobs`.
- **Admin UI**: `/fundle-sync` "Run Nightly Sync Now" button for manual testing.

### Point 14 — Legacy 154 numbers one-time sync ✅
- Hardcoded list of 154 phone numbers from doc. `POST /api/admin/sync/legacy-154?include_bills=true` queues background job that per-user: registers on Fundle if missing, then re-runs stuck bills through `_reprocess_single_bill`. Progress polled via `GET /api/admin/sync/status/{job_id}`.
- **Admin UI**: `/fundle-sync` page with progress bar showing processed / registered / already / failed / bills_synced / bills_failed counters.

### Point 15 — RWA + Office QR codes ✅
- Added `QR0124010` (source_code `SRC_RWA`) and `QR0124011` (source_code `SRC_OFFICE`) to `QR_CODES`. Consumer login flow already captures `?src=` from URL and persists as `first_touch_source` on user doc — no additional wiring needed.
- Both QR codes generate WhatsApp deep links with the source tag baked in. Admin can generate QR PNGs via existing `GET /api/qr-codes/{id}/generate`.
- Filter users by source via `GET /api/users?source=SRC_RWA` (already exists).

### New Files
- `/app/frontend/src/pages/FundleSync.jsx`
- `/app/backend/tests/test_iteration29_batch.py`

## Phase 20 (Feb 8, 2026 — part 4) — Point 3 real fix + Point 9 App Settings

### Point 3 — Force-Credit fallback now ACTUALLY works
- **Previous bug**: My phase-18 fix passed `force_credit=True` to `_reprocess_single_bill`, but the flag was defined in the signature and never USED in the function body — it just re-called Fundle, producing the same rejection.
- **Fix**: Added the actual `force_credit` branch at line ~3237 of `server.py`. When set, the function SKIPS Fundle `earn_points` and instead uses `_compute_auto_points(amount, store_name)` (tier × amount earn-rate). Persists `force_credited=true`, `force_credit_rate_pct`, `force_credit_category` on the bill.
- Now when admin fixes a brand + Fundle still rejects with brand-mismatch, the endpoint auto-force-credits locally. Verified end-to-end (iteration_28, 14/14 backend tests).

### Point 9 — Admin-configurable app fonts
- **Backend**: `GET/PUT /api/admin/app-settings` (admin auth) + `GET /api/consumer/app-settings` (public). Fields: `heading_font_family`, `heading_font_size_scale`, `heading_font_weight`, `content_font_family`, `content_font_size_scale`, `content_font_weight`. Scale clamped 0.6–2.0, weight 100–900.
- **Frontend Admin**: New `/app-settings` page with per-heading/per-content controls, live preview blocks, save + reset buttons.
- **Consumer PWA**: `ConsumerApp.jsx` calls `applyAppSettings()` on mount + every 5 min. Lazy-loads non-default Google Fonts (Playfair Display, Manrope, Outfit, Inter, Poppins, Roboto, Merriweather, Georgia, Cormorant Garamond) via injected `<link>` tags. Sets CSS variables `--font-heading`, `--font-body`, `--font-heading-scale`, `--font-body-scale`, `--font-heading-weight`, `--font-body-weight`. `consumer.css` now scales H1/H2/H3/H4 via the heading scale and uses `zoom` for body scale (avoids em-cascade compounding).

### Testing
- iteration_28: 14/14 backend + 100% frontend. Both Point 3 and Point 9 verified.
- File: `/app/backend/tests/test_point3_and_appsettings.py`

## Phase 19 (Feb 8, 2026 — part 3) — Camera "first tap fails" fix → v1.10

### Point 8b: First-tap camera race fixed
- **Problem**: On v1.9 APK, first "Open Camera" tap → "Camera unavailable" error. Second tap works.
- **Root cause**: `launchNativeCamera()` was calling `requestPermissions(CAMERA)` AND `startActivityForResult(ACTION_IMAGE_CAPTURE)` back-to-back. On MIUI/Xiaomi/OnePlus devices the permission dialog steals focus → camera intent dismissed → `RESULT_CANCELED` → error toast. Second tap works because permission is already granted.
- **Fix**: Split into `launchNativeCamera()` (checks permission — if missing, sets `pendingBridgeCameraLaunch=true` and requests) and `launchNativeCameraNow()` (actually fires the camera intent). `onRequestPermissionsResult()` now checks the flag and invokes `launchNativeCameraNow()` after the user grants permission. Denials call `__cp67OnCameraError('permission_denied')` with a helpful "enable in Settings" message.

### v1.10 Artefacts
- `versionCode=11`, `versionName="1.10"`, `application-label="Homeland Advantage"`
- `/app/twa-build/app-release-bundle.aab` (2.65 MB) → Play Console
- `/app/twa-build/app-release-signed.apk` (2.81 MB) → sideload
- Public: `/downloads/cp67-v1.10.aab`, `/downloads/cp67-v1.10.apk`, `/downloads/cp67-mall.{aab,apk}`

### Testing
- Iteration 27: 6/6 frontend scenarios + 3/3 backend regressions PASS. JS bridge contract verified end-to-end from browser.

## Phase 18 (Feb 8, 2026 — this session part 2) — CP67 Feedback Doc v3 (v1.9)

Addressed 4 pending items from the user's Google Doc:

### Point 3: "Fix Brand" → auto-force-credit fallback
- **Problem**: Admin picks correct brand from Fundle-master dropdown → reprocess still shows "Brand does not match" because our local `db.brands` list has drifted from Fundle's actual master.
- **Fix**: `/api/admin/bills/{bill_id}/edit-brand` now auto-falls-back to LOCAL force-credit (tier × amount earn-rate) when Fundle still rejects with brand-mismatch after the correction. Admin has already visually verified the bill, so no fraud risk. Frontend toast now says: `Brand fixed → "X". Fundle rejected but auto force-credited N pts locally.`
- **Payload flag** `auto_force_credit_on_fundle_reject` (default `true`) for opt-out.

### Point 6: App renamed to "Homeland Advantage"
- `build.gradle` → `name` and `launcherName` changed from "CP67 Mall" to "Homeland Advantage".
- `application-label` verified: `Homeland Advantage` in the built APK.

### Point 7: Removed "Install CP67" bottom banner
- `PWAInstallBanner` un-mounted from `ConsumerApp.jsx`. Users can still install via SideDrawer → "Install App" menu item.

### Point 8: Camera opens gallery instead of camera → Native JS Bridge
- **Root cause**: On newer Android WebView builds, `<input type="file" accept="image/*" capture="environment">` is ignored — the system Photo Picker is used instead of the camera.
- **Fix**: Added `AndroidBridge` JS interface via `webView.addJavascriptInterface(...)`. When the web page detects `window.AndroidBridge.openCamera` is available, it calls it directly. Java side launches `MediaStore.ACTION_IMAGE_CAPTURE` with a FileProvider-backed URI, reads the captured JPEG, base64-encodes it, and delivers it back via `window.__cp67OnCameraResult(dataUrl)`. Plain browser users still use the file-input fallback (`hasNativeCamera` check).

### v1.9 Artefacts
- `versionCode=10`, `versionName="1.9"`, `application-label="Homeland Advantage"`
- `/app/twa-build/app-release-bundle.aab` (2.65 MB) — Play Console upload
- `/app/twa-build/app-release-signed.apk` (2.81 MB) — sideload test
- Public: `/downloads/cp67-v1.9.aab`, `/downloads/cp67-v1.9.apk`, `/downloads/cp67-mall.{aab,apk}`

## Phase 17 (Feb 7, 2026 — this session part 1) — Campaign Engine + PWA Install Guide + Camera Crash Fix

### Android v1.8 — CAMERA FORCE-CLOSE FIXED (Point 5) ✅
- **Root cause identified**: `minifyEnabled true` in `app/build.gradle` with NO custom ProGuard rules meant R8 was stripping/obfuscating the WebView anonymous inner-class callback signatures (`onShowFileChooser` + `ValueCallback<Uri[]>`). The app crashed with "internal error / force close" the moment the user tapped the camera/gallery input in the release APK — because the runtime couldn't resolve the callback class.
- **Fix in `/app/twa-build/app/build.gradle`**: `minifyEnabled false`, `shrinkResources false` — this app is < 3 MB, R8 gains nothing but breaks WebView.
- **Belt-and-suspenders**: Created `/app/twa-build/app/proguard-rules.pro` keeping WebView, `ValueCallback`, `FileProvider`, and anonymous inner classes — protects future maintainers if they re-enable minify.
- **Hardened `WebViewActivity.onShowFileChooser`**: catches `Throwable` (not just `ActivityNotFoundException`) on every branch, always releases `fileUploadCallback` on failure so the page doesn't hang, null-safety on `fileChooserParams`.
- **Bumped `versionCode=9`, `versionName="1.8"`**. Built + signed both `app-release-signed.apk` (2.8 MB) and `app-release-bundle.aab` (2.6 MB), also copied to `/app/frontend/public/downloads/cp67-v1.8.{apk,aab}` and `cp67-mall.{apk,aab}`.

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
- (P1) **User action required**: Trigger production redeploy so live users get Point 19 (staff incentives), Point 11, Point 16, campaign engine, Android v1.10, and all other pending fixes.
- (P2) Refactor `server.py` (~7900 lines) into `/routes/admin_bills.py`, `/routes/admin_campaigns.py`, `/services/ocr.py`, `/services/tagnpay.py`, `/utils/campaigns.py`.
- (P2) Brand/Store separate dashboard.
- (P2) Automate footfall data via email parser.
- (P2) Advanced Analytics: RFM, CLV, AI Concierge.
- (P2) Wire Firebase Cloud Messaging on Web Push subscription endpoints.

## Upcoming Tasks (P1)
- Campaign-aware bill processing: Auto-apply multipliers during active campaigns
- Web Push delivery: configure VAPID keypair + Firebase project; add backend send endpoint
- Native "Settings" deep-link from TWA so users access app settings instead of Chrome's

## Future Tasks (P2)
- Automate Footfall Data via Email Parser
- **Refactor monolithic server.py** (8200+ lines → `/routes/admin_bills.py`, `/services/ocr.py`, `/services/tagnpay.py`)
- Brand/Store Dashboard (separate brand login)
- Advanced Analytics (RFM, CLV, AI Concierge)

## Phase 11 (Aug 5-6, 2026) — Bulk Reprocess Recovery + Bill Image + Ops Alerts (Points 19/24/25)
Fixed the three critical items from the client's Google Doc (Points 19, 24, 25):

**Point 19 ✅ (Aug 5)** — Bulk Reprocess was silently skipping bills marked "WhatsApp bill processing failed":
- Auto-force re-OCR when `rejection_reason` starts with "WhatsApp bill processing failed" or "OCR could not extract" — no more silent skips due to caller flag.
- New `no_image` action bucket cleanly separates "image unavailable" from "OCR failed on image" (with specific HTTP/download error in `rejection_reason`).
- Synthetic bill_no auto-generation (`WA-{FIRST8}`) when OCR extracts a valid amount but no bill number — lets Fundle receive a valid earn_points payload.
- Phone-based user fallback (`91XXX` / 10-digit) when `user_id` doesn't match — rescues legacy stubs from user_id drift.
- Admin Bills UI: Bulk Reprocess grids now show 6 counters (Approved / Rejected / Manual / Pending / No image / Skipped).
- Regression suite at `/app/backend/tests/test_bulk_reprocess_whatsapp_failed.py`. Testing agent: 100% pass.

**Point 24 ✅ (Aug 6)** — Bill image was not opening in admin panel:
- `GET /api/bills/{bill_id}/image` now normalizes stored `image_url` into a browser-renderable data: URL:
  - `data:image/...` returned as-is
  - `base64:<b64>` wrapped as `data:image/jpeg;base64,<b64>`
  - `https://` (Karix) fetched server-side with Bearer auth and returned as `data:jpeg;base64,...` (also persisted to skip future round-trips)
- Response includes `fetch_error` when download fails so the admin sees exactly why (e.g. "HTTP 404", "Name or service not known").
- Bills.jsx: image wrapped in `<a target=_blank>` so admin can click-to-open; graceful error placeholder when image can't be loaded.

**Point 25 ✅ (Aug 6)** — Mall-ops alert whenever a bill goes pending/rejected:
- New env `ADMIN_ALERT_PHONES` (default: `9766692497`) + DB override via `db.settings`.
- Admin API: `GET/PUT /api/admin/alerts/config` and `POST /api/admin/alerts/test` for CRUD + test-send.
- Alert dedup via `admin_alerts_sent.<status>` field on bill doc — retries never spam.
- Wired inline alerts on: (a) admin reject via `POST /api/bills/{id}/process`, (b) WhatsApp stub creation (Point 19 fallback), (c) reprocess age-rule rejection.
- Safety-net background scanner runs every 60s to catch any transition path not wired inline.
- Startup backfill: marks all pre-existing bills as `admin_alerts_sent.backfill=<iso>` so the scanner never floods ops with historical bills.
- Bills.jsx: new "Alert Phones" button opens a dialog with number editor + test-send button.
- Regression suite at `/app/backend/tests/test_point24_25_bill_image_and_alerts.py`. Testing agent: 12/12 pass.

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


## Feb 2026 — Client Feedback Points 2, 3, 4, 5 Completed

### Point 2 — Staff QR opens correct WhatsApp number
- Bug: Staff QR used hard-coded fallback `917988077663` (non-existent) making scans show "invalid number" in WhatsApp
- Fix: `WA_BUSINESS_PHONE → WHATSAPP_NUMBER (917347576767) → hard-code` fallback chain in `/api/admin/staff/{id}/qr` and `/api/admin/staff/qr-cards.pdf` and `/api/staff/qr`

### Point 3 — Category-wise & Brand-wise slab config
- Extended `staff_config` schema with `category_slabs` and `brand_slabs` dicts
- Awarding priority: brand override → category (via brands.category lookup) → default
- Admin `/staff-incentives` → Slabs tab now has "Category-wise Slabs" and "Brand-wise Slabs" editors

### Point 4 — Bulk-upload template + Brand Category column
- New endpoint: `GET /api/admin/staff/bulk-import/template.csv` returns CSV with `Mob No, Name of Employee, Brand Name, Brand Category`
- Bulk-import CSV now accepts and forward-fills `Brand Category`. Also auto-upserts new brands into `brands` collection with the given category.
- Admin UI: "Template" button next to "Bulk Import CSV", plus `Brand Category` field in Add Staff dialog

### Point 5 — Retailer / Brand Manager login
- New `retailer_managers` collection (name, phone, brands[], is_active) with admin CRUD at `/api/admin/staff/retailer-managers`
- OTP-based login at `POST /api/staff/retailer/auth/{send-otp,verify-otp}` (issues JWT with role `retailer_manager`)
- `GET /api/staff/retailer/dashboard` returns brand-scoped aggregate (redeemable / redeemed / pending) + staff table + recent redemptions with **zero consumer PII**
- New PWA routes at `/staff-app/retailer/login` and `/staff-app/retailer`
- Admin UI: new "Retailer Logins" tab to whitelist manager phones

## Feb 2026 — Client Feedback Points 5, 6, 7 Completed

### Point 5 — Retailer login (discoverability polish)
- Base flow (whitelist + OTP + brand-scoped dashboard) already shipped in Feb 2026 pass 1.
- Added on top: `/staff-incentives` → Retailer Logins tab now shows the retailer portal URL with **Copy URL** and **Open Portal** buttons, plus a per-row **WhatsApp Invite** button that opens `wa.me/91<phone>` with the portal link pre-filled.

### Point 6 — Friendly "session expired" handling
- Bug: Admin JWT expires after 24h → backend legitimately returned 401 `{detail:"Invalid token"}`. Frontend surfaced that raw detail as a scary toast on bulk-upload.
- Fix: `handle401()` helper in `StaffIncentives.jsx` wired to `doBulkImport`, `downloadTemplate`, `uploadBrandCategoryMapping`, `downloadMappingTemplate` — displays "Session expired — please sign in again" and redirects to `/`.

### Point 7 — Live dropdowns + Brand↔Category mapping upload + "All" scope
- New endpoint `GET /api/admin/staff/catalog/brands-categories` returns distinct brands + categories from the brands collection.
- New endpoints `GET /api/admin/staff/catalog/brand-category-mapping/template.csv` and `POST /api/admin/staff/catalog/brand-category-mapping` (with `dry_run` support) — upload a CSV (`Brand Name, Brand Category`) to bulk update/insert brand→category mappings.
- `OverrideEditor` now uses `<select>` populated from the live catalog instead of free-text; the Category-wise picker includes an **"All (categories & brands)"** option that persists as `__ALL__` in `staff_config.category_slabs`.
- `_resolve_slabs_for_staff()` priority updated: **brand → category → __ALL__ → default**.
- Slabs tab now includes a "Brand ↔ Category Mapping" upload block with Template + Upload buttons, and applies to both Registration Slabs and Bill Upload Slabs.


## Feb 2026 — Client Point 26: Registration Coupon Inventory

### Delivered
- New MongoDB collection `coupon_codes` with schema: `{id, source_code, brand_name, code, value, expiry, status, issued_to_phone, issued_at, created_at}`
- New backend module `/app/backend/routes/coupons.py` with admin endpoints under `/api/admin/coupons/*`:
  - `GET /template.csv` — downloadable CSV template (Brand Name, Coupon Code, Coupon Value, Expiry Date)
  - `POST /bulk-upload` — CSV upload tied to a `source_code` (SRC_RWA, SRC_OFFICE, etc.), supports `dry_run`
  - `GET /inventory?source_code=...` — per-source × brand × status counts + totals
  - `GET /issued?source_code=...` — list of issued coupons with customer phone
  - `GET /list` — filterable list
  - `POST /delete` — bulk-remove available (unissued) coupons
- Atomic issuance helper `issue_coupon_for_registration(phone, source_code)` uses `find_one_and_update` (sort by created_at) so two concurrent registrations can never receive the same coupon.
- Hooked into `process_new_user_registration` in server.py: new customers registering via non-parking / non-generic sources get one coupon popped from inventory and the welcome WhatsApp message is appended with brand, code, value, and expiry.
- New admin UI at `/coupons` (sidebar "Registration Coupons") with source dropdown, KPI tiles, Template + Upload CSV, Inventory + Issued tabs.

### Validation
Strict `^\d{4}-\d{2}-\d{2}$` regex + `date.fromisoformat()` rejects compact ISO (`20281231`), week-date (`2028-W01-1`), malformed, and empty expiry values. Bug testing agent iteration 43 verified 100% backend + 100% frontend, no critical or minor issues.

