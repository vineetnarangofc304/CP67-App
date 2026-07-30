import React, { useEffect, useState } from 'react';
import { useStaffAuth } from '../StaffApp';
import { toast } from 'sonner';
import { Wallet, Clock } from 'lucide-react';

export default function StaffRedeem() {
  const { token, API_URL } = useStaffAuth();
  const [dashboard, setDashboard] = useState(null);
  const [history, setHistory] = useState([]);
  const [amount, setAmount] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [d, h] = await Promise.all([
        fetch(`${API_URL}/staff/dashboard`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json()),
        fetch(`${API_URL}/staff/redemptions`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json()),
      ]);
      setDashboard(d);
      setHistory(h.redemptions || []);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [token]);

  const submit = async () => {
    const amt = Number(amount);
    if (!amt || amt <= 0) { toast.error('Enter a valid amount'); return; }
    setBusy(true);
    try {
      const r = await fetch(`${API_URL}/staff/redeem`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ amount: amt }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || 'Redeem failed');
      toast.success(`Redemption submitted · Ref ${data.reference}`);
      setAmount('');
      load();
    } catch (e) {
      toast.error(e.message);
    } finally { setBusy(false); }
  };

  const redeemable = dashboard?.summary?.redeemable || 0;

  return (
    <div data-testid="staff-redeem-page">
      <div className="sa-card gradient">
        <div className="sa-label">Redeemable Balance</div>
        <div className="sa-value">₹{redeemable}</div>
        <div className="sa-small" style={{ marginTop: 6 }}>
          Redemption is settled by CP67 admin within 3-5 business days.
        </div>
      </div>

      <div className="sa-card">
        <div className="sa-label">Amount to redeem</div>
        <input
          type="number"
          className="sa-input"
          placeholder="₹0"
          value={amount}
          onChange={e => setAmount(e.target.value)}
          disabled={redeemable === 0}
          style={{ marginTop: 8, marginBottom: 14 }}
          data-testid="redeem-amount-input"
        />
        <button
          className="sa-btn full"
          onClick={submit}
          disabled={busy || redeemable === 0}
          data-testid="redeem-submit-btn"
        >
          {busy ? 'Submitting…' : <><Wallet size={16} /> Request Redemption</>}
        </button>
      </div>

      <h3 style={{ fontSize: 15, fontWeight: 600, margin: '20px 0 8px' }}>Recent Requests</h3>
      <div className="sa-card">
        {loading && <div className="sa-small">Loading…</div>}
        {!loading && history.length === 0 && (
          <div className="sa-small" style={{ padding: 20, textAlign: 'center' }}>No redemptions yet.</div>
        )}
        {history.map(h => (
          <div key={h.id} className="sa-list-item">
            <div>
              <div style={{ fontWeight: 600 }}>{h.reference}</div>
              <div className="sa-small" style={{ fontSize: 12 }}>
                <Clock size={11} style={{ display: 'inline', marginRight: 2 }} />
                {h.requested_at?.slice(0, 16).replace('T', ' ')}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontWeight: 700 }}>₹{h.amount}</div>
              <span className={`sa-chip ${h.status === 'settled' ? 'good' : h.status === 'rejected' ? 'bad' : 'pending'}`}>{h.status}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
