import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, useInView } from 'framer-motion';
import { ArrowLeft, Award, Star, Crown, Shield, Gem, Zap, Diamond, Trophy, Lock, ChevronDown, ChevronUp } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';

const TIER_META = {
  Bronze: { icon: Shield, gradient: 'linear-gradient(135deg, #CD7F32 0%, #A0522D 100%)', glow: 'rgba(205, 127, 50, 0.2)' },
  Silver: { icon: Star, gradient: 'linear-gradient(135deg, #D4D4D4 0%, #A8A8A8 100%)', glow: 'rgba(192, 192, 192, 0.2)' },
  Gold: { icon: Crown, gradient: 'linear-gradient(135deg, #FFD700 0%, #B8960C 100%)', glow: 'rgba(255, 215, 0, 0.2)' },
  Platinum: { icon: Gem, gradient: 'linear-gradient(135deg, #E8E8E0 0%, #B0AFA8 100%)', glow: 'rgba(229, 228, 226, 0.2)' },
  Titanium: { icon: Zap, gradient: 'linear-gradient(135deg, #878681 0%, #5A5A56 100%)', glow: 'rgba(135, 134, 129, 0.2)' },
  Diamond: { icon: Diamond, gradient: 'linear-gradient(135deg, #4FC3F7 0%, #0288D1 100%)', glow: 'rgba(79, 195, 247, 0.2)' },
  Privilege: { icon: Trophy, gradient: 'linear-gradient(135deg, #8A2BE2 0%, #5D1A9E 100%)', glow: 'rgba(138, 43, 226, 0.2)' },
};

function AnimatedProgress({ value, delay = 0 }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true });
  return (
    <div ref={ref} style={{ width: '100%', height: 6, borderRadius: 3, background: 'rgba(255,255,255,0.2)', overflow: 'hidden' }}>
      <motion.div
        initial={{ width: 0 }}
        animate={inView ? { width: `${Math.min(value, 100)}%` } : {}}
        transition={{ duration: 1.2, delay, ease: 'easeOut' }}
        style={{ height: '100%', borderRadius: 3, background: 'linear-gradient(90deg, #FFDF73, #C68939)' }}
      />
    </div>
  );
}

