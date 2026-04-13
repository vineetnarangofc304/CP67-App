import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Search, MapPin, Clock, Heart, ChevronDown } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';

export default function Stores() {
  const [stores, setStores] = useState([]);
  const [categories, setCategories] = useState([]);
  const [floors, setFloors] = useState([]);
  const [selectedCat, setSelectedCat] = useState('All');
  const [selectedFloor, setSelectedFloor] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [favorites, setFavorites] = useState([]);
  const [showFavOnly, setShowFavOnly] = useState(false);
  const { token } = useConsumerAuth();
  const navigate = useNavigate();

  const fetchStores = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (selectedCat !== 'All') params.set('category', selectedCat);
      if (selectedFloor) params.set('floor', selectedFloor);
      if (search) params.set('search', search);
      const [storesRes, favRes] = await Promise.all([
        fetch(`${API}/stores?${params}`, { headers: { 'Authorization': `Bearer ${token}` } }),
        fetch(`${API}/favorites`, { headers: { 'Authorization': `Bearer ${token}` } }),
      ]);
      if (storesRes.ok) {
        const data = await storesRes.json();
        setStores(data.stores);
        if (data.categories?.length) setCategories(['All', ...data.categories]);
        if (data.floors?.length) setFloors(data.floors);
      }
      if (favRes.ok) {
        const data = await favRes.json();
        setFavorites(data.favorites || []);
      }
    } catch { /* */ }
    setLoading(false);
  }, [token, selectedCat, selectedFloor, search]);

  useEffect(() => { fetchStores(); }, [fetchStores]);

  const toggleFav = async (e, storeId) => {
    e.stopPropagation();
    try {
      const res = await fetch(`${API}/favorites/toggle`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ store_id: storeId })
      });
      if (res.ok) {
        const data = await res.json();
        setFavorites(data.favorites);
      }
    } catch { /* */ }
  };

  const displayed = showFavOnly ? stores.filter(s => favorites.includes(s.id)) : stores;

  return (
    <motion.div className="consumer-stores" initial={{ opacity: 0 }} animate={{ opacity: 1 }} data-testid="stores-screen">
      <div className="stores-header">
        <h1 style={{ fontFamily: 'var(--font-heading)', letterSpacing: '-0.02em' }}>Explore Stores</h1>
        <p className="stores-count">{stores.length} brands at CP67 Mall</p>
        <div className="stores-search">
          <Search size={18} />
          <input placeholder="Search stores, brands..." value={search}
            onChange={e => setSearch(e.target.value)} data-testid="store-search-input" />
        </div>
      </div>

      {/* Floor Filter */}
      {floors.length > 0 && (
        <div className="stores-floor-filter" data-testid="stores-floor-filter">
          <div className="stores-floor-select">
            <select value={selectedFloor} onChange={e => setSelectedFloor(e.target.value)}
              data-testid="stores-floor-dropdown">
              <option value="">All Floors</option>
              {floors.map(f => <option key={f} value={f}>{f}</option>)}
            </select>
            <ChevronDown size={14} />
          </div>
        </div>
      )}

      {/* Category Pills */}
      <div className="stores-categories" data-testid="store-categories">
        <button className={`category-pill ${showFavOnly ? 'active' : ''}`}
          onClick={() => { setShowFavOnly(!showFavOnly); setSelectedCat('All'); }} data-testid="cat-favorites">
          <Heart size={14} fill={showFavOnly ? 'currentColor' : 'none'} /> Favorites
        </button>
        {categories.map(c => (
          <button key={c} className={`category-pill ${selectedCat === c && !showFavOnly ? 'active' : ''}`}
            onClick={() => { setSelectedCat(c); setShowFavOnly(false); }} data-testid={`cat-${c.toLowerCase().replace(/ /g, '-')}`}>
            {c}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="consumer-loading"><div className="consumer-spinner" /></div>
      ) : (
        <div className="stores-grid" data-testid="stores-grid">
          {displayed.map((s, idx) => (
            <motion.div
              key={s.id}
              className="store-grid-card"
              onClick={() => navigate(`/app/stores/${s.id}`)}
              data-testid={`store-${s.id}`}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(idx * 0.03, 0.5), type: 'spring', damping: 20 }}
              whileTap={{ scale: 0.97 }}
            >
              <div className="store-grid-img">
                {s.logo_url ? (
                  <img src={s.logo_url} alt={s.name} loading="lazy" className="store-logo-img" />
                ) : s.cover_image ? (
                  <img src={s.cover_image} alt={s.name} loading="lazy" />
                ) : (
                  <div className="store-grid-placeholder"><span>{s.name[0]}</span></div>
                )}
                {s.floor && <span className="store-floor-tag"><MapPin size={12} /> {s.floor}</span>}
                <button className={`store-fav-btn ${favorites.includes(s.id) ? 'active' : ''}`}
                  onClick={e => toggleFav(e, s.id)} data-testid={`fav-${s.id}`}>
                  <Heart size={16} fill={favorites.includes(s.id) ? 'currentColor' : 'none'} />
                </button>
              </div>
              <div className="store-grid-info">
                <h3>{s.name}</h3>
                {s.category && <span className="store-cat">{s.category}</span>}
                {s.timing && <p className="store-timing"><Clock size={12} /> {s.timing}</p>}
              </div>
            </motion.div>
          ))}
          {displayed.length === 0 && <p className="no-results">{showFavOnly ? 'No favorite stores yet' : 'No stores found'}</p>}
        </div>
      )}
      <div className="home-spacer" />
    </motion.div>
  );
}
