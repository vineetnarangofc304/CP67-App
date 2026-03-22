import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, Award, ChevronRight, Star, Crown, Shield, Gem } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';

const TIER_ICONS = {
  Bronze: Shield,
  Silver: Star,
  Gold: Crown,
  Platinum: Gem,
};

const TIER_COLORS = {
  Bronze: { bg: '#CD7F32', gradient: 'linear-gradient(135deg, #CD7F32 0%, #A0522D 100%)', light: '#F5E6D3' },
  Silver: { bg: '#C0C0C0', gradient: 'linear-gradient(135deg, #C0C0C0 0%, #A8A8A8 100%)', light: '#F0F0F0' },
  Gold: { bg: '#D4AF37', gradient: 'linear-gradient(135deg, #D4AF37 0%, #B8960C 100%)', light: '#FFF8E1' },
  Platinum: { bg: '#6B5CE7', gradient: 'linear-gradient(135deg, #6B5CE7 0%, #8B5CF6 100%)', light: '#EDE9FE' },
};

export default function TierJourney() {
  const [tierData, setTierData] = useState(null);
  const [loading, setLoading] = useState(true);
  const { token } = useConsumerAuth();
  const navigate = useNavigate();

  const fetchTier = useCallback(async () => {
    try {
      const res = await fetch(`${API}/tier-info`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) setTierData(await res.json());
    } catch { /* */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { fetchTier(); }, [fetchTier]);

  if (loading) return <div className="consumer-loading"><div className="consumer-spinner" /></div>;

  const current = tierData?.current_tier || {};
  const tiers = tierData?.tiers || [];
  const totalEarned = tierData?.total_earned || 0;

  const currentIdx = tiers.findIndex(t => t.name === current.name);

  return (
    <motion.div className="tier-journey" initial={{ opacity: 0 }} animate={{ opacity: 1 }} data-testid="tier-journey-screen">
      <div className="tier-journey-header">
        <button className="tier-back-btn" onClick={() => navigate(-1)} data-testid="tier-back-btn">
          <ArrowLeft size={22} />
        </button>
        <h1>My Tier Journey</h1>
      </div>

      {/* Current Tier Hero */}
      <div className="tier-hero" style={{ background: TIER_COLORS[current.name]?.gradient }} data-testid="tier-hero">
        <div className="tier-hero-content">
          <div className="tier-hero-icon">
            {React.createElement(TIER_ICONS[current.name] || Shield, { size: 40 })}
          </div>
          <h2>{current.name} Member</h2>
          <p className="tier-hero-points">{totalEarned.toLocaleString()} lifetime points</p>
        </div>
      </div>

      {/* Progress Track */}
      <div className="tier-progress-track" data-testid="tier-progress-track">
        {tiers.map((tier, idx) => {
          const TierIcon = TIER_ICONS[tier.name] || Shield;
          const isReached = idx <= currentIdx;
          const isCurrent = idx === currentIdx;
          const colors = TIER_COLORS[tier.name] || TIER_COLORS.Bronze;
          const isLast = idx === tiers.length - 1;

          let progressInSegment = 0;
          if (idx < currentIdx) {
            progressInSegment = 100;
          } else if (isCurrent && !isLast) {
            const nextTier = tiers[idx + 1];
            const rangeStart = tier.min_points;
            const rangeEnd = nextTier.min_points;
            progressInSegment = Math.min(100, Math.max(0, ((totalEarned - rangeStart) / (rangeEnd - rangeStart)) * 100));
          }

          return (
            <div key={tier.name} className="tier-step" data-testid={`tier-step-${tier.name.toLowerCase()}`}>
              <div className="tier-step-left">
                <div
                  className={`tier-step-dot ${isReached ? 'reached' : ''} ${isCurrent ? 'current' : ''}`}
                  style={isReached ? { background: colors.bg, boxShadow: isCurrent ? `0 0 0 4px ${colors.light}` : 'none' } : {}}
                >
                  <TierIcon size={16} />
                </div>
                {!isLast && (
                  <div className="tier-step-line">
                    <div
                      className="tier-step-line-fill"
                      style={{ height: `${progressInSegment}%`, background: colors.bg }}
                    />
                  </div>
                )}
              </div>
              <div className={`tier-step-card ${isCurrent ? 'current-card' : ''}`} style={isCurrent ? { borderColor: colors.bg } : {}}>
                <div className="tier-step-card-header">
                  <span className="tier-step-name" style={isReached ? { color: colors.bg } : {}}>{tier.name}</span>
                  <span className="tier-step-points">{tier.min_points.toLocaleString()}+ pts</span>
                </div>
                {isCurrent && (
                  <div className="tier-step-current-tag" style={{ background: colors.light, color: colors.bg }}>
                    Current Tier
                  </div>
                )}
                <ul className="tier-step-benefits">
                  {tier.benefits.map((b, i) => (
                    <li key={i}><ChevronRight size={12} /> {b}</li>
                  ))}
                </ul>
                {isCurrent && !isLast && (
                  <div className="tier-step-progress">
                    <div className="tier-step-progress-bar">
                      <div className="tier-step-progress-fill" style={{ width: `${progressInSegment}%`, background: colors.bg }} />
                    </div>
                    <p className="tier-step-progress-text">
                      {(tiers[idx + 1].min_points - totalEarned).toLocaleString()} pts to {tiers[idx + 1].name}
                    </p>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="home-spacer" />
    </motion.div>
  );
}
