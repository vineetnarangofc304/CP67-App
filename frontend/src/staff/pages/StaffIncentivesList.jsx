import React, { useEffect, useState } from 'react';
import { useStaffAuth } from '../StaffApp';

const CHIP_MAP = {
  redeemable: { class: 'good', label: 'Ready' },
  redeemed: { class: 'dim', label: 'Redeemed' },
  approved: { class: 'good', label: 'Approved' },
  pending: { class: 'pending', label: 'Pending' },
  pending_verification: { class: 'pending', label: 'Under review' },
  cancelled: { class: 'bad', label: 'Cancelled' },
  expired: { class: 'bad', label: 'Expired' },
};

export default function StaffIncentivesList() {
  const { token, API_URL } = useStaffAuth();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_URL}/staff/incentives`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(d => { setRows(d.incentives || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, [token, API_URL]);

  return (
    <div data-testid="staff-incentives-list">
      <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 6 }}>Earnings History</h2>
      <p className="sa-small" style={{ marginBottom: 20 }}>Every credit is tied to a bill or new customer signup you drove.</p>
      <div className="sa-card">
        {loading && <div className="sa-small">Loading…</div>}
        {!loading && rows.length === 0 && (
          <div className="sa-small" style={{ padding: 20, textAlign: 'center' }}>
            No incentives yet. Share your QR at the till to start earning.
          </div>
        )}
        {rows.map(r => {
          const chip = CHIP_MAP[r.status] || { class: 'dim', label: r.status };
          return (
            <div key={r.id} className="sa-list-item">
              <div>
                <div style={{ fontWeight: 600, textTransform: 'capitalize' }}>
                  {r.type === 'registration' ? 'New Customer' : 'Bill Upload'}
                </div>
                <div className="sa-small" style={{ fontSize: 12 }}>
                  {r.created_at?.slice(0, 16).replace('T', ' ')}
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontWeight: 700, color: 'var(--sa-accent)' }}>₹{r.amount}</div>
                <span className={`sa-chip ${chip.class}`} style={{ marginTop: 2, display: 'inline-block' }}>{chip.label}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
