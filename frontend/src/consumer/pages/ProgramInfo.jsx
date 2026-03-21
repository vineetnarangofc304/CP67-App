import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { ShoppingBag, Star, Gift, Clock, ChevronRight, Phone, Mail, MapPin } from 'lucide-react';

const API_BASE = process.env.REACT_APP_BACKEND_URL + '/api/consumer';

export default function ProgramInfo() {
  const [brands, setBrands] = useState([]);

  useEffect(() => {
    fetch(`${API_BASE}/stores`)
      .then(r => r.json())
      .then(data => setBrands(Array.isArray(data) ? data : (data.stores || []).slice(0, 50)))
      .catch(() => {});
  }, []);

  return (
    <div className="program-info-page" data-testid="program-info-page">
      {/* Hero */}
      <div className="program-hero">
        <div className="program-hero-content">
          <h1>Homeland Advantage</h1>
          <p>CP67 Mall's Exclusive Loyalty Program</p>
          <div className="program-tagline">Shop &bull; Earn &bull; Redeem &bull; Repeat</div>
        </div>
      </div>

      {/* How It Works */}
      <section className="program-section">
        <h2>How It Works</h2>
        <div className="program-steps">
          {[
            { icon: <ShoppingBag size={24} />, title: 'Shop', desc: 'Shop at any store inside CP67 Mall' },
            { icon: <Star size={24} />, title: 'Earn', desc: 'Upload your bill on WhatsApp to earn loyalty points' },
            { icon: <Gift size={24} />, title: 'Redeem', desc: 'Redeem points at participating brands for instant discounts' },
          ].map((step, i) => (
            <motion.div
              key={i}
              className="program-step-card"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.15 }}
            >
              <div className="step-icon">{step.icon}</div>
              <h3>{step.title}</h3>
              <p>{step.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Participating Brands */}
      <section className="program-section">
        <h2>Participating Brands</h2>
        <p className="section-subtitle">Earn & redeem points at these stores</p>
        <div className="program-brands-grid">
          {brands.map((b, i) => (
            <div key={i} className="program-brand-chip" data-testid={`brand-chip-${i}`}>
              {b.logo_url ? (
                <img src={b.logo_url} alt={b.name} className="brand-chip-logo" />
              ) : (
                <div className="brand-chip-initial">{(b.name || '?')[0]}</div>
              )}
              <span>{b.name}</span>
            </div>
          ))}
          {brands.length === 0 && (
            <p className="program-loading">Loading brands...</p>
          )}
        </div>
      </section>

      {/* Terms & Conditions */}
      <section className="program-section program-terms">
        <h2>Terms & Conditions</h2>
        <ul>
          <li><Clock size={14} /> Bills must be uploaded within <strong>15 days</strong> of purchase</li>
          <li><ShoppingBag size={14} /> Only bills from stores inside <strong>CP67 Mall</strong> are eligible</li>
          <li><Star size={14} /> Points are calculated based on bill amount and store</li>
          <li><Gift size={14} /> Points can be redeemed at participating brands for instant discounts</li>
          <li><Clock size={14} /> Bills above Rs 30,000 require manual verification (24-48 hrs)</li>
          <li><Star size={14} /> Duplicate bills will not be processed for rewards</li>
          <li><ShoppingBag size={14} /> E-bills and screenshots are accepted</li>
        </ul>
      </section>

      {/* Support */}
      <section className="program-section program-support">
        <h2>Need Help?</h2>
        <div className="support-cards">
          <a href="mailto:advantage@homelandgroup.org" className="support-card">
            <Mail size={20} />
            <span>advantage@homelandgroup.org</span>
          </a>
          <a href="tel:9729676767" className="support-card">
            <Phone size={20} />
            <span>97296 76767</span>
          </a>
          <div className="support-card">
            <MapPin size={20} />
            <span>Support Desk, Ground Floor, CP67 Mall</span>
          </div>
        </div>
      </section>

      <div className="program-footer">
        <p>Powered by Fundle.ai</p>
      </div>
    </div>
  );
}
