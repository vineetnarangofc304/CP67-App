import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useConsumerAuth, API } from '../ConsumerApp';

const interestOptions = ['Fashion', 'Food & Dining', 'Beauty', 'Electronics', 'Entertainment', 'Sports', 'Kids', 'Home & Living'];

export default function Onboarding() {
  const [name, setName] = useState('');
  const [gender, setGender] = useState('');
  const [interests, setInterests] = useState([]);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { token, refreshProfile } = useConsumerAuth();

  const toggleInterest = (i) => {
    setInterests(prev => prev.includes(i) ? prev.filter(x => x !== i) : [...prev, i]);
  };

  const complete = async () => {
    if (!name.trim()) return;
    setLoading(true);
    try {
      await fetch(`${API}/profile`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ name: name.trim(), gender, interests })
      });
      await refreshProfile();
      navigate('/app/home', { replace: true });
    } catch {
      setLoading(false);
    }
  };

  return (
    <motion.div
      className="consumer-onboarding"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      data-testid="onboarding-screen"
    >
      <div className="onboarding-header">
        <h1>Let's get to know you</h1>
        <p>Personalize your CP67 experience</p>
      </div>

      <div className="onboarding-form">
        <label>Your Name</label>
        <input
          type="text"
          placeholder="Enter your name"
          value={name}
          onChange={e => setName(e.target.value)}
          data-testid="onboarding-name"
          className="onboarding-input"
        />

        <label>Gender</label>
        <div className="onboarding-gender">
          {['Male', 'Female', 'Other'].map(g => (
            <button
              key={g}
              className={`gender-pill ${gender === g ? 'active' : ''}`}
              onClick={() => setGender(g)}
              data-testid={`gender-${g.toLowerCase()}`}
            >
              {g}
            </button>
          ))}
        </div>

        <label>Your Interests</label>
        <div className="onboarding-interests">
          {interestOptions.map(i => (
            <button
              key={i}
              className={`interest-pill ${interests.includes(i) ? 'active' : ''}`}
              onClick={() => toggleInterest(i)}
              data-testid={`interest-${i.toLowerCase().replace(/ /g, '-')}`}
            >
              {i}
            </button>
          ))}
        </div>
      </div>

      <button
        className="onboarding-submit"
        onClick={complete}
        disabled={loading || !name.trim()}
        data-testid="complete-onboarding-btn"
      >
        {loading ? 'Setting up...' : 'Start Exploring'}
      </button>
    </motion.div>
  );
}
