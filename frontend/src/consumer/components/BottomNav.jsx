import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Home, Search, Wallet, CalendarDays, User } from 'lucide-react';

const tabs = [
  { path: '/app/home', icon: Home, label: 'Home' },
  { path: '/app/stores', icon: Search, label: 'Explore' },
  { path: '/app/upload', icon: null, label: 'Scan', isCenter: true },
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
              key="scan"
              data-testid="nav-scan-btn"
              className="consumer-nav-center-btn"
              onClick={() => navigate('/app/upload')}
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round">
                <rect x="3" y="3" width="7" height="7" rx="1" />
                <rect x="14" y="3" width="7" height="7" rx="1" />
                <rect x="3" y="14" width="7" height="7" rx="1" />
                <rect x="14" y="14" width="7" height="7" rx="1" />
                <line x1="12" y1="1" x2="12" y2="5" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="1" y1="12" x2="5" y2="12" />
                <line x1="19" y1="12" x2="23" y2="12" />
              </svg>
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
