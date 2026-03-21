import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, ArrowUpRight, ArrowDownRight, Filter } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'earn', label: 'Earned' },
  { id: 'redeem', label: 'Redeemed' },
];

export default function Transactions() {
  const [transactions, setTransactions] = useState([]);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const { token } = useConsumerAuth();
  const navigate = useNavigate();

  const fetchTransactions = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/transactions?filter_type=${filter}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setTransactions(data.transactions || []);
      }
    } catch { /* */ }
    setLoading(false);
  }, [token, filter]);

  useEffect(() => { fetchTransactions(); }, [fetchTransactions]);

  return (
    <motion.div className="consumer-transactions-page" initial={{ opacity: 0 }} animate={{ opacity: 1 }} data-testid="transactions-screen">
      <div className="bill-upload-header">
        <button className="bill-back" onClick={() => navigate(-1)} data-testid="txn-back-btn"><ArrowLeft size={22} /></button>
        <h1>Transaction History</h1>
      </div>

      {/* Filter Tabs */}
      <div className="txn-filter-tabs" data-testid="txn-filters">
        {FILTERS.map(f => (
          <button key={f.id} className={`txn-filter-tab ${filter === f.id ? 'active' : ''}`}
            onClick={() => setFilter(f.id)} data-testid={`filter-${f.id}`}>
            {f.label}
          </button>
        ))}
      </div>

      {/* Transactions List */}
      <div className="txn-list" data-testid="txn-list">
        {loading ? (
          <div className="consumer-loading"><div className="consumer-spinner" /></div>
        ) : transactions.length > 0 ? (
          transactions.map((t, i) => (
            <motion.div key={t.id || i} className="txn-list-item"
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.03 }} data-testid={`txn-item-${i}`}>
              <div className={`txn-list-icon ${t.type}`}>
                {t.type === 'earn' ? <ArrowUpRight size={18} /> : <ArrowDownRight size={18} />}
              </div>
              <div className="txn-list-info">
                <h4>{t.description || t.store_name}</h4>
                <p>
                  {t.bill_no && <span>#{t.bill_no} &middot; </span>}
                  {new Date(t.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
                </p>
              </div>
              <div className="txn-list-points">
                <span className={t.type === 'earn' ? 'positive' : 'negative'}>
                  {t.points > 0 ? '+' : ''}{t.points} pts
                </span>
                {t.amount > 0 && <span className="txn-amount">Rs {t.amount.toLocaleString()}</span>}
              </div>
            </motion.div>
          ))
        ) : (
          <div className="txn-empty">
            <Filter size={40} />
            <p>No {filter !== 'all' ? filter : ''} transactions found</p>
          </div>
        )}
      </div>
      <div className="home-spacer" />
    </motion.div>
  );
}
