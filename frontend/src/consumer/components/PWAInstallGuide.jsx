import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Smartphone, Download, Share as ShareIcon, MoreVertical } from 'lucide-react';

/**
 * PWA Install Guide — two surfaces:
 *
 * 1) <PWAInstallGuideModal open onClose /> — controlled modal with iOS + Android instructions.
 * 2) <PWAInstallBanner /> — non-intrusive bottom-right pill that offers "Install App";
 *    only shown when the site is not already running in standalone mode AND user
 *    has not dismissed it. Auto-uses beforeinstallprompt on Android when available.
 *
 * Both are safe to mount from anywhere. Dismissal is persisted per browser via localStorage.
 */

const DISMISS_KEY = 'cp67_install_banner_v1';

function isStandalone() {
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    window.navigator.standalone === true
  );
}

function isIOS() {
  return /iPhone|iPad|iPod/i.test(navigator.userAgent);
}

function isAndroid() {
  return /Android/i.test(navigator.userAgent);
}

function useBeforeInstallPrompt() {
  const [deferred, setDeferred] = useState(null);
  useEffect(() => {
    const handler = (e) => { e.preventDefault(); setDeferred(e); };
    window.addEventListener('beforeinstallprompt', handler);
    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);
  return [deferred, setDeferred];
}

export function PWAInstallGuideModal({ open, onClose }) {
  const [deferred, setDeferred] = useBeforeInstallPrompt();
  const ios = isIOS();
  const android = isAndroid();

  const handleInstallNative = async () => {
    if (deferred) {
      deferred.prompt();
      try { await deferred.userChoice; } catch { /* dismissed */ }
      setDeferred(null);
      onClose && onClose();
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="cp-modal-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          data-testid="install-guide-backdrop"
        >
          <motion.div
            className="cp-modal cp-modal-install"
            initial={{ scale: 0.9, y: 16 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.9, y: 16, opacity: 0 }}
            onClick={(e) => e.stopPropagation()}
            data-testid="install-guide-modal"
          >
            <button className="cp-modal-close" onClick={onClose} aria-label="Close" data-testid="install-guide-close">
              <X size={18} />
            </button>
            <div className="cp-modal-icon">
              <Smartphone size={32} />
            </div>
            <h2 style={{ fontFamily: 'var(--font-heading)' }}>Add CP67 to your Home Screen</h2>
            <p>Open it like a regular app and stay signed in across visits — no keystore needed.</p>

            {ios && (
              <div className="cp-install-block" data-testid="install-steps-ios">
                <div className="cp-install-heading"><ShareIcon size={16} /> On iPhone / iPad (Safari)</div>
                <ol className="cp-install-steps">
                  <li>Tap the <strong>Share</strong> button (square with up-arrow) at the bottom of Safari.</li>
                  <li>Scroll down and choose <strong>“Add to Home Screen”</strong>.</li>
                  <li>Tap <strong>Add</strong> — the CP67 icon appears on your home screen.</li>
                </ol>
              </div>
            )}

            {android && (
              <div className="cp-install-block" data-testid="install-steps-android">
                <div className="cp-install-heading"><MoreVertical size={16} /> On Android (Chrome)</div>
                {deferred ? (
                  <p style={{ marginTop: 8 }}>Chrome can install this app in one tap:</p>
                ) : (
                  <ol className="cp-install-steps">
                    <li>Tap the <strong>three-dot menu</strong> in Chrome (top-right).</li>
                    <li>Choose <strong>“Install app”</strong> or <strong>“Add to Home Screen”</strong>.</li>
                    <li>Confirm — the CP67 icon appears on your home screen.</li>
                  </ol>
                )}
              </div>
            )}

            {/* Desktop / other browsers */}
            {!ios && !android && (
              <div className="cp-install-block" data-testid="install-steps-desktop">
                <div className="cp-install-heading"><Download size={16} /> On desktop (Chrome / Edge)</div>
                <ol className="cp-install-steps">
                  <li>Look for the <strong>Install</strong> icon in the address bar (right side).</li>
                  <li>Click it and confirm — CP67 opens as its own app window.</li>
                </ol>
              </div>
            )}

            <div className="cp-modal-actions">
              <button className="cp-btn-ghost" onClick={onClose} data-testid="install-guide-dismiss">
                Close
              </button>
              {android && deferred && (
                <button className="cp-btn-primary" onClick={handleInstallNative} data-testid="install-guide-install-native">
                  <Download size={16} /> Install Now
                </button>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function PWAInstallBanner() {
  const [visible, setVisible] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [deferred] = useBeforeInstallPrompt();

  useEffect(() => {
    if (isStandalone()) return;
    if (localStorage.getItem(DISMISS_KEY)) return;
    // Delay so it doesn't compete with page-load animations.
    const t = setTimeout(() => setVisible(true), 3500);
    return () => clearTimeout(t);
  }, []);

  const dismiss = () => {
    localStorage.setItem(DISMISS_KEY, '1');
    setVisible(false);
  };

  return (
    <>
      <AnimatePresence>
        {visible && (
          <motion.div
            className="cp-install-banner"
            initial={{ y: 60, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 60, opacity: 0 }}
            data-testid="install-banner"
          >
            <div className="cp-install-banner-icon">
              <Download size={16} />
            </div>
            <div className="cp-install-banner-text">
              <strong>Install CP67</strong>
              <span>{deferred ? 'One tap to add to home screen' : 'Add to home screen'}</span>
            </div>
            <button
              className="cp-install-banner-cta"
              onClick={() => setShowModal(true)}
              data-testid="install-banner-cta"
            >
              How
            </button>
            <button
              className="cp-install-banner-close"
              onClick={dismiss}
              aria-label="Dismiss"
              data-testid="install-banner-close"
            >
              <X size={14} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
      <PWAInstallGuideModal open={showModal} onClose={() => setShowModal(false)} />
    </>
  );
}

export default PWAInstallGuideModal;
