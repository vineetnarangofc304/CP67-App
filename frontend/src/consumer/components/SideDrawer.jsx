import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { X, User, Gift, Receipt, FileText, HelpCircle, Shield, ChevronRight, LogOut, Building2, Share2, Award, Crown, Download } from 'lucide-react';
import { useConsumerAuth } from '../ConsumerApp';
import { PWAInstallGuideModal } from './PWAInstallGuide';

const menuItems = [
  { path: '/app/profile', icon: User, label: 'My Profile' },
  { path: '/app/redeem-brands', icon: Award, label: 'Redeem at Brands' },
  { path: '/app/tier-journey', icon: Crown, label: 'Tier Journey' },
  { path: '/app/transactions', icon: Receipt, label: 'Transactions' },
  { path: '/app/bill-history', icon: FileText, label: 'Bill History' },
  { path: '/app/amenities', icon: Building2, label: 'Amenities' },
  { path: '/app/referrals', icon: Share2, label: 'Refer & Earn' },
  { path: '/app/help', icon: HelpCircle, label: 'Help & Support' },
  { path: '/app/legal', icon: Shield, label: 'Legal' },
];

export default function SideDrawer({ isOpen, onClose }) {
  const navigate = useNavigate();
  const { user, logout } = useConsumerAuth();
  const [showInstallGuide, setShowInstallGuide] = useState(false);

  const handleNav = (path) => {
    onClose();
    navigate(path);
  };

  const handleLogout = () => {
    onClose();
    logout();
    navigate('/app/welcome');
  };

  const handleInstall = () => {
    setShowInstallGuide(true);
  };

  const isStandalone = () =>
    window.matchMedia('(display-mode: standalone)').matches ||
    window.navigator.standalone === true;

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div className="drawer-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            exit={{ opacity: 0 }} onClick={onClose} data-testid="drawer-overlay" />
          <motion.div className="drawer-panel" initial={{ x: '-100%' }} animate={{ x: 0 }}
            exit={{ x: '-100%' }} transition={{ type: 'spring', damping: 24, stiffness: 200 }} data-testid="side-drawer">
            {/* Header */}
            <div className="drawer-header">
              <div className="drawer-user-info">
                <img src="/ha-logo-white.png" alt="Homeland Advantage" className="drawer-ha-logo" />
                <div>
                  <h3 style={{ fontFamily: 'var(--font-heading)' }}>{user?.name || 'User'}</h3>
                  <p>{user?.phone || ''}</p>
                </div>
              </div>
              <button className="drawer-close" onClick={onClose} data-testid="close-drawer"><X size={22} /></button>
            </div>

            {/* Menu Items */}
            <nav className="drawer-nav">
              {menuItems.map((item, idx) => (
                <motion.button
                  key={item.path}
                  className="drawer-nav-item"
                  onClick={() => handleNav(item.path)}
                  data-testid={`drawer-${item.label.toLowerCase().replace(/\s+/g, '-')}`}
                  initial={{ x: -30, opacity: 0 }}
                  animate={{ x: 0, opacity: 1 }}
                  transition={{ delay: 0.1 + idx * 0.04, type: 'spring', damping: 20 }}
                  whileTap={{ scale: 0.97, x: 4 }}
                >
                  <item.icon size={20} />
                  <span>{item.label}</span>
                  <ChevronRight size={16} className="drawer-chevron" />
                </motion.button>
              ))}
              {!isStandalone() && (
                <motion.button
                  className="drawer-nav-item"
                  onClick={handleInstall}
                  data-testid="drawer-install-app"
                  initial={{ x: -30, opacity: 0 }}
                  animate={{ x: 0, opacity: 1 }}
                  transition={{ delay: 0.1 + menuItems.length * 0.04, type: 'spring', damping: 20 }}
                  whileTap={{ scale: 0.97, x: 4 }}
                >
                  <Download size={20} />
                  <span>Install App</span>
                  <ChevronRight size={16} className="drawer-chevron" />
                </motion.button>
              )}
            </nav>

            {/* Logout */}
            <div className="drawer-footer">
              <button className="drawer-logout" onClick={handleLogout} data-testid="drawer-logout">
                <LogOut size={20} />
                <span>Logout</span>
              </button>
            </div>
          </motion.div>
        </>
      )}
      <PWAInstallGuideModal open={showInstallGuide} onClose={() => setShowInstallGuide(false)} />
    </AnimatePresence>
  );
}
