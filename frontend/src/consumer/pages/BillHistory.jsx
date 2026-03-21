import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, FileText, CheckCircle, XCircle, Clock, AlertCircle } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';

const statusConfig = {
  approved: { icon: CheckCircle, color: '#22c55e', label: 'Approved' },
  auto_approved: { icon: CheckCircle, color: '#22c55e', label: 'Approved' },
  rejected: { icon: XCircle, color: '#ef4444', label: 'Rejected' },
  pending: { icon: Clock, color: '#f59e0b', label: 'Pending' },
  processing: { icon: Clock, color: '#3b82f6', label: 'Processing' },
  manual_review: { icon: AlertCircle, color: '#f59e0b', label: 'Under Review' },
  pending_review: { icon: AlertCircle, color: '#f59e0b', label: 'Under Review' },
  duplicate: { icon: XCircle, color: '#94a3b8', label: 'Duplicate' },
};

export default function BillHistory() {
  const [bills, setBills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState('all');
  const { token } = useConsumerAuth();
  const navigate = useNavigate();

  const fetchBills = useCallback(async () => {
    try {
      const res = await fetch(`${API}/bills`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setBills(data.bills || []);
      }
    } catch { /* */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { fetchBills(); }, [fetchBills]);

  const filtered = filterStatus === 'all' ? bills : bills.filter(b => {
    if (filterStatus === 'approved') return b.status === 'approved' || b.status === 'auto_approved';
    if (filterStatus === 'pending') return ['pending', 'processing', 'manual_review', 'pending_review'].includes(b.status);
    if (filterStatus === 'rejected') return b.status === 'rejected' || b.status === 'duplicate';
    return true;
  });

  return (
    <motion.div className="consumer-bill-history" initial={{ opacity: 0 }} animate={{ opacity: 1 }} data-testid="bill-history-screen">
      <div className="bill-upload-header">
        <button className="bill-back" onClick={() => navigate(-1)} data-testid="bill-history-back"><ArrowLeft size={22} /></button>
        <h1>Bill History</h1>
      </div>

      {/* Status Filters */}
      <div className="txn-filter-tabs" data-testid="bill-filters">
        {['all', 'approved', 'pending', 'rejected'].map(s => (
          <button key={s} className={`txn-filter-tab ${filterStatus === s ? 'active' : ''}`}
            onClick={() => setFilterStatus(s)} data-testid={`bill-filter-${s}`}>
            {s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>

      <div className="bill-history-list" data-testid="bill-list">
        {loading ? (
          <div className="consumer-loading"><div className="consumer-spinner" /></div>
        ) : filtered.length > 0 ? (
          filtered.map((bill, i) => {
            const cfg = statusConfig[bill.status] || statusConfig.pending;
            const StatusIcon = cfg.icon;
            return (
              <motion.div key={bill.id} className="bill-history-item"
                initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.03 }} data-testid={`bill-item-${i}`}>
                <div className="bill-hist-icon" style={{ color: cfg.color }}><StatusIcon size={22} /></div>
                <div className="bill-hist-info">
                  <h4>{bill.store_name || 'Processing...'}</h4>
                  <p>
                    {bill.bill_no && <span>#{bill.bill_no} &middot; </span>}
                    {bill.created_at && new Date(bill.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
                  </p>
                  {bill.rejection_reason && <p className="bill-rejection-reason">{bill.rejection_reason}</p>}
                </div>
                <div className="bill-hist-right">
                  {bill.amount > 0 && <span className="bill-hist-amount">Rs {bill.amount.toLocaleString()}</span>}
                  <span className="bill-hist-status" style={{ color: cfg.color }}>{cfg.label}</span>
                  {bill.points_issued > 0 && <span className="bill-hist-points">+{bill.points_issued} pts</span>}
                </div>
              </motion.div>
            );
          })
        ) : (
          <div className="txn-empty">
            <FileText size={40} />
            <p>No {filterStatus !== 'all' ? filterStatus : ''} bills found</p>
          </div>
        )}
      </div>
      <div className="home-spacer" />
    </motion.div>
  );
}
