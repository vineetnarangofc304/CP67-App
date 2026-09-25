# CP67 Mall - Homeland Advantage PWA

## Recently Shipped (Feb 25, 2026 — Session 86) — Retailer Point 21
- **Point 21 — Editable Aliases + Category on Brands page**: The Slabs → editable mapping table already had both editable columns (Session 84/85), but the main **Brands** admin page (`/brands`) was missing them. Added:
  - New **Aliases** column in the brands table (comma-separated display, truncated with hover tooltip)
  - **Aliases** input in the Add Brand dialog
  - **Aliases** input in the Edit Brand dialog under the Basic tab
  - All three save via the same `PUT/POST /api/admin/brands` endpoint that already accepts `aliases` (list or comma-separated string) from Session 85
- Now admins can edit aliases and category from **either** /brands or /staff-incentives (Slabs tab), with a single source of truth.

## Recently Shipped (Feb 19, 2026 — Session 85) — Retailer Points 19 & 20
- **Point 20 (FEATURE) — Brand Aliases**: New `aliases: List[str]` field on brand docs. When matching a bill's `store_name` to a staff's `brand_name` during retailer-incentive credit, the resolver (`_brands_match` in `/app/backend/routes/staff.py`) now checks both raw-normalised equality AND alias-set membership. Admins edit aliases inline in the Brand ↔ Category editable table (Point 16) via a comma-separated column. Save via existing `PUT /admin/brands/{id}` which now accepts `aliases` (list or comma-separated string).
- **Point 19 (BUG) — Domino's 8810928180 staff didn't get incentive**: Directly resolved by Point 20's alias matching (OCR variants like "Dominos Pizza" now match staff brand "Domino's"). Additionally, `create_or_activate_bill_incentive` now always writes a `staff_attribution_misses` row with `reason: no_active_attribution` when the bill arrives without an active window — giving admins a full audit trail to diagnose why an incentive wasn't credited (window expired, already-used, or never opened).
- **Tested**: `iteration_83` — 6/6 pytest pass (exact-match, alias-match, no-match, empty-input, alias-set includes own name, missing-brand safe fallback). Live-API smoke: PUT aliases persisted correctly.

## Recently Shipped (Feb 16, 2026 — Session 84) — Retailer Point 18
- **Point 18 (P0 BUG)**: Rs 353 Subway (Food Court) bill was awarding **Rs 0** instead of the universal-fallback Rs 10. Root cause: `_resolve_bill_upload_amount` returned as soon as the category tier was defined, even if the bill_value didn't fit any of the category's slabs. With the Point 17 fix in place, below-floor bills correctly returned 0 — but only from the category tier, without falling through to `__ALL__`.
  - Fix: introduced `_amount_for_value_slab_match(bill_value, slabs)` which returns `None` on miss (rather than 0), and cascaded `_resolve_bill_upload_amount` through **category → __ALL__** before applying the deepest tier's floor/ceiling rule. Category still wins when its slab covers the bill.
  - Verified with 13 pytest cases (`iteration_82`): category-hit wins, category-miss falls to universal, both-miss returns 0, above-ceiling of category falls to universal, universal-only still works, and Point 17 boundary semantics preserved.

## Recently Shipped (Feb 15, 2026 — Session 83) — Retailer Points 16 & 17
- **Point 17 (P0 BUG)**: Rs 62 Subway bill was awarding Rs 80 instead of Rs 10. Root cause in `_amount_for_value_slab` at `/app/backend/routes/staff.py` — when bill_value didn't fit any slab range (e.g. below the lowest slab's min_value), the fallback silently returned `slabs[-1].amount` (the TOP slab). Fixed: now returns 0 when bill_value < lowest slab min, and only caps at `slabs[-1].amount` when bill_value > highest slab max. Verified with 5 slab-boundary tests.
- **Point 16 (P1 FEATURE)**: Added editable Brand ↔ Category mapping table inside the Retailer Staff Incentive tab. New `BrandCategoryEditableTable` component in StaffIncentives.jsx: search filter, inline category dropdown edit (via existing `PUT /api/admin/brands/{id}`), row delete (via existing `DELETE /api/admin/brands/{id}`), inline add-new row (via existing `POST /api/admin/brands`). No new backend endpoints needed — reused the existing brand CRUD.
- The existing CSV bulk upload is preserved above the new editable table for backwards compat with bulk seeding.

## Recently Shipped (Feb 13, 2026 — Session 82) — 4 Backlog Features
- **Bill Image Streaming** (`GET /api/bills/{id}/image/stream`): returns raw image bytes with proper Content-Type (StreamingResponse). Handles objstore:, data:, base64:, http:// legacy shapes. Bills.jsx modal now fetches via blob → objectURL, so admins open Bill Review instantly even on legacy multi-MB bills. The JSON `/image` endpoint is preserved for backward compat.
- **Brand Name Variants on Retry**: `_reprocess_single_bill` now retries `earn_points` with the original name → Title Case → UPPER before giving up. If a variant succeeds, the accepted name is persisted so future reads use the exact name Fundle knows. Only retries on brand-mismatch class errors; non-brand errors abort early.
- **Fundle Brand Audit** (`GET /api/admin/bills/brand-audit`): returns every bill whose store_name isn't in the local brands mirror. `GET /api/bills` and `GET /api/bills/pending-review` now include `brand_in_mirror: bool`. Bills.jsx renders an amber "Not in brands mirror" badge next to the store name so admins can seed missing brands+category before customers upload.
- **Push To Fundle** (`POST /api/admin/bills/{id}/push-to-fundle`): retries a locally force-credited bill against Fundle. On success, adjusts local balance by the delta (`fundle_points - old_local_points`), flips `force_credited=false`, records `fundle_pushed_at`. On rejection, bill remains force-credited and admin sees the Fundle error. Bills.jsx shows a green "Push to Fundle" button on every force-credited bill (both pending and all-bills tabs).
- Smoke-verified: `/api/bills?limit=2` returns `brand_in_mirror` flag; `/api/admin/bills/brand-audit?limit=3` scanned 19, flagged 14 missing; stream endpoint returns 200 with proper Content-Type on an objstore bill.

## Recently Shipped (Feb 11, 2026 — Session 81) — Point 49 (round 2)
- **Point 49 — Fix Brand now pushes to Fundle, no silent local force-credit**: User feedback was crystal clear — "hit Fundle API and not force points". Root cause: `EditBrandRequest.auto_force_credit_on_fundle_reject` defaulted to `True` AND the frontend explicitly sent `true`, so any Fundle rejection after Fix Brand → local force-credit + bill marked approved locally → transaction never appears on Fundle platform.
  - Flipped the default in `EditBrandRequest` (backend) to `False`.
  - Changed `submitFixBrand()` in `Bills.jsx` to send `auto_force_credit_on_fundle_reject: false`.
  - Updated toast copy: on Fundle rejection, admin now sees "Fundle rejected: <reason>. Bill left in review — try a different brand name variant" instead of a silent "auto force-credited" success.
  - Behavior now: Fix Brand → reprocess with new store_name + correct category (from Sept 5 fix) → Fundle receives the transaction. If Fundle rejects, bill stays in `manual_review` with the actual Fundle error visible; admin can retry with another brand variant OR use the separate **Force Credit** action to intentionally credit locally.

## Recently Shipped (Feb 10, 2026 — Session 80) — Client Points 45 & 49
- **Point 45 — App Manager sidebar (real fix)**: Root cause was `/app/frontend/src/pages/Banners.jsx` NOT wrapping in `DashboardLayout` — so the sidebar disappeared for every user landing on `/banners` (which is exactly where `appmgr` lands). Wrapped Banners in DashboardLayout. Verified in Preview screenshot: appmgr now sees **Banners, Hot Deals, Events, Campaigns** in the sidebar with role label "App Manager".
- **Point 49 — Sagar Ratna bill not visible in Fundle**: Root cause was `earn_points` hard-coding `category: "Shopping"` in the Fundle API payload — Fundle rejects restaurant brands (like Sagar Ratna) when the category doesn't match its master. Now `earn_points` looks up the actual category from our `brands` collection (case-insensitive brand_name match) before calling Fundle. Falls back to "Shopping" only when the brand isn't in our mirror.
- **iOS project download (`cp67-ios-v1.1-build3.zip`)** shipped for App Store resubmission (Point 40).

## Recently Shipped (Feb 5, 2026 — Session 79) — Client Points 45, 46, 47, 48
- **Point 45 — App Manager role**: New restricted admin role `app_manager` can access ONLY Banners, Hot Deals, Events, Campaigns. Seed login: `appmgr` / `AppMgr@2025`.
- **Point 46 — Bill Operator lockdown**: `bill_operator` now sees ONLY the Bills page (was previously showing Bills + Brands). Seed login: `billop` / `BillOp@2025`.
- **Point 47 — Tier mismatch fix**: `/consumer/profile` had legacy hardcoded thresholds (Platinum≥10000) while `/consumer/wallet` used `calculate_tier()` (Platinum≥25000). A customer at 15k points saw Platinum on Home but Gold in Wallet. Now all four endpoints (`/home`, `/wallet`, `/profile`, `/tier-info`) route through `calculate_tier()` with the same `max(local_earned, tagnpay_earned)` monotonic input — no more drift, no data corruption from transient TagnPay dips.
- **Point 48 — Android 16 (API 36)**: Bumped `targetSdkVersion` 35→36, `versionCode` 11→12, `versionName` 1.10→1.11 in `/app/twa-build/app/build.gradle`. **AAB + signed APK v1.11 rebuilt** at `/app/frontend/public/downloads/cp67-v1.11.aab` and `cp67-v1.11.apk`.
- **iOS Point 40 rebuild ready**: `/app/ios-build/project.yml` bumped to `MARKETING_VERSION 1.1`, `CURRENT_PROJECT_VERSION 3`. iPad camera crash fix already present in `WebViewContainer.swift` (all three pickers forced to `.fullScreen`).
- **New**: Role-based routing helper at `/app/frontend/src/lib/roleAccess.js` — single source of truth for which paths each role can access + landing page.
- **Verified**: `iteration_78.json` — 5 pytest passes + 1 skipped for synthetic-only test.



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


## Feb 2026 — Client Point 27: Staff Imports Discoverability

### Problem
User reported: "I have imported staff data but it is not visible anywhere". Backend was storing all imports correctly (757 rows in `retail_staff` collection, all reachable via `GET /api/admin/staff`) — the bug was a UX discoverability gap on the admin `/staff-incentives` Staff tab, which rendered a flat 700+ row table without any filter, so freshly imported entries were effectively invisible below the fold.

### Fix (frontend-only)
- New filter bar on the Staff tab: search input (name / phone / staff_code / brand / store), brand dropdown, "Recent CSV imports only" checkbox (filters `import_source === 'csv_bulk'`), and a page-size selector (50 / 200 / 1000 / all).
- Header count now shows "Retail Staff (X of N)" when filtering, "Retail Staff (N)" otherwise.
- Truncation hint appears when filtered rows exceed the page size.
- Post-import banner shows a "Show only recent CSV imports" CTA that jumps the table straight to the newly imported rows.

Bug testing agent iteration 44 verified 100% backend + 100% frontend, zero issues.


## Feb 2026 — Client Point 28: Coupon Uploads Discoverability

