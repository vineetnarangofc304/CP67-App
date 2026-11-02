import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import BottomNav from './components/BottomNav';
import SideDrawer from './components/SideDrawer';
import InAppPopup from './components/InAppPopup';
import NotificationPrompt from './components/NotificationPrompt';
import Welcome from './pages/Welcome';
import Login from './pages/Login';
import Onboarding from './pages/Onboarding';
import Home from './pages/Home';
import Stores from './pages/Stores';
import StoreDetail from './pages/StoreDetail';
import Wallet from './pages/Wallet';
import BillUpload from './pages/BillUpload';
import Events from './pages/Events';
import Offers from './pages/Offers';
import Profile from './pages/Profile';
import Notifications from './pages/Notifications';
import ProgramInfo from './pages/ProgramInfo';
import Transactions from './pages/Transactions';
import BillHistory from './pages/BillHistory';
import Rewards from './pages/Rewards';
import HelpSupport from './pages/HelpSupport';
import Legal from './pages/Legal';
import NotificationPrefs from './pages/NotificationPrefs';
import MallMap from './pages/MallMap';
import Amenities from './pages/Amenities';
import Referrals from './pages/Referrals';
import RedeemBrands from './pages/RedeemBrands';
import TierJourney from './pages/TierJourney';

const API = process.env.REACT_APP_BACKEND_URL + '/api/consumer';

const ConsumerAuthContext = createContext(null);
export const useConsumerAuth = () => useContext(ConsumerAuthContext);
export { API };

