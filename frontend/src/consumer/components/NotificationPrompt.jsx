import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Bell, BellOff, X, Smartphone, Download } from 'lucide-react';
import {
  registerServiceWorker,
  shouldPromptForNotifications,
  requestNotificationPermission,
  subscribeUserToPush,
  markPromptShown,
} from '../push';

/**
 * Two-step onboarding shown on first launch:
 * 1) "Enable notifications" prompt with friendly explanation.
 * 2) For iOS Safari (or non-installed PWA), a quick "Add to Home Screen" guide.
 *
 * The component is self-contained — mount it once at the top of ConsumerApp
 * and it'll only render when needed.
 */

const INSTALL_FLAG = 'cp67_install_guide_v1';

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

export default function NotificationPrompt({ token }) {
  const [showNotif, setShowNotif] = useState(false);
  const [showInstall, setShowInstall] = useState(false);
  const [deferredPrompt, setDeferredPrompt] = useState(null);

  useEffect(() => {
    // Register SW unconditionally so push handler exists when subscribed later.
    registerServiceWorker();

    // Capture native beforeinstallprompt for Android Chrome.
    const handler = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
    };
    window.addEventListener('beforeinstallprompt', handler);

    // Decide what to show. Delay 1.5s so the home screen renders first.
    const t = setTimeout(() => {
      if (token && shouldPromptForNotifications()) {
        setShowNotif(true);
      } else if (
        token &&
        !isStandalone() &&
        !localStorage.getItem(INSTALL_FLAG) &&
        (isIOS() || isAndroid())
      ) {
        setShowInstall(true);
      }
    }, 1500);

    return () => {
      clearTimeout(t);
      window.removeEventListener('beforeinstallprompt', handler);
    };
  }, [token]);

  const handleEnable = async () => {
    const res = await requestNotificationPermission();
    setShowNotif(false);
    if (res === 'granted') {
      await subscribeUserToPush(token);
      // Optional: show install guide next, if not installed
      if (!isStandalone() && !localStorage.getItem(INSTALL_FLAG)) {
        setTimeout(() => setShowInstall(true), 600);
      }
    }
  };

  const handleSkip = () => {
    markPromptShown();
    setShowNotif(false);
    if (!isStandalone() && !localStorage.getItem(INSTALL_FLAG)) {
      setTimeout(() => setShowInstall(true), 400);
    }
  };

  const handleInstallNative = async () => {
    if (deferredPrompt) {
      deferredPrompt.prompt();
      try { await deferredPrompt.userChoice; } catch { /* user dismissed */ }
      setDeferredPrompt(null);
    }
    localStorage.setItem(INSTALL_FLAG, '1');
    setShowInstall(false);
  };

  const dismissInstall = () => {
    localStorage.setItem(INSTALL_FLAG, '1');
    setShowInstall(false);
  };

  return (
    <AnimatePresence>
      {showNotif && (
        <motion.div
          className="cp-modal-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={handleSkip}
          data-testid="notif-prompt-backdrop"
        >
          <motion.div
            className="cp-modal cp-modal-notif"
            initial={{ scale: 0.9, y: 16 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.9, y: 16, opacity: 0 }}
            onClick={(e) => e.stopPropagation()}
            data-testid="notif-prompt"
          >
            <button className="cp-modal-close" onClick={handleSkip} aria-label="Close" data-testid="notif-prompt-close">
              <X size={18} />
            </button>
            <div className="cp-modal-icon">
              <Bell size={32} />
            </div>
            <h2>Stay in the loop</h2>
            <p>
              Get instant alerts about new offers, points credited, redemption
              confirmations and exclusive CP67 events.
            </p>
            <div className="cp-modal-actions">
              <button className="cp-btn-ghost" onClick={handleSkip} data-testid="notif-prompt-skip">
                <BellOff size={16} /> Maybe later
              </button>
              <button className="cp-btn-primary" onClick={handleEnable} data-testid="notif-prompt-enable">
                <Bell size={16} /> Enable notifications
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}

      {showInstall && (
        <motion.div
          className="cp-modal-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={dismissInstall}
          data-testid="install-prompt-backdrop"
        >
          <motion.div
            className="cp-modal cp-modal-install"
            initial={{ scale: 0.9, y: 16 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.9, y: 16, opacity: 0 }}
            onClick={(e) => e.stopPropagation()}
            data-testid="install-prompt"
          >
            <button className="cp-modal-close" onClick={dismissInstall} aria-label="Close" data-testid="install-prompt-close">
              <X size={18} />
            </button>
            <div className="cp-modal-icon">
              <Smartphone size={32} />
            </div>
            <h2>Add CP67 to your Home Screen</h2>
            <p>Open it like a regular app and stay signed in across visits.</p>

            {isIOS() && (
              <ol className="cp-install-steps" data-testid="install-steps-ios">
                <li>Tap the <strong>Share</strong> button in Safari (square with up-arrow).</li>
                <li>Scroll down and choose <strong>“Add to Home Screen”</strong>.</li>
                <li>Tap <strong>Add</strong> — you’ll see the CP67 icon on your home screen.</li>
              </ol>
            )}

            {isAndroid() && (
              <>
                {deferredPrompt ? (
                  <p style={{ marginTop: 12 }}>
                    Tap the button below — Chrome will ask you to install the
                    app.
                  </p>
                ) : (
                  <ol className="cp-install-steps" data-testid="install-steps-android">
                    <li>Tap the <strong>three-dot menu</strong> in Chrome (top right).</li>
                    <li>Choose <strong>“Install app”</strong> or <strong>“Add to Home Screen”</strong>.</li>
                    <li>Confirm to add the CP67 icon to your home screen.</li>
                  </ol>
                )}
              </>
            )}

            <div className="cp-modal-actions">
              <button className="cp-btn-ghost" onClick={dismissInstall} data-testid="install-prompt-skip">
                Not now
              </button>
              {isAndroid() && deferredPrompt && (
                <button className="cp-btn-primary" onClick={handleInstallNative} data-testid="install-prompt-install">
                  <Download size={16} /> Install
                </button>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
