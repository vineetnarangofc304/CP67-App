import React, { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';
import { useNavigate } from 'react-router-dom';

/**
 * Consumer popup / in-app message.
 * Fetches the highest-priority active popup once per session, respects
 * admin-configured show_frequency (once / daily / every_session).
 */
export default function InAppPopup() {
  const { token } = useConsumerAuth();
  const [popup, setPopup] = useState(null);
  const [showing, setShowing] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (!token) return;
    // Session guard: only fetch once per SPA session
    if (window.__cp67PopupChecked) return;
    window.__cp67PopupChecked = true;

    const t = setTimeout(async () => {
      try {
        const r = await fetch(`${API}/popups/active`, { headers: { Authorization: `Bearer ${token}` } });
        if (r.ok) {
          const d = await r.json();
          if (d.popup) { setPopup(d.popup); setShowing(true); }
        }
      } catch { /* ignore */ }
    }, 1500); // give the main screen a beat to paint
    return () => clearTimeout(t);
  }, [token]);

  const dismiss = async () => {
    setShowing(false);
    if (popup?.id) {
      try {
        await fetch(`${API}/popups/dismiss`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify({ popup_id: popup.id }),
        });
      } catch { /* ignore */ }
    }
  };

  const cta = () => {
    if (popup?.cta_url) {
      dismiss();
      if (popup.cta_url.startsWith('/')) navigate(popup.cta_url);
      else window.open(popup.cta_url, '_blank');
    }
  };

  if (!showing || !popup) return null;

  return (
    <div style={S.backdrop} onClick={dismiss} data-testid="popup-backdrop">
      <div style={S.card} onClick={e => e.stopPropagation()} data-testid="in-app-popup">
        <button style={S.close} onClick={dismiss} aria-label="Close" data-testid="popup-close"><X size={18} /></button>
        {popup.image_url && (
          <img src={popup.image_url} alt="" style={S.image} />
        )}
        <div style={S.body}>
          <h2 style={S.title}>{popup.title}</h2>
          <p style={S.text}>{popup.body}</p>
          {popup.cta_label && popup.cta_url && (
            <button style={S.cta} onClick={cta} data-testid="popup-cta">
              {popup.cta_label}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

const S = {
  backdrop: {
    position: 'fixed', inset: 0, background: 'rgba(30, 27, 24, 0.55)', backdropFilter: 'blur(4px)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20, zIndex: 1000,
    animation: 'fadeIn 200ms ease',
  },
  card: {
    background: '#FFF', borderRadius: 20, maxWidth: 360, width: '100%',
    boxShadow: '0 24px 60px rgba(0,0,0,0.35)', position: 'relative', overflow: 'hidden',
  },
  close: {
    position: 'absolute', top: 12, right: 12, width: 32, height: 32,
    borderRadius: 999, background: 'rgba(255,255,255,0.85)', border: 'none',
    display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', zIndex: 2,
  },
  image: { width: '100%', display: 'block', maxHeight: 180, objectFit: 'cover' },
  body: { padding: '22px 22px 24px' },
  title: {
    fontFamily: "'Playfair Display', serif", fontSize: 22, margin: 0,
    color: '#1E1B18', letterSpacing: '-0.01em',
  },
  text: { color: '#635E56', fontSize: 15, lineHeight: 1.5, margin: '10px 0 18px' },
  cta: {
    width: '100%', padding: '14px 20px', background: 'linear-gradient(135deg, #B8860B, #DAA520)',
    color: '#FFF', border: 'none', borderRadius: 12, fontSize: 15, fontWeight: 600, cursor: 'pointer',
  },
};
