import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, Bell, Gift, ShoppingBag, CheckCircle } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';

const typeIcons = {
  points: Gift,
  bill: ShoppingBag,
  system: Bell,
};

export default function Notifications() {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const { token } = useConsumerAuth();
  const navigate = useNavigate();

  const fetchNotifications = useCallback(async () => {
    try {
      const res = await fetch(`${API}/notifications`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setNotifications(data.notifications || []);
      }
    } catch { /* */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { fetchNotifications(); }, [fetchNotifications]);

  const markAllRead = async () => {
    await fetch(`${API}/notifications/read-all`, {
      method: 'PUT',
      headers: { 'Authorization': `Bearer ${token}` }
    });
    setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
  };

  if (loading) return <div className="consumer-loading"><div className="consumer-spinner" /></div>;

  return (
    <motion.div
      className="consumer-notifications"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      data-testid="notifications-screen"
    >
      <div className="notif-header">
        <button onClick={() => navigate(-1)} data-testid="notif-back-btn"><ArrowLeft size={22} /></button>
        <h1>Notifications</h1>
        {notifications.some(n => !n.is_read) && (
          <button className="notif-mark-all" onClick={markAllRead} data-testid="mark-all-read">
            <CheckCircle size={16} /> Read All
          </button>
        )}
      </div>

      <div className="notif-list" data-testid="notifications-list">
        {notifications.map(n => {
          const Icon = typeIcons[n.type] || Bell;
          return (
            <div key={n.id} className={`notif-item ${n.is_read ? '' : 'unread'}`} data-testid={`notif-${n.id}`}>
              <div className="notif-icon"><Icon size={18} /></div>
              <div className="notif-body">
                <h4>{n.title}</h4>
                <p>{n.body}</p>
                <span className="notif-time">{new Date(n.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</span>
              </div>
            </div>
          );
        })}
        {notifications.length === 0 && (
          <div className="notif-empty">
            <Bell size={40} />
            <p>No notifications yet</p>
          </div>
        )}
      </div>
    </motion.div>
  );
}
