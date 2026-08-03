import React, { useEffect } from 'react';

/**
 * Public Privacy Policy — required by Apple App Store 5.1.1 and Google Play.
 * Route: /privacy
 * Kept intentionally plain HTML so App Store review always renders it.
 */
export default function Privacy() {
  useEffect(() => { document.title = 'Privacy Policy · Homeland Advantage'; }, []);

  const updated = 'August 3, 2026';

  return (
    <div style={S.root}>
      <div style={S.container}>
        <h1 style={S.h1}>Privacy Policy</h1>
        <p style={S.sub}>Homeland Advantage · CP67 Mall</p>
        <p style={S.sub}>Last updated: {updated}</p>

        <h2 style={S.h2}>1. Who we are</h2>
        <p style={S.p}>
          Homeland Advantage is a customer loyalty program operated by Homeland
          Group / Fundle Experiences ("we", "us"). This app helps CP67 Mall
          shoppers earn and redeem reward points for their purchases.
        </p>

        <h2 style={S.h2}>2. What data we collect</h2>
        <ul style={S.ul}>
          <li><b>Account:</b> phone number, name, email, gender, date of birth, address (all self-provided).</li>
          <li><b>Transaction:</b> bill images and their extracted details (store, amount, invoice number, date) used to award points.</li>
          <li><b>Loyalty:</b> points balance, redemption history, tier, referral code.</li>
          <li><b>Device:</b> device model, OS version, IP address, app version — for analytics and troubleshooting only.</li>
          <li><b>Push tokens</b> (APNs / FCM) if you opt in to notifications.</li>
        </ul>

        <h2 style={S.h2}>3. How we use it</h2>
        <ul style={S.ul}>
          <li>Verify bill uploads and credit reward points.</li>
          <li>Show your points balance, tier, referral rewards and personalised offers.</li>
          <li>Send WhatsApp / SMS / push messages related to your reward activity (transactional).</li>
          <li>Improve app quality (aggregate, anonymised analytics).</li>
          <li>Prevent fraud and enforce program terms.</li>
        </ul>

        <h2 style={S.h2}>4. Camera & photo access</h2>
        <p style={S.p}>
          The camera is used solely to capture and upload bill images. Photo
          library access is used only when you pick an existing bill photo.
          We never access other photos or media, and we do not scan your gallery.
        </p>

        <h2 style={S.h2}>5. Who we share it with</h2>
        <ul style={S.ul}>
          <li><b>Fundle / TagnPay</b> — our loyalty ledger; receives your phone, bill amount, store, invoice number.</li>
          <li><b>Karix</b> — sends the WhatsApp and SMS OTPs to your phone.</li>
          <li><b>OpenAI / Google (Gemini)</b> — OCRs your bill image; images are sent for text extraction and not retained by us for training.</li>
          <li>We do <b>not</b> sell your data. We do not share it for third-party advertising.</li>
        </ul>

        <h2 style={S.h2}>6. Data retention</h2>
        <p style={S.p}>
          We keep your account data for as long as you have an active
          Homeland Advantage membership. Transactional bill records are
          retained for 7 years for tax and audit purposes (India IT Act
          requirement). When you delete your account (see §8), we anonymise
          the ledger while retaining the audit trail.
        </p>

        <h2 style={S.h2}>7. Your rights</h2>
        <ul style={S.ul}>
          <li>Access or edit your profile inside the app (Profile screen).</li>
          <li>Opt out of push and marketing messages any time in Notification Preferences.</li>
          <li>Request a copy of your data by emailing <a href="mailto:privacy@fundlexperiences.com">privacy@fundlexperiences.com</a>.</li>
        </ul>

        <h2 style={S.h2}>8. Deleting your account</h2>
        <p style={S.p}>
          You can delete your account and personal data at any time:
        </p>
        <ol style={S.ol}>
          <li>Open the Homeland Advantage app.</li>
          <li>Go to <b>Profile</b> (bottom tab).</li>
          <li>Scroll down and tap <b>Delete Account</b>.</li>
          <li>Confirm — your PII (name, email, address, phone) is deleted immediately.</li>
        </ol>
        <p style={S.p}>
          Alternatively, email <a href="mailto:privacy@fundlexperiences.com">privacy@fundlexperiences.com</a> from
          your registered phone/email and we will delete within 7 business days.
        </p>

        <h2 style={S.h2}>9. Children</h2>
        <p style={S.p}>
          Homeland Advantage is not directed at children under 13, and we do
          not knowingly collect data from anyone under 13.
        </p>

        <h2 style={S.h2}>10. Security</h2>
        <p style={S.p}>
          Data is encrypted in transit (TLS 1.2+) and at rest. Access to
          production systems is restricted to authorised staff with 2FA.
        </p>

        <h2 style={S.h2}>11. Changes to this policy</h2>
        <p style={S.p}>
          We may update this policy from time to time. Material changes are
          notified in-app or by email. Continued use of the app after an
          update constitutes acceptance.
        </p>

        <h2 style={S.h2}>12. Contact</h2>
        <p style={S.p}>
          Fundle Experiences Pvt. Ltd.<br />
          CP67 Mall, Sector 67, Sahibzada Ajit Singh Nagar (Mohali), Punjab, India<br />
          Email: <a href="mailto:privacy@fundlexperiences.com">privacy@fundlexperiences.com</a>
        </p>

        <div style={S.footer}>
          <a href="/app/welcome" style={S.link}>Back to Homeland Advantage</a>
        </div>
      </div>
    </div>
  );
}

const S = {
  root: {
    minHeight: '100vh',
    background: '#FAF8F5',
    padding: '40px 20px 80px',
    fontFamily: "'Outfit', system-ui, -apple-system, sans-serif",
    color: '#1E1B18',
    lineHeight: 1.6,
  },
  container: { maxWidth: 720, margin: '0 auto' },
  h1: { fontFamily: "'Playfair Display', serif", fontSize: 34, margin: 0, letterSpacing: '-0.01em' },
  h2: { fontFamily: "'Playfair Display', serif", fontSize: 20, marginTop: 28, marginBottom: 8, color: '#3D3934' },
  sub: { color: '#8B857A', margin: 0, fontSize: 14 },
  p: { color: '#3D3934', fontSize: 15 },
  ul: { color: '#3D3934', fontSize: 15, paddingLeft: 20 },
  ol: { color: '#3D3934', fontSize: 15, paddingLeft: 20 },
  footer: { marginTop: 40, textAlign: 'center', fontSize: 14 },
  link: { color: '#B8860B', textDecoration: 'none', fontWeight: 500 },
};
