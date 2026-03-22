import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Bell, ChevronRight, Gift, MapPin, ShoppingBag, Ticket, Camera, Menu } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';

export default function Home({ onMenuOpen }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const { token, user } = useConsumerAuth();
  const navigate = useNavigate();

  const fetchHome = useCallback(async () => {
    try {
      const res = await fetch(`${API}/home`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) setData(await res.json());
    } catch { /* ignore */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { fetchHome(); }, [fetchHome]);

  if (loading) return <div className="consumer-loading"><div className="consumer-spinner" /></div>;

  const u = data?.user || {};
  const firstName = (u.name || user?.name || 'There').split(' ')[0];

  return (
    <motion.div
      className="consumer-home"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      data-testid="home-screen"
    >
      {/* Header */}
      <div className="home-top">
        <div className="home-greeting-row">
          <button className="home-menu-btn" onClick={onMenuOpen} data-testid="menu-btn"><Menu size={22} /></button>
          <div className="home-greeting">
            <p className="home-greeting-sub">Welcome back,</p>
            <h1 data-testid="home-user-name">{firstName}</h1>
          </div>
        </div>
        <button className="home-bell" onClick={() => navigate('/app/notifications')} data-testid="notifications-btn">
          <Bell size={22} />
        </button>
      </div>

      {/* Points Card */}
      <div className="home-points-card" data-testid="points-card" onClick={() => navigate('/app/wallet')}>
        <div className="points-card-bg" />
        <div className="points-card-content">
          <div className="points-card-left">
            <span className="points-label">CP67 Points</span>
            <h2 className="points-value">{(u.balance_points || 0).toLocaleString()}</h2>
          </div>
          <div className="points-card-right">
            <span className={`tier-badge tier-${(u.tier || 'Bronze').toLowerCase()}`}>{u.tier || 'Bronze'}</span>
            <ChevronRight size={18} />
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="home-quick-actions" data-testid="quick-actions">
        {[
          { icon: Camera, label: 'Scan Bill', path: '/app/upload', color: '#C68939' },
          { icon: Gift, label: 'Offers', path: '/app/offers', color: '#e74c3c' },
          { icon: Ticket, label: 'Events', path: '/app/events', color: '#8b5cf6' },
          { icon: MapPin, label: 'Mall Map', path: '/app/stores', color: '#3b82f6' },
        ].map(a => (
          <button key={a.label} className="quick-action-btn" onClick={() => navigate(a.path)} data-testid={`quick-${a.label.toLowerCase().replace(' ', '-')}`}>
            <div className="quick-action-icon" style={{ background: `${a.color}18` }}>
              <a.icon size={22} color={a.color} />
            </div>
            <span>{a.label}</span>
          </button>
        ))}
      </div>

      {/* Banners */}
      {data?.banners?.length > 0 && (
        <div className="home-section">
          <div className="home-banners" data-testid="home-banners">
            {data.banners.map(b => (
              <div key={b.id} className="home-banner-card">
                <img src={b.image_url} alt={b.title} loading="lazy" />
                <div className="banner-overlay">
                  <h3>{b.title}</h3>
                  <p>{b.subtitle}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Trending Offers */}
      {data?.trending_offers?.length > 0 && (
        <div className="home-section">
          <div className="home-section-header">
            <h2>Hot Deals</h2>
            <button onClick={() => navigate('/app/offers')} data-testid="see-all-offers">See All <ChevronRight size={16} /></button>
          </div>
          <div className="home-offers-scroll" data-testid="trending-offers">
            {data.trending_offers.map(o => (
              <div key={o.id} className="home-offer-card" onClick={() => navigate(`/app/stores/${o.store_id}`)}>
                <div className="offer-card-img">
                  <img src={o.image_url} alt={o.title} loading="lazy" />
                  <span className="offer-badge">{o.discount_value}</span>
                </div>
                <div className="offer-card-info">
                  <h4>{o.title}</h4>
                  <p>{o.store_name}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Featured Stores */}
      {data?.featured_stores?.length > 0 && (
        <div className="home-section">
          <div className="home-section-header">
            <h2>Featured Stores</h2>
            <button onClick={() => navigate('/app/stores')} data-testid="see-all-stores">See All <ChevronRight size={16} /></button>
          </div>
          <div className="home-stores-grid" data-testid="featured-stores">
            {data.featured_stores.map(s => (
              <div key={s.id} className="home-store-card" onClick={() => navigate(`/app/stores/${s.id}`)} data-testid={`store-card-${s.id}`}>
                <div className="store-card-img">
                  {s.cover_image ? <img src={s.cover_image} alt={s.name} loading="lazy" /> : <div className="store-grid-placeholder"><span>{s.name[0]}</span></div>}
                </div>
                <div className="store-card-info">
                  <h4>{s.name}</h4>
                  <span className="store-category-tag">{s.category}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Events */}
      {data?.upcoming_events?.length > 0 && (
        <div className="home-section">
          <div className="home-section-header">
            <h2>Upcoming Events</h2>
            <button onClick={() => navigate('/app/events')} data-testid="see-all-events">See All <ChevronRight size={16} /></button>
          </div>
          <div className="home-events-scroll" data-testid="upcoming-events">
            {data.upcoming_events.map(e => (
              <div key={e.id} className="home-event-card" onClick={() => navigate('/app/events')}>
                <img src={e.image_url} alt={e.title} loading="lazy" />
                <div className="event-card-overlay">
                  <span className="event-date">{new Date(e.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}</span>
                  <h4>{e.title}</h4>
                  <p>{e.time}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="home-spacer" />
    </motion.div>
  );
}
