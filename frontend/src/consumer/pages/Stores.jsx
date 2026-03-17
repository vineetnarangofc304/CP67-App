import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Search, MapPin, Clock } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';

export default function Stores() {
  const [stores, setStores] = useState([]);
  const [categories, setCategories] = useState([]);
  const [selectedCat, setSelectedCat] = useState('All');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const { token } = useConsumerAuth();
  const navigate = useNavigate();

  const fetchStores = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (selectedCat !== 'All') params.set('category', selectedCat);
      if (search) params.set('search', search);
      const res = await fetch(`${API}/stores?${params}`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setStores(data.stores);
        if (data.categories?.length) setCategories(['All', ...data.categories]);
      }
    } catch { /* ignore */ }
    setLoading(false);
  }, [token, selectedCat, search]);

  useEffect(() => { fetchStores(); }, [fetchStores]);

  return (
    <motion.div
      className="consumer-stores"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      data-testid="stores-screen"
    >
      <div className="stores-header">
        <h1>Explore Stores</h1>
        <div className="stores-search">
          <Search size={18} />
          <input
            placeholder="Search stores, brands..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            data-testid="store-search-input"
          />
        </div>
      </div>

      <div className="stores-categories" data-testid="store-categories">
        {categories.map(c => (
          <button
            key={c}
            className={`category-pill ${selectedCat === c ? 'active' : ''}`}
            onClick={() => setSelectedCat(c)}
            data-testid={`cat-${c.toLowerCase().replace(/ /g, '-')}`}
          >
            {c}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="consumer-loading"><div className="consumer-spinner" /></div>
      ) : (
        <div className="stores-grid" data-testid="stores-grid">
          {stores.map(s => (
            <div
              key={s.id}
              className="store-grid-card"
              onClick={() => navigate(`/app/stores/${s.id}`)}
              data-testid={`store-${s.id}`}
            >
              <div className="store-grid-img">
                {s.cover_image ? (
                  <img src={s.cover_image} alt={s.name} loading="lazy" />
                ) : (
                  <div className="store-grid-placeholder">
                    <span>{s.name[0]}</span>
                  </div>
                )}
                {s.floor && <span className="store-floor-tag"><MapPin size={12} /> {s.floor}</span>}
              </div>
              <div className="store-grid-info">
                <h3>{s.name}</h3>
                <span className="store-cat">{s.category}</span>
                <p className="store-timing"><Clock size={12} /> {s.timing}</p>
              </div>
            </div>
          ))}
          {stores.length === 0 && <p className="no-results">No stores found</p>}
        </div>
      )}
      <div className="home-spacer" />
    </motion.div>
  );
}
