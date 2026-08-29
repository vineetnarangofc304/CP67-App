import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, Phone, Shield } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';

export default function Login() {
  const [step, setStep] = useState('phone');
  const [phone, setPhone] = useState('');
  const [otp, setOtp] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const { login, token, loading: authLoading } = useConsumerAuth();

  // If session is already valid, skip the Login screen.
  useEffect(() => {
    if (!authLoading && token) {
      navigate('/app/home', { replace: true });
    }
  }, [authLoading, token, navigate]);

  const sendOTP = async () => {
    if (phone.length < 10) { setError('Enter a valid 10-digit phone number'); return; }
    setLoading(true);
    setError('');
    
    // Use XMLHttpRequest to avoid fetch body stream issues
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API}/auth/send-otp`, true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.onload = function() {
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch { /* ignore */ }
      if (xhr.status >= 200 && xhr.status < 300) {
        if (data.success) {
          setStep('otp');
        } else {
          setError(data.detail || 'Failed to send OTP');
        }
      } else {
        setError(data.detail || 'Failed to send OTP');
      }
      setLoading(false);
    };
    xhr.onerror = function() {
      setError('Network error. Please try again.');
      setLoading(false);
    };
    xhr.send(JSON.stringify({ phone: phone.replace(/\D/g, '').slice(-10) }));
  };

  const verifyOTP = async () => {
    if (otp.length !== 4 && otp.length !== 6) { setError('Enter the 6-digit OTP'); return; }
    setLoading(true);
    setError('');

    // Capture marketing-attribution params (?src=SRC_MARKETING&qr=QR0124008) — set
    // when a customer scans a marketing QR / clicks an ad. Stored once in localStorage
    // so it survives the OTP step + page refreshes.
    let source = null, qrCode = null;
    try {
      const params = new URLSearchParams(window.location.search);
      source = params.get('src') || params.get('source') || localStorage.getItem('cp67_src');
      qrCode = params.get('qr') || params.get('qr_code') || localStorage.getItem('cp67_qr');
      if (source) localStorage.setItem('cp67_src', source);
      if (qrCode) localStorage.setItem('cp67_qr', qrCode);
    } catch { /* SSR safety */ }

    // Use XMLHttpRequest to avoid fetch body stream issues
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API}/auth/verify-otp`, true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.onload = function() {
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch { /* ignore */ }
      if (xhr.status >= 200 && xhr.status < 300) {
        if (data.success && data.token) {
          login(data.token, data.user);
          // Clear the attribution params now that they've been persisted on the user
          try {
            localStorage.removeItem('cp67_src');
            localStorage.removeItem('cp67_qr');
          } catch { /* ignore */ }
          if (data.is_new || !data.user.onboarding_complete) {
            navigate('/app/onboarding', { replace: true });
          } else {
            navigate('/app/home', { replace: true });
          }
        } else {
          setError(data.detail || 'Invalid OTP');
        }
      } else {
        setError(data.detail || 'Invalid OTP');
      }
      setLoading(false);
    };
    xhr.onerror = function() {
      setError('Network error. Please try again.');
      setLoading(false);
    };
    xhr.send(JSON.stringify({
      phone: phone.replace(/\D/g, '').slice(-10),
      otp,
      source,
      qr_code: qrCode,
    }));
  };

  return (
    <motion.div
      className="consumer-login"
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      data-testid="login-screen"
    >
      <div className="login-header">
        <button className="login-back" onClick={() => step === 'otp' ? setStep('phone') : navigate('/app/welcome')} data-testid="login-back-btn">
          <ArrowLeft size={22} />
        </button>
      </div>

      <div className="login-body">
        <img src="/ha-logo-white.png" alt="Homeland Advantage" className="login-ha-logo" />

        {step === 'phone' && (
          // Point 41a: brand tagline block above the heading — locks the app's identity on first view.
          <div style={{ marginBottom: 18 }} data-testid="login-tagline">
            <div style={{ color: '#D4AF37', fontFamily: 'var(--font-heading)', fontSize: 13, letterSpacing: '0.18em', textTransform: 'uppercase', marginBottom: 4 }}>
              CP67&apos;s Loyalty Programme
            </div>
            <div style={{ color: 'rgba(26,26,46,0.75)', fontSize: 14, letterSpacing: '0.02em', fontWeight: 500 }}>
              Shop. Scan. Earn.
            </div>
          </div>
        )}

        <h1 style={{ fontFamily: 'var(--font-heading)', letterSpacing: '-0.02em' }}>{step === 'phone' ? 'Welcome to Homeland Advantage' : 'Verify OTP'}</h1>
        <p className="login-subtitle">
          {step === 'phone'
            ? 'Enter your phone number to continue'
            : `We've sent a code to +91 ${phone.slice(-10).replace(/(\d{5})(\d{5})/, '$1 $2')}`
          }
        </p>

        {step === 'phone' ? (
          <div className="login-input-group">
            <div className="login-phone-input">
              <span className="login-country">+91</span>
              <input
                type="tel"
                placeholder="Enter phone number"
                maxLength={10}
                value={phone}
                onChange={e => setPhone(e.target.value.replace(/\D/g, ''))}
                data-testid="phone-input"
                autoFocus
              />
            </div>
            {error && <p className="login-error" data-testid="login-error">{error}</p>}
            <button
              className="login-submit"
              onClick={sendOTP}
              disabled={loading || phone.length < 10}
              data-testid="send-otp-btn"
            >
              {loading ? 'Sending...' : 'Send OTP'}
            </button>
          </div>
        ) : (
          <div className="login-input-group">
            <div className="login-otp-inputs">
              {[0, 1, 2, 3, 4, 5].map(i => (
                <input
                  key={i}
                  type="tel"
                  inputMode="numeric"
                  maxLength={1}
                  className="login-otp-box"
                  value={otp[i] || ''}
                  data-testid={`otp-input-${i}`}
                  autoFocus={i === 0}
                  onChange={e => {
                    const v = e.target.value.replace(/\D/g, '');
                    // If the input fired with multiple chars (paste / SMS autofill),
                    // distribute them across boxes starting from i.
                    if (v.length > 1) {
                      const next = (otp.slice(0, i) + v).replace(/\D/g, '').slice(0, 6);
                      setOtp(next);
                      const focusIdx = Math.min(next.length, 5);
                      const inputs = e.target.parentElement.querySelectorAll('input');
                      inputs[focusIdx]?.focus();
                      return;
                    }
                    const newOtp = otp.split('');
                    newOtp[i] = v;
                    setOtp(newOtp.join(''));
                    if (v && i < 5) e.target.nextElementSibling?.focus();
                  }}
                  onPaste={e => {
                    e.preventDefault();
                    const txt = (e.clipboardData.getData('text') || '').replace(/\D/g, '').slice(0, 6);
                    if (!txt) return;
                    setOtp(txt);
                    const inputs = e.currentTarget.parentElement.querySelectorAll('input');
                    inputs[Math.min(txt.length, 5)]?.focus();
                  }}
                  onKeyDown={e => {
                    if (e.key === 'Backspace' && !otp[i] && i > 0) {
                      e.target.previousElementSibling?.focus();
                    }
                  }}
                />
              ))}
            </div>
            {error && <p className="login-error" data-testid="login-error">{error}</p>}
            <button
              className="login-submit"
              onClick={verifyOTP}
              disabled={loading || (otp.length !== 4 && otp.length !== 6)}
              data-testid="verify-otp-btn"
            >
              {loading ? 'Verifying...' : 'Verify & Continue'}
            </button>
            <button className="login-resend" onClick={sendOTP} data-testid="resend-otp-btn">
              Resend OTP
            </button>
          </div>
        )}

        <p className="login-terms">
          By continuing, you agree to CP67&apos;s <span className="login-terms-link" onClick={() => navigate('/app/legal')} data-testid="terms-link">Terms of Service</span> and Privacy Policy
        </p>
      </div>
    </motion.div>
  );
}