const ConsumerAuthProvider = ({ children }) => {
  const [token, setToken] = useState(localStorage.getItem('cp67_consumer_token'));
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchProfile = useCallback(async (t) => {
    try {
      const res = await fetch(`${API}/profile`, {
        headers: { 'Authorization': `Bearer ${t}` }
      });
      if (res.ok) {
        const data = await res.json();
        setUser(data);
        return data;
      }
      // Only clear the session if the server explicitly says the token is bad.
      // Anything else (5xx, network blip, TagnPay timeout) must NOT log the user out —
      // this was the root cause of "OTP every reopen" reported by CP67 team.
      if (res.status === 401 || res.status === 403) {
        localStorage.removeItem('cp67_consumer_token');
        setToken(null);
        setUser(null);
      }
      return null;
    } catch {
      // Network error: keep token, user can retry. Don't force re-login.
      return null;
    }
  }, []);

  useEffect(() => {
    if (token) {
      fetchProfile(token).finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [token, fetchProfile]);

  const login = (t, u) => {
    localStorage.setItem('cp67_consumer_token', t);
    setToken(t);
    setUser(u);
  };

  const logout = () => {
    localStorage.removeItem('cp67_consumer_token');
    setToken(null);
    setUser(null);
  };

  const refreshProfile = () => token && fetchProfile(token);

  // iOS APNs token auto-register — fires when the native shell posts
  // window.__cp67APNsToken (see WebViewContainer.swift). Idempotent.
  useEffect(() => {
    if (!token) return;
    const register = async (apnsToken) => {
      if (!apnsToken) return;
      try {
        await fetch(`${API}/push/apns/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify({
            apns_token: apnsToken,
            bundle_id: 'com.fundle.cp67ios',
            device_model: navigator.userAgent,
            os_version: (navigator.userAgent.match(/OS (\d+_\d+)/) || [])[1] || '',
            app_version: '1.0',
          }),
        });
      } catch { /* silent */ }
    };
    // If token already present at page load
    if (window.__cp67APNsToken) register(window.__cp67APNsToken);
    // Or when native pushes it later
    const handler = (e) => register(e.detail);
    window.addEventListener('apnsTokenReady', handler);
    return () => window.removeEventListener('apnsTokenReady', handler);
  }, [token]);

  return (
    <ConsumerAuthContext.Provider value={{ token, user, login, logout, loading, refreshProfile, API }}>
      {children}
    </ConsumerAuthContext.Provider>
  );
};

const ProtectedConsumer = ({ children }) => {
  const { token, loading, user } = useConsumerAuth();
  if (loading) return <div className="consumer-loading boot" data-testid="app-boot-loader"><img src="/ha-logo-full.png" alt="Homeland Advantage" className="consumer-boot-logo" /><div className="consumer-spinner" /></div>;
  if (!token) return <Navigate to="/app/login" replace />;
  if (user && !user.onboarding_complete && window.location.pathname !== '/app/onboarding') {
    return <Navigate to="/app/onboarding" replace />;
  }
  return children;
};

const hideNav = ['/app/welcome', '/app/login', '/app/onboarding', '/app/legal'];

// Load Google Fonts on demand & inject dynamic font CSS variables.
async function applyAppSettings() {
  try {
    const r = await fetch(`${API}/app-settings`);
    if (!r.ok) return;
    const d = await r.json();
    const s = d.settings || {};
    const heading = s.heading_font_family || 'Antique Olive';
    const content = s.content_font_family || 'Antique Olive';
    const hScale = Number(s.heading_font_size_scale) || 1.0;
    const cScale = Number(s.content_font_size_scale) || 1.0;
    const hWeight = Number(s.heading_font_weight) || 700;
    const cWeight = Number(s.content_font_weight) || 400;

    // Lazy-load Google Fonts for any non-default family
    const nonDefault = new Set();
    if (heading && heading !== 'Antique Olive') nonDefault.add(heading);
    if (content && content !== 'Antique Olive' && content !== heading) nonDefault.add(content);
    nonDefault.forEach((family) => {
      const id = 'gf-' + family.replace(/\s+/g, '-').toLowerCase();
      if (!document.getElementById(id)) {
        const link = document.createElement('link');
        link.id = id;
        link.rel = 'stylesheet';
        link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(family)}:wght@300;400;500;600;700;800&display=swap`;
        document.head.appendChild(link);
      }
    });

    const root = document.documentElement;
    root.style.setProperty('--font-heading', `'${heading}', 'Playfair Display', serif`);
    root.style.setProperty('--font-body', `'${content}', 'Outfit', -apple-system, sans-serif`);
    root.style.setProperty('--font-heading-scale', String(hScale));
    root.style.setProperty('--font-body-scale', String(cScale));
    root.style.setProperty('--font-heading-weight', String(hWeight));
    root.style.setProperty('--font-body-weight', String(cWeight));
  } catch { /* silent — defaults remain */ }
}

export default function ConsumerApp() {
  const location = useLocation();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const showBottomNav = !hideNav.includes(location.pathname);

  // Fetch admin-set font settings on first mount + refresh every 5 min so
  // admin changes propagate to already-open consumer sessions eventually.
  useEffect(() => {
    applyAppSettings();
    const iv = setInterval(applyAppSettings, 5 * 60 * 1000);
    return () => clearInterval(iv);
  }, []);

  return (
    <ConsumerAuthProvider>
      <ConsumerShell drawerOpen={drawerOpen} setDrawerOpen={setDrawerOpen} showBottomNav={showBottomNav} location={location} />
    </ConsumerAuthProvider>
  );
}

function ConsumerShell({ drawerOpen, setDrawerOpen, showBottomNav, location }) {
  const { token } = useConsumerAuth();
  return (
    <div className="consumer-app">
      <SideDrawer isOpen={drawerOpen} onClose={() => setDrawerOpen(false)} />
      <InAppPopup />
      {/* NotificationPrompt disabled per CP67 team request — no pop-up on login.
          Users can enable notifications via Profile → Notification Settings. */}
      {/* {token && <NotificationPrompt token={token} />} */}
      {/* PWA Install Banner removed per CP67 team request (Point 7, Feb 8 2026).
          The Install App option is still available via the SideDrawer menu. */}
      {/* {token && <PWAInstallBanner />} */}
      <AnimatePresence mode="wait">
        <Routes location={location} key={location.pathname}>
          <Route path="welcome" element={<Welcome />} />
          <Route path="login" element={<Login />} />
          <Route path="onboarding" element={<ProtectedConsumer><Onboarding /></ProtectedConsumer>} />
          <Route path="home" element={<ProtectedConsumer><Home onMenuOpen={() => setDrawerOpen(true)} /></ProtectedConsumer>} />
          <Route path="stores" element={<ProtectedConsumer><Stores /></ProtectedConsumer>} />
          <Route path="stores/:storeId" element={<ProtectedConsumer><StoreDetail /></ProtectedConsumer>} />
          <Route path="wallet" element={<ProtectedConsumer><Wallet /></ProtectedConsumer>} />
          <Route path="upload" element={<ProtectedConsumer><BillUpload /></ProtectedConsumer>} />
          <Route path="events" element={<ProtectedConsumer><Events /></ProtectedConsumer>} />
          <Route path="offers" element={<ProtectedConsumer><Offers /></ProtectedConsumer>} />
          <Route path="profile" element={<ProtectedConsumer><Profile /></ProtectedConsumer>} />
          <Route path="notifications" element={<ProtectedConsumer><Notifications /></ProtectedConsumer>} />
          <Route path="transactions" element={<ProtectedConsumer><Transactions /></ProtectedConsumer>} />
          <Route path="bill-history" element={<ProtectedConsumer><BillHistory /></ProtectedConsumer>} />
          <Route path="rewards" element={<ProtectedConsumer><Rewards /></ProtectedConsumer>} />
          <Route path="help" element={<ProtectedConsumer><HelpSupport /></ProtectedConsumer>} />
          <Route path="legal" element={<Legal />} />
          <Route path="notification-settings" element={<ProtectedConsumer><NotificationPrefs /></ProtectedConsumer>} />
          <Route path="mall-map" element={<ProtectedConsumer><MallMap /></ProtectedConsumer>} />
          <Route path="amenities" element={<ProtectedConsumer><Amenities /></ProtectedConsumer>} />
          <Route path="referrals" element={<ProtectedConsumer><Referrals /></ProtectedConsumer>} />
          <Route path="redeem-brands" element={<ProtectedConsumer><RedeemBrands /></ProtectedConsumer>} />
          <Route path="redeem" element={<ProtectedConsumer><RedeemBrands /></ProtectedConsumer>} />
          <Route path="tier-journey" element={<ProtectedConsumer><TierJourney /></ProtectedConsumer>} />
          <Route path="program" element={<ProgramInfo />} />
          <Route path="" element={<Navigate to="/app/welcome" replace />} />
          <Route path="*" element={<Navigate to="/app/home" replace />} />
        </Routes>
      </AnimatePresence>
      {showBottomNav && <BottomNav />}
    </div>
  );
}
