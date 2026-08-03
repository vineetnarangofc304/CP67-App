# Homeland Advantage — iOS App Build

This folder contains the native iOS wrapper (SwiftUI + WKWebView) around the
Homeland Advantage PWA hosted at `https://mall-rewards-1.emergent.host/app/*`.

## What's in here

```
ios-build/
├── project.yml                          # XcodeGen spec (generates .xcodeproj)
├── CP67iOS/
│   ├── CP67App.swift                    # SwiftUI @main entry
│   ├── ContentView.swift                # Root view — cream splash → WKWebView
│   ├── WebViewContainer.swift           # WKWebView + JS bridge (camera + gallery)
│   ├── AppDelegate.swift                # APNs registration
│   ├── Info.plist                       # Permissions, orientation, ATS, URL schemes
│   ├── CP67iOS.entitlements             # Universal Links + Push env
│   ├── LaunchScreen.storyboard          # Cream splash w/ "Homeland Advantage" label
│   └── Assets.xcassets/                 # AppIcon slot (drop your 1024×1024 PNG here)
```

The camera bridge mirrors your Android `AndroidBridge` exactly:
- Web calls `window.iOSBridge.openCamera()`
- Native launches `UIImagePickerController` with camera
- User captures → downscaled to 1600px longest edge → JPEG 82% → base64
- Native calls `window.__cp67OnCameraResult(dataUrl)` — same handler your Android build uses

`BillUpload.jsx` will pick this up automatically because `window.__cp67Native` is set.

---

## Build on your Mac (~30 min first time)

### 0. One-time Mac setup

```bash
# Install Xcode from the Mac App Store first (~15 GB).
xcode-select --install                              # Command-line tools
sudo xcodebuild -license accept                     # Accept Xcode licence
brew install xcodegen                               # Generates the .xcodeproj from project.yml
```

### 1. Get the project onto your Mac

```bash
# Copy the whole ios-build/ folder from Emergent to your Mac.
# Options:
#   a) Save to GitHub → clone on Mac
#   b) Emergent → Download Code → unzip on Mac
```

### 2. Add your app icon

Export a **1024×1024 PNG** of the Homeland Advantage icon and save as
`CP67iOS/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png`.

Xcode will auto-generate the smaller sizes.

### 3. Generate the Xcode project

```bash
cd ios-build
xcodegen generate
open CP67iOS.xcodeproj
```

### 4. Configure signing

In Xcode:
1. Click the **CP67iOS** target in the sidebar
2. **Signing & Capabilities** tab
3. Tick **Automatically manage signing**
4. **Team** → sign in with your Apple ID → pick your team
5. Bundle ID auto-suggests `com.fundle.cp67ios` — leave as-is (or change if you registered a different one)
6. Under **Capabilities**, verify these are present (auto-added from entitlements):
   - Push Notifications
   - Associated Domains (`applinks:mall-rewards-1.emergent.host`)

### 5. First run on a real device

1. Connect an iPhone via USB
2. Xcode → top bar → select your device
3. Cmd + R (Run)
4. First-run: iPhone → Settings → General → VPN & Device Management → trust your dev cert

Test:
- App loads the PWA splash → wallet screen
- Tap **Upload Bill → Camera** → iOS asks permission → camera opens → capture → OCR runs

### 6. Push notifications setup (do once)

In App Store Connect:
1. **Users and Access** → **Keys** → **APNs** → create an "APNs Auth Key" (.p8 file)
2. Save the key ID + team ID
3. In your backend, upload the .p8 to whatever push service you use (Firebase, OneSignal, or direct APNs)

The Swift code already registers for remote notifications and forwards the APNs token to the webview via `window.__cp67APNsToken` — your PWA push code can grab it and send to backend.

---

## Ship to App Store (~1 hour)

### 1. Bump version

`project.yml` → `MARKETING_VERSION: "1.0"` and `CURRENT_PROJECT_VERSION: "1"`.
Increment `CURRENT_PROJECT_VERSION` for every TestFlight/App Store upload.

### 2. Archive

