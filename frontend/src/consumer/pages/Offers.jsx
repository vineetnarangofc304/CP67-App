import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Tag, Clock } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';

export default function Offers() {
  const [offers, setOffers] = useState([]);
  const [loading, setLoading] = useState(true);
  const { token } = useConsumerAuth();
  const navigate = useNavigate();

  const fetchOffers = useCallback(async () => {
    try {
      const res = await fetch(`${API}/offers`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setOffers(data.offers || []);
      }
    } catch { /* */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { fetchOffers(); }, [fetchOffers]);

  if (loading) return <div className="consumer-loading"><div className="consumer-spinner" /></div>;

  return (
    <motion.div
      className="consumer-offers"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      data-testid="offers-screen"
    >
      <div className="offers-header">
        <h1>Offers & Deals</h1>
        <p>Exclusive deals for CP67 members</p>
      </div>

      <div className="offers-list" data-testid="offers-list">
        {offers.map(o => (
          <div
            key={o.id}
            className="offer-list-card"
            onClick={() => navigate(`/app/stores/${o.store_id}`)}
            data-testid={`offer-${o.id}`}
          >
            <div className="offer-list-img">
              <img src={o.image_url} alt={o.title} loading="lazy" />
              <div className="offer-list-badge">
                <Tag size={14} />
                <span>{o.discount_value}</span>
              </div>
            </div>
            <div className="offer-list-body">
              <span className="offer-store-name">{o.store_name}</span>
              <h3>{o.title}</h3>
              <p>{o.description}</p>
              <div className="offer-validity">
                <Clock size={12} />
                <span>Valid till {new Date(o.valid_until).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}</span>
              </div>
            </div>
          </div>
        ))}
        {offers.length === 0 && <p className="no-results">No active offers right now</p>}
      </div>
      <div className="home-spacer" />
    </motion.div>
  );
}
