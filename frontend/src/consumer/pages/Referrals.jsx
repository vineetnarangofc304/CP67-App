import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Share2, Copy, Users, Gift, CheckCircle, ArrowRight } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';
import { toast } from 'sonner';

export default function Referrals() {
  const [referral, setReferral] = useState(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [applyCode, setApplyCode] = useState('');
  const [applying, setApplying] = useState(false);
  const { token } = useConsumerAuth();

  const fetchReferral = useCallback(async () => {
    try {
      const res = await fetch(`${API}/referral`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) setReferral(await res.json());
    } catch { /* */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { fetchReferral(); }, [fetchReferral]);

  const copyCode = () => {
    if (!referral?.referral_code) return;
    navigator.clipboard.writeText(referral.referral_code).then(() => {
      setCopied(true);
      toast.success('Referral code copied!');
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => {
      toast.error('Could not copy. Try manually.');
    });
  };

  const shareReferral = async () => {
    if (!referral) return;
    if (navigator.share) {
      try {
        await navigator.share({
          title: 'Homeland Advantage - CP67 Mall',
          text: referral.share_text,
          url: referral.referral_link
        });
      } catch { /* user cancelled */ }
    } else {
      copyCode();
    }
  };

  const handleApply = async () => {
    if (!applyCode.trim()) return;
    setApplying(true);
    try {
      const res = await fetch(`${API}/referral/apply?code=${applyCode.trim()}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (res.ok) {
        toast.success(data.message);
        setApplyCode('');
      } else {
        toast.error(data.detail || 'Could not apply code');
      }
    } catch {
      toast.error('Something went wrong');
    }
    setApplying(false);
  };

  if (loading) return <div className="consumer-loading"><div className="consumer-spinner" /></div>;

  return (
    <motion.div className="consumer-referrals" initial={{ opacity: 0 }} animate={{ opacity: 1 }} data-testid="referrals-screen">
      <div className="referrals-header">
        <h1>Refer & Earn</h1>
        <p>Invite friends and earn bonus points</p>
      </div>

      {/* Referral Code Card */}
      <div className="referral-code-card" data-testid="referral-code-card">
        <div className="referral-card-bg" />
        <div className="referral-card-content">
          <p className="referral-card-label">Your Referral Code</p>
          <div className="referral-code-display">
            <span className="referral-code-text" data-testid="referral-code">{referral?.referral_code || '---'}</span>
            <button className="referral-copy-btn" onClick={copyCode} data-testid="copy-referral-btn">
              {copied ? <CheckCircle size={18} /> : <Copy size={18} />}
            </button>
          </div>
          <p className="referral-card-sub">Share this code with friends to earn {referral?.points_per_referral || 50} points each</p>
        </div>
      </div>

      {/* Share Button */}
      <button className="referral-share-btn" onClick={shareReferral} data-testid="share-referral-btn">
        <Share2 size={18} /> Share with Friends
      </button>

      {/* Stats */}
      <div className="referral-stats" data-testid="referral-stats">
        <div className="referral-stat-card">
          <div className="referral-stat-icon"><Users size={20} /></div>
          <div className="referral-stat-info">
            <span className="referral-stat-value" data-testid="total-referrals">{referral?.total_referrals || 0}</span>
            <span className="referral-stat-label">Friends Referred</span>
          </div>
        </div>
        <div className="referral-stat-card">
          <div className="referral-stat-icon earn"><Gift size={20} /></div>
          <div className="referral-stat-info">
            <span className="referral-stat-value" data-testid="bonus-points">{referral?.bonus_points_earned || 0}</span>
            <span className="referral-stat-label">Bonus Points Earned</span>
          </div>
        </div>
      </div>

      {/* How it Works */}
      <div className="referral-how" data-testid="referral-how-it-works">
        <h2>How It Works</h2>
        <div className="referral-steps">
          <div className="referral-step">
            <div className="referral-step-num">1</div>
            <div className="referral-step-info">
              <h4>Share Your Code</h4>
              <p>Send your unique referral code to friends & family</p>
            </div>
          </div>
          <div className="referral-step-arrow"><ArrowRight size={16} /></div>
          <div className="referral-step">
            <div className="referral-step-num">2</div>
            <div className="referral-step-info">
              <h4>Friend Signs Up</h4>
              <p>They join Homeland Advantage using your code</p>
            </div>
          </div>
          <div className="referral-step-arrow"><ArrowRight size={16} /></div>
          <div className="referral-step">
            <div className="referral-step-num">3</div>
            <div className="referral-step-info">
              <h4>Both Earn Points</h4>
              <p>You both get {referral?.points_per_referral || 50} bonus points</p>
            </div>
          </div>
        </div>
      </div>

      {/* Apply Referral Code */}
      <div className="referral-apply-section" data-testid="referral-apply-section">
        <h2>Have a Referral Code?</h2>
        <div className="referral-apply-form">
          <input
            placeholder="Enter referral code"
            value={applyCode}
            onChange={e => setApplyCode(e.target.value.toUpperCase())}
            data-testid="referral-apply-input"
          />
          <button
            onClick={handleApply}
            disabled={applying || !applyCode.trim()}
            data-testid="apply-referral-btn"
          >
            {applying ? 'Applying...' : 'Apply'}
          </button>
        </div>
      </div>

      <div className="home-spacer" />
    </motion.div>
  );
}
