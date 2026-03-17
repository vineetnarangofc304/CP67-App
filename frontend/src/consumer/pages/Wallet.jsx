import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowUpRight, ArrowDownRight, ChevronRight, TrendingUp } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';

export default function Wallet() {
  const [wallet, setWallet] = useState(null);
  const [loading, setLoading] = useState(true);
  const { token } = useConsumerAuth();
  const navigate = useNavigate();

  const fetchWallet = useCallback(async () => {
    try {
      const res = await fetch(`${API}/wallet`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) setWallet(await res.json());
    } catch { /* */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { fetchWallet(); }, [fetchWallet]);

  if (loading) return <div className="consumer-loading"><div className="consumer-spinner" /></div>;

  const tier = wallet?.tier || {};

  return (
    <motion.div
      className="consumer-wallet"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      data-testid="wallet-screen"
    >
      <div className="wallet-header">
        <h1>My Wallet</h1>
      </div>

      {/* Points Card */}
      <div className="wallet-card" data-testid="wallet-card">
        <div className="wallet-card-bg" />
        <div className="wallet-card-content">
          <p className="wallet-label">Available Points</p>
          <h2 className="wallet-balance" data-testid="wallet-balance">{(wallet?.balance || 0).toLocaleString()}</h2>
          <div className="wallet-tier-section">
            <span className={`tier-badge tier-${(tier.name || 'bronze').toLowerCase()}`}>{tier.name || 'Bronze'} Member</span>
          </div>
        </div>
      </div>

      {/* Tier Progress */}
      {tier.next && (
        <div className="wallet-tier-progress" data-testid="tier-progress">
          <div className="tier-progress-header">
            <span><TrendingUp size={14} /> {tier.progress}% to {tier.next}</span>
            <span>{tier.next_at - tier.current_points} pts to go</span>
          </div>
          <div className="tier-progress-bar">
            <motion.div
              className="tier-progress-fill"
              initial={{ width: 0 }}
              animate={{ width: `${tier.progress}%` }}
              transition={{ duration: 1, ease: 'easeOut' }}
              style={{ background: tier.color }}
            />
          </div>
        </div>
      )}

      {/* Quick Action */}
      <button className="wallet-upload-btn" onClick={() => navigate('/app/upload')} data-testid="wallet-upload-btn">
        Scan Bill to Earn Points
        <ChevronRight size={18} />
      </button>

      {/* Transactions */}
      <div className="wallet-transactions" data-testid="transactions-list">
        <h2>Recent Activity</h2>
        {wallet?.transactions?.length > 0 ? (
          wallet.transactions.map(t => (
            <div key={t.id} className={`transaction-item status-${t.status}`} data-testid={`txn-${t.id}`}>
              <div className="txn-icon">
                {t.status === 'approved' ? <ArrowUpRight size={18} /> : <ArrowDownRight size={18} />}
              </div>
              <div className="txn-info">
                <h4>{t.store_name}</h4>
                <p>Rs.{(t.amount || 0).toLocaleString()} &middot; {new Date(t.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}</p>
              </div>
              <div className="txn-points">
                {t.status === 'approved' && <span className="txn-earned">+{t.points}</span>}
                <span className={`txn-status-badge ${t.status}`}>{t.status}</span>
              </div>
            </div>
          ))
        ) : (
          <div className="wallet-empty">
            <p>No transactions yet. Upload your first bill to start earning points!</p>
          </div>
        )}
      </div>

      <div className="home-spacer" />
    </motion.div>
  );
}
