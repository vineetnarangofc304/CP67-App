import React, { useEffect, useState } from 'react';
import { useStaffAuth } from '../StaffApp';
import { toast } from 'sonner';
import { Share2, Copy } from 'lucide-react';

export default function StaffQR() {
  const { token, API_URL } = useStaffAuth();
  const [qr, setQr] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_URL}/staff/qr`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(d => { setQr(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [token, API_URL]);

  if (loading) return <div className="sa-small">Loading QR…</div>;
  if (!qr) return <div className="sa-small">Failed to load QR</div>;

  const copyLink = async () => {
    try { await navigator.clipboard.writeText(qr.whatsapp_url); toast.success('Link copied'); }
    catch { toast.error('Copy failed'); }
  };

  const share = async () => {
    if (navigator.share) {
      try { await navigator.share({ title: `Join CP67 via ${qr.staff_code}`, url: qr.whatsapp_url }); }
      catch { /* user cancelled */ }
    } else { copyLink(); }
  };

  return (
    <div data-testid="staff-qr-page">
      <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 6 }}>Your Attribution QR</h2>
      <p className="sa-small" style={{ marginBottom: 20 }}>
        Show this at billing. Every customer who scans and uploads a bill within 15 min earns you an incentive.
      </p>
      <div className="sa-card" style={{ textAlign: 'center' }}>
        {qr.qr_image_base64 && (
          <img
            src={`data:image/png;base64,${qr.qr_image_base64}`}
            alt="Staff QR"
            style={{ width: '100%', maxWidth: 320, borderRadius: 12, background: 'white', padding: 12 }}
            data-testid="staff-qr-image"
          />
        )}
        <div style={{ marginTop: 16, fontSize: 18, fontWeight: 700, color: 'var(--sa-accent)' }}>
          {qr.staff_code}
        </div>
        <div className="sa-small" style={{ marginTop: 2 }}>{qr.brand_name}</div>

        <div style={{ display: 'flex', gap: 10, marginTop: 20, justifyContent: 'center' }}>
          <button className="sa-btn" onClick={share} data-testid="qr-share-btn"><Share2 size={16} /> Share</button>
          <button className="sa-btn ghost" onClick={copyLink} data-testid="qr-copy-btn"><Copy size={16} /> Copy Link</button>
        </div>
      </div>

      <div className="sa-card">
        <div className="sa-label">Prefilled WhatsApp message</div>
        <div style={{ marginTop: 8, fontSize: 13, fontFamily: 'monospace', color: 'var(--sa-text-dim)', wordBreak: 'break-all' }}>
          {decodeURIComponent(qr.whatsapp_url.split('?text=')[1] || '')}
        </div>
      </div>
    </div>
  );
}