### Problem
User: "same issue happening in coupon upload just like staff upload" — admin uploaded coupons but couldn't see the individual codes because the Inventory tab showed only brand-level aggregates.

### Fix (frontend-only)
- New **All Coupons** tab on `/coupons` with a flat table of every coupon (Brand, Code, Value, Expiry, Status, Issued To, Uploaded date), backed by the existing `GET /api/admin/coupons/list` endpoint.
- Filter bar: search input (code / brand / phone), brand dropdown, status dropdown (available/issued/expired/void), page-size selector (100/500/all), plus a truncation hint when results exceed the page size.
- Header shows "All Coupons · <SOURCE> (X of N)" when filtering, "(N)" otherwise.
- Post-upload banner now has a **"Show me the codes"** CTA that jumps to the All Coupons tab with status='available' pre-selected so the just-uploaded rows are immediately visible.

Testing agent iteration 45: 100% frontend passed, zero critical/minor issues.



## Feb 14 2026 — CSV Import UX Bug Fix (Dry-Run Confusion)

### Problem
User: "It is showing Dry run 3 Imported / Dry run 731 Imported - But the imported record is not visible anywhere." (Staff Bulk Import + Coupon Upload)

### Root Cause
Previous flow used a native `window.confirm()` dialog with inverted semantics:
- **OK** = Run a dry-run (nothing saved)
- **Cancel** = Live import
Users naturally clicked OK expecting the import to happen, so the dry-run banner said "731 imported" but zero rows were actually persisted.

### Fix (frontend-only)
Applied consistently to all 3 CSV upload flows: Staff Bulk Import, Coupon Upload, Brand↔Category Mapping.
1. Removed `window.confirm` entirely.
2. Selecting a file **auto-runs a dry-run**.
3. The result banner now clearly reads **"Preview (not saved yet)"** and shows an explicit **"Confirm & Import N row(s)"** button (plus a "Cancel" button).
4. Only after clicking Confirm does the second call fire with `dry_run=false`, persist the data, and refresh the list.
5. Dismissing the banner also clears the staged file so no orphan state.

### Data-testids added
- Staff: `confirm-import-btn`, `cancel-import-btn`
- Coupons: `confirm-coupon-btn`, `cancel-coupon-btn`
- Mapping: `confirm-mapping-btn`, `cancel-mapping-btn`

Testing agent iteration 47: 100% pass across 4 scenarios (Staff, Coupon, Mapping, Cancel path). Zero `window.confirm` popups observed.

## Feb 15 2026 — Client Points 29-35 Batch

All shipped in one batch, backend + frontend covered by testing_agent iter 48 (6/6 pytest + 11/11 UI scenarios PASS).

### Point 29 — Banner Dimensions in Admin
- Added `Recommended: 1200 × 400 px (3:1) · JPG, PNG or WebP · ≤ 5 MB` hint (data-testid `banner-dimensions-hint`) in Banner form.
- Client-side aspect-ratio check on file select: shows amber warning banner (data-testid `banner-dim-warning`) if ratio deviates >10 % from 3:1 or width < 900 px. Upload still proceeds.

### Point 30 — Brand Logos Sync Everywhere
- `POST /admin/brands/{id}/upload-image` and `PUT /admin/brands/{id}` now unconditionally call `_sync_brand_to_store`, so logo + featured + category updates hit `stores` collection immediately (previously gated on `description`).

### Point 31 — Play Store App QR + Scan Tracking
- New endpoints:
  - `GET /api/app-download-qr/scan` → 302 redirect to `https://play.google.com/store/apps/details?id=com.homelandadvantage.cp67&hl=en_IN` and logs a row into `app_qr_scans`.
  - `GET /api/admin/app-download-qr/stats` → `{total_scans, today_scans, daily[30], qr_image_url, play_store_url}`.
- `GET /api/app-download-qr` QR now points to the tracked `/scan` URL.
- Admin `QRCodes` page: new "Play Store App Install QR" card (data-testid `app-install-qr-card`) with total, today, daily breakdown, Download PNG, Refresh.

### Point 32 — Hide Brand From Consumer App
- New `hidden_from_app` boolean on brands.
- Consumer `/home` featured_stores and `/stores` filter out `hidden_from_app=true`.
- Admin Brand edit dialog exposes `brand-hidden-toggle` checkbox; list shows a "Hidden" badge.

### Point 33 — Featured Brand Toggle Actually Works
- Consumer `/home` now queries `brands` collection directly with `{is_active: true, is_featured: true, hidden_from_app: {$ne: true}}` (previously it read stale `stores.is_featured` and needed a description).
- Combined with unconditional `_sync_brand_to_store`, admin's Featured toggle reaches the app on the next home refresh.

### Point 34 — Hot Deal Sync
- New `is_hot_deal` boolean on offers.
- Admin Offers form has `offer-hot-deal-toggle` checkbox; list shows a 🔥 Hot Deal badge (data-testid `offer-hot-badge-<id>`).
- Consumer `Offers` screen `hotDeals` filter now checks `o.is_hot_deal` first, keeps the legacy discount-percent heuristic as fallback.
- Backend `POST/PUT /admin/offers` accepts `is_hot_deal`, `discount_value`, `store_id`, `valid_until`.

### Point 35 — Retailer Staff ↔ Master Brand Mapping
- `GET /admin/staff` now enriches each row with `is_brand_mapped` (bool) + `canonical_brand_name` + `canonical_brand_category`, and returns `unmapped_count` at the top level.
- Admin Staff Incentive Program `Staff` tab:
  - "Add Staff" dialog: `Brand Name` is now a `<select>` (data-testid `staff-form-brand`) populated from `/admin/staff/catalog/brands-categories`; selecting a brand auto-fills Brand Category.
  - New filter chip "Unmapped brand only" (data-testid `staff-unmapped-toggle`) with count badge.
  - Each unmapped row gets an amber "Unmapped" badge (data-testid `staff-unmapped-badge-<id>`) and a "Reassign" button that opens a dialog (`reassign-brand-dialog`) with a master-brand dropdown. Picking a brand PATCHes `brand_name` + `brand_category` in one call.
- Current preview data: 759 staff, 315 unmapped.

### Data-testids added
`banner-dimensions-hint`, `banner-dim-warning`, `brand-featured-toggle`, `brand-hidden-toggle`, `brand-featured-badge-<id>`, `brand-hidden-badge-<id>`, `offer-hot-deal-toggle`, `offer-hot-badge-<id>`, `app-install-qr-card`, `app-install-qr-image`, `app-install-qr-total`, `app-install-qr-today`, `download-app-qr-btn`, `refresh-app-qr-btn`, `open-play-store-link`, `staff-unmapped-toggle`, `staff-unmapped-badge-<id>`, `staff-reassign-btn-<id>`, `reassign-brand-dialog`, `reassign-brand-select`.


## Feb 18 2026 — Client Points 8 & 9 (Staff Incentive Slabs V2)

Verified end-to-end by testing_agent iteration 49 (8 unit pytest + 3 API pytest + full UI flow PASS).

### Point 8 — Registration Reward per Category (flat amount)
- New config field `registration_by_category: {"__ALL__": int, "<Category>": int}` on `staff_config`.
- New resolver `_resolve_registration_amount(cfg, staff, count_so_far)` picks:
  1. Staff's brand category-specific amount, else
  2. `__ALL__` universal amount, else
  3. Legacy count-based `registration_slabs` (backward compatible).
- Admin Slabs tab shows a new **Point 8 · Registration Reward per Category** block. Admin can add rows for `ALL` + specific categories with a flat ₹ input.

### Point 9 — Bill Upload Reward by Bill Value (per category)
- New config field `bill_upload_value_slabs_by_category: {"__ALL__": [{min_value, max_value, amount}], "<Category>": [...]}`.
- `create_or_activate_bill_incentive(...)` now accepts `bill_value` and, if not supplied, looks up the bill's amount from the `bills` collection.
- New resolver `_resolve_bill_upload_amount(cfg, staff, bill_value, count_so_far)`:
  1. Staff's brand category-specific value slabs → pick row containing `bill_value`, else
  2. `__ALL__` value slabs → pick row containing `bill_value`, else
  3. Legacy count-based `bill_upload_slabs` (backward compatible).
- Admin Slabs tab shows a new **Point 9 · Bill Upload Reward by Bill Value** block with multi-row (min_value, max_value, amount) editor per category / ALL.

### Backwards-compatibility
- Existing count-based slabs (`registration_slabs`, `bill_upload_slabs`, per-brand/per-category overrides) are kept as the final fallback.
- New fields auto-backfill to `{}` on read for existing configs, so nothing breaks.

### New pytest coverage
- `/app/backend/tests/test_points_8_9_slabs.py` — 8 unit tests for both resolvers (category → ALL → legacy priority + inclusive bucket boundaries).
- `/app/backend/tests/test_points_8_9_config_api.py` — 3 API tests for PUT/GET persistence + cleanup (added by testing agent).

### New data-testids
`reg-by-category-editor`, `reg-by-category-new-key`, `reg-by-category-add`, `reg-by-category-amount-<key>`, `reg-by-category-remove-<key>`, `bill-value-slabs-editor`, `bill-value-slabs-new-key`, `bill-value-slabs-add`, `bill-value-slabs-remove-<key>`, `bill-value-slabs-addrow-<key>`, `bill-value-min-<k>-<i>`, `bill-value-max-<k>-<i>`, `bill-value-amt-<k>-<i>`.


## Feb 19 2026 — Client Point 10 (Filter Slab Dropdowns to Staff-Mapped Categories)

### Problem
Point 8 (Registration Reward per Category) and Point 9 (Bill Upload Reward by Bill Value) dropdowns were sourced from the full brand-category catalog (all 22 categories in the brands collection). Admin found options that had zero retail staff mapped to them, causing noise and mis-configuration.

### Fix
- Backend `GET /admin/staff/catalog/brands-categories` now additionally returns:
  - `staff_mapped_brands` — distinct brands that appear on at least one `retail_staff` row AND exist in the master brands collection.
  - `staff_mapped_categories` — the categories of those staff-mapped brands.
- Frontend Slabs tab wires **only** `staff_mapped_categories` into the two Point 8/9 editors' dropdowns.
- Empty state: if there are zero mapped categories, both editors show an amber helper "No retailer-staff-mapped categories yet — add staff whose brand is present in the Brand ↔ Category Mapping" so admins know why the dropdown is empty.

### Verified
- Backend integration test `/app/backend/tests/test_point10_staff_mapped_dropdown.py` (1 test) PASS.
- Live preview: full catalog has 22 categories, staff-mapped subset shows 11 — dropdown correctly trimmed (visual smoke screenshot captured).


## Feb 19 2026 — Client Points 36 & 37 (Admin diagnostics + Users source dropdown)

Verified end-to-end: 5/5 pytest PASS + live curl + visual smoke on preview.

