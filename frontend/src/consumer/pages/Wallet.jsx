import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowUpRight, ArrowDownRight, ChevronRight, ChevronDown, ChevronUp, TrendingUp, Gift, Receipt, Clock } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';

const EARNING_SLABS = [
  { range: '0 - 10,000', retail: '10%', jewellery: '5%' },
  { range: '10,001 - 25,000', retail: '15%', jewellery: '7.5%' },
  { range: '25,001 - 75,000', retail: '20%', jewellery: '10%' },
  { range: '75,001 - 1,50,000', retail: '25%', jewellery: '12.5%' },
  { range: '1,50,001 - 3,00,000', retail: '30%', jewellery: '15%' },
  { range: '3,00,001 - 5,00,000', retail: '32.5%', jewellery: '16.25%' },
  { range: '5,00,001 & Above', retail: '35%', jewellery: '17.5%' },
];

function AnimatedCounter({ value, duration = 1.2 }) {
  const [display, setDisplay] = React.useState(0);
  const ref = React.useRef(null);
  React.useEffect(() => {
    const end = parseInt(value) || 0;
    if (end === 0) { setDisplay(0); return; }
    const step = Math.ceil(end / (duration * 60));
    let current = 0;
    const timer = setInterval(() => {
      current += step;
      if (current >= end) { setDisplay(end); clearInterval(timer); }
      else setDisplay(current);
    }, 1000 / 60);
    return () => clearInterval(timer);
  }, [value, duration]);
  return <span ref={ref}>{display.toLocaleString()}</span>;
}

export default function Wallet() {
  const [wallet, setWallet] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showSlabs, setShowSlabs] = useState(false);
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
      <div className="wallet-header"><h1 style={{ fontFamily: 'Playfair Display, serif', letterSpacing: '-0.02em' }}>My Wallet</h1></div>

      {/* Points Card */}
      <motion.div
        className="wallet-card"
        data-testid="wallet-card"
        initial={{ y: -40, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ type: 'spring', damping: 14 }}
      >
        <div className="wallet-card-bg" />
        {/* Shimmer sweep */}
        <motion.div style={{ position: 'absolute', inset: 0, borderRadius: 'var(--cp-radius)', overflow: 'hidden', zIndex: 1, pointerEvents: 'none' }}>
          <motion.div
            style={{ width: '40%', height: '100%', background: 'linear-gradient(90deg, transparent, rgba(255,223,115,0.1), transparent)' }}
            animate={{ x: ['-100%', '350%'] }}
            transition={{ duration: 3, repeat: Infinity, repeatDelay: 5, ease: 'easeInOut' }}
          />
        </motion.div>
        <div className="wallet-card-content">
          <p className="wallet-label">Available Balance</p>
          <h2 className="wallet-balance" data-testid="wallet-balance"><AnimatedCounter value={wallet?.balance || 0} /></h2>
          <p className="wallet-conversion">Points</p>
          <div className="wallet-tier-section" onClick={() => navigate('/app/tier-journey')} style={{ cursor: 'pointer' }}>
            <motion.span
              className={`tier-badge tier-${(tier.name || 'bronze').toLowerCase()}`}
              data-testid="tier-badge"
              whileTap={{ scale: 0.95 }}
              animate={{ scale: [1, 1.04, 1] }}
              transition={{ duration: 2.5, repeat: Infinity }}
            >
              {tier.name || 'Bronze'} Member
            </motion.span>
            <ChevronRight size={16} style={{ color: 'rgba(255,255,255,0.7)', marginLeft: 4 }} />
          </div>
        </div>
      </motion.div>

      {/* Points Breakdown */}
      <div className="gold-divider" style={{ margin: '0 20px 16px' }} />
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
        <motion.button className="wallet-action-btn primary" onClick={() => navigate('/app/upload')} data-testid="wallet-scan-btn" whileTap={{ scale: 0.95 }}>
          <Receipt size={18} /> Scan Bill
        </motion.button>
        <motion.button className="wallet-action-btn" onClick={() => navigate('/app/redeem')} data-testid="wallet-rewards-btn" whileTap={{ scale: 0.95 }}>
          <Gift size={18} /> Redeem
        </motion.button>
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

      {/* Points Value & Earning Slab */}
      <div className="wallet-earning-slab" data-testid="earning-slab-section">
        <div className="earning-slab-conversion" data-testid="points-conversion">
          <TrendingUp size={16} />
          <span>10 Points = INR 1</span>
          <span className="earning-slab-sub">Earn & redeem across 100+ brands</span>
        </div>
        <button className="earning-slab-toggle" onClick={() => setShowSlabs(!showSlabs)} data-testid="toggle-slabs-btn">
          Points Earning Slab
          {showSlabs ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
        {showSlabs && (
          <div className="earning-slab-table" data-testid="slab-table">
            <div className="slab-row slab-header">
              <span>Purchase (INR)</span>
              <span>Retail</span>
              <span>Jewellery & Electronics</span>
            </div>
            {EARNING_SLABS.map((s, i) => (
              <div key={i} className="slab-row">
                <span>{s.range}</span>
                <span className="slab-retail">{s.retail}</span>
                <span className="slab-jewel">{s.jewellery}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="home-spacer" />
    </motion.div>
  );
}
