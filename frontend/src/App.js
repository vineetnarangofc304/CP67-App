import React, { createContext, useContext, useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { Toaster } from 'sonner';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import QRCodes from './pages/QRCodes';
import Users from './pages/Users';
import Bills from './pages/Bills';
import WhatsAppSimulator from './pages/WhatsAppSimulator';
import WhatsAppLogs from './pages/WhatsAppLogs';
import Analytics from './pages/Analytics';
import AdminUsers from './pages/AdminUsers';
import ParkingScanner from './pages/ParkingScanner';
import ParkingReport from './pages/ParkingReport';
import Brands from './pages/Brands';
import Reports from './pages/Reports';
import Campaigns from './pages/Campaigns';
import AppSettings from './pages/AppSettings';
import Banners from './pages/Banners';
import Offers from './pages/Offers';
import Events from './pages/Events';
import BlockedUsers from './pages/BlockedUsers';
import ConsumerApp from './consumer/ConsumerApp';

const API_URL = process.env.REACT_APP_BACKEND_URL + '/api';

// Auth Context
const AuthContext = createContext(null);

export const useAuth = () => useContext(AuthContext);

const AuthProvider = ({ children }) => {
  const [token, setToken] = useState(localStorage.getItem('cp67_token'));
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) {
      queueMicrotask(() => setLoading(false));
      return;
    }
    let cancelled = false;
    const xhr = new XMLHttpRequest();
    xhr.open('GET', `${API_URL}/admin/me`, true);
    xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.onload = () => {
      if (cancelled) return;
      if (xhr.status >= 200 && xhr.status < 300) {
        try { setUser(JSON.parse(xhr.responseText)); } catch { /* ignore */ }
      } else {
        localStorage.removeItem('cp67_token');
        setToken(null);
      }
      setLoading(false);
    };
    xhr.onerror = () => {
      if (cancelled) return;
      localStorage.removeItem('cp67_token');
      setToken(null);
      setLoading(false);
    };
    try { xhr.send(); } catch { queueMicrotask(() => setLoading(false)); }
    return () => { cancelled = true; };
  }, [token]);

  // Helper that uses XHR to fully avoid Chrome's fetch "body stream already read"
  // issue seen behind Cloudflare on production for non-200 responses.
  const _xhrPost = (url, body, extraHeaders = {}) => new Promise((resolve) => {
    try {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', url, true);
      xhr.setRequestHeader('Content-Type', 'application/json');
      Object.entries(extraHeaders).forEach(([k, v]) => xhr.setRequestHeader(k, v));
      xhr.onload = () => {
        let data = {};
        try { data = xhr.responseText ? JSON.parse(xhr.responseText) : {}; } catch { /* ignore */ }
        resolve({ status: xhr.status, ok: xhr.status >= 200 && xhr.status < 300, data });
      };
      xhr.onerror = () => resolve({ status: 0, ok: false, data: {} });
      xhr.send(body);
    } catch {
      resolve({ status: 0, ok: false, data: {} });
    }
  });

  const _xhrGet = (url, extraHeaders = {}) => new Promise((resolve) => {
    try {
      const xhr = new XMLHttpRequest();
      xhr.open('GET', url, true);
      Object.entries(extraHeaders).forEach(([k, v]) => xhr.setRequestHeader(k, v));
      xhr.onload = () => {
        let data = {};
        try { data = xhr.responseText ? JSON.parse(xhr.responseText) : {}; } catch { /* ignore */ }
        resolve({ status: xhr.status, ok: xhr.status >= 200 && xhr.status < 300, data });
      };
      xhr.onerror = () => resolve({ status: 0, ok: false, data: {} });
      xhr.send();
    } catch {
      resolve({ status: 0, ok: false, data: {} });
    }
  });

  const login = async (username, password) => {
    const { ok, status, data } = await _xhrPost(`${API_URL}/admin/login`, JSON.stringify({ username, password }));
    if (!ok || !data.token) {
      throw new Error(data.detail || (status === 0 ? 'Network error. Please try again.' : `Login failed (HTTP ${status})`));
    }
    localStorage.setItem('cp67_token', data.token);
    setToken(data.token);
    const meResp = await _xhrGet(`${API_URL}/admin/me`, { 'Authorization': `Bearer ${data.token}` });
    setUser(meResp.ok ? meResp.data : { username: data.username });
    return data;
  };

  const logout = () => {
    localStorage.removeItem('cp67_token');
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ token, user, login, logout, loading, API_URL }}>
      {children}
    </AuthContext.Provider>
  );
};

const PARKING_ROUTES = ['/parking-scanner', '/parking-report'];

const ProtectedRoute = ({ children, allowParking = false }) => {
  const { token, user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-slate-900"></div>
      </div>
    );
  }

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  // Parking staff can only access parking routes
  if (user?.role === 'parking_staff' && !allowParking) {
    return <Navigate to="/parking-scanner" replace />;
  }

  return children;
};

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster position="top-right" richColors />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/qr-codes" element={<ProtectedRoute><QRCodes /></ProtectedRoute>} />
          <Route path="/users" element={<ProtectedRoute><Users /></ProtectedRoute>} />
          <Route path="/bills" element={<ProtectedRoute><Bills /></ProtectedRoute>} />
          <Route path="/parking-scanner" element={<ProtectedRoute allowParking><ParkingScanner /></ProtectedRoute>} />
          <Route path="/parking-report" element={<ProtectedRoute allowParking><ParkingReport /></ProtectedRoute>} />
          <Route path="/whatsapp" element={<ProtectedRoute><WhatsAppSimulator /></ProtectedRoute>} />
          <Route path="/whatsapp-logs" element={<ProtectedRoute><WhatsAppLogs /></ProtectedRoute>} />
          <Route path="/analytics" element={<ProtectedRoute><Analytics /></ProtectedRoute>} />
          <Route path="/admin-users" element={<ProtectedRoute><AdminUsers /></ProtectedRoute>} />
          <Route path="/blocked-users" element={<ProtectedRoute><BlockedUsers /></ProtectedRoute>} />
          <Route path="/brands" element={<ProtectedRoute><Brands /></ProtectedRoute>} />
          <Route path="/campaigns" element={<ProtectedRoute><Campaigns /></ProtectedRoute>} />
          <Route path="/app-settings" element={<ProtectedRoute><AppSettings /></ProtectedRoute>} />
          <Route path="/banners" element={<ProtectedRoute><Banners /></ProtectedRoute>} />
          <Route path="/offers" element={<ProtectedRoute><Offers /></ProtectedRoute>} />
          <Route path="/events" element={<ProtectedRoute><Events /></ProtectedRoute>} />
          <Route path="/reports" element={<ProtectedRoute><Reports /></ProtectedRoute>} />
          {/* Consumer App */}
          <Route path="/app/*" element={<ConsumerApp />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