Xcode:
1. Top bar → device dropdown → **Any iOS Device (arm64)**
2. **Product → Archive** (5-10 min)
3. When Organizer opens → **Distribute App → App Store Connect → Upload**
4. Select automatic signing → Upload

### 3. App Store Connect listing

https://appstoreconnect.apple.com → My Apps → **+** → New App

| Field | Value |
|---|---|
| Platform | iOS |
| Name | Homeland Advantage |
| Primary Language | English (India) |
| Bundle ID | `com.fundle.cp67ios` |
| SKU | homeland-advantage-ios |
| Category (primary) | Shopping |
| Category (secondary) | Lifestyle |

### 4. App Information (once)

- **Privacy Policy URL**: `https://mall-rewards-1.emergent.host/privacy`
- **Copyright**: `© 2026 Fundle Experiences`
- **Age Rating**: run questionnaire → 4+ likely

### 5. Version metadata (per release)

- **Description**: (draft below)
- **Keywords**: `mall,rewards,loyalty,cp67,homeland,advantage,shopping,points,parking,offers`
- **Support URL**: `https://mall-rewards-1.emergent.host/support`
- **Marketing URL** (optional): your marketing site
- **Screenshots** — required sizes:
  - **6.7" (iPhone 15 Pro Max)**: 1290 × 2796 — at least 3
  - **6.5" (iPhone 14 Plus)**: 1242 × 2688 — optional but recommended
  - Take these by running the app on iPhone 15 Pro Max simulator + Cmd+S

Suggested screenshots to capture:
1. Login screen (welcome to Homeland Advantage)
2. Wallet card showing tier + points
3. Bill upload screen
4. Store directory
5. Offers/hot deals grid

### 6. Test Account

Apple review team will use this — **must** be filled or auto-reject.

Under "App Review Information":
- **Sign-in required**: YES
- **User name**: `9876543210`
- **Password**: leave blank (OTP-based)
- **Notes**: paste this exactly:

  > This app uses phone + OTP login. To test:
  > 1. Enter phone `9876543210`
  > 2. Tap "Send OTP"
  > 3. Enter OTP `1234` (dev bypass enabled for reviewers)
  > 4. Full dashboard loads with sample loyalty data.
  >
  > Account deletion is available under Profile → Delete Account.

### 7. Submit

- Click **Add for Review** → **Submit for Review**
- Typical review time: **24-72 hours**

If rejected, Apple usually points to a specific guideline — common ones for wrapped web-apps:

| Guideline | Fix |
|---|---|
| 4.2 Minimum Functionality | Add more native features (camera, push, universal links) — already handled ✅ |
| 5.1.1 Data Collection | Fill "App Privacy" section accurately |
| 2.3.7 Metadata | Screenshots must reflect actual iPhone app, not web/Android |
| 5.1.1(v) Account Deletion | Delete Account must be reachable in ≤2 taps (implemented at Profile → Delete) ✅ |

---

## Suggested App Store description

```
Homeland Advantage — the exclusive rewards app for CP67 Mall.

Earn points every time you shop, dine, and celebrate at CP67. Redeem across
150+ participating brands. Track your tier journey from Bronze to Diamond
and unlock premium benefits along the way.

WHAT YOU CAN DO
• Upload bills to earn instant reward points
• Track your tier and points balance in one place
• Discover hot deals and exclusive brand offers
• Get free parking coupons for new members
• Attend member-only events and celebrations
• Refer friends and earn bonus rewards

BUILT FOR CP67 SHOPPERS
The Homeland Advantage program brings together your favourite brands under
one loyalty wallet — no more juggling paper cards or forgotten coupons.

Homeland Advantage · CP67 Mall
```

---

## Files that reference the production URL

If you ever change the production domain, edit **only** these places:

1. `CP67iOS/ContentView.swift` — `appURL`
2. `CP67iOS/CP67iOS.entitlements` — `applinks:*` entries
3. `CP67iOS/Info.plist` — `NSAppTransportSecurity` exception domains

The rest is domain-agnostic.