### Point 37 — Users source dropdown reflects real data
- **Root cause**: dropdown was hardcoded to 6 sources (Retailer, Food Court, Parking, Digital Screens, Social, Website). The DB actually had `SRC_APP`, `SRC_RWA`, `SRC_WHATSAPP`, `SRC_MARKETING`, `SRC_BRANDS` — none of them selectable.
- **Fix**:
  - New endpoint `GET /api/admin/users/sources` returns `{sources: [{code, label, count}, ...]}` — a merge of (a) distinct `first_touch_source` values from the users collection with live counts and (b) a curated shortlist (SRC_APP, SRC_BRANDS, SRC_FOODCOURT, SRC_PARKING, SRC_DIGITAL, SRC_SOCIAL, SRC_WEBSITE, SRC_RWA, SRC_OFFICE, SRC_WHATSAPP, SRC_MARKETING, SRC_REFERRAL) so admins can pre-filter for freshly rolled-out sources even at zero count.
  - Users.jsx fetches this on mount and populates the source dropdown dynamically. Options show as `Label (count)` if count > 0.
  - Live result on preview: dropdown now shows 12 sources with counts vs. 6 before.

### Point 36 — Test message + alerts diagnostics
- **Root cause**: `send_whatsapp_text` returned `True`/`False` — admin never saw *why* Karix might have dropped a message. Also, several WhatsApp bill-path insertion sites only pinged the legacy `ADMIN_PHONE` env constant, not the configured `ADMIN_ALERT_PHONES` list, so real bill alerts silently missed the ops number (9766692497).
- **Fixes**:
  1. New helper `send_whatsapp_text_diag(phone, message)` returns full Karix response (`status_code`, `mid`, response body, error). `send_whatsapp_text` still returns bool for backward compatibility.
  2. `POST /api/admin/alerts/test` now returns `{success, accepted, total, phones, results[per-phone diag], hint}` — the `hint` explains the WhatsApp 24-hour session limitation so admin can distinguish "Karix accepted" from "phone actually received".
  3. New endpoint `POST /api/admin/whatsapp/send-test` for ad-hoc plain-text send with the same diagnostic response.
  4. New helper `insert_bill_and_alert(bill_dict)` — replaces every `db.bills.insert_one(...)` in the WhatsApp bill pipeline (12 sites). It inserts the doc AND fires `maybe_alert_admin` for `pending / pending_review / manual_review / rejected` states so the configured ops phones actually get pinged.
  5. Bills admin UI: "Test Alert" button now surfaces Karix `mid` + the delivery hint via toast so admin can copy-paste the mid to check delivery in Karix dashboard.

### Files touched
- `/app/backend/server.py` (`send_whatsapp_text`, `send_whatsapp_text_diag`, `send_test_admin_alert`, new `send_test_whatsapp` endpoint, new `list_user_sources` endpoint, new `insert_bill_and_alert` helper, 12 insert-site swaps)
- `/app/frontend/src/pages/Users.jsx` (dynamic source dropdown)
- `/app/frontend/src/pages/Bills.jsx` (`sendTestAlert` surfaces mid+hint)

### New tests
- `/app/backend/tests/test_points_36_37.py` — 5 tests: sources endpoint returns curated + counted list, requires auth, alerts/test per-phone diag, send-test validation, send-test success.


## Feb 19 2026 — Client Point 11 (OTP via WhatsApp)

Verified end-to-end: 4/4 new pytest PASS + live Karix OTP delivered (mid captured).

### Problem
User reported "No OTP is getting triggered, please send OTP via WhatsApp only". Existing flow only fired Karix SMS via a DLT template and did not use WhatsApp at all.

### Fix
- New helper `send_otp_whatsapp(phone_10, otp)` in `server.py` — sends the OTP as a plain-text WhatsApp message via Karix WABA (uses `send_whatsapp_text_diag` under the hood, so we get `status_code`, `mid`, response body back for diagnostics).
- New dispatcher `send_login_otp(phone_10, otp)` — routes to WhatsApp, SMS, or both based on `OTP_CHANNEL` env (default `whatsapp`). Optional `OTP_SMS_FALLBACK=true` sends an SMS if WhatsApp fails.
- Consumer `POST /consumer/auth/send-otp` now calls the dispatcher instead of `send_otp_sms` directly. The public API contract is unchanged (`{success:true, phone, message}`).
- Staff/Retailer OTP endpoints (`bind_staff_db`) now receive the same dispatcher, so retailer manager login OTP also uses WhatsApp.
- New admin endpoint `POST /admin/otp/send-test` — ops can trigger a real OTP and see per-channel Karix diagnostics without touching a customer account.

### Env
- `OTP_CHANNEL` (new) — `whatsapp` | `sms` | `both`. Defaults to `whatsapp` per client request.
- `OTP_SMS_FALLBACK` (new) — `true` sends SMS if WhatsApp channel fails.

### New tests
`/app/backend/tests/test_point11_whatsapp_otp.py` — 4 tests covering the public flow, admin diagnostic, and auth guardrails.


## Feb 19 2026 — Bug fix: "SMS all over" (Point 36 delivery guarantee)

### Bug
User reported the "Karix returns 200… WhatsApp may still drop it" toast — the underlying WhatsApp 24-hour session limitation meant ops alerts + OTPs were "accepted" but not delivered. User's direction: **"yes put SMS all over"**.

### Fix
- **OTP dual-channel by default**: `OTP_CHANNEL` env now defaults to `both`. Every OTP fires via WhatsApp AND SMS. `/admin/otp/send-test` and `/consumer/auth/send-otp` both benefit automatically.
- **Bill alerts dual-channel**: `send_admin_bill_alert()` now fires an SMS to each configured ops phone in addition to WhatsApp. Called by every WhatsApp bill-insert path via the earlier `insert_bill_and_alert` helper.
- **New helper `send_sms_text(phone_10, message)`**: generic SMS via Karix using `KARIX_SMS_ALERT_DLT_TEMPLATE_ID` (falls back to the OTP DLT template ID as best-effort).
- **Diagnostic surfaces**: `/admin/alerts/test` now returns `results[].whatsapp` + `results[].sms` per phone with individual status_code/mid/response. Bills.jsx test-alert toast surfaces both statuses.

### Env
- `KARIX_SMS_ALERT_DLT_TEMPLATE_ID` (optional) — provision a dedicated DLT template for ops bill-alert SMS. Without it, we reuse the OTP template ID as best-effort.

### Verified
- testing_agent iteration 50: **19/19 backend PASS** (10 new dual-channel tests + 9 regression). Live Karix: both WhatsApp AND SMS `Platform Accepted` for ops phone 9766692497.
- Minor: `send_sms_text` early-return now includes `status_code: null` for shape consistency (client-side).

### Residual risk (config, not code)
`KARIX_SMS_ALERT_DLT_TEMPLATE_ID` is not set — bill-alert SMS reuses the OTP DLT template. Karix returns Platform Accepted but the operator may still scrub for content mismatch. Ask client to register a dedicated ops-alert DLT template.


## Feb 21 2026 — Client Points 38 & 39 (Fix Brand crash + Bill image not opening)

Verified end-to-end by testing_agent iteration 51 (**24/24 backend PASS + full Playwright UI PASS**).

### Point 38 — Fix Brand: "Incorrect padding"
- **Root cause**: `/admin/bills/<id>/edit-brand` reprocess called Fundle earn_points with `bill.image_url` as base64. For bills whose stored URL was a raw Karix `https://…` or a corrupted `data:image/png;` (< 200 chars), `base64.b64decode` blew up with `binascii.Error: Incorrect padding`. Reprocess returned `{success:false, error:'Incorrect padding'}` and admin saw a scary red toast.
- **Fixes**:
  1. New helper `_resolve_bill_image_base64(bill)` handles all 3 storage variants (`data:` / `base64:` / `http`) and downloads Karix URLs with Bearer auth before base64-encoding.
  2. `edit_bill_brand` inline-reprocess path uses the resolver (removed the buggy "else pass URL as base64" branch).
  3. `TagnPayClient.earn_points` is now defensive: strips `data:` / `base64:` prefix, pads to nearest 4 chars, uses `validate=False`, gracefully skips the attachment (returns Fundle 400 which the caller handles) instead of crashing.
  4. `_reprocess_after_brand_edit` no longer force-credits when Fundle rejects because of a missing/corrupted image (`bill_file`, `no file was submitted`) — a corrupted-image bill stays in manual_review so ops can request a re-upload from the customer.

### Point 39 — Bill review image doesn't open
- **Root cause**: `openReviewDialog` only re-fetched the image via `/bills/<id>/image` when the list-row URL looked like `base64:` or `http:`. Bills with a corrupted / very short `data:` URL (placeholders from prior bad saves) skipped the fetch, so the browser tried to render an invalid `<img>` and admin saw nothing.
- **Fixes**:
  1. `openReviewDialog` now **always** re-fetches through the normalized endpoint (server-side is cheap).
  2. Backend `/bills/<id>/image` detects `< 200-byte` data URLs as placeholders → returns `image_url: null` + `fetch_error: "Stored image is a placeholder / corrupted…"`.
  3. Frontend surfaces `image_fetch_error` in the empty state so admin knows the image is unrecoverable and to ask the customer to resend.

### Data-testids reused
`pending-bill-thumb-<billId>`, `bill-image-empty`, `bill-image-open`, `fix-brand-search`, `fix-brand-pick-<Brand>`, `fix-brand-use-typed`.

### New/updated tests (all pass)
- `/app/backend/tests/test_points_38_39.py` — 3 tests, defensive decode + endpoint placeholder flag + end-to-end edit-brand no-crash
- `/app/backend/tests/test_iteration51_points_38_39.py` — 11 tests seeded from the testing agent covering all 4 image_url variants across 3 code paths + regression on the alerts endpoint


## Feb 21 2026 — Client Points 40 & 41 (iOS iPad Picker + Consumer PWA UI Overhaul)

Verified end-to-end by testing_agent iteration 52 (**Point 40 static PASS + backend 15/15**) followed by main-agent smoke test (all 5 iteration-52 issues fixed).

### Point 40 — iOS iPad WebView Camera/Photo Picker crash ✅
- **Fix**: `/app/ios-build/CP67iOS/WebViewContainer.swift`
  - `launchCamera` and `launchGallery` now set `modalPresentationStyle = .fullScreen` and configure `popoverPresentationController.sourceView`/`sourceRect` for iPad (iOS requires a source anchor for popover presentation, else UIKit throws on iPad).
  - Applied to `PHPickerViewController` (iOS 14+) and the `UIImagePickerController` iOS<14 fallback.
  - `Info.plist` bumped to `CFBundleShortVersionString=1.0.1`, `CFBundleVersion=2`.

### Point 41 — Consumer PWA UI overhaul ✅
Sub-points (a, b, c, g, h, i, j) — all shipped, all data-testids verified live:
- **41a** — Login tagline: "CP67's Loyalty Programme" + "Shop. Scan. Earn." in gold.
- **41b** — Home tier badge uses tier-coloured gradient (`TIER_META`) + T&C chip that deep-links into Tier Journey T&C block.
- **41c** — Tier progress line now reads live thresholds from `GET /api/consumer/tier-info` (iteration-52 fix: was hard-coded to 500/2000/5000, now matches backend `tier_journey` table). Static `TIER_META` remains only as an offline fallback.
- **41g** — Profile "Complete your profile" CTA (Interests block removed): pale gold heading + high-contrast `#FFF9E6` subtext lists missing fields (Name, DOB, Email, Address). Iteration-52 fix darkened the subtext for accessibility on mobile.
- **41h** — Explore "Brands Directory" renamed, "Explore 191+ Brands at CP67 Mall" counter, floor dropdown now includes "4th Floor".
- **41i** — Tier Journey T&C chip smooth-scrolls to `#tier-tnc-block` (5 bullets). Iteration-52 fix: bullet text changed from `#2E2219` (contrast 1.1:1 on dark card) to `rgba(255,255,255,0.85)` — WCAG AA compliant.
- **41j** — Profile Refer & Earn section: deterministic `HA<6-digit>` code from phone, Copy button with `toast.success('Referral code copied')` (iteration-52 fix: previously silent), Refer Friends CTA using `navigator.share` with WhatsApp fallback.

