import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { MapPin, ChevronDown, ChevronUp, Search, Layers } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';

const FLOOR_ICONS = {
  'Lower Ground': 'LG',
  'Ground Floor': 'G',
  'First Floor': '1',
  'Second Floor': '2',
  'Third Floor': '3',
  'Food Court': 'FC',
};

export default function MallMap() {
  const [floors, setFloors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openFloor, setOpenFloor] = useState(null);
  const [search, setSearch] = useState('');
  const { token } = useConsumerAuth();

  const fetchMap = useCallback(async () => {
    try {
      const res = await fetch(`${API}/mall-map`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setFloors(data.floors || []);
        if (data.floors?.length) setOpenFloor(data.floors[0].floor);
      }
    } catch { /* */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { fetchMap(); }, [fetchMap]);

  const filteredFloors = floors.map(f => ({
    ...f,
    stores: f.stores.filter(s =>
      s.name.toLowerCase().includes(search.toLowerCase()) ||
      (s.category || '').toLowerCase().includes(search.toLowerCase())
    )
  })).filter(f => f.stores.length > 0);

  const totalStores = floors.reduce((sum, f) => sum + f.stores.length, 0);

  if (loading) return <div className="consumer-loading"><div className="consumer-spinner" /></div>;

  return (
    <motion.div className="consumer-mallmap" initial={{ opacity: 0 }} animate={{ opacity: 1 }} data-testid="mallmap-screen">
      <div className="mallmap-header">
        <h1>Mall Map</h1>
        <p>{totalStores} stores across {floors.length} floors</p>
      </div>

      <div className="mallmap-search">
        <Search size={18} />
        <input
          placeholder="Search stores by name or category..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          data-testid="mallmap-search-input"
        />
      </div>

      <div className="mallmap-legend">
        <Layers size={14} />
        <span>Tap a floor to explore stores</span>
      </div>

      <div className="mallmap-floors" data-testid="mallmap-floors">
        {filteredFloors.map((floor, idx) => {
          const isOpen = openFloor === floor.floor;
          const shortCode = FLOOR_ICONS[floor.floor] || floor.floor.charAt(0);

          return (
            <motion.div
              key={floor.floor}
              className={`mallmap-floor-section ${isOpen ? 'open' : ''}`}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.05 }}
              data-testid={`floor-${floor.floor.replace(/\s+/g, '-').toLowerCase()}`}
            >
              <button
                className="mallmap-floor-toggle"
                onClick={() => setOpenFloor(isOpen ? null : floor.floor)}
                data-testid={`toggle-${floor.floor.replace(/\s+/g, '-').toLowerCase()}`}
              >
                <div className="floor-badge">{shortCode}</div>
                <div className="floor-toggle-info">
                  <h3>{floor.floor}</h3>
                  <span>{floor.stores.length} {floor.stores.length === 1 ? 'store' : 'stores'}</span>
                </div>
                {isOpen ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
              </button>

              <AnimatePresence>
                {isOpen && (
                  <motion.div
                    className="mallmap-store-grid"
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.25 }}
                  >
                    {floor.stores.map(store => (
                      <div key={store.name} className="mallmap-store-item" data-testid={`mapstore-${store.name.replace(/\s+/g, '-').toLowerCase()}`}>
                        <div className="mallmap-store-avatar">
                          {store.logo_url ? (
                            <img src={store.logo_url} alt={store.name} loading="lazy" />
                          ) : (
                            <span>{store.name[0]}</span>
                          )}
                        </div>
                        <div className="mallmap-store-info">
                          <h4>{store.name}</h4>
                          {store.category && <span className="mallmap-store-cat">{store.category}</span>}
                        </div>
                        <MapPin size={14} className="mallmap-pin" />
                      </div>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          );
        })}
        {filteredFloors.length === 0 && <p className="no-results">No stores found matching "{search}"</p>}
      </div>
      <div className="home-spacer" />
    </motion.div>
  );
}
