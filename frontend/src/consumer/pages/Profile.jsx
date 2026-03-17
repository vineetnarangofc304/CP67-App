import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { LogOut, ChevronRight, ShieldCheck, Phone, Mail, Heart, User } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';
import { toast } from 'sonner';

export default function Profile() {
  const [profile, setProfile] = useState(null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [loading, setLoading] = useState(true);
  const { token, logout } = useConsumerAuth();
  const navigate = useNavigate();

  const fetchProfile = useCallback(async () => {
    try {
      const res = await fetch(`${API}/profile`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setProfile(data);
        setForm({ name: data.name || '', email: data.email || '', gender: data.gender || '' });
      }
    } catch { /* */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { fetchProfile(); }, [fetchProfile]);

  const saveProfile = async () => {
    try {
      await fetch(`${API}/profile`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify(form)
      });
      toast.success('Profile updated!');
      setEditing(false);
      fetchProfile();
    } catch {
      toast.error('Update failed');
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/app/welcome', { replace: true });
  };

  if (loading) return <div className="consumer-loading"><div className="consumer-spinner" /></div>;

  return (
    <motion.div
      className="consumer-profile"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      data-testid="profile-screen"
    >
      <div className="profile-header-section">
        <div className="profile-avatar">
          <span>{(profile?.name || '?')[0].toUpperCase()}</span>
        </div>
        <h1 data-testid="profile-name">{profile?.name || 'CP67 Member'}</h1>
        <span className={`tier-badge tier-${(profile?.tier || 'bronze').toLowerCase()}`}>{profile?.tier || 'Bronze'} Member</span>
        <p className="profile-points">{(profile?.balance_points || 0).toLocaleString()} Points</p>
      </div>

      <div className="profile-section">
        <h2>Personal Info</h2>
        {editing ? (
          <div className="profile-edit-form">
            <div className="profile-field">
              <label><User size={14} /> Name</label>
              <input value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))} data-testid="edit-name" />
            </div>
            <div className="profile-field">
              <label><Mail size={14} /> Email</label>
              <input value={form.email} onChange={e => setForm(f => ({...f, email: e.target.value}))} data-testid="edit-email" />
            </div>
            <div className="profile-edit-actions">
              <button className="profile-save-btn" onClick={saveProfile} data-testid="save-profile-btn">Save Changes</button>
              <button className="profile-cancel-btn" onClick={() => setEditing(false)}>Cancel</button>
            </div>
          </div>
        ) : (
          <div className="profile-info-list">
            <div className="profile-info-item">
              <Phone size={16} />
              <div><label>Phone</label><p>{profile?.phone}</p></div>
            </div>
            <div className="profile-info-item">
              <User size={16} />
              <div><label>Name</label><p>{profile?.name || 'Not set'}</p></div>
            </div>
            <div className="profile-info-item">
              <Mail size={16} />
              <div><label>Email</label><p>{profile?.email || 'Not set'}</p></div>
            </div>
            <button className="profile-edit-btn" onClick={() => setEditing(true)} data-testid="edit-profile-btn">
              Edit Profile <ChevronRight size={16} />
            </button>
          </div>
        )}
      </div>

      {profile?.interests?.length > 0 && (
        <div className="profile-section">
          <h2><Heart size={16} /> Interests</h2>
          <div className="profile-interests">
            {profile.interests.map(i => <span key={i} className="interest-tag">{i}</span>)}
          </div>
        </div>
      )}

      <div className="profile-section">
        <h2><ShieldCheck size={16} /> Referral Code</h2>
        <div className="profile-referral">
          <span data-testid="referral-code">{profile?.referral_code || 'N/A'}</span>
        </div>
      </div>

      <button className="profile-logout" onClick={handleLogout} data-testid="logout-btn">
        <LogOut size={18} /> Sign Out
      </button>

      <div className="home-spacer" />
    </motion.div>
  );
}
