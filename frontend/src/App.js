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
    if (token) {
      fetch(`${API_URL}/admin/me`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
        .then(res => {
          if (res.ok) return res.json();
          throw new Error('Invalid token');
        })
        .then(data => {
          setUser(data);
          setLoading(false);
        })
        .catch(() => {
          localStorage.removeItem('cp67_token');
          setToken(null);
          setLoading(false);
        });
    } else {
      setLoading(false);
    }
  }, [token]);

  const login = async (username, password) => {
    const response = await fetch(`${API_URL}/admin/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Login failed');
    }
    const data = await response.json();
    localStorage.setItem('cp67_token', data.token);
    setToken(data.token);
    // Fetch full user profile to get role
    const meRes = await fetch(`${API_URL}/admin/me`, {
      headers: { 'Authorization': `Bearer ${data.token}` }
    });
    if (meRes.ok) {
      const meData = await meRes.json();
      setUser(meData);
    } else {
      setUser({ username: data.username });
    }
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