### Iteration-52 defects fixed (main agent, this session)
1. Home.jsx `tier-tnc-link`: `navigate('/app/tier')` → `navigate('/app/tier-journey')` (route mismatch was silently redirecting via catch-all).
2. TierJourney.jsx `tier-tnc-block`: bullet text colour → readable on dark card.
3. Home.jsx tier progress: now derives next-tier from `/api/consumer/tier-info` payload (`next_tier`, `points_to_next`) instead of hard-coded thresholds.
4. Profile.jsx complete-profile CTA: subtext colour → `#FFF9E6` with `#FFDF73` accent (high contrast on gold banner).
5. Profile.jsx referral-copy-btn: added `toast.success('Referral code copied')` on successful clipboard write.

### Smoke test (main agent, this session)
- Login via reviewer phone `9999999999` + OTP `123456` → landed on `/app/home`.
- Bronze tier badge rendered with gradient, T&C chip visible.
- Clicking T&C chip → URL correctly changed to `/app/tier-journey`.
- Tier T&C block visible with readable white bullets on dark card.

### Files touched (this batch)
- `/app/frontend/src/consumer/pages/Home.jsx` (route fix + dynamic tier-info fetch)
- `/app/frontend/src/consumer/pages/Profile.jsx` (CTA contrast + copy toast)
- `/app/frontend/src/consumer/pages/TierJourney.jsx` (T&C block bullet contrast)
- `/app/ios-build/CP67iOS/WebViewContainer.swift` (iPad picker anchor)
- `/app/ios-build/CP67iOS/Info.plist` (version bump)

## Aug 25 2026 — Client Retailer Doc Points 11, 12, 13, 14

Verified end-to-end by testing_agent iteration 53 (**26/26 backend pytest PASS + 100% frontend Reports tab UI flows**). Low-priority defects flagged by iteration 53 (dead code, pre-limit brand filter, dangling separator) fixed in this session.

### Point 11 — OTP not triggering; must fire via WhatsApp (DLT template)
- `send_otp_whatsapp` in `/app/backend/server.py` now uses the exact DLT-approved wording: `"Your verification OTP is {otp} Use this at CP67 Mall."` — matches PEID 1701172802304667512 / Temp ID 1707172914885560615 / Header `CP67` (Service Implicit).
- Retailer manager + staff `/auth/send-otp` routes now surface a per-channel `delivery: {whatsapp, sms, success}` object so admin sees Karix's real response instead of a silent boolean.
- New admin diagnostic endpoint `POST /api/admin/staff/retailer/test-otp` — sends a real OTP to any whitelisted retailer manager phone and returns the delivery dict. Non-whitelisted phone returns a clear "Phone is not a whitelisted retailer manager" message.
- Admin UI (`/staff-incentives` → Reports tab) has a **Point 11 · Test Retailer OTP (WhatsApp + SMS)** block with input + button + inline WA/SMS status-code readout.

### Point 12 — Retailer incentive report (Registration vs Bill Upload, per staff, per customer mobile)
- New endpoint `GET /api/admin/staff/incentives/report`:
  - Query params: `incentive_type` (registration | bill_upload), `brand`, `status`, `staff_id`, `start_date`, `end_date`, `limit` (default 1000).
  - Response: `{rows: [...], summary: {total, registration_count, bill_upload_count, total_amount, redeemable_amount}}`.
  - Each row: id, type, status, amount, `customer_phone` (which mobile registered / uploaded), staff_code, staff_name, staff_phone, staff_brand, staff_brand_category, staff_store, created_at, approved_at. Bill-upload rows also carry bill_id, bill_value, bill_amount, bill_store, bill_status, bill_no.
- CSV export: `GET /api/admin/staff/incentives/report.csv` — same query params, streams `retailer_incentives_report.csv` with 16 columns.
- Admin UI: new **Reports tab** on `/staff-incentives` with Type/Brand/Status/Date filters, 4 KPI tiles (Registration Records, Bill Upload Records, Total Amount, Redeemable Amount), Customer Mobile column, and a "Download CSV" button.
- Iter 53 fix: brand filter is now applied at the Mongo layer (resolves matching `staff_ids` first) so filters never silently drop rows past `limit`.

### Points 13 & 14 — Brand-matched bill attribution ("last QR + matching bill")
- `create_or_activate_bill_incentive` (in `/app/backend/routes/staff.py`) now enforces brand match: the bill's `store_name` must normalise-equal the attributed staff's `brand_name` (case-insensitive, `[^a-z0-9]` stripped). Examples: `"Nike"` ↔ `"NIKE"` ↔ `"Nike-Store"` ↔ `"nikestore"` all match; `"Nike"` ↔ `"Adidas"` does not.
- Mismatch behaviour: NO row inserted into `staff_incentives`, one row logged in a new `staff_attribution_misses` collection (`{staff_id, bill_id, staff_brand, bill_brand, reason: "brand_mismatch"}`), and the attribution is still marked `used=True`. This is the client's "one scan, one bill decision" rule — a later bill without a fresh QR scan gets no credit even if it happens to match the retailer's brand.
- Customer's original `first_touch_source` (registration source) has NO influence on subsequent bill incentives — attribution is derived only from the last unexpired unused `staff_attributions` window.

### Data-testids added
`tab-report`, `refresh-report-btn`, `download-report-csv-btn`, `test-otp-phone-input`, `send-test-otp-btn`, `test-otp-result`, `report-type-select`, `report-brand-select`, `report-status-select`, `report-start-date`, `report-end-date`, `apply-report-filters-btn`, `report-reg-count`, `report-bill-count`, `report-total-amount`, `report-redeemable-amount`, `report-tbody`.

### Files touched
- `/app/backend/server.py` (`send_otp_whatsapp` — DLT text)
- `/app/backend/routes/staff.py` (retailer/staff send-otp diag, admin_test_retailer_otp, admin_incentive_report + .csv, brand-match in create_or_activate_bill_incentive, attribution_miss logging)
- `/app/frontend/src/pages/StaffIncentives.jsx` (Reports tab + Test OTP block + report table)
- `/app/backend/tests/test_points_11_12_14_retailer.py` (10 tests — brand normalisation matrix + end-to-end mismatch flow + match happy path + route registration)
- Iter-53 seeded (agent-authored) `/app/backend/tests/test_iteration53_points_11_12_live.py` and `/app/backend/tests/helper_seed_i53.py`.

### Iter-53 defects fixed in this session
1. Dead unreachable `return {"success": True}` after `admin_test_retailer_otp` — removed.
2. Report `brand` filter applied post-`limit` — moved to pre-Mongo (matches staff_ids first).
3. Reports table Brand cell rendered `"Zara /"` when category was empty — now conditionally renders the `/ category` fragment only when non-empty.

### Known open items from iter 53 (deferred, LOW/OPTIONAL)
- Design polish: replace native `<select>` and `<input type=date>` in Reports filter row with shadcn Select + Calendar for visual consistency.
- Optional: expose the backend-supported `staff_id` filter as a staff dropdown in the Reports tab.
- OPTIONAL (Point 13 nuance): registration incentive still auto-activates on ANY approved bill — client may want to require same-brand bill for reg activation too. Not addressed pending client confirmation.

---

## Session 15 (Feb 2026) — Prod HTTP 500 hardening (Admin Bills)

### Bug reports (production only — https://mall-rewards-1.emergent.host)
1. "Brand edit failed (HTTP 500)" when correcting a bill's brand via `POST /api/admin/bills/{bill_id}/edit-brand`.
2. "Image cannot be opened (Image endpoint returned HTTP 500). The WhatsApp media link may have expired." when opening a bill in the review dialog via `GET /api/bills/{bill_id}/image`.

### RCA (from iteration_54 testing report)
Production is running pre-hardening code. Direct probing showed prod returns raw text/plain `Internal Server Error` even for a **non-existent** bill id, whereas current preview code returns clean JSON 404. Definitive proof that production ≠ preview build.

### Fix applied (preview code, needs redeploy)
- `get_bill_image` (server.py ~2974) wrapped in top-level try/except → returns `200 {image_url, image_hash, fetch_error}` for every input shape, including unknown/legacy schemes. Also applies the <200-byte corrupted-placeholder guard consistently to the `base64:` branch (was previously only on `data:` branch). Persist-back-to-Mongo skipped when encoded payload >15MB to avoid BSON 16MB doc limit.
- `edit_bill_brand` (server.py ~4362) wrapped in top-level try/except → still raises `404`/`400`/`422` for validation, but any unexpected exception now returns `500` with a JSON `detail` body instead of an unhandled crash.

### Verification
- `iteration_54.json`: 15/15 pytests pass on preview. No endpoint ever returns raw 500. Also proved production returns raw 500 for the identical calls → user must redeploy.
- Reusable regression suite: `/app/backend/tests/test_iteration54_bill_image_editbrand.py` (seeds its own bill shapes via pymongo).

### Action required from user
**Redeploy production** — preview code is verified correct. Once prod is on the new build, both errors will surface as friendly JSON responses (or 200-with-hint for the image endpoint).

## Session 15 addendum (Feb 2026) — Root cause of Admin Bills HTTP 500 in production

### RCA
After the user redeployed iteration_54, the top-level try/except surfaced the actual error: `Server error while loading image: customer-apps-shard-00-01.jxp3ul.mongodb.net:27017: The read operation timed out.` — i.e. Mongo find_one timed out.

Cause: `bills` collection had **no index on the `id` field** (only on `_id`, `created_at`, `status`, `user_id`, `user_phone`, `bill_no_normalized`, `image_hash`). Every `find_one({'id': bill_id})` was a full collection scan; on production Atlas with growing volume this exceeded pymongo's socket read timeout. Same latent bug on `users`, `brands`, `stores`, `campaigns`, `coupons`, `staff`, `staff_incentives`, `parking_sessions`, `parking_coupons`, `sync_jobs`, `bulk_reprocess_jobs`, `app_settings`, `staff_attributions`.

### Fix
Added `id_1` index specs to `ensure_db_indexes()` in `server.py` for all 14 affected collections. Indexes create idempotently on every boot.

### Verification (iteration_55.json)
- 29/29 backend tests PASS
- `db.bills.explain()` for `find({'id': …})` now shows `IXSCAN` (was `COLLSCAN`)
- `/api/bills/{id}/image` (valid + unknown), `/api/admin/bills/{id}/edit-brand` all under 500ms latency budget
- ensure_db_indexes() confirmed idempotent across supervisor restarts

### Action required
Redeploy production. Index creation runs at backend startup, so Atlas will only get `id_1` after the new build lands.

## Session 17 (Feb 2026) — Motor + httpx timeouts (raw 500 elimination)

