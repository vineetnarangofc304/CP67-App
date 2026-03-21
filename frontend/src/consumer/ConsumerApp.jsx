import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import BottomNav from './components/BottomNav';
import SideDrawer from './components/SideDrawer';
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
      throw new Error('Invalid token');
    } catch {
      localStorage.removeItem('cp67_consumer_token');
      setToken(null);
      setUser(null);
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

  return (
    <ConsumerAuthContext.Provider value={{ token, user, login, logout, loading, refreshProfile, API }}>
      {children}
    </ConsumerAuthContext.Provider>
  );
};

const ProtectedConsumer = ({ children }) => {
  const { token, loading, user } = useConsumerAuth();
  if (loading) return <div className="consumer-loading"><div className="consumer-spinner" /></div>;
  if (!token) return <Navigate to="/app/login" replace />;
  if (user && !user.onboarding_complete && window.location.pathname !== '/app/onboarding') {
    return <Navigate to="/app/onboarding" replace />;
  }
  return children;
};

const showNav = ['/app', '/app/home', '/app/stores', '/app/wallet', '/app/events', '/app/offers', '/app/profile', '/app/notifications'];

export default function ConsumerApp() {
  const location = useLocation();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const showBottomNav = showNav.includes(location.pathname) || location.pathname === '/app/';

  return (
    <ConsumerAuthProvider>
      <div className="consumer-app">
        <SideDrawer isOpen={drawerOpen} onClose={() => setDrawerOpen(false)} />
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
            <Route path="legal" element={<ProtectedConsumer><Legal /></ProtectedConsumer>} />
            <Route path="notification-settings" element={<ProtectedConsumer><NotificationPrefs /></ProtectedConsumer>} />
            <Route path="mall-map" element={<ProtectedConsumer><MallMap /></ProtectedConsumer>} />
            <Route path="amenities" element={<ProtectedConsumer><Amenities /></ProtectedConsumer>} />
            <Route path="referrals" element={<ProtectedConsumer><Referrals /></ProtectedConsumer>} />
            <Route path="redeem-brands" element={<ProtectedConsumer><RedeemBrands /></ProtectedConsumer>} />
            <Route path="program" element={<ProgramInfo />} />
            <Route path="" element={<Navigate to="/app/welcome" replace />} />
            <Route path="*" element={<Navigate to="/app/home" replace />} />
          </Routes>
        </AnimatePresence>
        {showBottomNav && <BottomNav />}
      </div>
    </ConsumerAuthProvider>
  );
}
