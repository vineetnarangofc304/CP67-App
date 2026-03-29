import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Home, Search, Wallet, User, Camera } from 'lucide-react';

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
            <motion.button
              key="upload-bill"
              data-testid="nav-upload-bill-btn"
              className="consumer-nav-center-btn"
              onClick={() => navigate('/app/upload')}
              whileTap={{ scale: 0.9, rotate: -5 }}
              whileHover={{ scale: 1.05 }}
            >
              <Camera size={24} strokeWidth={2.5} />
            </motion.button>
          );
        }

        const Icon = tab.icon;
        return (
          <motion.button
            key={tab.path}
            data-testid={`nav-${tab.label.toLowerCase()}-btn`}
            className={`consumer-nav-tab ${isActive ? 'active' : ''}`}
            onClick={() => navigate(tab.path)}
            whileTap={{ scale: 0.85 }}
          >
            <Icon size={20} strokeWidth={isActive ? 2.2 : 1.5} />
            <span>{tab.label}</span>
            {isActive && (
              <motion.div
                layoutId="activeTab"
                style={{
                  position: 'absolute', top: -1, left: '50%', transform: 'translateX(-50%)',
                  width: 20, height: 3, borderRadius: 2,
                  background: 'var(--cp-gold)',
                }}
                transition={{ type: 'spring', stiffness: 400, damping: 30 }}
              />
            )}
          </motion.button>
        );
      })}
    </nav>
  );
}
