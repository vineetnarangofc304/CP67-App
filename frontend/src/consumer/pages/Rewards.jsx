import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowLeft, Gift, Star, Check, X, Loader2 } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';

export default function Rewards() {
  const [rewards, setRewards] = useState([]);
  const [history, setHistory] = useState([]);
  const [balance, setBalance] = useState(0);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('catalog');
  const [redeeming, setRedeeming] = useState(null);
  const [result, setResult] = useState(null);
  const { token } = useConsumerAuth();
  const navigate = useNavigate();

  const fetchData = useCallback(async () => {
    try {
      const [rewardsRes, walletRes, histRes] = await Promise.all([
        fetch(`${API}/rewards`, { headers: { 'Authorization': `Bearer ${token}` } }),
        fetch(`${API}/wallet/detailed`, { headers: { 'Authorization': `Bearer ${token}` } }),
        fetch(`${API}/rewards/history`, { headers: { 'Authorization': `Bearer ${token}` } }),
      ]);
      if (rewardsRes.ok) {
        const data = await rewardsRes.json();
        setRewards(data.rewards || []);
      }
      if (walletRes.ok) {
        const data = await walletRes.json();
        setBalance(data.balance || 0);
      }
      if (histRes.ok) {
        const data = await histRes.json();
        setHistory(data.redemptions || []);
      }
    } catch { /* */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleRedeem = async (reward) => {
    if (balance < reward.points_required) return;
    setRedeeming(reward.id);
    try {
      const res = await fetch(`${API}/rewards/redeem`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ reward_id: reward.id, points: reward.points_required })
      });
      const data = await res.json();
      if (res.ok) {
        setResult({ success: true, message: data.message, newBalance: data.new_balance });
        setBalance(data.new_balance);
        fetchData();
      } else {
        setResult({ success: false, message: data.detail || 'Redemption failed' });
      }
    } catch {
      setResult({ success: false, message: 'Network error' });
    }
    setRedeeming(null);
  };

  // Group rewards by store
  const grouped = {};
  rewards.forEach(r => {
    const store = r.store_name || 'Other';
    if (!grouped[store]) grouped[store] = [];
    grouped[store].push(r);
  });

  if (loading) return <div className="consumer-loading"><div className="consumer-spinner" /></div>;

  return (
    <motion.div className="consumer-rewards-page" initial={{ opacity: 0 }} animate={{ opacity: 1 }} data-testid="rewards-screen">
      <div className="bill-upload-header">
        <button className="bill-back" onClick={() => navigate(-1)} data-testid="rewards-back"><ArrowLeft size={22} /></button>
        <h1>Rewards</h1>
      </div>

      {/* Balance Bar */}
      <div className="rewards-balance-bar" data-testid="rewards-balance">
        <span>Available Points</span>
        <strong>{balance.toLocaleString()} pts = Rs {balance.toLocaleString()}</strong>
      </div>

      {/* Tabs */}
      <div className="txn-filter-tabs" data-testid="rewards-tabs">
        <button className={`txn-filter-tab ${tab === 'catalog' ? 'active' : ''}`}
          onClick={() => setTab('catalog')} data-testid="tab-catalog">Catalog</button>
        <button className={`txn-filter-tab ${tab === 'history' ? 'active' : ''}`}
          onClick={() => setTab('history')} data-testid="tab-history">Redeemed</button>
      </div>

      {/* Result Modal */}
      <AnimatePresence>
        {result && (
          <motion.div className="reward-result-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="reward-result-card" initial={{ scale: 0.8 }} animate={{ scale: 1 }}>
              <div className={`reward-result-icon ${result.success ? 'success' : 'error'}`}>
                {result.success ? <Check size={32} /> : <X size={32} />}
              </div>
              <h3>{result.success ? 'Redeemed!' : 'Failed'}</h3>
              <p>{result.message}</p>
              <button onClick={() => setResult(null)} data-testid="close-result-btn" className="reward-result-close">OK</button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {tab === 'catalog' ? (
        <div className="rewards-catalog" data-testid="rewards-catalog">
          {Object.entries(grouped).map(([store, storeRewards]) => (
            <div key={store} className="rewards-store-group">
              <h3 className="rewards-store-name">{store}</h3>
              <div className="rewards-grid">
                {storeRewards.map(r => {
                  const canRedeem = balance >= r.points_required;
                  return (
                    <div key={r.id} className={`reward-card ${!canRedeem ? 'locked' : ''}`} data-testid={`reward-${r.id}`}>
                      <div className="reward-card-top">
                        <div className="reward-discount">Rs {r.discount_value}</div>
                        <div className="reward-label">OFF</div>
                      </div>
                      <div className="reward-card-bottom">
                        <p className="reward-name">{r.name}</p>
                        <div className="reward-cost">{r.points_required} pts</div>
                        <button className="reward-redeem-btn"
                          disabled={!canRedeem || redeeming === r.id}
                          onClick={() => handleRedeem(r)} data-testid={`redeem-${r.id}`}>
                          {redeeming === r.id ? <Loader2 size={14} className="spin" /> : canRedeem ? 'Redeem' : 'Locked'}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
          {rewards.length === 0 && (
            <div className="txn-empty"><Gift size={40} /><p>No rewards available yet</p></div>
          )}
        </div>
      ) : (
        <div className="rewards-history" data-testid="rewards-history">
          {history.length > 0 ? history.map((h, i) => (
            <div key={h.id} className="reward-history-item" data-testid={`redeem-history-${i}`}>
              <div className="reward-hist-icon"><Gift size={18} /></div>
              <div className="reward-hist-info">
                <h4>{h.reward_name}</h4>
                <p>{new Date(h.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}</p>
              </div>
              <div className="reward-hist-points">-{h.points_used} pts</div>
            </div>
          )) : (
            <div className="txn-empty"><Gift size={40} /><p>No redemptions yet</p></div>
          )}
        </div>
      )}
      <div className="home-spacer" />
    </motion.div>
  );
}
