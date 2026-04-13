import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, useInView, AnimatePresence } from 'framer-motion';
import { Bell, ChevronRight, Gift, MapPin, ShoppingBag, Ticket, Camera, Menu, TrendingUp, Sparkles } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';

function AnimatedCounter({ value, duration = 1.5 }) {
  const [display, setDisplay] = useState(0);
  const ref = useRef(null);
  const inView = useInView(ref, { once: true });
  useEffect(() => {
    if (!inView) return;
    const start = 0;
    const end = parseInt(value) || 0;
    if (end === 0) { setDisplay(0); return; }
    const step = Math.ceil(end / (duration * 60));
    let current = start;
    const timer = setInterval(() => {
      current += step;
      if (current >= end) { setDisplay(end); clearInterval(timer); }
      else setDisplay(current);
    }, 1000 / 60);
    return () => clearInterval(timer);
  }, [value, duration, inView]);
  return <span ref={ref}>{display.toLocaleString()}</span>;
}

const stagger = { hidden: {}, visible: { transition: { staggerChildren: 0.08 } } };
const fadeUp = { hidden: { y: 20, opacity: 0 }, visible: { y: 0, opacity: 1, transition: { type: 'spring', damping: 20 } } };

export default function Home({ onMenuOpen }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [bannerIdx, setBannerIdx] = useState(0);
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

  // Auto-rotate banners
  useEffect(() => {
    if (!data?.banners?.length) return;
    const t = setInterval(() => setBannerIdx(i => (i + 1) % data.banners.length), 4000);
    return () => clearInterval(t);
  }, [data?.banners]);

  if (loading) return (
    <div className="consumer-loading" style={{ flexDirection: 'column', gap: 12 }}>
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
        style={{ width: 36, height: 36, border: '3px solid var(--cp-border)', borderTopColor: 'var(--cp-gold)', borderRadius: '50%' }}
      />
    </div>
  );

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
          <motion.button className="home-menu-btn" onClick={onMenuOpen} data-testid="menu-btn" whileTap={{ scale: 0.9 }}>
            <Menu size={22} />
          </motion.button>
          <img src="/ha-logo-white.png" alt="Homeland Advantage" className="home-ha-logo" />
          <div className="home-greeting">
            <h1 data-testid="home-user-name" style={{ fontFamily: 'var(--font-heading)', letterSpacing: '-0.02em' }}>Homeland Advantage</h1>
          </div>
        </div>
        <motion.button className="home-bell" onClick={() => navigate('/app/notifications')} data-testid="notifications-btn" whileTap={{ scale: 0.9 }}>
          <Bell size={22} />
        </motion.button>
      </div>

      {/* Points Card — Animated */}
      <motion.div
        className="home-points-card"
        data-testid="points-card"
        onClick={() => navigate('/app/wallet')}
        initial={{ y: -60, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ type: 'spring', damping: 14, stiffness: 100 }}
        whileTap={{ scale: 0.98 }}
        style={{ cursor: 'pointer' }}
      >
        <div className="points-card-bg" />
        {/* Shimmer sweep */}
        <motion.div
          style={{ position: 'absolute', inset: 0, borderRadius: 'var(--cp-radius)', overflow: 'hidden', zIndex: 1, pointerEvents: 'none' }}
        >
          <motion.div
            style={{ width: '40%', height: '100%', background: 'linear-gradient(90deg, transparent, rgba(255,223,115,0.12), transparent)' }}
            animate={{ x: ['-100%', '350%'] }}
            transition={{ duration: 3, repeat: Infinity, repeatDelay: 4, ease: 'easeInOut' }}
          />
        </motion.div>
        <div className="points-card-content">
          <div className="points-card-left">
            <span className="points-label">
              <TrendingUp size={13} style={{ marginRight: 4 }} /> CP67 Points
            </span>
            <h2 className="points-value"><AnimatedCounter value={u.balance_points || 0} /></h2>
            <span className="points-card-name">{firstName}</span>
          </div>
          <div className="points-card-right">
            <motion.span
              className={`tier-badge tier-${(u.tier || 'Bronze').toLowerCase()}`}
              animate={{ scale: [1, 1.05, 1] }}
              transition={{ duration: 2, repeat: Infinity }}
            >
              {u.tier || 'Bronze'}
            </motion.span>
            <ChevronRight size={18} />
          </div>
        </div>
      </motion.div>

      {/* Quick Actions — Staggered */}
      <motion.div className="home-quick-actions" data-testid="quick-actions" variants={stagger} initial="hidden" animate="visible">
        {[
          { icon: Camera, label: 'Scan Bill', path: '/app/upload', color: '#C68939' },
          { icon: Gift, label: 'Redeem', path: '/app/redeem', color: '#e74c3c' },
          { icon: Ticket, label: 'Events', path: '/app/events', color: '#8b5cf6' },
          { icon: MapPin, label: 'Explore', path: '/app/stores', color: '#3b82f6' },
        ].map(a => (
          <motion.button
            key={a.label}
            className="quick-action-btn"
            onClick={() => navigate(a.path)}
            data-testid={`quick-${a.label.toLowerCase().replace(' ', '-')}`}
            variants={fadeUp}
            whileTap={{ scale: 0.9 }}
            whileHover={{ y: -2 }}
          >
            <motion.div
              className="quick-action-icon"
              style={{ background: `${a.color}18` }}
              whileHover={{ rotate: [0, -10, 10, 0] }}
              transition={{ duration: 0.4 }}
            >
              <a.icon size={22} color={a.color} />
            </motion.div>
            <span>{a.label}</span>
          </motion.button>
        ))}
      </motion.div>

      {/* Banners — Auto-rotating with crossfade */}
      {data?.banners?.length > 0 && (
        <div className="home-section">
          <div className="home-banners" data-testid="home-banners" style={{ position: 'relative', borderRadius: 16, overflow: 'hidden', height: 180 }}>
            <AnimatePresence mode="wait">
              <motion.div
                key={bannerIdx}
                className="home-banner-card"
                initial={{ opacity: 0, scale: 1.05 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ duration: 0.6 }}
                style={{ position: 'absolute', inset: 0 }}
              >
                <img src={data.banners[bannerIdx].image_url} alt={data.banners[bannerIdx].title} loading="lazy" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                <div className="banner-overlay">
                  <h3>{data.banners[bannerIdx].title}</h3>
                  <p>{data.banners[bannerIdx].subtitle}</p>
                </div>
              </motion.div>
            </AnimatePresence>
            {/* Banner dots */}
            {data.banners.length > 1 && (
              <div style={{ position: 'absolute', bottom: 10, left: '50%', transform: 'translateX(-50%)', display: 'flex', gap: 6, zIndex: 5 }}>
                {data.banners.map((_, i) => (
                  <motion.div
                    key={i}
                    onClick={(e) => { e.stopPropagation(); setBannerIdx(i); }}
                    style={{
                      width: i === bannerIdx ? 20 : 6, height: 6,
                      borderRadius: 3,
                      background: i === bannerIdx ? '#FFDF73' : 'rgba(255,255,255,0.5)',
                      cursor: 'pointer',
                    }}
                    layout
                    transition={{ type: 'spring', stiffness: 300, damping: 25 }}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Trending Offers */}
      {data?.trending_offers?.length > 0 && (
        <motion.div className="home-section" initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}>
          <div className="gold-divider" style={{ margin: '4px 20px 16px' }} />
          <div className="home-section-header">
            <h2 style={{ fontFamily: 'var(--font-heading)' }}>
              <Sparkles size={16} style={{ display: 'inline', marginRight: 6, color: 'var(--cp-gold)' }} />
              Hot Deals
            </h2>
            <button onClick={() => navigate('/app/offers')} data-testid="see-all-offers">See All <ChevronRight size={16} /></button>
          </div>
          <div className="home-offers-scroll" data-testid="trending-offers">
            {data.trending_offers.map((o, i) => (
              <motion.div
                key={o.id}
                className="home-offer-card"
                onClick={() => navigate(`/app/stores/${o.store_id}`)}
                initial={{ opacity: 0, x: 40 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                whileTap={{ scale: 0.96 }}
              >
                <div className="offer-card-img">
                  <img src={o.image_url} alt={o.title} loading="lazy" />
                  <span className="offer-badge">{o.discount_value}</span>
                </div>
                <div className="offer-card-info">
                  <h4>{o.title}</h4>
                  <p>{o.store_name}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Featured Stores */}
      {data?.featured_stores?.length > 0 && (
        <motion.div className="home-section" initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}>
          <div className="gold-divider" style={{ margin: '4px 20px 16px' }} />
          <div className="home-section-header">
            <h2 style={{ fontFamily: 'var(--font-heading)' }}>Featured Stores</h2>
            <button onClick={() => navigate('/app/stores')} data-testid="see-all-stores">See All <ChevronRight size={16} /></button>
          </div>
          <div className="home-stores-grid" data-testid="featured-stores">
            {data.featured_stores.map((s, i) => (
              <motion.div
                key={s.id}
                className="home-store-card"
                onClick={() => navigate(`/app/stores/${s.id}`)}
                data-testid={`store-card-${s.id}`}
                initial={{ opacity: 0, scale: 0.9 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.05 }}
                whileTap={{ scale: 0.96 }}
              >
                <div className="store-card-img">
                  {s.cover_image ? <img src={s.cover_image} alt={s.name} loading="lazy" /> : <div className="store-grid-placeholder"><span>{s.name[0]}</span></div>}
                </div>
                <div className="store-card-info">
                  <h4>{s.name}</h4>
                  <span className="store-category-tag">{s.category}</span>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Events */}
      {data?.upcoming_events?.length > 0 && (
        <motion.div className="home-section" initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}>
          <div className="home-section-header">
            <h2 style={{ fontFamily: 'var(--font-heading)' }}>Upcoming Events</h2>
            <button onClick={() => navigate('/app/events')} data-testid="see-all-events">See All <ChevronRight size={16} /></button>
          </div>
          <div className="home-events-scroll" data-testid="upcoming-events">
            {data.upcoming_events.map((e, i) => (
              <motion.div
                key={e.id}
                className="home-event-card"
                onClick={() => navigate('/app/events')}
                initial={{ opacity: 0, x: 40 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                whileTap={{ scale: 0.96 }}
              >
                <img src={e.image_url} alt={e.title} loading="lazy" />
                <div className="event-card-overlay">
                  <span className="event-date">{new Date(e.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}</span>
                  <h4>{e.title}</h4>
                  <p>{e.time}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}

      <div className="home-spacer" />
    </motion.div>
  );
}
