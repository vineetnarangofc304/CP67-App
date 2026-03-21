import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Search, MapPin, Clock, Heart } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';

export default function Stores() {
  const [stores, setStores] = useState([]);
  const [categories, setCategories] = useState([]);
  const [selectedCat, setSelectedCat] = useState('All');
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
      if (search) params.set('search', search);
      const [storesRes, favRes] = await Promise.all([
        fetch(`${API}/stores?${params}`, { headers: { 'Authorization': `Bearer ${token}` } }),
        fetch(`${API}/favorites`, { headers: { 'Authorization': `Bearer ${token}` } }),
      ]);
      if (storesRes.ok) {
        const data = await storesRes.json();
        setStores(data.stores);
        if (data.categories?.length) setCategories(['All', ...data.categories]);
      }
      if (favRes.ok) {
        const data = await favRes.json();
        setFavorites(data.favorites || []);
      }
    } catch { /* */ }
    setLoading(false);
  }, [token, selectedCat, search]);

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
        <h1>Explore Stores</h1>
        <div className="stores-search">
          <Search size={18} />
          <input placeholder="Search stores, brands..." value={search}
            onChange={e => setSearch(e.target.value)} data-testid="store-search-input" />
        </div>
      </div>

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
          {displayed.map(s => (
            <div key={s.id} className="store-grid-card" onClick={() => navigate(`/app/stores/${s.id}`)} data-testid={`store-${s.id}`}>
              <div className="store-grid-img">
                {s.cover_image ? (
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
                <span className="store-cat">{s.category}</span>
                <p className="store-timing"><Clock size={12} /> {s.timing}</p>
              </div>
            </div>
          ))}
          {displayed.length === 0 && <p className="no-results">{showFavOnly ? 'No favorite stores yet' : 'No stores found'}</p>}
        </div>
      )}
      <div className="home-spacer" />
    </motion.div>
  );
}
