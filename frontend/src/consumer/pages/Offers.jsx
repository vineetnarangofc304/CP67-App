import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Tag, Clock, Zap, Filter, ChevronRight } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';

export default function Offers() {
  const [offers, setOffers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
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

  // Separate hot deals (>30% discount or containing "flash"/"hot" in title)
  const hotDeals = offers.filter(o => {
    const val = parseInt((o.discount_value || '').replace(/[^0-9]/g, ''));
    return val >= 30 || /flash|hot|mega|clearance/i.test(o.title);
  });

  const filtered = filter === 'hot' ? hotDeals : offers;

  if (loading) return <div className="consumer-loading"><div className="consumer-spinner" /></div>;

  return (
    <motion.div className="consumer-offers" initial={{ opacity: 0 }} animate={{ opacity: 1 }} data-testid="offers-screen">
      <div className="offers-header">
        <h1>Offers & Deals</h1>
        <p>Exclusive deals for CP67 members</p>
      </div>

      {/* Filter Tabs */}
      <div className="offers-filters" data-testid="offers-filters">
        <button className={`offers-filter-pill ${filter === 'all' ? 'active' : ''}`}
          onClick={() => setFilter('all')} data-testid="filter-all">
          <Tag size={14} /> All Offers ({offers.length})
        </button>
        <button className={`offers-filter-pill hot ${filter === 'hot' ? 'active' : ''}`}
          onClick={() => setFilter('hot')} data-testid="filter-hot-deals">
          <Zap size={14} /> Hot Deals ({hotDeals.length})
        </button>
      </div>

      {/* Hot Deals Banner */}
      {filter === 'all' && hotDeals.length > 0 && (
        <div className="hot-deals-section" data-testid="hot-deals-section">
          <div className="hot-deals-header">
            <div className="hot-deals-title">
              <Zap size={16} />
              <h2>Flash Sales</h2>
            </div>
            <button className="hot-deals-see-all" onClick={() => setFilter('hot')} data-testid="see-all-hot-deals">
              See All <ChevronRight size={14} />
            </button>
          </div>
          <div className="hot-deals-scroll">
            {hotDeals.slice(0, 4).map(o => (
              <div key={o.id} className="hot-deal-card" onClick={() => navigate(`/app/stores/${o.store_id}`)}
                data-testid={`hot-deal-${o.id}`}>
                <div className="hot-deal-img">
                  <img src={o.image_url} alt={o.title} loading="lazy" />
                  <div className="hot-deal-badge"><Zap size={12} /> {o.discount_value}</div>
                </div>
                <div className="hot-deal-body">
                  <span className="hot-deal-store">{o.store_name}</span>
                  <h4>{o.title}</h4>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* All Offers */}
      <div className="offers-list" data-testid="offers-list">
        {filter === 'all' && <h2 className="offers-section-title">All Offers</h2>}
        {filtered.map(o => (
          <div key={o.id} className="offer-list-card"
            onClick={() => navigate(`/app/stores/${o.store_id}`)}
            data-testid={`offer-${o.id}`}>
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
        {filtered.length === 0 && <p className="no-results">{filter === 'hot' ? 'No hot deals right now' : 'No active offers right now'}</p>}
      </div>
      <div className="home-spacer" />
    </motion.div>
  );
}
