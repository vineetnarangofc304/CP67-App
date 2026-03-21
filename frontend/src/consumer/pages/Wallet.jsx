import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowUpRight, ArrowDownRight, ChevronRight, TrendingUp, Gift, Receipt, Clock } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';

export default function Wallet() {
  const [wallet, setWallet] = useState(null);
  const [loading, setLoading] = useState(true);
  const { token } = useConsumerAuth();
  const navigate = useNavigate();

  const fetchWallet = useCallback(async () => {
    try {
      const res = await fetch(`${API}/wallet/detailed`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) setWallet(await res.json());
    } catch { /* */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { fetchWallet(); }, [fetchWallet]);

  if (loading) return <div className="consumer-loading"><div className="consumer-spinner" /></div>;

  const tier = wallet?.tier || {};

  return (
    <motion.div className="consumer-wallet" initial={{ opacity: 0 }} animate={{ opacity: 1 }} data-testid="wallet-screen">
      <div className="wallet-header"><h1>My Wallet</h1></div>

      {/* Points Card */}
      <div className="wallet-card" data-testid="wallet-card">
        <div className="wallet-card-bg" />
        <div className="wallet-card-content">
          <p className="wallet-label">Available Balance</p>
          <h2 className="wallet-balance" data-testid="wallet-balance">{(wallet?.balance || 0).toLocaleString()}</h2>
          <p className="wallet-conversion">= Rs {(wallet?.balance || 0).toLocaleString()}</p>
          <div className="wallet-tier-section">
            <span className={`tier-badge tier-${(tier.name || 'bronze').toLowerCase()}`}>{tier.name || 'Bronze'} Member</span>
          </div>
        </div>
      </div>

      {/* Points Breakdown */}
      <div className="wallet-breakdown" data-testid="points-breakdown">
        <div className="breakdown-item">
          <div className="breakdown-icon earn"><ArrowUpRight size={18} /></div>
          <div className="breakdown-info">
            <span className="breakdown-label">Total Earned</span>
            <span className="breakdown-value">{(wallet?.total_earned || 0).toLocaleString()}</span>
          </div>
        </div>
        <div className="breakdown-divider" />
        <div className="breakdown-item">
          <div className="breakdown-icon redeem"><Gift size={18} /></div>
          <div className="breakdown-info">
            <span className="breakdown-label">Redeemed</span>
            <span className="breakdown-value">{(wallet?.total_redeemed || 0).toLocaleString()}</span>
          </div>
        </div>
        <div className="breakdown-divider" />
        <div className="breakdown-item">
          <div className="breakdown-icon expired"><Clock size={18} /></div>
          <div className="breakdown-info">
            <span className="breakdown-label">Expired</span>
            <span className="breakdown-value">{(wallet?.expired || 0).toLocaleString()}</span>
          </div>
        </div>
      </div>

      {/* Tier Progress */}
      {tier.next && (
        <div className="wallet-tier-progress" data-testid="tier-progress">
          <div className="tier-progress-header">
            <span><TrendingUp size={14} /> {tier.progress}% to {tier.next}</span>
            <span>{(tier.next_at - tier.current_points).toLocaleString()} pts to go</span>
          </div>
          <div className="tier-progress-bar">
            <motion.div className="tier-progress-fill" initial={{ width: 0 }} animate={{ width: `${tier.progress}%` }}
              transition={{ duration: 1, ease: 'easeOut' }} style={{ background: tier.color }} />
          </div>
        </div>
      )}

      {/* Quick Actions */}
      <div className="wallet-actions" data-testid="wallet-actions">
        <button className="wallet-action-btn primary" onClick={() => navigate('/app/upload')} data-testid="wallet-scan-btn">
          <Receipt size={18} /> Scan Bill
        </button>
        <button className="wallet-action-btn" onClick={() => navigate('/app/rewards')} data-testid="wallet-rewards-btn">
          <Gift size={18} /> Rewards
        </button>
      </div>

      {/* Quick Nav */}
      <div className="wallet-nav-links">
        <button onClick={() => navigate('/app/transactions')} data-testid="view-all-transactions">
          View All Transactions <ChevronRight size={16} />
        </button>
        <button onClick={() => navigate('/app/bill-history')} data-testid="view-bill-history">
          Bill History <ChevronRight size={16} />
        </button>
      </div>

      {/* Recent Transactions */}
      <div className="wallet-transactions" data-testid="recent-transactions">
        <h2>Recent Activity</h2>
        {wallet?.recent_transactions?.length > 0 ? (
          wallet.recent_transactions.map(t => (
            <div key={t.id} className={`transaction-item status-${t.status}`} data-testid={`txn-${t.id}`}>
              <div className="txn-icon">
                {t.type === 'earn' ? <ArrowUpRight size={18} /> : <ArrowDownRight size={18} />}
              </div>
              <div className="txn-info">
                <h4>{t.store_name}</h4>
                <p>{new Date(t.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}</p>
              </div>
              <div className="txn-points">
                <span className={t.type === 'earn' ? 'txn-earned' : 'txn-redeemed'}>
                  {t.points > 0 ? '+' : ''}{t.points}
                </span>
              </div>
            </div>
          ))
        ) : (
          <div className="wallet-empty"><p>No transactions yet. Upload your first bill to start earning!</p></div>
        )}
      </div>

      <div className="home-spacer" />
    </motion.div>
  );
}
