import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Home, Search, Wallet, User, Camera } from 'lucide-react';

const tabs = [
  { path: '/app/home', icon: Home, label: 'Home' },
  { path: '/app/stores', icon: Search, label: 'Explore' },
  { path: '/app/upload', icon: null, label: 'Upload Bill', isCenter: true },
  { path: '/app/wallet', icon: Wallet, label: 'Wallet' },
  { path: '/app/profile', icon: User, label: 'Profile' },
];

export default function BottomNav() {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <nav className="consumer-bottom-nav" data-testid="consumer-bottom-nav">
      {tabs.map(tab => {
        const isActive = location.pathname === tab.path;

        if (tab.isCenter) {
          return (
            <button
              key="upload-bill"
              data-testid="nav-upload-bill-btn"
              className="consumer-nav-center-btn"
              onClick={() => navigate('/app/upload')}
            >
              <Camera size={26} strokeWidth={2.5} />
              <span className="center-btn-label">Upload Bill</span>
            </button>
          );
        }

        const Icon = tab.icon;
        return (
          <button
            key={tab.path}
            data-testid={`nav-${tab.label.toLowerCase()}-btn`}
            className={`consumer-nav-tab ${isActive ? 'active' : ''}`}
            onClick={() => navigate(tab.path)}
          >
            <Icon size={22} strokeWidth={isActive ? 2.5 : 1.8} />
            <span>{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