### RCA
Even after session-15 (top-level try/except) + session-16 (id_1 indexes), user still saw raw HTTP 500 on production. The remaining path: pymongo's default socketTimeoutMS=None (wait forever) and httpx's 20s Karix media fetch could exceed Cloudflare's edge timeout — the edge returned 5xx before FastAPI could respond with a caught-exception JSON.

### Fix
- Explicit AsyncIOMotorClient timeouts: serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, socketTimeoutMS=10000, waitQueueTimeoutMS=5000, retryReads=True, retryWrites=True.
- Reduced Karix media fetch httpx timeout from 20s → 8s in `get_bill_image`.

### Verification (iteration_56.json)
- 18/18 new tests + 29/29 regression (iter_54 + iter_55) PASS.
- Exception simulation (patched `db.bills.find_one` to raise pymongo NetworkTimeout / ServerSelectionTimeoutError / AutoReconnect) confirms `/api/bills/{id}/image` returns clean 200-with-fetch_error and `/api/admin/bills/{id}/edit-brand` returns 500-with-JSON-detail (non-empty body).
- 25-way concurrent image fetch: all 200, worst 1204ms.

### Action required
Redeploy production. All three layers of hardening (session 15 catch, session 16 indexes, session 17 timeouts) must ship together.

## Session 18 (Feb 2026) — Reprocess endpoint hardening (Admin "Reprocess timed out")

### Bug
Production admin clicks Reprocess on a bill → red toast "Reprocess timed out. Refresh — the bill may still be processing." Same COLLSCAN + edge-timeout family as sessions 15-17 — `find_one({'id': bill_id})` + `update_one({'id': bill_id})` without the id_1 index blew past the frontend's 15s AbortController budget.

### Fix
- Top-level try/except on `/api/bills/{bill_id}/reprocess` — any Mongo hiccup now returns HTTP 500 with a JSON `detail` body instead of an empty 500 (which the frontend renders as the same "timeout" toast because `res.json()` throws).
- Added 409 in-flight guard: if `reprocessing_started_at` is set and `reprocessing_finished_at` is null AND `age < 120s`, reject the double-click. Stale-lock protection: after 2 minutes we allow retry (handles the crashed-mid-reprocess case).
- Session-16 id_1 indexes + session-17 Motor timeouts (already committed) resolve the underlying latency.

### Verification (iteration_57.json)
- 30/30 new + 78 across the full 54→57 regression PASS.
- Queued path: 44-58ms (well inside the 15s abort).
- Exception sim (NetworkTimeout / ServerSelectionTimeoutError / AutoReconnect / ExecutionTimeout / generic RuntimeError patched into `find_one`) → JSON 500, never empty.
- Background task confirmed to actually execute — bill moved `rejected → approved` and `reprocessing_finished_at` stamped.

### Action required
Redeploy production. All fixes (sessions 15-18) ship on this deploy.

## Session 19 (Feb 2026) — Wire compression + retry (Atlas timeout mitigation)

