import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Search, ChevronDown, MapPin, Award } from 'lucide-react';
import { API } from '../ConsumerApp';

export default function RedeemBrands() {
  const [brands, setBrands] = useState([]);
  const [total, setTotal] = useState(0);
  const [floors, setFloors] = useState([]);
  const [categories, setCategories] = useState([]);
  const [search, setSearch] = useState('');
  const [selFloor, setSelFloor] = useState('');
  const [selCategory, setSelCategory] = useState('');
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const fetchBrands = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set('search', search);
      if (selFloor) params.set('floor', selFloor);
      if (selCategory) params.set('category', selCategory);
      const res = await fetch(`${API}/participating-brands?${params}`);
      if (res.ok) {
        const data = await res.json();
        setBrands(data.brands || []);
        setTotal(data.total || 0);
        if (data.filters) {
          setFloors(data.filters.floors || []);
          setCategories(data.filters.categories || []);
        }
      }
    } catch { /* */ }
    setLoading(false);
  }, [search, selFloor, selCategory]);

  useEffect(() => { fetchBrands(); }, [fetchBrands]);

  const clearFilters = () => {
    setSearch('');
    setSelFloor('');
    setSelCategory('');
  };

  const hasFilters = search || selFloor || selCategory;

  return (
    <motion.div className="consumer-redeem-brands" initial={{ opacity: 0 }} animate={{ opacity: 1 }} data-testid="redeem-brands-screen">
      <div className="redeem-brands-header">
        <div className="redeem-brands-title-row">
          <Award size={22} className="redeem-brands-icon" />
          <div>
            <h1>Participating Brands</h1>
            <p>{total} brands where you can earn & redeem points</p>
          </div>
        </div>
      </div>

      {/* Search */}
      <div className="redeem-brands-search" data-testid="redeem-brands-search">
        <Search size={18} />
        <input
          placeholder="Search brands..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          data-testid="redeem-search-input"
        />
      </div>

      {/* Filters */}
      <div className="redeem-brands-filters" data-testid="redeem-brands-filters">
        <div className="redeem-filter-select">
          <select
            value={selFloor}
            onChange={e => setSelFloor(e.target.value)}
            data-testid="redeem-floor-filter"
          >
            <option value="">All Floors</option>
            {floors.map(f => <option key={f} value={f}>{f}</option>)}
          </select>
          <ChevronDown size={14} className="select-chevron" />
        </div>
        <div className="redeem-filter-select">
          <select
            value={selCategory}
            onChange={e => setSelCategory(e.target.value)}
            data-testid="redeem-category-filter"
          >
            <option value="">All Categories</option>
            {categories.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <ChevronDown size={14} className="select-chevron" />
        </div>
        {hasFilters && (
          <button className="redeem-clear-btn" onClick={clearFilters} data-testid="redeem-clear-filters">
            Clear
          </button>
        )}
      </div>

      {/* Brand Grid */}
      {loading ? (
        <div className="consumer-loading"><div className="consumer-spinner" /></div>
      ) : (
        <div className="redeem-brands-grid" data-testid="redeem-brands-grid">
          {brands.map((b, idx) => (
            <motion.div
              key={b.id || b.name}
              className="redeem-brand-card"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: Math.min(idx * 0.02, 0.5) }}
              onClick={() => b.id && navigate(`/app/stores/${b.id}`)}
              data-testid={`redeem-brand-${b.name.replace(/\s+/g, '-').toLowerCase()}`}
            >
              <div className="redeem-brand-logo">
                {b.logo_url ? (
                  <img src={b.logo_url} alt={b.name} loading="lazy" />
                ) : (
                  <span className="redeem-brand-initial">{b.name[0]}</span>
                )}
              </div>
              <div className="redeem-brand-name">{b.name}</div>
              {b.floor && (
                <div className="redeem-brand-floor">
                  <MapPin size={10} /> {b.floor}
                </div>
              )}
            </motion.div>
          ))}
          {brands.length === 0 && (
            <p className="no-results">No brands found{hasFilters ? ' matching your filters' : ''}</p>
          )}
        </div>
      )}

      <div className="redeem-brands-disclaimer" data-testid="redeem-brands-disclaimer">
        Brand participation is subject to terms and conditions of the Homeland Advantage program.
      </div>

      <div className="home-spacer" />
    </motion.div>
  );
}
