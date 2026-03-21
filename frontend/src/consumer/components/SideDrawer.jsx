import React from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { X, User, Gift, Receipt, FileText, HelpCircle, Shield, ChevronRight, LogOut, Map, Building2, Share2, Award } from 'lucide-react';
import { useConsumerAuth } from '../ConsumerApp';

const menuItems = [
  { path: '/app/profile', icon: User, label: 'My Profile' },
  { path: '/app/rewards', icon: Gift, label: 'My Rewards' },
  { path: '/app/redeem-brands', icon: Award, label: 'Redeem at Brands' },
  { path: '/app/transactions', icon: Receipt, label: 'Transactions' },
  { path: '/app/bill-history', icon: FileText, label: 'Bill History' },
  { path: '/app/mall-map', icon: Map, label: 'Mall Map' },
  { path: '/app/amenities', icon: Building2, label: 'Amenities' },
  { path: '/app/referrals', icon: Share2, label: 'Refer & Earn' },
  { path: '/app/help', icon: HelpCircle, label: 'Help & Support' },
  { path: '/app/legal', icon: Shield, label: 'Legal' },
];

export default function SideDrawer({ isOpen, onClose }) {
  const navigate = useNavigate();
  const { user, logout } = useConsumerAuth();

  const handleNav = (path) => {
    onClose();
    navigate(path);
  };

  const handleLogout = () => {
    onClose();
    logout();
    navigate('/app/welcome');
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div className="drawer-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            exit={{ opacity: 0 }} onClick={onClose} data-testid="drawer-overlay" />
          <motion.div className="drawer-panel" initial={{ x: '-100%' }} animate={{ x: 0 }}
            exit={{ x: '-100%' }} transition={{ type: 'tween', duration: 0.25 }} data-testid="side-drawer">
            {/* Header */}
            <div className="drawer-header">
              <div className="drawer-user-info">
                <div className="drawer-avatar">{(user?.name || 'U')[0]}</div>
                <div>
                  <h3>{user?.name || 'User'}</h3>
                  <p>{user?.phone || ''}</p>
                </div>
              </div>
              <button className="drawer-close" onClick={onClose} data-testid="close-drawer"><X size={22} /></button>
            </div>

            {/* Menu Items */}
            <nav className="drawer-nav">
              {menuItems.map(item => (
                <button key={item.path} className="drawer-nav-item" onClick={() => handleNav(item.path)}
                  data-testid={`drawer-${item.label.toLowerCase().replace(/\s+/g, '-')}`}>
                  <item.icon size={20} />
                  <span>{item.label}</span>
                  <ChevronRight size={16} className="drawer-chevron" />
                </button>
              ))}
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
    </AnimatePresence>
  );
}
