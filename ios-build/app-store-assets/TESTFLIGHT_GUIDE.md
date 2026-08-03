# TestFlight Beta — 100-user distribution guide

TestFlight lets you distribute the iOS build to up to **10,000** external testers
without going through App Store review each time. Great for CP67 mall staff
and VIP shoppers to bang on the build before public launch.

---

## Prerequisites
- The Homeland Advantage app must already exist in App Store Connect
  *(create it once via the guide in `APP_STORE_LISTING.md`)*
- You've uploaded a build via Xcode → Archive → Distribute → Upload
  *(the build shows up in App Store Connect → **TestFlight** tab within 10-15 min)*

---

## 1. Internal Testing (Apple team, up to 100 testers, instant)

Internal testers must have a role on your App Store Connect team
(Admin, Developer, Marketing, App Manager). They get the build **within minutes** of
upload — no Apple review required.

1. App Store Connect → Your App → **TestFlight** tab
2. Left sidebar → **Internal Testing** → **+**
3. Name the group (e.g. "CP67 Mall Staff")
4. Tick "Enable automatic distribution" (new builds auto-invited)
5. Add users by their Apple ID / email
6. Save

Each tester gets an email → they install the **TestFlight** app from the App Store → tap the invite link → app appears in TestFlight.

---

## 2. External Testing (up to 10,000, needs a one-time Apple review)

Use this for VIP shoppers, brand partners, or a public beta programme.

### 2a. Create an external group

1. TestFlight tab → **External Testing** → **+ Create New Group**
2. Name: e.g. "CP67 VIP Beta"
3. Description shown to testers: e.g. "Get early access to the CP67 mall rewards app before public launch."
4. Save

### 2b. Add testers (3 ways)

**By email** — paste up to 100 emails at a time
```
TestFlight → External Testing → your group → Testers tab → + → Add New Testers
```

**Via public invite link** — best for viral distribution
```
TestFlight → External Testing → your group → Test Information → Enable Public Link
→ Set enrollment limit (e.g. 500 initial slots)
→ Copy the link (looks like https://testflight.apple.com/join/AbCd123)
```
Share the link on WhatsApp, email newsletter, or a QR code at the mall
information desk.

**Via CSV import** — for bulk mall-member migrations
```
TestFlight → External Testing → your group → Testers → + → Import from CSV
CSV columns: Email, First Name, Last Name (headerless format works too)
```

### 2c. Submit build for TestFlight review

External TestFlight builds need Apple approval **once per version** (usually
under 24 hours; often within 2-4 hours for well-formed builds).

1. TestFlight tab → **iOS Builds** → click your build
2. Fill in test info if prompted:
   - **What to Test**: "Please try uploading a bill and check that points are credited within 60 seconds. Report any camera or login issues via the support email in the app."
   - **Beta App Description**: same as your App Store description (or shorter)
   - **Feedback Email**: `beta@fundlexperiences.com`
   - **Contact Email + First/Last Name** (required for review)
3. Submit for review

Once approved, all external testers get an email + push. New builds within
the same version letter (e.g. 1.0 → 1.1 → 1.2) are auto-approved for the
same group.

---

## 3. First-tester experience

Send them these 4 lines:

```
Hi! You're invited to test the Homeland Advantage app for CP67 Mall on your iPhone.

1) Install "TestFlight" from the App Store (free)
2) Tap this link on your iPhone: <paste-your-invite-link>
3) Tap "Install" on the Homeland Advantage row
4) Open the app, sign in with your phone number

Feedback / bugs → beta@fundlexperiences.com  or  shake your phone inside the app.
```

---

## 4. Shake-to-report feedback

TestFlight has a **built-in feedback system**: when a tester takes a screenshot
inside a TestFlight build and shares it, Apple attaches the device details
and forwards it to your App Store Connect inbox at **TestFlight → Feedback**.

Nothing you need to code — it's free with TestFlight.

---

## 5. Beta churn / retire testers

- TestFlight builds **expire 90 days** after upload. If you don't ship a new
  build within 90 days, testers get "This beta has expired". Rebuild + reupload.
- Testers can be removed from a group any time. Their app icon greys out.

---

## 6. Recommended beta cadence for CP67 launch

| Week | Action |
|---|---|
| 1 | Internal group only — CP67 mall admin team of 5-10 people |
| 2 | External group A — 30 friendly VIP shoppers via email invite |
| 3 | External group B — public link + QR code at info desk (300 slots) |
| 4 | Fix top-5 reported issues, upload build 1.1, keep beta open |
| 5 | Submit v1.1 to App Store for public release |
