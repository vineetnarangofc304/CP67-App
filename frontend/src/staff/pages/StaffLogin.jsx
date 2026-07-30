import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStaffAuth } from '../StaffApp';
import { toast } from 'sonner';

export default function StaffLogin() {
  const { login, API_URL } = useStaffAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState('phone');
  const [phone, setPhone] = useState('');
  const [otp, setOtp] = useState(['', '', '', '', '', '']);
  const [busy, setBusy] = useState(false);
  const otpRefs = useRef([]);

  const sendOtp = async () => {
    if (!/^[0-9]{10}$/.test(phone)) { toast.error('Enter a valid 10-digit phone'); return; }
    setBusy(true);
    try {
      const r = await fetch(`${API_URL}/staff/auth/send-otp`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone }),
      });
      if (!r.ok) throw new Error('send failed');
      toast.success('OTP sent to your phone');
      setStep('otp');
      setTimeout(() => otpRefs.current[0]?.focus(), 100);
    } catch (e) {
      toast.error('Failed to send OTP');
    } finally { setBusy(false); }
  };

  const handleOtpChange = (i, v) => {
    if (v.length > 1) {
      // paste 6-digit
      const digits = v.replace(/\D/g, '').slice(0, 6).split('');
      const next = [...otp];
      digits.forEach((d, idx) => { if (idx < 6) next[idx] = d; });
      setOtp(next);
      const focusIdx = Math.min(digits.length, 5);
      otpRefs.current[focusIdx]?.focus();
      return;
    }
    const cleaned = v.replace(/\D/g, '');
    const next = [...otp];
    next[i] = cleaned;
    setOtp(next);
    if (cleaned && i < 5) otpRefs.current[i + 1]?.focus();
  };

  const verifyOtp = async () => {
    const code = otp.join('');
    if (code.length < 4) { toast.error('Enter the OTP'); return; }
    setBusy(true);
    try {
      const r = await fetch(`${API_URL}/staff/auth/verify-otp`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone, otp: code }),
      });
      if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.detail || 'invalid'); }
      const d = await r.json();
      login(d.token, d.staff);
      toast.success(`Welcome, ${d.staff.name}`);
      navigate('/staff-app', { replace: true });
    } catch (e) {
      toast.error(e.message || 'OTP verification failed');
    } finally { setBusy(false); }
  };

  return (
    <div className="sa-splash">
      <div style={{ width: '100%', maxWidth: 380 }}>
        <div className="sa-logo-lg">HA</div>
        <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 6 }}>Retail Staff Portal</h1>
        <p className="sa-small" style={{ marginBottom: 28 }}>
          Homeland Advantage · CP67 Mall<br />
          Earn incentives for every customer you onboard.
        </p>

        {step === 'phone' && (
          <div className="sa-card">
            <label className="sa-label">Phone Number</label>
            <input
              type="tel"
              className="sa-input"
              placeholder="10-digit mobile"
              value={phone}
              onChange={e => setPhone(e.target.value.replace(/\D/g, '').slice(0, 10))}
              style={{ marginTop: 8, marginBottom: 16 }}
              data-testid="staff-phone-input"
            />
            <button className="sa-btn full" onClick={sendOtp} disabled={busy} data-testid="staff-send-otp-btn">
              {busy ? 'Sending…' : 'Send OTP'}
            </button>
          </div>
        )}

        {step === 'otp' && (
          <div className="sa-card">
            <label className="sa-label">Enter OTP sent to +91 {phone}</label>
            <div className="sa-otp-boxes" style={{ marginTop: 12, marginBottom: 16 }} data-testid="staff-otp-boxes">
              {otp.map((d, i) => (
                <input
                  key={i}
                  ref={el => otpRefs.current[i] = el}
                  value={d}
                  onChange={e => handleOtpChange(i, e.target.value)}
                  onKeyDown={e => { if (e.key === 'Backspace' && !otp[i] && i > 0) otpRefs.current[i - 1]?.focus(); }}
                  inputMode="numeric"
                  maxLength={i === 0 ? 6 : 1}
                  data-testid={`staff-otp-${i}`}
                />
              ))}
            </div>
            <button className="sa-btn full" onClick={verifyOtp} disabled={busy} data-testid="staff-verify-otp-btn">
              {busy ? 'Verifying…' : 'Verify & Sign In'}
            </button>
            <button className="sa-btn ghost full" onClick={() => setStep('phone')} style={{ marginTop: 10 }} data-testid="staff-change-phone-btn">
              Change phone
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
