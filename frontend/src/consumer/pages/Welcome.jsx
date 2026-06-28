import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, Gift, ShoppingBag, Star, Sparkles } from 'lucide-react';
import { useConsumerAuth } from '../ConsumerApp';

const floatingCoins = Array.from({ length: 8 }, (_, i) => ({
  id: i,
  x: Math.random() * 100,
  delay: Math.random() * 2,
  duration: 2 + Math.random() * 3,
  size: 8 + Math.random() * 16,
}));

export default function Welcome() {
  const navigate = useNavigate();
  const { token, loading } = useConsumerAuth();

  // If the user already has a valid session, skip Welcome + Login entirely.
  // Without this, every TWA cold-start lands at Welcome and forces a new OTP
  // even though the JWT in localStorage is still valid.
  useEffect(() => {
    if (!loading && token) {
      navigate('/app/home', { replace: true });
    }
  }, [loading, token, navigate]);

  if (loading || token) {
    // Render nothing while we redirect — avoids the flash of Welcome screen.
    return <div className="consumer-loading"><div className="consumer-spinner" /></div>;
  }

  return (
    <motion.div
      className="consumer-welcome"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      data-testid="welcome-screen"
    >
      <div className="welcome-bg">
        <div className="welcome-grain" />
        <div className="welcome-gradient" />
      </div>

      {/* Floating coin particles */}
      {floatingCoins.map(coin => (
        <motion.div
          key={coin.id}
          style={{
            position: 'absolute',
            left: `${coin.x}%`,
            top: '-20px',
            width: coin.size,
            height: coin.size,
            borderRadius: '50%',
            background: 'linear-gradient(135deg, #FFDF73, #C68939)',
            zIndex: 1,
            opacity: 0.6,
          }}
          initial={{ y: -20, opacity: 0, rotate: 0 }}
          animate={{
            y: ['0vh', '110vh'],
            opacity: [0, 0.7, 0.7, 0],
            rotate: [0, 720],
          }}
          transition={{
            duration: coin.duration + 3,
            delay: coin.delay + 0.5,
            repeat: Infinity,
            ease: 'linear',
          }}
        />
      ))}

      <div className="welcome-content">
        {/* Logo drops from top with spring physics */}
        <motion.div
          className="welcome-logo"
          initial={{ y: -200, opacity: 0, scale: 0.5 }}
          animate={{ y: 0, opacity: 1, scale: 1 }}
          transition={{ type: 'spring', damping: 12, stiffness: 100, delay: 0.3 }}
        >
          <img src="/ha-logo-white.png" alt="Homeland Advantage" className="welcome-ha-logo" />
        </motion.div>

        {/* Title with staggered word reveal */}
        <motion.div
          style={{ textAlign: 'center', marginBottom: 8 }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.8 }}
        >
          <h1 style={{
            fontFamily: 'var(--font-heading)',
            fontSize: 28,
            fontWeight: 700,
            color: '#fff',
            lineHeight: 1.2,
            letterSpacing: '-0.02em',
          }}>
            <motion.span
              initial={{ y: 30, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ delay: 0.9, type: 'spring', damping: 15 }}
              style={{ display: 'block' }}
            >
              Shop. Earn.
            </motion.span>
            <motion.span
              initial={{ y: 30, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ delay: 1.1, type: 'spring', damping: 15 }}
              style={{ display: 'block', color: '#FFDF73' }}
            >
              Redeem. Repeat.
            </motion.span>
          </h1>
        </motion.div>

        {/* Features with staggered slide-in */}
        <motion.div className="welcome-features">
          {[
            { icon: Gift, text: 'Earn rewards on every purchase', delay: 1.3 },
            { icon: ShoppingBag, text: '100+ premium brands at CP67', delay: 1.5 },
            { icon: Star, text: 'Unlock 7 exclusive tiers', delay: 1.7 },
          ].map(({ icon: Icon, text, delay }) => (
            <motion.div
              key={text}
              className="welcome-feature"
              initial={{ x: -60, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              transition={{ delay, type: 'spring', damping: 18 }}
              whileTap={{ scale: 0.97 }}
            >
              <Icon size={20} />
              <span>{text}</span>
            </motion.div>
          ))}
        </motion.div>

        <motion.button
          className="welcome-cta"
          data-testid="get-started-btn"
          onClick={() => navigate('/app/login')}
          initial={{ y: 40, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 2, type: 'spring', damping: 14 }}
          whileTap={{ scale: 0.95 }}
          whileHover={{ scale: 1.02 }}
          style={{ position: 'relative', overflow: 'hidden' }}
        >
          <motion.div
            style={{
              position: 'absolute', inset: 0,
              background: 'linear-gradient(90deg, transparent, rgba(255,223,115,0.3), transparent)',
            }}
            animate={{ x: ['-100%', '200%'] }}
            transition={{ duration: 2, repeat: Infinity, repeatDelay: 3 }}
          />
          <span style={{ position: 'relative', zIndex: 1, display: 'flex', alignItems: 'center', gap: 8 }}>
            Get Started <Sparkles size={18} />
          </span>
        </motion.button>

        <motion.p
          className="welcome-signin"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 2.3 }}
        >
          Already a member?{' '}
          <button onClick={() => navigate('/app/login')}>Sign In</button>
        </motion.p>
      </div>
    </motion.div>
  );
}
