# Test Credentials

## Consumer App
- Phone: `9876543210`
- OTP: `1234` (dev mode)

## Admin Dashboard
- Username: `admin`
- Password: `CP67Admin@2025`

## Restricted Admin Roles (Points 45, 46)
- **Bill Operator** — only sees `/bills`
  - Username: `billop`
  - Password: `BillOp@2025`
- **App Manager** — only sees `/banners`, `/offers` (Hot Deals), `/events`, `/campaigns`
  - Username: `appmgr`
  - Password: `AppMgr@2025`

## Parking Staff Login
- **Gate 1**: Username `parking1`, Password `Parking1@2025` — sees only Gate 1 exits
- **Gate 2**: Username `parking2`, Password `Parking2@2025` — sees only Gate 2 exits
- Access: Only Parking Scanner and Parking Report pages
- QR codes: `/api/parking/exit-qr/gate1` and `/api/parking/exit-qr/gate2`

## Parking QR Test
- WhatsApp: Send "Hi! Sign me up for CP67 Rewards | SRC_PARKING" to 917347576767
- Use any non-blocked, non-registered phone number

## Retail Staff Mini-App (Point 19)
- URL: `/staff-app/login`
- Test staff phone: any phone that admin has added via `/staff-incentives`
- OTP: `1234` (dev bypass; real 6-digit OTP is also sent via Karix SMS)
- Sample seed: `9876500001` (staff `HL-0001`, brand `Zara`) — created via API/tests
- Admin management: `/staff-incentives` (Staff / Leaderboard / Redemptions / Slabs tabs)
- Attribution: customer sends WhatsApp msg containing `#STAFF:<qr_token>` → 15-min window


## Android TWA Signing Keystore (PROD)
- Keystore: `/app/twa-build/android.keystore`
- Alias: `android`
- Keystore password: `CP67Mall@2025`
- Key password: `CP67Mall@2025`
- SHA-256: `32:BF:48:D0:63:E1:4C:64:26:7B:59:1B:45:50:97:AE:46:F1:8F:E9:EE:35:4C:B6:BE:BB:03:23:5C:31:40:5E`
- ⚠ Back up the keystore before Play Store submission — losing it means losing the ability to publish updates.

## Play Console / App Store Account
- Email: `Bharat.sharma@fundle.ai`
- Password: `Bharat@123`
