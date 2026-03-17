import React from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, Gift, ShoppingBag, Star } from 'lucide-react';

export default function Welcome() {
  const navigate = useNavigate();

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

      <div className="welcome-content">
        <motion.div
          className="welcome-logo"
          initial={{ scale: 0.5, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ delay: 0.2, type: 'spring', stiffness: 200 }}
        >
          <div className="welcome-logo-ring">
            <span>CP67</span>
          </div>
          <p className="welcome-tagline">MALL &middot; MOHALI</p>
        </motion.div>

        <motion.div
          className="welcome-features"
          initial={{ y: 40, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.5 }}
        >
          <div className="welcome-feature">
            <Gift size={20} />
            <span>Earn rewards on every purchase</span>
          </div>
          <div className="welcome-feature">
            <ShoppingBag size={20} />
            <span>Exclusive deals from 100+ brands</span>
          </div>
          <div className="welcome-feature">
            <Star size={20} />
            <span>Premium member-only experiences</span>
          </div>
        </motion.div>

        <motion.button
          className="welcome-cta"
          data-testid="get-started-btn"
          onClick={() => navigate('/app/login')}
          initial={{ y: 30, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.8 }}
          whileTap={{ scale: 0.97 }}
        >
          Get Started
          <ArrowRight size={20} />
        </motion.button>

        <motion.p
          className="welcome-signin"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1 }}
        >
          Already a member?{' '}
          <button onClick={() => navigate('/app/login')}>Sign In</button>
        </motion.p>
      </div>
    </motion.div>
  );
}
