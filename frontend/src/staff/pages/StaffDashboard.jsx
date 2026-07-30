import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useStaffAuth } from '../StaffApp';
import { QrCode, ListChecks, Wallet, TrendingUp } from 'lucide-react';

export default function StaffDashboard() {
  const { token, staff, API_URL } = useStaffAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_URL}/staff/dashboard`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [token, API_URL]);

  if (loading) return <div className="sa-small">Loading…</div>;
  if (!data) return <div className="sa-small">No data</div>;

  const s = data.summary || {};
  const p = data.performance || {};

  return (
    <div data-testid="staff-dashboard">
      <div className="sa-card gradient">
        <div className="sa-label">Total Earned</div>
        <div className="sa-value">₹{s.total_earned || 0}</div>
        <div className="sa-small" style={{ marginTop: 6 }}>
          <span style={{ color: 'var(--sa-good)' }}>₹{s.redeemable || 0}</span> ready to redeem
          {s.on_hold > 0 && <> · <span style={{ color: 'var(--sa-text-dim)' }}>₹{s.on_hold} on hold</span></>}
        </div>
      </div>

      <div className="sa-grid-2" style={{ marginBottom: 16 }}>
        <div className="sa-card" style={{ marginBottom: 0 }}>
          <div className="sa-label">Registrations</div>
          <div style={{ fontSize: 28, fontWeight: 700, marginTop: 4 }}>{p.registrations || 0}</div>
          <div className="sa-small">₹{p.current_registration_rate}/next</div>
        </div>
        <div className="sa-card" style={{ marginBottom: 0 }}>
          <div className="sa-label">Bill Uploads</div>
          <div style={{ fontSize: 28, fontWeight: 700, marginTop: 4 }}>{p.bill_uploads || 0}</div>
          <div className="sa-small">₹{p.current_upload_rate}/next</div>
        </div>
      </div>

      <div className="sa-card">
        <div style={{ fontWeight: 600, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
          <TrendingUp size={16} color="var(--sa-accent)" /> How to earn
        </div>
        <div className="sa-small" style={{ lineHeight: 1.6 }}>
          1. Show your QR to every customer at billing<br />
          2. Ask them to scan it and open the WhatsApp chat<br />
          3. Earn <b style={{ color: 'var(--sa-accent)' }}>₹{p.current_registration_rate}</b> per new customer once they upload their first bill<br />
          4. Earn <b style={{ color: 'var(--sa-accent)' }}>₹{p.current_upload_rate}</b> per bill uploaded within 15 min of QR scan
        </div>
      </div>

      <div className="sa-grid-2" style={{ marginTop: 4 }}>
        <Link to="/staff-app/qr" className="sa-btn full" style={{ textDecoration: 'none' }} data-testid="quick-qr-btn">
          <QrCode size={16} /> My QR
        </Link>
        <Link to="/staff-app/redeem" className="sa-btn full violet" style={{ textDecoration: 'none' }} data-testid="quick-redeem-btn">
          <Wallet size={16} /> Redeem
        </Link>
      </div>

      <Link to="/staff-app/incentives" style={{ display: 'block', marginTop: 16, color: 'var(--sa-text-dim)', textDecoration: 'none', textAlign: 'center', fontSize: 14 }}>
        View all earnings →
      </Link>
    </div>
  );
}
