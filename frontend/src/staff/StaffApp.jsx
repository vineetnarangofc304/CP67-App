import React, { createContext, useContext, useEffect, useState } from 'react';
import { Routes, Route, Navigate, Link, useLocation, useNavigate } from 'react-router-dom';
import { Toaster, toast } from 'sonner';
import './staff.css';
import StaffLogin from './pages/StaffLogin';
import StaffDashboard from './pages/StaffDashboard';
import StaffQR from './pages/StaffQR';
import StaffIncentivesList from './pages/StaffIncentivesList';
import StaffRedeem from './pages/StaffRedeem';
import RetailerLogin from './pages/RetailerLogin';
import RetailerDashboard from './pages/RetailerDashboard';
import { LayoutDashboard, QrCode, Wallet, ListChecks, LogOut } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL + '/api';

const StaffAuthContext = createContext(null);
export const useStaffAuth = () => useContext(StaffAuthContext);

const StaffAuthProvider = ({ children }) => {
  const [token, setToken] = useState(localStorage.getItem('sa_staff_token'));
  const [staff, setStaff] = useState(() => {
    try { return JSON.parse(localStorage.getItem('sa_staff_profile') || 'null'); } catch { return null; }
  });
  const [loading, setLoading] = useState(!!token);

  // Retailer (brand manager) session — separate from staff session
  const [retailerToken, setRetailerToken] = useState(localStorage.getItem('sa_retailer_token'));
  const [retailer, setRetailer] = useState(() => {
    try { return JSON.parse(localStorage.getItem('sa_retailer_profile') || 'null'); } catch { return null; }
  });

  useEffect(() => {
    if (!token) { setLoading(false); return; }
    let cancelled = false;
    fetch(`${API_URL}/staff/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => { if (!r.ok) throw new Error('unauth'); return r.json(); })
      .then(d => { if (!cancelled) { setStaff(d.staff); localStorage.setItem('sa_staff_profile', JSON.stringify(d.staff)); } })
      .catch(() => {
        if (cancelled) return;
        localStorage.removeItem('sa_staff_token');
        localStorage.removeItem('sa_staff_profile');
        setToken(null); setStaff(null);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [token]);

  const login = (tk, staffData) => {
    localStorage.setItem('sa_staff_token', tk);
    localStorage.setItem('sa_staff_profile', JSON.stringify(staffData));
    setToken(tk); setStaff(staffData);
  };
  const logout = () => {
    localStorage.removeItem('sa_staff_token');
    localStorage.removeItem('sa_staff_profile');
    setToken(null); setStaff(null);
  };

  const loginRetailer = (tk, mgr) => {
    localStorage.setItem('sa_retailer_token', tk);
    localStorage.setItem('sa_retailer_profile', JSON.stringify(mgr));
    setRetailerToken(tk); setRetailer(mgr);
  };
  const logoutRetailer = () => {
    localStorage.removeItem('sa_retailer_token');
    localStorage.removeItem('sa_retailer_profile');
    setRetailerToken(null); setRetailer(null);
  };

  return (
    <StaffAuthContext.Provider value={{
      token, staff, login, logout, loading, API_URL,
      retailerToken, retailer, loginRetailer, logoutRetailer,
    }}>
      {children}
    </StaffAuthContext.Provider>
  );
};

const StaffProtected = ({ children }) => {
  const { token, loading } = useStaffAuth();
  if (loading) return <div className="staff-app-root sa-splash"><div className="sa-small">Loading…</div></div>;
  if (!token) return <Navigate to="/staff-app/login" replace />;
  return children;
};

const RetailerProtected = ({ children }) => {
  const { retailerToken } = useStaffAuth();
  if (!retailerToken) return <Navigate to="/staff-app/retailer/login" replace />;
  return children;
};

const StaffTabBar = () => {
  const location = useLocation();
  const path = location.pathname;
  const tabs = [
    { to: '/staff-app', icon: LayoutDashboard, label: 'Home' },
    { to: '/staff-app/incentives', icon: ListChecks, label: 'Earnings' },
    { to: '/staff-app/qr', icon: QrCode, label: 'My QR' },
    { to: '/staff-app/redeem', icon: Wallet, label: 'Redeem' },
  ];
  return (
    <nav className="sa-tab-bar" data-testid="staff-tab-bar">
      {tabs.map(t => {
        const active = t.to === '/staff-app' ? path === '/staff-app' : path.startsWith(t.to);
        return (
          <Link key={t.to} to={t.to} className={`sa-tab ${active ? 'active' : ''}`} data-testid={`tab-${t.label.toLowerCase()}`}>
            <t.icon size={20} />
            <span>{t.label}</span>
          </Link>
        );
      })}
    </nav>
  );
};

const StaffTopBar = () => {
  const { staff, logout } = useStaffAuth();
  const navigate = useNavigate();
  const doLogout = () => { logout(); toast.success('Signed out'); navigate('/staff-app/login'); };
  return (
    <div className="sa-topbar">
      <div className="sa-brand">Homeland <span>·</span> Retail</div>
      {staff && (
        <button onClick={doLogout} className="sa-btn ghost" data-testid="staff-logout-btn" style={{ padding: '6px 10px', fontSize: 12 }}>
          <LogOut size={14} /> {staff.staff_code}
        </button>
      )}
    </div>
  );
};

const StaffLayout = ({ children }) => (
  <div className="staff-app-root">
    <StaffTopBar />
    <div className="container">{children}</div>
    <StaffTabBar />
    <Toaster position="top-center" theme="dark" />
  </div>
);

const RetailerTopBar = () => {
  const { retailer, logoutRetailer } = useStaffAuth();
  const navigate = useNavigate();
  const doLogout = () => { logoutRetailer(); toast.success('Signed out'); navigate('/staff-app/retailer/login'); };
  return (
    <div className="sa-topbar">
      <div className="sa-brand">Homeland <span>·</span> Retailer</div>
      {retailer && (
        <button onClick={doLogout} className="sa-btn ghost" data-testid="retailer-logout-btn" style={{ padding: '6px 10px', fontSize: 12 }}>
          <LogOut size={14} /> {retailer.name}
        </button>
      )}
    </div>
  );
};

const RetailerLayout = ({ children }) => (
  <div className="staff-app-root">
    <RetailerTopBar />
    <div className="container">{children}</div>
    <Toaster position="top-center" theme="dark" />
  </div>
);

export default function StaffApp() {
  return (
    <StaffAuthProvider>
      <Routes>
        {/* Retailer manager routes (Point 5) */}
        <Route path="/retailer/login" element={
          <div className="staff-app-root">
            <RetailerLogin />
            <Toaster position="top-center" theme="dark" />
          </div>
        } />
        <Route path="/retailer" element={<RetailerProtected><RetailerLayout><RetailerDashboard /></RetailerLayout></RetailerProtected>} />

        {/* Staff routes */}
        <Route path="/login" element={
          <div className="staff-app-root">
            <StaffLogin />
            <Toaster position="top-center" theme="dark" />
          </div>
        } />
        <Route path="/" element={<StaffProtected><StaffLayout><StaffDashboard /></StaffLayout></StaffProtected>} />
        <Route path="/incentives" element={<StaffProtected><StaffLayout><StaffIncentivesList /></StaffLayout></StaffProtected>} />
        <Route path="/qr" element={<StaffProtected><StaffLayout><StaffQR /></StaffLayout></StaffProtected>} />
        <Route path="/redeem" element={<StaffProtected><StaffLayout><StaffRedeem /></StaffLayout></StaffProtected>} />
        <Route path="*" element={<Navigate to="/staff-app" replace />} />
      </Routes>
    </StaffAuthProvider>
  );
}
