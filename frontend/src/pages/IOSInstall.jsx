import React, { useEffect } from 'react';
import { Share, Plus, Check, Smartphone } from 'lucide-react';

/**
 * Public iOS install guide — no auth, no chrome, shareable link.
 * Designed for iPhone Safari but readable on any browser.
 * Route: /ios-install
 */
export default function IOSInstall() {
  useEffect(() => {
    document.title = 'Install Homeland Advantage on iPhone';
  }, []);

  const isIOS = /iPhone|iPad|iPod/i.test(navigator.userAgent);
  const isSafari = /^((?!chrome|android|crios|fxios).)*safari/i.test(navigator.userAgent);
  const isStandalone = window.navigator.standalone === true;

  const shareUrl = window.location.href;
  const copyLink = async () => {
    try { await navigator.clipboard.writeText(shareUrl); alert('Link copied — paste it in WhatsApp/SMS.'); }
    catch { /* ignore */ }
  };

  return (
    <div style={styles.root}>
      <div style={styles.container}>
        <div style={styles.logo}>HA</div>
        <h1 style={styles.h1}>Add Homeland Advantage to your iPhone</h1>
        <p style={styles.subtitle}>
          Open it like a real app. No App Store, no download — just three taps.
        </p>

        {isStandalone && (
          <div style={styles.installedBanner}>
            <Check size={18} /> You're already using the installed app.
          </div>
        )}

        {isIOS && !isSafari && (
          <div style={styles.warningBanner}>
            You're not in <b>Safari</b>. Tap the share icon in your current browser
            → <b>Open in Safari</b> → then follow the steps below.
          </div>
        )}

        <ol style={styles.steps}>
          <li style={styles.step}>
            <div style={styles.stepNum}>1</div>
            <div>
              <div style={styles.stepTitle}>
                <Share size={18} style={{ verticalAlign: '-4px' }} /> Tap the <b>Share</b> button
              </div>
              <div style={styles.stepBody}>
                It's the square icon with an up-arrow — at the <b>bottom</b> of Safari.
              </div>
            </div>
          </li>

          <li style={styles.step}>
            <div style={styles.stepNum}>2</div>
            <div>
              <div style={styles.stepTitle}>
                <Plus size={18} style={{ verticalAlign: '-4px' }} /> Choose <b>Add to Home Screen</b>
              </div>
              <div style={styles.stepBody}>
                Scroll the share menu — you'll see it below Copy, Print, etc.
              </div>
            </div>
          </li>

          <li style={styles.step}>
            <div style={styles.stepNum}>3</div>
            <div>
              <div style={styles.stepTitle}>
                <Check size={18} style={{ verticalAlign: '-4px' }} /> Tap <b>Add</b>
              </div>
              <div style={styles.stepBody}>
                The Homeland Advantage icon appears on your home screen. Tap it any time to open the app instantly.
              </div>
            </div>
          </li>
        </ol>

        <div style={styles.diagramBox}>
          <div style={styles.diagramTitle}>Where to find the Share button</div>
          <svg viewBox="0 0 320 180" style={{ width: '100%', maxWidth: 320 }} aria-label="Share button location diagram">
            {/* Phone frame */}
            <rect x="60" y="10" width="200" height="160" rx="18" fill="#1B1B1E" stroke="#333" strokeWidth="2" />
            {/* Screen */}
            <rect x="70" y="20" width="180" height="130" rx="6" fill="#0B0B0E" />
            {/* URL bar */}
            <rect x="80" y="130" width="160" height="14" rx="7" fill="#2A2A2E" />
            {/* Share icon */}
            <g transform="translate(210, 132)">
              <rect x="-2" y="-2" width="18" height="18" rx="4" fill="none" stroke="#FFB300" strokeWidth="1.5" />
              <path d="M7 10 V2 M4 5 L7 2 L10 5" stroke="#FFB300" strokeWidth="1.5" fill="none" strokeLinecap="round" />
              <rect x="3" y="7" width="8" height="6" fill="none" stroke="#FFB300" strokeWidth="1.2" />
            </g>
            {/* Arrow pointing to share */}
            <path d="M280 145 Q 260 130 236 138" stroke="#FFB300" strokeWidth="2" fill="none" strokeDasharray="3,3" />
            <text x="285" y="150" fontSize="11" fill="#FFB300" fontFamily="system-ui">Tap here</text>
            {/* Home indicator */}
            <rect x="145" y="158" width="30" height="3" rx="1.5" fill="#555" />
          </svg>
        </div>

        <div style={styles.actionsRow}>
          <button style={styles.shareBtn} onClick={copyLink} data-testid="copy-guide-link">
            Copy this guide's link to share
          </button>
        </div>

        <div style={styles.faq}>
          <div style={styles.faqTitle}>Common questions</div>
          <details style={styles.faqItem}>
            <summary style={styles.faqQ}>Why can't I find "Add to Home Screen"?</summary>
            <div style={styles.faqA}>
              You need to be in <b>Safari</b>, not Chrome / Instagram / WhatsApp browser.
              If this page opened inside another app, tap the top-right menu →{' '}
              <b>Open in Safari / Open in browser</b>, then try again.
            </div>
          </details>
          <details style={styles.faqItem}>
            <summary style={styles.faqQ}>Does it need updates from the App Store?</summary>
            <div style={styles.faqA}>
              No. The app updates automatically the next time you open it — same as our website.
            </div>
          </details>
          <details style={styles.faqItem}>
            <summary style={styles.faqQ}>Will it work offline?</summary>
            <div style={styles.faqA}>
              It caches the app shell, so the last-seen screens open instantly. Points, offers,
              and bill uploads still need internet.
            </div>
          </details>
          <details style={styles.faqItem}>
            <summary style={styles.faqQ}>Can I remove it later?</summary>
            <div style={styles.faqA}>
              Yes — long-press the Homeland Advantage icon on the home screen → <b>Remove App</b>.
            </div>
          </details>
        </div>

        <div style={styles.footer}>
          Homeland Advantage · CP67 Mall<br />
          <a href="/app/welcome" style={styles.footerLink}>Open the app in this browser</a>
        </div>
      </div>
    </div>
  );
}

