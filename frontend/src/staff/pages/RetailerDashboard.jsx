import React, { useEffect, useState } from 'react';
import { useStaffAuth } from '../StaffApp';
import { toast } from 'sonner';

// Point 5: Retailer manager aggregate dashboard.
// Shows totals across all whitelisted brands, plus per-staff breakdown,
// with ZERO consumer PII (no phone / bill / name).
export default function RetailerDashboard() {
  const { retailerToken, API_URL, logoutRetailer } = useStaffAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API_URL}/staff/retailer/dashboard`, {
        headers: { Authorization: `Bearer ${retailerToken}` },
      });
      if (r.status === 401 || r.status === 403) {
        logoutRetailer();
        return;
      }
      if (!r.ok) throw new Error('load failed');
      setData(await r.json());
    } catch (e) {
      toast.error('Failed to load dashboard');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  if (loading) return <div className="sa-small">Loading…</div>;
  if (!data) return <div className="sa-small">Unable to load data.</div>;

  const s = data.summary || {};

  return (
    <div style={{ paddingBottom: 24 }} data-testid="retailer-dashboard">
      <div style={{ marginBottom: 16 }}>
        <div className="sa-small">Signed in as</div>
        <div style={{ fontWeight: 700, fontSize: 18 }}>{data.manager?.name}</div>
        <div className="sa-small">Brands: {(data.manager?.brands || []).join(', ')}</div>
      </div>

      <div className="sa-kpi-row" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10, marginBottom: 16 }}>
        <div className="sa-card"><div className="sa-small">Redeemable</div><div style={{ fontSize: 22, fontWeight: 700 }}>₹{s.redeemable || 0}</div></div>
        <div className="sa-card"><div className="sa-small">Redeemed</div><div style={{ fontSize: 22, fontWeight: 700 }}>₹{s.redeemed || 0}</div></div>
        <div className="sa-card"><div className="sa-small">Pending</div><div style={{ fontSize: 22, fontWeight: 700 }}>₹{s.pending || 0}</div></div>
        <div className="sa-card"><div className="sa-small">Active Staff</div><div style={{ fontSize: 22, fontWeight: 700 }}>{s.active_staff || 0}/{s.total_staff || 0}</div></div>
      </div>

      <div className="sa-card" style={{ marginBottom: 16 }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Staff Incentives</div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: 'left', borderBottom: '1px solid #333' }}>
                <th style={{ padding: '6px 4px' }}>Staff</th>
                <th style={{ padding: '6px 4px' }}>Redeemable</th>
                <th style={{ padding: '6px 4px' }}>Redeemed</th>
                <th style={{ padding: '6px 4px' }}>Pending</th>
              </tr>
            </thead>
            <tbody data-testid="retailer-staff-tbody">
              {(data.staff || []).map((x, i) => (
                <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  <td style={{ padding: '6px 4px' }}>
                    <div style={{ fontWeight: 600 }}>{x.name}</div>
                    <div className="sa-small">{x.staff_code} · {x.brand_name}</div>
                  </td>
                  <td style={{ padding: '6px 4px' }}>₹{x.redeemable}</td>
                  <td style={{ padding: '6px 4px' }}>₹{x.redeemed}</td>
                  <td style={{ padding: '6px 4px' }}>₹{x.pending}</td>
                </tr>
              ))}
              {(data.staff || []).length === 0 && (
                <tr><td colSpan={4} style={{ padding: 16, textAlign: 'center', opacity: 0.6 }}>No staff onboarded yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="sa-card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Recent Redemptions</div>
        {(data.redemptions || []).length === 0 && <div className="sa-small">No redemption requests yet.</div>}
        {(data.redemptions || []).slice(0, 20).map((r, i) => (
          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.05)', fontSize: 13 }}>
            <div>
              <div style={{ fontWeight: 600 }}>{r.staff_name}</div>
              <div className="sa-small">{r.reference} · {r.requested_at?.slice(0, 10)}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontWeight: 700 }}>₹{r.amount}</div>
              <div className="sa-small" style={{ color: r.status === 'settled' ? '#4ade80' : r.status === 'rejected' ? '#f87171' : '#fbbf24' }}>{r.status}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