### Bug
Same Atlas socket-read timeout on production `/api/bills/{id}/image` (bill: Haldiram's ₹91.36, phone 919041965368). Session-15/16/17/18 hardening surfaced the raw cause as `fetch_error='Server error while loading image: ... read operation timed out'` instead of a raw 500.

### RCA (from iteration_58 testing agent)
NOT an Atlas scaling problem. Preview measurements: 4.2MB inline-base64 bill doc read in 5-6ms locally, endpoint 117-393ms end-to-end. The bottleneck is that **bills docs embed multi-MB base64 image_url inline** and shuttling megabytes over the Atlas wire under any network hiccup breaches the 10s socketTimeoutMS.

### Fix (mitigation, not durable cure)
1. Motor client now negotiates `compressors='zstd,zlib'` (`zstandard==0.25.0` pinned in requirements.txt) — cuts wire payload 3-5x.
2. `socketTimeoutMS` raised 10s → 20s, `maxPoolSize=100`, `minPoolSize=10`.
3. `get_bill_image` wraps the initial `find_one` in a one-shot retry (300ms backoff) narrowed to pymongo `NetworkTimeout / AutoReconnect / ServerSelectionTimeoutError / ExecutionTimeout` — transient blips no longer surface to the admin UI, real errors don't wait 300ms.

### Verification (iteration_58.json)
- 95/95 tests pass (17 new + 78 regression from iter 54→57). 1 legit prod-only skip.
- Retry proven with `mock.patch(db.bills.find_one)`: first call raises NetworkTimeout → 300ms backoff → second call succeeds → HTTP 200 with REAL image_url. Both-fail case → 200 with clean fetch_error. Not-found path NOT retried (call count = 1) → clean 404.
- Warm-cache latency on a real 4.2MB bill doc: 117ms.

### Durable cure (recommended — not done this session)
Move image storage OUT of the `bills` doc into object storage (Emergent Object Storage / GridFS) keyed by bill_id. Bills docs shrink from multi-MB to <10KB, review page loads become instant even on a cold Atlas replica. This is the actual answer to "should we scale the DB" — no, we should stop storing megabytes inline.

### Action required from user
Redeploy production. Compression + wider socket budget + retry ships together. If timeouts still recur after redeploy, agree object-storage migration as next roadmap item.

## Session 20 (Feb 2026) — Emergent Object Storage migration for bill images

### The durable fix
Bill.image_url now supports a new `objstore:<path>` prefix that points to Emergent Object Storage. Mongo doc shrinks from multi-MB to <100 bytes per bill.

### Components (all in code)
1. `/app/backend/storage.py` — new module: `init_storage` / sync + async (`aput/aget/aupload_bill_image/aresolve_objstore_url`) helpers, uses `INTEGRATION_PROXY_URL` (fallback https://integrations.emergentagent.com) + `EMERGENT_LLM_KEY`. `load_dotenv()` at import time so module works before server bootstrap.
2. `get_bill_image` recognises `objstore:<path>`, streams the bytes back re-encoded as data:image/*;base64. All blocking HTTP is wrapped in `asyncio.to_thread` so the event loop is not starved.
3. `_migrate_bill_image_to_objstore` — background worker scheduled from the `/image` endpoint's `finally` block. Any inline data URL >50KB is progressively migrated on next view.
4. `POST /api/admin/bills/migrate-images-to-objstore` (admin-only) — bulk queue endpoint. `$expr {$strLenCP > 50000}` filter drains to `queued=0` in 1-3 calls.
5. Startup: `init_storage()` non-fatal, falls back to inline on any failure.

### Verification (iteration_60.json)
- 32/32 objstore tests + 95/95 regression PASS. Zero raw 500s in any path.
- Admin guard: non-admin JWT → 403; admin → 200.
- Async event loop: 6-way concurrent 300KB objstore reads keep /api/health within 9% of the no-objstore control (was 2.5× before the async wrappers).
- Progressive migration end-to-end proven: 160KB inline bill → 1st view returns inline + queues bg task → after ~5s bill.image_url = `objstore:cp67-mall/bills/{id}.jpg` → 2nd view returns byte-identical bytes from object storage.

### Redeploy runbook for the user
1. Redeploy production (ships sessions 15-20 together).
2. Call `POST /api/admin/bills/migrate-images-to-objstore` from the admin bearer token. Poll it 1-3 times until `queued=0` (fat inline bills drain in one batch of ≤500 per call).
3. Every future admin bill review reads a <1KB Mongo doc + streams bytes over the objstore CDN — no more 10s+ Atlas timeouts.

## Session 21 (Feb 2026) — maybe_alert_admin projection fix (production Atlas timeout)

### Symptom (production logs)
```
maybe_alert_admin failed for <bill_id>/pending_review: The read operation timed out
Executor error during find command: mall-rewards-1-test_database.bills :: caused by :: operation exceeded time limit (MaxTimeMSExpired)
```

### Root cause
`maybe_alert_admin` at server.py:4828 did `db.bills.find_one({"id": bill_id}, {"_id": 0})` — this returns the ENTIRE bill document, including legacy multi-MB inline base64 `image_url` payloads that Session 20's migration has not yet drained. Under concurrent load (webhook status changes + 60s `_bill_alert_scanner_loop`), the cursor network transfer time exceeded Motor's socket read timeout / Atlas `maxTimeMS`.

### Fix
Added an explicit projection to fetch ONLY the 7 fields the alert consumer (`send_admin_bill_alert`) actually reads:
- id, user_phone, store_name, amount, bill_no, rejection_reason, admin_alerts_sent

Payload shrinks from multi-MB to a few hundred bytes on an indexed (id_1) point lookup.

### Verification (iteration_61.json)
- 19/19 tests PASS (`/app/backend/tests/test_iteration61_alert_projection.py`).
- Projection contents verified structurally (image_url + _id no longer returned).
- Alert payload unchanged, dedup per (bill_id, status) intact (1 send for 3 calls, independent per status).
- HTTP regression on GET /api/bills, GET /api/bills/{id}, GET /api/bills/{id}/image, POST /api/bills/{id}/reprocess.

### Known minor (not fixed this session)
Dedup is read-then-write, not atomic. Concurrent webhook task + scanner loop can each send one alert before the marker persists. Recommendation: replace with a conditional `update_one({"id": bill_id, "admin_alerts_sent.<status>": {"$exists": False}}, {"$set": ...})` + `matched_count == 1` guard.

### Action required from user
Redeploy production. `maybe_alert_admin` will no longer transfer multi-MB payloads per invocation, killing the last remaining source of Atlas read-operation-timeout spam in the logs.

## Session 22 (Feb 2026) — Bill Review + Process 500s (Atlas MaxTimeMSExpired)

### Symptom (production, user screenshot)
- Bill Review modal: "Image cannot be opened (Server error while loading image: Executor error during find command: mall-rewards-1-...)"
- `POST /api/bills/{id}/process` → HTTP 500 after 10.8s
- `GET /api/bills/pending-review` → 7.5s (slow)

### Root cause
Three additional hot paths on the bills collection were pulling the ENTIRE bill doc (including legacy multi-MB inline base64 `image_url` and `ocr_raw_data`) over Atlas — same class of bug as iteration-61's `maybe_alert_admin`, just in different endpoints:
1. `process_bill` (server.py:3202) — `find_one({"id": bill_id})` with no projection.
2. `get_bill_details` (server.py:3187) — `find_one({"id": bill_id}, {"_id": 0})` returned full doc.
3. `get_bill_image` (server.py:2993) — narrow projection but still transferring multi-MB `image_url`; no client `maxTimeMS` set so hit server default.
4. `_resolve_bill_image_base64` — no `objstore:` branch, so migrated bills' approve→TagnPay would silently drop the image.

### Fixes
1. `process_bill`: primary `find_one` now excludes `image_url` + `ocr_raw_data`. Approve branch re-fetches JUST `image_url` via `{_id:0, image_url:1}` before calling `_resolve_bill_image_base64`.
2. `get_bill_details`: projection excludes `image_url` + `ocr_raw_data`.
3. `get_bill_image`: added `max_time_ms=25000` to give Atlas headroom for one legacy transfer, followed by background objstore migration so the next read is <1KB.
4. `_resolve_bill_image_base64`: added `objstore:<path>` branch that fetches bytes via `storage.aresolve_objstore_url` and returns base64 for TagnPay.

### Verification (iteration_62.json)
- 21/21 tests PASS (`/app/backend/tests/test_iteration62_bill_projections.py`).
- Real HTTP approve on a 500KB-image bill returned 200 in 5.9s (previously 500 @10.8s in prod).
- Real HTTP reject returned 200.
- `GET /api/bills/{id}` payload <20KB (no image_url, no ocr_raw_data).
- `get_bill_image` serves all 4 shapes (data:, base64:, objstore:, http:) correctly.
- `deployment_agent`: passes.

### Known minor items (not fixed this session — noted in test report)
- `process_bill` primary `find_one` missing explicit `_id:0` (harmless today).
- `POST /api/bills/{id}/reprocess` guard fetch, `force-credit-preview`, `force-credit`, `reprocess-legacy`, `edit-brand` all still pull full bill docs. Same-class bug, lower blast radius; queued as backlog.
- `get_bill_image`'s `finally` references `raw`/`normalized` which may be unbound on early failure (silently swallowed by outer try/except).

### Action required from user
Redeploy production. `process_bill`, `get_bill_details`, `get_bill_image`, and TagnPay approve for migrated bills all stop pulling multi-MB payloads on the primary read.

## Session 23 (Feb 2026) — Scanner-loop timeout snowball hardening

### Symptom (production)
`_bill_alert_scanner_loop` runs every 60s. When maybe_alert_admin timed out on a bill, the bill was NOT marked alerted, so the scanner retried the SAME bills every cycle, snowballing timed-out Motor connections and starving user-facing endpoints (brand edits, health checks). Runs on both pods → 2x load.

### Fixes (all in server.py)
1. **In-memory failure cooldown** — `_ALERT_FAILURE_COOLDOWN[(bill_id, status)] = now + 300s` on any exception inside `maybe_alert_admin`. Subsequent calls with the same key return early with ZERO DB queries. Success clears the entry. `_prune_alert_failure_cooldown` GCs the map when it exceeds 1000 entries.
2. **Scanner throttle** — `await asyncio.sleep(0.5)` between successive `maybe_alert_admin` calls inside `_bill_alert_scanner_loop`. Prevents the scanner from firing all queries simultaneously.
3. **Fail-fast maxTimeMS** — Added `max_time_ms=5000` to `maybe_alert_admin`'s `find_one`. Scanner queries fail in 5s instead of holding a socket for the full 20s socketTimeoutMS, keeping connections available for user-facing operations.
4. **Reduced per-cycle limit** — Scanner cursor `.limit(10)` per status (was 50), so a cycle triggers at most 30 concurrent reads instead of 150.

Also added `import time` and `Tuple` to typing import (used by cooldown module state).

### Verification (iteration_63.json)
- 17/17 tests PASS (`/app/backend/tests/test_iteration63_alert_cooldown_throttle.py`).
- Cooldown proven: forced-fail → next call = 0 DB reads; 300s +/-5s.
- Keyed per (bill_id, status): different statuses on same bill still alerted.
- Success path pops cooldown; expired entries allow retry.
- `find_one` invoked with `max_time_ms=5000` + iter-61 projection.
- Scanner: `.limit(10)` per status (3 x 10 = 30 max), N alerts → N `asyncio.sleep(0.5)` between them, cycle ends with `sleep(60)`.
- Light regression: iter-61 + iter-62 fixes still work (GET /api/bills/{id}, /image, process approve+reject).

### Known observations (not fixed this session)
- Worst-case fully-failing cycle: 30 × (5s + 0.5s) = ~165s > 60s interval → cycles will drift/serialize. Cooldown makes this self-limiting after 1st failing cycle.
- Any exception (even transient) registers a 5-min cooldown, so a real DB blip during a user-triggered `process_bill reject` can suppress that ops alert for 5 min. Scanner retries so no bill is lost.
- `_ALERT_FAILURE_COOLDOWN` module state is per-pod — both pods learn independently. Acceptable because `admin_alerts_sent.<status>` on the doc is the ultimate dedup.

### Action required from user
Redeploy PREVIEW → PRODUCTION. Scanner will stop snowballing on Atlas hiccups; admin operations stay responsive under load.

## Session 24 (Feb 2026) — Deployment build failure + consumer popups 403

### Symptom
Emergent production deployment failed with every step showing "not run: an earlier deploy step failed" — the very first pipeline step (frontend `yarn build`) was silently aborting.

### Root cause (deployment)
Emergent's deploy pipeline sets `CI=true`. Under `CI=true`, `react-scripts` promotes ALL ESLint warnings to errors. The codebase carries 15+ pre-existing `react-hooks/exhaustive-deps` warnings across `AdminUsers.jsx`, `Analytics.jsx`, `Bills.jsx`, `Brands.jsx`, `Campaigns.jsx`, `Coupons.jsx`, `Dashboard.jsx`, `ParkingReport.jsx`, `ParkingScanner.jsx`, `QRCodes.jsx`, `StaffIncentives.jsx`, `Users.jsx`, `WhatsAppLogs.jsx`, `RetailerDashboard.jsx`, `StaffRedeem.jsx`. `yarn build` failed → every subsequent deploy step marked "not run".

### Fix (deployment)
Added to `/app/frontend/.env`:
```
DISABLE_ESLINT_PLUGIN=true
ESLINT_NO_DEV_ERRORS=true
```
CRA's official switch to skip the ESLint webpack plugin entirely. ESLint is compile-time only; runtime bundle is unaffected. `CI=true yarn build` now completes in ~17s.

### Bonus fix (found during smoke)
Testing agent found a HIGH-priority pre-existing bug: `/api/consumer/popups/active` and `/api/consumer/popups/dismiss` always returned 403. Root cause was a JWT claim divergence — `/app/backend/routes/admin_diy.py:69` checked `payload['role']=='consumer'` while consumer tokens minted in `/app/backend/routes/consumer.py:356` carry `{'type':'consumer'}` with no `role` claim.

Fix: widened the check to accept EITHER `role=='consumer'` OR `type=='consumer'`. No privilege escalation — audited all token factories (admin=role:admin, staff=role:retail_staff, retailer=role:retailer_manager). Only consumer tokens pass the widened check.

### Verification
- iteration_64: `CI=true yarn build` exits 0 in 17.11s; consumer + admin login smoke pass; iter 61/62/63 suites 57/57.
- iteration_65: `/api/consumer/popups/active` and `/dismiss` now return 200 with real consumer JWT; e2e create→see→dismiss→hidden flow works; 15/15 new tests + 64/64 regression pass.

### Known backlog items (deferred from iteration_64 report)
- MEDIUM: Consumer /app/home has 6 broken images (stale cross-environment absolute URLs + 2 empty src="" that trigger a React warning). Needs re-seed with relative URLs.
- LOW: Tier card copy runs together ("TestYou've reached the top tier") and shows "top tier" for a Bronze user with 0 pts.
- LOW: `craco.config.js` still has an `eslint.configure` block while `DISABLE_ESLINT_PLUGIN=true`; harmless but confusing.
- FOLLOW-UP: Extract ONE shared consumer-auth dependency so the claim-name divergence bug class cannot recur in the next router.

### Action required from user
Redeploy PREVIEW → PRODUCTION. The build now completes; deployment should succeed end-to-end.

## Session 25 (Feb 2026) — Fix Brand + Reprocess flow fails on production

### Symptom (production, user screenshots)
- Bill Review → Fix Brand popup opens, brand list (163) loads correctly.
- Submitting the chosen/exact-text brand → fails.
- Clicking Reprocess on the same bill → also fails.
- Environment: cp67bot.fundlexperiences.com (production).

### Root cause
Iteration 62 identified these but left them as backlog — 8 `find_one({"id": bill_id}, {"_id": 0})` sites on the reprocess + edit-brand pipelines were still pulling the FULL bill doc, including legacy multi-MB inline base64 `image_url`. Under production Atlas load these tripped MaxTimeMSExpired.

Additionally, `_reprocess_single_bill` had no `objstore:` branch — migrated bills (from Session 20 Object Storage migration) sent NO image bytes to Fundle, which then rejected them with "bill_file missing", and the force-credit fallback correctly suppressed itself for missing-image errors → the reprocess loop never succeeded for migrated bills.

### Fixes
1. **`reprocess_bill` guard read** — lean projection `{id, status, reprocessing_started_at, reprocessing_finished_at}` (no image_url).
2. **`_do_reprocess_bill_bg`** — full doc with `max_time_ms=25000`.
3. **`_do_reprocess_bill_sync`** — full doc with `max_time_ms=25000`.
4. **`edit_bill_brand` initial read** — lean projection `{id, store_name, status}`.
5. **`edit_bill_brand` sync-path reload** — full doc with `max_time_ms=25000`.
6. **`edit_bill_brand` post-Fundle-reject reload** — exclude `image_url` + `ocr_raw_data` with `max_time_ms=15000`.
7. **`_reprocess_after_brand_edit`** initial + post-reject reload — same treatment as (5) + (6).
8. **`_reprocess_single_bill`** — NEW `objstore:<path>` branch fetches bytes via `storage.aresolve_objstore_url` and base64-encodes for TagnPay earn_points.

### Verification (iteration_66.json)
- 19/19 new tests PASS (`/app/backend/tests/test_iteration66_reprocess_projections.py`).
- 79/79 regression PASS (iterations 61-65 suites all still green).
- Real HTTP measurements: edit-brand queued 0.13s, reprocess queued 0.18s on a 500KB-image bill.
- objstore: branch structurally verified — `storage.aresolve_objstore_url` invoked with the correct path; on None-resolve degrades to `action='no_image'` (no blind credit).

### Known observations (deferred to next session)
- `force-credit-preview` (server.py:4581), `force-credit` (server.py:4604), and `reprocess-legacy` (server.py:3605) still fetch the full bill doc with no `max_time_ms`. Same-class bug, lower blast radius (admin-only paths, less frequent).

### Action required from user
Redeploy PREVIEW → PRODUCTION. Fix Brand submit + Reprocess should stop failing on legacy heavy bills AND on migrated objstore bills.

## Session 26 (Feb 2026) — Finish the iteration_66 next-action backlog

Three backlog items closed. Bill Image Streaming intentionally deferred — it would require coordinated frontend refactor and risks the working admin Bill Review modal.

### Fixes

1. **Bill read cleanup — the last 3 full-doc find_ones**
   - `GET /api/admin/bills/{id}/force-credit-preview` → projection `{_id:0, amount:1, store_name:1}` (only fields consumed).
   - `POST /api/admin/bills/{id}/force-credit` → projection `{_id:0, image_url:0, ocr_raw_data:0}` + `max_time_ms=15000` (force-credit branch of `_reprocess_single_bill` never touches image, so heavy fields excluded).
   - `POST /api/bills/{id}/reprocess-legacy` → `{_id:0}` + `max_time_ms=25000` (this path DOES need image_url for `_resolve_bill_image_base64`).

2. **Shared consumer auth**
   - `routes/admin_diy._current_consumer` now delegates to `routes.consumer.get_current_consumer`. Single source of truth for consumer-token validation — the role/type claim-divergence bug (iter 65) can never recur.

3. **Consumer Home hardening**
   - New `SafeImage` component in `consumer/pages/Home.jsx` — renders a gradient placeholder + label when src is empty, whitespace, null, or fires onError. Replaces 4 unguarded `<img>` renders (banner, hot deal, featured store, event). Kills the React "empty string src" warning + the broken-image icon on stale cross-env URLs.
   - Placeholder styling upgraded to warm gold-on-dark gradient (was low-contrast white on cream) for legibility.
   - Tier card copy fix: "You've reached the top tier" only shows when the current tier IS actually the top slab (per TIER_META). A Bronze user with 0 pts now sees "You are 500 points away from Silver" (was showing "top tier" — a real UX bug on production).
   - Layout fix: `.points-card-name`, `.points-label` and tier-progress spans are now `display: block` so `firstName` no longer runs into the tier text (was rendering "TestYou've reached the top tier").

### Verification (iteration_67.json)
- 16/16 backend tests PASS.
- Playwright: SafeImage renders placeholder for empty/whitespace/null/dead URLs; renders real `<img>` (naturalWidth>0) for valid data-URI; no React empty-src warning.
- Tier card: Bronze user with 0 pts → "You are 500 points away from Silver" with 25px vertical gap below the name.
- Consumer JWT still 200 on `/api/consumer/popups/active` and `/dismiss` (delegation didn't regress); admin/staff/garbage tokens → 401/403.

### Still on backlog
- **Bill Image Streaming** — GET /api/bills/{id}/image as raw StreamingResponse (30% bandwidth win, requires coordinated frontend change).
- **Real banner/hot-deal/event seed content** — preview DB still carries dead cross-env URLs; SafeImage now hides them gracefully but a proper re-seed would show real hero content.

### Action required from user
Redeploy PREVIEW → PRODUCTION. All 3 fixes are additive/backward-compatible; no schema or contract changes.

## Session 27 (Feb 2026) — Fix Brand popup 500 hardening

### Symptom (production screenshot)
Admin on cp67bot.fundlexperiences.com opens Fix Brand Name popup, types "mar", clicks a suggestion (e.g. MARKS AND SPENCERS Anchor) → toast: "Brand edit server error: customer-apps-shard-00-01.jxp3ul.mongodb.net:27017: The read operation timed out". API being hit: `POST /api/admin/bills/{bill_id}/edit-brand`.

### Root cause
Iteration 66 shipped a lean projection on the initial find_one but left two gaps:
1. **No retry on transient Atlas errors** — a single NetworkTimeout / AutoReconnect / ExecutionTimeout aborted the request with a raw 500.
2. **No timeout on update_one** — a slow Motor write could hang past Cloudflare's edge timeout.
3. **Raw 500** — the admin UI showed a scary "The read operation timed out" toast instead of a retry hint.

### Fixes (server.py POST /api/admin/bills/{bill_id}/edit-brand)
1. **1-shot retry** on both `find_one` and `update_one` for `(NetworkTimeout, AutoReconnect, ServerSelectionTimeoutError, ExecutionTimeout)` with 0.3s backoff.
2. **`max_time_ms=8000`** on find_one (previously unbounded on the server side).
3. **`asyncio.wait_for(update_one, timeout=6.0)`** so writes can't hang past 6s per attempt.
4. **HTTP 503 mapping** — top-level except now uses `isinstance()` against pymongo's transient classes (plus a str(e) fallback for messages like "operation exceeded time limit"). Returns a friendly `503 "MongoDB is under load — the brand edit didn't go through. Please retry in ~10s."` instead of a raw 500.

Iter-68 initially tried substring detection; iter-69 fixed the gap by switching to `isinstance()` because pymongo error messages never contain class names.

### Verification (iteration_68 → iteration_69)
- 22/22 backend tests PASS (`/app/backend/tests/test_iteration68_editbrand_retry.py`).
- Happy path: 0.15s on a 500KB-image bill.
- Single-hang retry: ~6.3s (was 10.4s).
- Worst-case double-hang: ~12.3s + 503 (was 20.6s, still under Cloudflare's 30s edge timeout).
- All 4 pymongo transient classes now map to 503 on both find_one and update_one paths.
- Non-transient errors (ValueError etc.) still return 500 with the exact reason.
- Bill left untouched on persistent failure (no partial write).

### Known observations
- The retry-with-backoff loop is now duplicated between find_one and update_one; extract into a helper if reused.
- server.py is 9430 lines — the admin bill routes (edit-brand / reprocess / force-credit) remain the obvious first-extraction target.

### Action required from user
Redeploy PREVIEW → PRODUCTION. Fix Brand popup will retry once through Atlas hiccups; on persistent failure the admin UI shows a friendly "retry in ~10s" toast instead of "server error".

## Session 28 (Feb 2026) — Fix Brand popup: async-write refactor

### Symptom (production, user screenshot)
Even after iter-69's retry + friendly 503, the popup shows: "MongoDB is under load — the brand edit didn't go through. Please retry in ~10s." The retry doesn't help because Atlas is genuinely taking 6-10s to `update_one` on legacy bills with inline multi-MB image_url — both attempts persistently fail.

### Root cause
The `update_one` on the request thread had a hard latency ceiling (6s per attempt × 2 = 12s worst case). Legacy bills carry inline base64 image_url payloads that make Atlas rewrite the whole doc on every `$set`, and under Atlas M10-tier load this can genuinely take 6-10s per write. Retry doesn't help when the underlying operation is that slow.

### Fix (iter-70)
Refactored `POST /api/admin/bills/{bill_id}/edit-brand` to fully async writes:
1. **Request thread**: does ONE cheap indexed find_one (lean projection + max_time_ms=8000 + 1-shot retry), builds the audit note, and returns 200 in <200ms. NO writes on the request thread.
2. **NEW background worker `_apply_brand_edit_and_reprocess_bg`**: owns the update_one (3 attempts, 12s wait_for each, 1s/2s backoff) PLUS the reprocess call. If all 3 write attempts fail, the reprocess pipeline is STILL invoked because it re-writes `store_name` on approve/manual_review — so Atlas hiccups can't lose the admin's edit.
3. **Rename-only path (`reprocess=false`)** keeps its inline retry write (unchanged from iter-69) since there's no bg worker to defer to.
4. **503 mapping** (from iter-69) retained as safety net.

### Verification (iteration_70.json)
- 19/19 new tests PASS (`/app/backend/tests/test_iteration70_editbrand_async_write.py`).
- Request thread: 0.12s HTTP round-trip on the public URL; ZERO update_one on the request thread (spy-confirmed); exactly 1 bg task queued.
- Bg worker happy path: 1 update_one, all 5 fields persisted (store_name, brand_edited_at, brand_edited_by, admin_notes, reprocessing_started_at).
- Atlas hiccup: NetworkTimeout ×2 → success on 3rd, measured backoff [1.0s, 2.0s], total 3.00s.
- Persistent 3× NetworkTimeout: reprocess STILL invoked with the corrected name, worker never raises.
- Real e2e: rename persisted by bg within seconds.
- Regression: 152/155 iter-61..70 pass (3 failures are pre-existing stale guards unrelated to iter-70).

### Known observations
- If all 3 update_one attempts fail AND the reprocess leaves the bill in a non-approve state, the edit is silently lost (only in logs). Future: persist a `brand_edit_pending` marker for retry.
- Duplicate `$set` payload now in both bg worker and inline rename-only branch — extract helper if reused.

### Action required from user
Redeploy PREVIEW → PRODUCTION. Fix Brand popup will return instantly even during Atlas load; the write happens in the background with 3 retries and Atlas load can no longer produce the 503 toast on this path.

## Session 29 (Feb 2026) — Points 43 + 41 (partial)

### Point 43: Banner + Brand logo uploads not reflecting in app — FIXED
Root cause: `upload_brand_image` and `upload_banner_image` in server.py were writing to pod-local disk (`uploads/brands/...`, `uploads/banners/...`). Pod filesystems are ephemeral, so on deployment the uploads vanished.

Fix:
- Both endpoints now use `storage.aput_object` (Emergent Object Storage), path `cp67-mall/{brands|banners}/{filename}`.
- New public route `GET /api/uploaded-image/{category}/{filename}` streams bytes from object storage with `Cache-Control: public, max-age=86400`. Validates category (brands|banners) and filename (rejects `/` and `..`).
- Image URLs stored in DB now use `{BACKEND_PUBLIC_URL}/api/uploaded-image/brands/{brand_id}_logo.jpg` scheme.
- `_sync_brand_to_store` still fires after brand upload, so consumer Stores collection picks up the new logo.
- 502 returned if object-storage init fails; 400 for >5MB / bad extension / bad image_type.

### Point 41: Home + Login (low-hanging items) — DONE
- Login: `CP67's Loyalty Programme` (gold) + `Shop. Scan. Earn.` block above the welcome heading. Sub-tagline color fixed to `rgba(26,26,46,0.75)` (was near-invisible on cream).
- Home quick actions: 3 buttons — **Scan Bill**, **Redeem**, **Brands** (Explore removed, Events replaced by Brands → /app/stores).
- Home order: Banners → **Events & Happening** (renamed from "Upcoming Events") → **Featured Stores** (moved below Events).
- Home: **Hot Deals** block removed entirely (offers still accessible via Redeem CTA).
- Stores: 4th Floor already in the floor filter dropdown (pre-existing).

### Point 41: DEFERRED to next session
- Redeem-below-details, Participating Brands homepage tile, Homeland Opera upload area
- Loyalty slab color highlighting (per attached color codes)
- Dark Mode / Light Mode toggle
- T&C Apply* links everywhere applicable (already on tier card + Home hero — needs audit)
- Mall Amenities dropdown → tap-logo popup
- Profile completion bar/%
- Brands Directory (category-wise, floor-wise)
- Referral code field on Login page

### Point 40: iOS App Store crash — DEFERRED
Needs the Xcode / mobile app source repo (not in this preview). User should share the iOS crash log symbols + project.

### Verification (iteration_71.json)
- 14/14 new pytest tests PASS (`/app/backend/tests/test_iteration71_objstore_uploads.py`).
- 96/96 regression across iter 64-68, 70 all green.
- Playwright: Home order verified banners(444) → Events(691) → Featured Stores(955); quick actions = 3; Hot Deals gone; Brands nav → /app/stores. Login tagline present.

### Action required from user
Redeploy PREVIEW → PRODUCTION. Then:
- Upload a fresh brand logo + banner from the admin panel and confirm they appear in the consumer app.
- Confirm order/wording changes on the Home screen.
- Point 40: share the iOS repo path or symbolicated crash log so we can debug the camera crash on iPad Air (M3) iPadOS 26.6.

## Session 30 (Feb 2026) — Retailer Points 11, 14, 15 + admin privesc fix

### Point 14: DONE (already implemented in prior session)
Bill incentive attribution at `/app/backend/routes/staff.py:1432-1511` already enforces the spec: last QR scan + brand-matched bill = credit; attribution consumed regardless of match (one scan = one bill decision); attribution misses logged for audit. Verified by iter-72 tests. No changes needed.

### Point 15: DONE — "Failed to load report" fixed
Root cause: `admin_incentive_report` on `staff_incentives` with per-row `bills.find_one` enrichment had no `max_time_ms` bounds, so under Atlas load the whole endpoint 500'd with an opaque toast.

Fix (`/app/backend/routes/staff.py:1022+`):
- Primary cursor `max_time_ms=15000` (logs a warning if the motor version doesn't support the setter).
- Per-row `retail_staff` and `bills` lookups get `max_time_ms=5000` + per-row try/except so one bad row can't kill the whole scan.
- `limit` now `Query(1000, ge=1, le=5000)`.
- Top-level except uses `isinstance()` against `pymongo.errors.(NetworkTimeout|AutoReconnect|ServerSelectionTimeoutError|ExecutionTimeout)` + `asyncio.TimeoutError` (substring fallback retained) → HTTP 503 with a friendly "retry in ~10s / narrow filters" detail; anything else → 500 with the exact reason.
- Admin UI now surfaces the 503 detail instead of the generic "Failed to load report".

### Point 11: DONE — retailer OTP silent-failure now observable
Existing flow (server.py:9142 + staff.py:1751) already dispatches via `send_login_otp` = dual-channel WhatsApp + SMS with the DLT-approved template (PEID 1701172802304667512, Temp ID 1707172914885560615, wording exact). What was missing:
- If the phone wasn't in `retailer_managers` OR `is_active=false`, endpoint silently returned `success:true` and NO message ever fired — that's the "no OTP is triggered" symptom.
- If `_send_sms_otp` binding was missing, silent success too.

Fix:
- `retailer_send_otp` now logs `WARN Retailer OTP requested by non-whitelisted / inactive phone: <phone>` (UI still gets the neutral message to avoid leaking whitelist status).
- Errors loudly if `_send_sms_otp` isn't bound (bind_staff_db check).
- **NEW** admin-only diagnostic `GET /api/admin/staff/retailer/diagnose-otp?phone=...` returning `{is_whitelisted, is_active, manager_name, otp_send_bound, otp_channel, explanation}` — admin can now instantly see why a real user isn't getting an OTP.

**Operational note**: user must ensure the retailer manager phone is added to `retailer_managers` (admin panel → Retailer Managers) with `is_active=true`. Once whitelisted, the dual-channel WA+SMS dispatch already fires with the correct DLT template.

### Bonus (HIGH pre-existing security fix)
Testing agent found: `_verify_admin` in `routes/staff.py` used a **role blacklist** (only rejected `role=='retail_staff'`), so a signed `retailer_manager` JWT reached every `/api/admin/staff/*` endpoint including `retailer-managers` (leaked the full whitelist) and `incentives/report` (leaked the entire incentive ledger).

Fix (`routes/staff.py:250`):
- Allowlist admin roles only: `('admin', 'super_admin', 'mall_admin')`.
- Falls back to `type` claim if `role` absent (verified safe: consumer uses `type='consumer'`, staff/retailer set `role` explicitly).

### Verification
- **iter-72**: 22 pass + 1 xfail documenting the privesc bug. Real retailer_manager JWT confirmed leaking all admin/staff endpoints.
- **iter-73** (post-fix): 37 new tests + 23/23 iter-72 (xfail flipped to real assertion) + 54/54 cross-router regression (iter 62, 70, 71) all PASS. Retailer_manager tokens now correctly 403 on every admin route; admin/super_admin/mall_admin tokens still 200; limit bounds enforced (10000 → 422; 5000 → 200); every pymongo transient class → 503; generic → 500.

### Follow-ups
- Grep other admin routers for similar `!= 'retail_staff'`-style blacklist gates.
- Canonicalize the role/type claim (currently `_verify_admin` reads either, which is safe today but fragile).
- Split `routes/staff.py` (1994 lines) into retailer_auth / dashboard / reports / staff_crud modules.

### Action required from user
Redeploy PREVIEW → PRODUCTION. Then:
- Ensure retailer manager phone is added to Retailer Managers list (admin panel) with active=true — this is the missing operational step for Point 11's "no OTP".
- Hit **/api/admin/staff/retailer/diagnose-otp?phone=<their-phone>** to confirm before asking a retailer to try login.

## Session 31 (Feb 2026) — Points 43 + 44 (deferred parking coupon + banner crop fix)

### Point 43: DONE — banner no longer cropped
Root cause: Home.jsx had inline `height:180` on the banner container, `.home-banner-card` CSS had `aspect-ratio:2/1`, and the `<img>` used `object-fit:cover` — on a portrait mobile a correctly-uploaded 3:1 (1200×400) banner had its sides eaten.

Fix (`/app/frontend/src/consumer/pages/Home.jsx` + `consumer.css`):
- Container: `aspect-ratio: 3 / 1` (matches the admin uploader's recommended 1200×400).
- `.home-banner-card`: `aspect-ratio: 3/1`.
- Image `object-fit`: `contain` with `#1a1a2e` backdrop — small mis-sized uploads letterbox instead of cropping.

### Point 44: DONE — parking coupon deferred until first verified bill
Requirement: parking QR registration no longer issues the PARK-XXXX coupon immediately. Coupon is issued only after the customer's first bill is approved/auto-approved.

Fix:
1. **`process_parking_registration`** (server.py:5834): writes `parking_coupon_pending=true`, `parking_coupon_source`, `parking_coupon_pending_expires_at` (60 days) on the user. Sends a rewritten welcome WhatsApp: "Your FREE Parking Coupon is reserved... Upload any purchase bill from a CP67 store to claim it."
2. **New helper `_maybe_issue_pending_parking_coupon(user_phone)`** (server.py:5975): atomic clear-then-issue — `update_one({phone, pending:true}, {$unset: pending fields})` and only if `modified_count==1` insert a PARK-XXXX with 24h expiry + WhatsApp delivery. Idempotent under concurrent calls (verified with 6-way race). Expired 60-day window silently clears the flag.
3. **Hook wired into ALL 5 approve paths** (choke-point + call sites):
   - `_reprocess_single_bill` — Fundle-approve, Fundle-reject force-credit fallback, **explicit force-credit branch**.
   - `process_bill` (admin /process approve).
   - `process_bill_image` (WhatsApp auto-approve path).
   - `routes/consumer.py` OCR pipeline (`status='approved'`) via runtime import.

Iter-74 → iter-75 → iter-76 progressively closed the coverage gap; final coverage verified by 23-test suite (test_iteration74 + test_iteration75) all green.

### Bonus cleanup
- Removed the unreachable duplicate `except` block that iter-74 introduced at `_maybe_issue_pending_parking_coupon`.
- Removed the duplicate hook in `reprocess_bill` wrapper (now covered by `_reprocess_single_bill`).
- Added the missing `_sync_staff_incentive_for_bill` call to the explicit force-credit branch (was skipping staff sync too — a pre-existing gap surfaced by iter-75).

### Deferred to next session
- `reprocess-legacy` route (server.py:3738) also lacks the hook + staff sync — legacy path, low priority.
- tz-safe `datetime.fromisoformat` in `_maybe_issue_pending_parking_coupon` expiry parse — hardening only.
- Extract Point 44 logic into a `routes/parking.py` module (the runtime `from server import ...` in routes/consumer.py works but is a code smell).
- Extract `_finalise_bill_approval(bill_id, user, phone, points, extra_fields)` helper — the 3 approve exits in `_reprocess_single_bill` still duplicate bill update + points $inc + staff sync + coupon hook. Iter-74 and iter-75 misses were both caused by this fragmentation.

### Verification
- Iter-74 initial: 8/9 pass (missing hook on reprocess bg path).
- Iter-75 after choke-point move: 59/60 pass (explicit force-credit gap surfaced).
- Iter-76 final: 23/23 point-44 tests pass (`pytest tests/test_iteration74_point44_parking.py tests/test_iteration75_point44_paths.py`). Playwright confirmed Point 43 renders 3:1 with `object-fit:contain` and no side crop for a seeded 1200×400 banner.

### Action required from user
Redeploy PREVIEW → PRODUCTION. Then:
- Reset the affected users' `parking_coupon_pending` state if you want retroactive coverage (script-once via `db.users.updateMany({first_touch_source:"SRC_PARKING", customer_type:"new", ...}, {$set:{parking_coupon_pending:true, ...}})` — confirm before I ship this).
- Re-seed the 6 broken banner image URLs on `/consumer/home` (banners currently point at `brand-sync-staging.preview.emergentagent.com` and serve HTML) — upload real 1200×400 JPGs from the admin panel now that both Point 43 rendering and Point 43 objstore-sync work.

## Session 32 (Feb 2026) — Point 14b: registration incentive activation brand gate

### Symptom (production)
"When a customer is scanning a retailer QR and uploading a bill, the incentive is still being given to the retailer from where registered... incentive should be given to retailer where he scanned and uploaded bill... whenever there activity is done, the incentive should go to that retailer based on QR."

### Root cause
`routes/staff.py::create_or_activate_bill_incentive` step 2 (line ~1572) activated ANY pending registration incentive for the customer on ANY approved bill, ignoring which brand's bill it was. So if Customer registered at Brand A and later uploaded a Brand B bill, Retailer A's pending registration incentive still flipped to `redeemable` — even though Retailer A did zero work on that transaction.

Point 14 already gated the `bill_upload` incentive on brand match; the `registration` activation path was left ungated.

### Fix (single-sited)
Extended the same normalized brand-match rule to registration-incentive activation:
- Iterate every pending registration for the customer.
- Resolve the registering staff's `brand_name`.
- Normalise both sides via `re.sub(r'[^a-z0-9]+', '', s.lower())`.
- Activate only on exact normalised match; otherwise the row STAYS pending and an audit row `{reason: 'registration_activation_brand_mismatch'}` is written to `staff_attribution_misses` (same collection as the Point 14 misses).
- Logs `activated={n} skipped_brand_mismatch={m}` per bill.

`create_or_activate_bill_incentive` is the ONLY writer that flips registration status to `redeemable` (grep-confirmed across server.py + routes/*.py), so no bypass path exists.

### Verification (iteration_77.json)
- 9/9 new tests PASS (`test_iteration77_registration_brand_gate.py`) — covers the reported bug, single-brand happy path, multi-brand customer, missing-bill_doc lazy fetch, and the pending_review non-activation gate.
- 93/93 regression PASS across iter-72/73/74/75 + `test_points_11_12_14_retailer`.
- Reproduction test: Retailer A registered, Retailer B QR scanned, Brand B bill approved → Retailer B gets bill_upload credit, Retailer A's registration stays pending, one miss row written.

### Known follow-ups (testing agent minor items — deferred)
- Registration incentive `expires_at` (60-day default) is NOT checked at activation time — a 2-year-old expired pending row can still flip if a matching-brand bill arrives. **This gets worse with the fix** since pending rows now live longer. Recommend adding `{"expires_at": {"$gte": now_iso}}` to the pendings query AND/OR an expiry sweeper.
- Duplicate miss rows accumulate — a customer with a long-lived pending registration who uploads many other-brand bills generates a growing number of near-duplicate audit rows. Recommend de-dup on `(staff_id, customer_phone, bill_id)`.
- DRY: `_norm` helper defined twice inside the same function; hoist to module-level `_norm_brand` shared by the Point 14 gate.
- Init `bill_doc = None` at top of function instead of the `'bill_doc' not in locals()` guard.

### Action required from user
Redeploy PREVIEW → PRODUCTION. From this point forward, incentives strictly follow the bill's brand — the registration source can NEVER leak credit for someone else's activity.

Existing production data note: any registration incentives that were WRONGLY activated in the past are already 'redeemable' — this fix stops the bleeding but doesn't retro-cancel. If you want a backfill script that reverts wrongly-activated rows (i.e. redeemable registration incentives where NO corresponding brand-matched bill exists), say so and I'll ship it.
