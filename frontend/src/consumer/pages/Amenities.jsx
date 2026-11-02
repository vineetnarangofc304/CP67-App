import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { MapPin, Wifi, Car, CreditCard, ShieldCheck, Baby, Phone, Zap, Droplets, AlertTriangle, HelpCircle, ChevronDown, ChevronUp } from 'lucide-react';
import { API } from '../ConsumerApp';

const CATEGORY_ICONS = {
  'Restrooms': Droplets,
  'Services': HelpCircle,
  'Connectivity': Wifi,
  'Parking & EV Services': Car,
  'Emergency': AlertTriangle,
};

const CATEGORY_COLORS = {
  'Restrooms': '#3b82f6',
  'Services': '#C68939',
  'Connectivity': '#8b5cf6',
  'Parking & EV Services': '#f59e0b',
  'Emergency': '#ef4444',
};

export default function Amenities() {
  const [amenities, setAmenities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openCat, setOpenCat] = useState(null);

  const fetchAmenities = useCallback(async () => {
    try {
      const res = await fetch(`${API}/amenities`);
      if (res.ok) {
        const data = await res.json();
        setAmenities(data.amenities || []);
        if (data.amenities?.length) setOpenCat(data.amenities[0].category);
      }
    } catch { /* */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchAmenities(); }, [fetchAmenities]);

  if (loading) return <div className="consumer-loading"><div className="consumer-spinner" /></div>;

  const totalItems = amenities.reduce((sum, a) => sum + a.items.length, 0);

  return (
    <motion.div className="consumer-amenities" initial={{ opacity: 0 }} animate={{ opacity: 1 }} data-testid="amenities-screen">
      <div className="amenities-header">
        <h1>Mall Amenities</h1>
        <p>{totalItems} facilities across {amenities.length} categories</p>
      </div>

      <a href="tel:7038770387" className="dining-call-card" data-testid="dining-reservation-call">
        <span className="dining-call-icon"><Phone size={18} /></span>
        <span className="dining-call-text">
          <strong>Call for Dining Reservation</strong>
          <small>+91 70387 70387</small>
        </span>
      </a>

      <div className="amenities-quick-grid" data-testid="amenities-quick-grid">
        {amenities.map(cat => {
          const Icon = CATEGORY_ICONS[cat.category] || ShieldCheck;
          const color = CATEGORY_COLORS[cat.category] || '#C68939';
          return (
            <button
              key={cat.category}
              className={`amenity-quick-btn ${openCat === cat.category ? 'active' : ''}`}
              onClick={() => setOpenCat(openCat === cat.category ? null : cat.category)}
              style={{ '--amenity-color': color }}
              data-testid={`amenity-cat-${cat.category.replace(/\s+/g, '-').toLowerCase()}`}
            >
              <Icon size={20} />
              <span>{cat.category}</span>
            </button>
          );
        })}
      </div>

      <div className="amenities-sections" data-testid="amenities-sections">
        {amenities.map((cat, idx) => {
          const Icon = CATEGORY_ICONS[cat.category] || ShieldCheck;
          const color = CATEGORY_COLORS[cat.category] || '#C68939';
          const isOpen = openCat === cat.category;

          return (
            <motion.div
              key={cat.category}
              className={`amenity-section ${isOpen ? 'open' : ''}`}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.04 }}
            >
              <button
                className="amenity-section-toggle"
                onClick={() => setOpenCat(isOpen ? null : cat.category)}
                data-testid={`toggle-amenity-${cat.category.replace(/\s+/g, '-').toLowerCase()}`}
              >
                <div className="amenity-section-icon" style={{ background: `${color}15`, color }}>
                  <Icon size={18} />
                </div>
                <div className="amenity-section-info">
                  <h3>{cat.category}</h3>
                  <span>{cat.items.length} {cat.items.length === 1 ? 'location' : 'locations'}</span>
                </div>
                {isOpen ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
              </button>

              <AnimatePresence>
                {isOpen && (
                  <motion.div
                    className="amenity-items"
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    {cat.items.map((item, i) => (
                      <div key={i} className="amenity-item" data-testid={`amenity-${item.name.replace(/\s+/g, '-').toLowerCase()}`}>
                        <div className="amenity-item-dot" style={{ background: color }} />
                        <div className="amenity-item-info">
                          <h4>{item.name}</h4>
                          <p><MapPin size={12} /> {item.location}</p>
                        </div>
                        <span className="amenity-floor-tag">{item.floor}</span>
                      </div>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          );
        })}
      </div>
      <div className="home-spacer" />
    </motion.div>
  );
}
