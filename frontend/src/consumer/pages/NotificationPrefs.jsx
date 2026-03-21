import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, Bell, Tag, Star, Calendar, Receipt, Gift, Megaphone } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';
import { toast } from 'sonner';

const prefConfig = [
  { key: 'offers', icon: Tag, label: 'Offers & Deals', desc: 'New offers and exclusive deals' },
  { key: 'points_updates', icon: Star, label: 'Points Updates', desc: 'Points earned, redeemed, and expiry alerts' },
  { key: 'events', icon: Calendar, label: 'Events', desc: 'Upcoming events and shows at CP67' },
  { key: 'bill_status', icon: Receipt, label: 'Bill Status', desc: 'Updates on your uploaded bills' },
  { key: 'rewards', icon: Gift, label: 'Rewards', desc: 'New rewards and redemption confirmations' },
  { key: 'promotions', icon: Megaphone, label: 'Promotions', desc: 'Marketing messages and campaigns' },
];

export default function NotificationPrefs() {
  const [prefs, setPrefs] = useState({});
  const [loading, setLoading] = useState(true);
  const { token } = useConsumerAuth();
  const navigate = useNavigate();

  const fetchPrefs = useCallback(async () => {
    try {
      const res = await fetch(`${API}/notification-preferences`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setPrefs(data.preferences || {});
      }
    } catch { /* */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { fetchPrefs(); }, [fetchPrefs]);

  const togglePref = async (key) => {
    const updated = { ...prefs, [key]: !prefs[key] };
    setPrefs(updated);
    try {
      await fetch(`${API}/notification-preferences`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(updated)
      });
      toast.success(`${prefs[key] ? 'Disabled' : 'Enabled'} ${key.replace(/_/g, ' ')} notifications`);
    } catch {
      toast.error('Failed to update');
    }
  };

  if (loading) return <div className="consumer-loading"><div className="consumer-spinner" /></div>;

  return (
    <motion.div className="consumer-notif-prefs" initial={{ opacity: 0 }} animate={{ opacity: 1 }} data-testid="notif-prefs-screen">
      <div className="bill-upload-header">
        <button className="bill-back" onClick={() => navigate(-1)} data-testid="notif-prefs-back"><ArrowLeft size={22} /></button>
        <h1>Notifications</h1>
      </div>

      <div className="notif-prefs-header">
        <Bell size={24} />
        <div>
          <h2>Notification Preferences</h2>
          <p>Control what notifications you receive</p>
        </div>
      </div>

      <div className="notif-prefs-list" data-testid="notif-prefs-list">
        {prefConfig.map(({ key, icon: Icon, label, desc }) => (
          <div key={key} className="notif-pref-item" data-testid={`pref-${key}`}>
            <div className="notif-pref-icon"><Icon size={20} /></div>
            <div className="notif-pref-info">
              <h4>{label}</h4>
              <p>{desc}</p>
            </div>
            <button className={`notif-toggle ${prefs[key] ? 'on' : 'off'}`}
              onClick={() => togglePref(key)} data-testid={`toggle-${key}`}>
              <div className="notif-toggle-knob" />
            </button>
          </div>
        ))}
      </div>
      <div className="home-spacer" />
    </motion.div>
  );
}