const styles = {
  root: {
    minHeight: '100vh',
    background: 'linear-gradient(180deg, #FAF8F5 0%, #F3EFE8 100%)',
    padding: '32px 20px 80px',
    fontFamily: "'Outfit', system-ui, -apple-system, sans-serif",
    color: '#1E1B18',
  },
  container: {
    maxWidth: 520,
    margin: '0 auto',
  },
  logo: {
    width: 64,
    height: 64,
    borderRadius: 16,
    background: 'linear-gradient(135deg, #B8860B, #DAA520)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 26,
    fontWeight: 800,
    color: '#FFF',
    margin: '0 auto 24px',
    boxShadow: '0 8px 24px rgba(184, 134, 11, 0.35)',
  },
  h1: {
    fontFamily: "'Playfair Display', serif",
    fontSize: 30,
    lineHeight: 1.2,
    textAlign: 'center',
    margin: 0,
    fontWeight: 700,
    letterSpacing: '-0.01em',
  },
  subtitle: {
    textAlign: 'center',
    color: '#635E56',
    marginTop: 8,
    marginBottom: 28,
    fontSize: 15,
  },
  installedBanner: {
    background: '#E7F5EC',
    color: '#1E7A3A',
    padding: '10px 14px',
    borderRadius: 10,
    display: 'flex',
    gap: 8,
    alignItems: 'center',
    fontSize: 14,
    marginBottom: 20,
  },
  warningBanner: {
    background: '#FFF4E5',
    color: '#8A5A00',
    padding: '10px 14px',
    borderRadius: 10,
    fontSize: 13.5,
    marginBottom: 20,
    lineHeight: 1.5,
  },
  steps: {
    listStyle: 'none',
    padding: 0,
    margin: 0,
  },
  step: {
    display: 'flex',
    gap: 14,
    padding: '18px 18px',
    background: '#FFF',
    borderRadius: 14,
    border: '1px solid rgba(184, 134, 11, 0.15)',
    boxShadow: '0 2px 6px rgba(0,0,0,0.03)',
    marginBottom: 12,
  },
  stepNum: {
    flexShrink: 0,
    width: 36,
    height: 36,
    borderRadius: 999,
    background: 'linear-gradient(135deg, #B8860B, #DAA520)',
    color: '#FFF',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontWeight: 700,
    fontSize: 16,
  },
  stepTitle: {
    fontWeight: 600,
    fontSize: 15.5,
    marginBottom: 4,
  },
  stepBody: {
    color: '#635E56',
    fontSize: 14,
    lineHeight: 1.5,
  },
  diagramBox: {
    marginTop: 24,
    padding: 18,
    background: '#FFF',
    borderRadius: 14,
    border: '1px solid rgba(184, 134, 11, 0.15)',
    textAlign: 'center',
  },
  diagramTitle: {
    fontSize: 13,
    color: '#635E56',
    marginBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
  },
  actionsRow: {
    display: 'flex',
    justifyContent: 'center',
    marginTop: 24,
  },
  shareBtn: {
    padding: '12px 22px',
    background: '#1E1B18',
    color: '#FFF',
    border: 'none',
    borderRadius: 10,
    fontSize: 14.5,
    fontWeight: 500,
    cursor: 'pointer',
  },
  faq: {
    marginTop: 32,
  },
  faqTitle: {
    fontSize: 13,
    color: '#635E56',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    marginBottom: 8,
  },
  faqItem: {
    background: '#FFF',
    borderRadius: 10,
    padding: '12px 14px',
    marginBottom: 8,
    border: '1px solid rgba(184, 134, 11, 0.12)',
  },
  faqQ: {
    cursor: 'pointer',
    fontWeight: 500,
    fontSize: 14.5,
    listStyle: 'none',
  },
  faqA: {
    color: '#635E56',
    fontSize: 14,
    marginTop: 8,
    lineHeight: 1.5,
  },
  footer: {
    textAlign: 'center',
    color: '#8B857A',
    fontSize: 12,
    marginTop: 40,
    lineHeight: 1.6,
  },
  footerLink: {
    color: '#B8860B',
    textDecoration: 'none',
    fontWeight: 500,
  },
};
