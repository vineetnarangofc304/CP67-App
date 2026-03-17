import React, { useState } from 'react';
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
  const { login } = useConsumerAuth();

  const sendOTP = async () => {
    if (phone.length < 10) { setError('Enter a valid 10-digit phone number'); return; }
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${API}/auth/send-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: phone.replace(/\D/g, '').slice(-10) })
      });
      const data = await res.json();
      if (data.success) {
        setStep('otp');
      } else {
        setError(data.detail || 'Failed to send OTP');
      }
    } catch {
      setError('Network error. Please try again.');
    }
    setLoading(false);
  };

  const verifyOTP = async () => {
    if (otp.length < 4) { setError('Enter valid OTP'); return; }
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${API}/auth/verify-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: phone.replace(/\D/g, '').slice(-10), otp })
      });
      if (!res.ok) {
        const err = await res.json();
        setError(err.detail || 'Invalid OTP');
        setLoading(false);
        return;
      }
      const data = await res.json();
      login(data.token, data.user);
      if (data.is_new || !data.user.onboarding_complete) {
        navigate('/app/onboarding', { replace: true });
      } else {
        navigate('/app/home', { replace: true });
      }
    } catch {
      setError('Network error. Please try again.');
    }
    setLoading(false);
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
        <div className="login-icon-wrap">
          {step === 'phone' ? <Phone size={28} /> : <Shield size={28} />}
        </div>

        <h1>{step === 'phone' ? 'Welcome to CP67' : 'Verify OTP'}</h1>
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
              {[0, 1, 2, 3].map(i => (
                <input
                  key={i}
                  type="tel"
                  maxLength={1}
                  className="login-otp-box"
                  value={otp[i] || ''}
                  data-testid={`otp-input-${i}`}
                  autoFocus={i === 0}
                  onChange={e => {
                    const v = e.target.value.replace(/\D/g, '');
                    const newOtp = otp.split('');
                    newOtp[i] = v;
                    setOtp(newOtp.join(''));
                    if (v && i < 3) e.target.nextElementSibling?.focus();
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
              disabled={loading || otp.length < 4}
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
          By continuing, you agree to CP67's Terms of Service and Privacy Policy
        </p>
      </div>
    </motion.div>
  );
}
