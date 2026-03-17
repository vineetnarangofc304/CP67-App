import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, MapPin, Clock, Tag, ChevronRight } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';

export default function StoreDetail() {
  const { storeId } = useParams();
  const [store, setStore] = useState(null);
  const [loading, setLoading] = useState(true);
  const { token } = useConsumerAuth();
  const navigate = useNavigate();

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API}/stores/${storeId}`, { headers: { 'Authorization': `Bearer ${token}` } });
        if (res.ok) setStore(await res.json());
      } catch { /* */ }
      setLoading(false);
    })();
  }, [storeId, token]);

  if (loading) return <div className="consumer-loading"><div className="consumer-spinner" /></div>;
  if (!store) return <div className="consumer-error">Store not found</div>;

  return (
    <motion.div
      className="consumer-store-detail"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      data-testid="store-detail-screen"
    >
      <div className="store-detail-hero">
        <img src={store.cover_image} alt={store.name} />
        <div className="store-detail-hero-overlay" />
        <button className="store-detail-back" onClick={() => navigate(-1)} data-testid="store-back-btn">
          <ArrowLeft size={22} />
        </button>
        <div className="store-detail-hero-info">
          <span className="store-detail-category">{store.category}</span>
          <h1>{store.name}</h1>
        </div>
      </div>

      <div className="store-detail-body">
        <div className="store-detail-meta">
          <div className="meta-item"><MapPin size={16} /><span>{store.floor} &middot; Unit {store.unit_no}</span></div>
          <div className="meta-item"><Clock size={16} /><span>{store.timing}</span></div>
        </div>

        <p className="store-detail-desc">{store.description}</p>

        {store.tags?.length > 0 && (
          <div className="store-detail-tags">
            {store.tags.map(t => <span key={t} className="store-tag"><Tag size={12} /> {t}</span>)}
          </div>
        )}

        {store.offers?.length > 0 && (
          <div className="store-detail-section">
            <h2>Current Offers</h2>
            {store.offers.map(o => (
              <div key={o.id} className="store-offer-item" data-testid={`offer-${o.id}`}>
                <div className="store-offer-badge">{o.discount_value}</div>
                <div className="store-offer-info">
                  <h4>{o.title}</h4>
                  <p>{o.description}</p>
                </div>
                <ChevronRight size={18} />
              </div>
            ))}
          </div>
        )}

        <button className="store-upload-cta" onClick={() => navigate('/app/upload')} data-testid="store-upload-bill-btn">
          <span>Upload Bill from {store.name}</span>
          <ChevronRight size={18} />
        </button>
      </div>
    </motion.div>
  );
}