export default function TierJourney() {
  const [tierData, setTierData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expandedTier, setExpandedTier] = useState(null);
  const { token } = useConsumerAuth();
  const navigate = useNavigate();

  const fetchTiers = useCallback(async () => {
    try {
      const res = await fetch(`${API}/tier-info`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) setTierData(await res.json());
    } catch { /* */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { fetchTiers(); }, [fetchTiers]);

  if (loading) return <div className="consumer-loading"><div className="consumer-spinner" /></div>;

  const current = tierData?.current_tier || {};
  const tiers = tierData?.tiers || [];
  const totalEarned = tierData?.total_earned || 0;
  const currentIdx = tiers.findIndex(t => t.name === current.name);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      style={{ padding: '0 0 100px', background: '#140B00', minHeight: '100vh' }}
      data-testid="tier-journey-screen"
    >
      {/* Header */}
      <div style={{
        background: 'linear-gradient(135deg, #1A0F00, #2A1A08)',
        padding: '16px 20px 32px',
        borderRadius: '0 0 24px 24px',
        border: '1px solid rgba(201, 165, 90, 0.1)',
        borderTop: 'none',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          <motion.button
            onClick={() => navigate(-1)}
            whileTap={{ scale: 0.9 }}
            style={{ background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, padding: 8, cursor: 'pointer', color: '#fff' }}
            data-testid="back-button"
          >
            <ArrowLeft size={20} />
          </motion.button>
          <h1 style={{ fontFamily: 'Playfair Display, serif', color: '#fff', fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em' }}>
            Tier Journey
          </h1>
        </div>

        {/* Current tier badge */}
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', damping: 12 }}
          style={{
            background: 'rgba(255,255,255,0.1)',
            backdropFilter: 'blur(12px)',
            borderRadius: 16,
            padding: '20px',
            border: '1px solid rgba(255,255,255,0.15)',
          }}
          data-testid="current-tier-card"
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{
              width: 52, height: 52, borderRadius: 14,
              background: TIER_META[current.name]?.gradient || '#CD7F32',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              {React.createElement(TIER_META[current.name]?.icon || Shield, { size: 26, color: '#fff' })}
            </div>
            <div>
              <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.15em', fontWeight: 600 }}>
                Current Tier
              </div>
              <div style={{ color: '#fff', fontSize: 22, fontWeight: 700, fontFamily: 'Playfair Display, serif' }}>
                {current.name}
              </div>
            </div>
          </div>
          <div style={{ marginTop: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: 'rgba(255,255,255,0.7)', fontSize: 12, marginBottom: 6 }}>
              <span>{totalEarned.toLocaleString()} pts earned</span>
              {current.next_at && <span>{current.next_at.toLocaleString()} pts for {current.next_tier}</span>}
            </div>
            <AnimatedProgress
              value={current.next_at ? (totalEarned / current.next_at) * 100 : 100}
              delay={0.3}
            />
          </div>
          <div style={{ marginTop: 12, color: '#FFDF73', fontSize: 12, fontWeight: 500, textAlign: 'center' }}>
            10 Points = INR 1
          </div>
        </motion.div>
      </div>

      {/* Vertical Ladder */}
      <div style={{ padding: '24px 20px', position: 'relative' }}>
        <h2 style={{
          fontFamily: 'Playfair Display, serif', fontSize: 20, fontWeight: 700,
          color: '#F5F0E8', marginBottom: 24,
        }}>
          Your Reward Ladder
        </h2>

        {/* Vertical line */}
        <div style={{
          position: 'absolute',
          left: 38,
          top: 90,
          bottom: 40,
          width: 2,
          background: 'linear-gradient(to bottom, rgba(201,165,90,0.4), rgba(201,165,90,0.05))',
          borderRadius: 2,
          zIndex: 0,
        }} />

        {/* Tier cards */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 0, position: 'relative', zIndex: 1 }}>
          {tiers.map((tier, idx) => {
            const meta = TIER_META[tier.name] || {};
            const Icon = meta.icon || Shield;
            const isCurrentOrPast = idx <= currentIdx;
            const isCurrent = idx === currentIdx;
            const isExpanded = expandedTier === idx;

            return (
              <motion.div
                key={tier.name}
                initial={{ x: -30, opacity: 0 }}
                whileInView={{ x: 0, opacity: 1 }}
                viewport={{ once: true }}
                transition={{ delay: idx * 0.08, type: 'spring', damping: 18 }}
                data-testid={`tier-card-${tier.name.toLowerCase()}`}
              >
                <div
                  onClick={() => setExpandedTier(isExpanded ? null : idx)}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 16,
                    padding: '14px 0',
                    cursor: 'pointer',
                  }}
                >
                  {/* Node */}
                  <motion.div
                    style={{
                      width: 38, height: 38, borderRadius: 12, flexShrink: 0,
                      background: isCurrentOrPast ? meta.gradient : 'rgba(255,255,255,0.06)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      border: isCurrent ? '3px solid var(--cp-flash-gold)' : '2px solid transparent',
                      position: 'relative',
                      boxShadow: isCurrent ? `0 0 20px ${meta.glow || 'rgba(201,165,90,0.2)'}` : 'none',
                    }}
                    animate={isCurrent ? { scale: [1, 1.08, 1] } : {}}
                    transition={isCurrent ? { duration: 2, repeat: Infinity } : {}}
                  >
                    {isCurrentOrPast ? (
                      <Icon size={18} color="#fff" />
                    ) : (
                      <Lock size={14} color="#999" />
                    )}
                    {isCurrent && (
                      <motion.div
                        style={{
                          position: 'absolute', top: -6, right: -6,
                          width: 14, height: 14, borderRadius: '50%',
                          background: '#FFDF73', border: '2px solid #fff',
                        }}
                        animate={{ scale: [1, 1.2, 1] }}
                        transition={{ duration: 1.5, repeat: Infinity }}
                      />
                    )}
                  </motion.div>

                  {/* Info */}
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div>
                        <div style={{
                          fontSize: 16, fontWeight: 700,
                          fontFamily: 'Playfair Display, serif',
                          color: isCurrentOrPast ? '#F5F0E8' : '#5C5346',
                        }}>
                          {tier.name}
                          {isCurrent && (
                            <span style={{
                              marginLeft: 8, fontSize: 10, fontFamily: 'var(--font-body)',
                              background: 'var(--cp-gold)', color: '#1A0F00',
                              padding: '2px 8px', borderRadius: 20, fontWeight: 600,
                              textTransform: 'uppercase', letterSpacing: '0.1em',
                            }}>
                              You
                            </span>
                          )}
                        </div>
                        <div style={{
                          fontSize: 12, color: '#A3988B', marginTop: 2,
                        }}>
                          {tier.min_points.toLocaleString()}+ points
                        </div>
                      </div>
                      {isExpanded ? <ChevronUp size={16} color="#5C5346" /> : <ChevronDown size={16} color="#5C5346" />}
                    </div>

                    {/* Expanded benefits */}
                    <motion.div
                      initial={false}
                      animate={{ height: isExpanded ? 'auto' : 0, opacity: isExpanded ? 1 : 0 }}
                      transition={{ duration: 0.3 }}
                      style={{ overflow: 'hidden' }}
                    >
                      <div style={{
                        marginTop: 12, padding: 14, borderRadius: 12,
                        background: isCurrentOrPast ? 'rgba(255,255,255,0.05)' : 'rgba(255,255,255,0.02)',
                        border: isCurrent ? '1px solid rgba(201, 165, 90, 0.3)' : '1px solid rgba(255,255,255,0.06)',
                        boxShadow: isCurrent ? `0 0 20px ${meta.glow || 'rgba(201,165,90,0.1)'}` : 'none',
                      }}>
                        <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#A3988B', marginBottom: 8 }}>
                          Benefits
                        </div>
                        {tier.benefits?.map((b, bi) => (
                          <div key={bi} style={{
                            display: 'flex', alignItems: 'center', gap: 8,
                            fontSize: 13, color: '#F5F0E8',
                            padding: '4px 0',
                          }}>
                            <div style={{
                              width: 5, height: 5, borderRadius: '50%', flexShrink: 0,
                              background: isCurrentOrPast ? 'var(--cp-gold)' : '#5C5346',
                            }} />
                            {b}
                          </div>
                        ))}
                      </div>
                    </motion.div>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>

      {/* Points Earning Slab */}
      <motion.div
        style={{ margin: '0 20px 20px', padding: 20, borderRadius: 16, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)' }}
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        data-testid="points-earning-slab"
      >
        <h3 style={{ fontFamily: 'Playfair Display, serif', fontSize: 17, fontWeight: 700, marginBottom: 14, color: '#F5F0E8' }}>
          Points Earning Slab
        </h3>
        <div style={{
          background: 'linear-gradient(135deg, #C9A55A, #8F7233)',
          borderRadius: 12, padding: '14px 16px', color: '#1A0F00',
          fontSize: 15, fontWeight: 700, textAlign: 'center', marginBottom: 14,
          fontFamily: 'Playfair Display, serif',
        }}>
          10 Points = INR 1
        </div>
        {/* Slab table header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '2px solid rgba(255,255,255,0.1)', marginBottom: 4 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: '#A3988B', textTransform: 'uppercase', letterSpacing: '0.05em', flex: 1.2 }}>Purchase (INR)</span>
          <span style={{ fontSize: 11, fontWeight: 700, color: '#A3988B', textTransform: 'uppercase', letterSpacing: '0.05em', flex: 0.7, textAlign: 'center' }}>Retail</span>
          <span style={{ fontSize: 11, fontWeight: 700, color: '#A3988B', textTransform: 'uppercase', letterSpacing: '0.05em', flex: 1, textAlign: 'right' }}>Jewellery & Electronics</span>
        </div>
        {[
          { range: '0 - 10,000', retail: '10%', jewellery: '5%' },
          { range: '10,001 - 25,000', retail: '15%', jewellery: '7.5%' },
          { range: '25,001 - 75,000', retail: '20%', jewellery: '10%' },
          { range: '75,001 - 1,50,000', retail: '25%', jewellery: '12.5%' },
          { range: '1,50,001 - 3,00,000', retail: '30%', jewellery: '15%' },
          { range: '3,00,001 - 5,00,000', retail: '32.5%', jewellery: '16.25%' },
          { range: '5,00,001 & Above', retail: '35%', jewellery: '17.5%' },
        ].map((slab, i) => (
          <motion.div
            key={slab.range}
            initial={{ x: -20, opacity: 0 }}
            whileInView={{ x: 0, opacity: 1 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.06 }}
            style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '10px 0',
              borderBottom: i < 6 ? '1px solid rgba(255,255,255,0.06)' : 'none',
              fontSize: 13,
            }}
          >
            <span style={{ color: '#F5F0E8', flex: 1.2 }}>{slab.range}</span>
            <span style={{ color: '#C9A55A', fontWeight: 600, flex: 0.7, textAlign: 'center' }}>{slab.retail}</span>
            <span style={{ color: '#C9A55A', fontWeight: 600, flex: 1, textAlign: 'right' }}>{slab.jewellery}</span>
          </motion.div>
        ))}
      </motion.div>

      <div className="home-spacer" />
    </motion.div>
  );
}
