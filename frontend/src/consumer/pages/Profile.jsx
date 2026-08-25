import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { LogOut, ChevronRight, Phone, Mail, Heart, User, Calendar, MapPin, Users, Bell, Home, Navigation, Trash2 } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';
import { toast } from 'sonner';

export default function Profile() {
  const [profile, setProfile] = useState(null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [loading, setLoading] = useState(true);
  const [pincodeLoading, setPincodeLoading] = useState(false);
  const { token, logout } = useConsumerAuth();
  const navigate = useNavigate();

  const fetchProfile = useCallback(async () => {
    try {
      const res = await fetch(`${API}/profile`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setProfile(data);
        setForm({
          name: data.name || '', email: data.email || '', gender: data.gender || '',
          dob: data.dob || '', house_no: data.house_no || '', landmark: data.landmark || '',
          pincode: data.pincode || '', city: data.city || '', state: data.state || ''
        });
      }
    } catch { /* */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { fetchProfile(); }, [fetchProfile]);

  const lookupPincode = async (pincode) => {
    if (pincode.length !== 6) return;
    setPincodeLoading(true);
    try {
      const res = await fetch(`${API}/pincode/${pincode}`);
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          setForm(f => ({ ...f, city: data.city, state: data.state }));
        }
      }
    } catch { /* */ }
    setPincodeLoading(false);
  };

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

  const tierColors = { Bronze: '#B87333', Silver: '#A8A9AD', Gold: '#DAA520', Platinum: '#C4C4C0', Titanium: '#54545A', Diamond: '#A7D8DE', Privilege: '#6B3FA0' };

  const addressParts = [form.house_no, form.landmark, form.city, form.state, form.pincode].filter(Boolean).join(', ');

  return (
    <motion.div className="consumer-profile" initial={{ opacity: 0 }} animate={{ opacity: 1 }} data-testid="profile-screen">
      <div className="profile-header-section">
        <div className="profile-avatar" style={{ borderColor: tierColors[profile?.tier] || '#B87333' }}>
          <span>{(profile?.name || '?')[0].toUpperCase()}</span>
        </div>
        <h1 data-testid="profile-name">{profile?.name || 'CP67 Member'}</h1>
        <span className={`tier-badge tier-${(profile?.tier || 'bronze').toLowerCase()}`}>{profile?.tier || 'Bronze'} Member</span>
        <p className="profile-points">{(profile?.balance_points || 0).toLocaleString()} Points</p>
        {profile?.created_at && <p className="profile-since">Member since {new Date(profile.created_at).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })}</p>}
      </div>

      <div className="profile-section">
        <h2>Personal Info</h2>
        {editing ? (
          <div className="profile-edit-form">
            <div className="profile-field">
              <label><User size={14} /> Name</label>
              <input value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))} data-testid="edit-name" placeholder="Your name" />
            </div>
            <div className="profile-field">
              <label><Mail size={14} /> Email</label>
              <input type="email" value={form.email} onChange={e => setForm(f => ({...f, email: e.target.value}))} data-testid="edit-email" placeholder="your@email.com" />
            </div>
            <div className="profile-field">
              <label><Users size={14} /> Gender</label>
              <select value={form.gender} onChange={e => setForm(f => ({...f, gender: e.target.value}))} data-testid="edit-gender">
                <option value="">Select</option>
                <option value="male">Male</option>
                <option value="female">Female</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div className="profile-field">
              <label><Calendar size={14} /> Date of Birth</label>
              <input type="date" value={form.dob} onChange={e => setForm(f => ({...f, dob: e.target.value}))} data-testid="edit-dob" />
            </div>

            <h3 style={{ fontSize: 13, fontWeight: 600, color: 'var(--cp-text-2)', margin: '16px 0 8px', letterSpacing: '0.05em', textTransform: 'uppercase' }}>Address</h3>
            <div className="profile-field">
              <label><Home size={14} /> House / Flat No.</label>
              <input value={form.house_no} onChange={e => setForm(f => ({...f, house_no: e.target.value}))} data-testid="edit-house-no" placeholder="e.g. B-42, Tower 3" />
            </div>
            <div className="profile-field">
              <label><Navigation size={14} /> Landmark</label>
              <input value={form.landmark} onChange={e => setForm(f => ({...f, landmark: e.target.value}))} data-testid="edit-landmark" placeholder="Near..." />
            </div>
            <div className="profile-field">
              <label><MapPin size={14} /> Pincode</label>
              <input
                value={form.pincode} maxLength={6} inputMode="numeric"
                onChange={e => {
                  const val = e.target.value.replace(/\D/g, '');
                  setForm(f => ({...f, pincode: val}));
                  if (val.length === 6) lookupPincode(val);
                }}
                data-testid="edit-pincode" placeholder="6-digit pincode"
              />
              {pincodeLoading && <span style={{ fontSize: 11, color: 'var(--cp-gold)' }}>Looking up...</span>}
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <div className="profile-field" style={{ flex: 1 }}>
                <label>City</label>
                <input value={form.city} onChange={e => setForm(f => ({...f, city: e.target.value}))} data-testid="edit-city" placeholder="City" />
              </div>
              <div className="profile-field" style={{ flex: 1 }}>
                <label>State</label>
                <input value={form.state} onChange={e => setForm(f => ({...f, state: e.target.value}))} data-testid="edit-state" placeholder="State" />
              </div>
            </div>

            <div className="profile-edit-actions">
              <button className="profile-save-btn" onClick={saveProfile} data-testid="save-profile-btn">Save Changes</button>
              <button className="profile-cancel-btn" onClick={() => setEditing(false)}>Cancel</button>
            </div>
          </div>
        ) : (
          <div className="profile-info-list">
            {/* Point 41g: incentive banner shown when profile is incomplete — nudges the customer to fill Name, DOB and Address to unlock the 500-pt bonus. */}
            {(() => {
              const missing = [
                !profile?.name && 'Name',
                !profile?.dob && 'Date of Birth',
                !profile?.email && 'Email',
                (!profile?.house_no && !profile?.pincode) && 'Address',
              ].filter(Boolean);
              if (missing.length === 0) return null;
              return (
                <button
                  type="button"
                  onClick={() => setEditing(true)}
                  data-testid="complete-profile-cta"
                  style={{
                    width: '100%', textAlign: 'left', cursor: 'pointer',
                    background: 'linear-gradient(135deg, rgba(212,175,55,0.18) 0%, rgba(212,175,55,0.08) 100%)',
                    border: '1px solid rgba(212,175,55,0.4)', borderRadius: 12,
                    padding: '12px 14px', marginBottom: 12,
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
                  }}
                >
                  <div>
                    <div style={{ fontSize: 12, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#D4AF37', fontWeight: 700, marginBottom: 2 }}>Complete your profile</div>
                    <div style={{ fontSize: 13, color: '#FFF9E6', fontWeight: 500 }}>Add {missing.join(', ')} and earn <strong style={{ color: '#FFDF73' }}>+500 pts</strong></div>
                  </div>
                  <ChevronRight size={18} color="#D4AF37" />
                </button>
              );
            })()}
            <div className="profile-info-item"><Phone size={16} /><div><label>Phone</label><p>{profile?.phone}</p></div></div>
            <div className="profile-info-item"><User size={16} /><div><label>Name</label><p>{profile?.name || 'Not set'}</p></div></div>
            <div className="profile-info-item"><Mail size={16} /><div><label>Email</label><p>{profile?.email || 'Not set'}</p></div></div>
            <div className="profile-info-item"><Users size={16} /><div><label>Gender</label><p>{profile?.gender ? profile.gender.charAt(0).toUpperCase() + profile.gender.slice(1) : 'Not set'}</p></div></div>
            <div className="profile-info-item"><Calendar size={16} /><div><label>Date of Birth</label><p>{profile?.dob || 'Not set'}</p></div></div>
            <div className="profile-info-item"><MapPin size={16} /><div><label>Address</label><p>{addressParts || 'Not set'}</p></div></div>
            <button className="profile-edit-btn" onClick={() => setEditing(true)} data-testid="edit-profile-btn">
              Edit Profile <ChevronRight size={16} />
            </button>
          </div>
        )}
      </div>

      {/* Point 41g: removed Interests block (kept the data but hid the UI per client request) */}

      {/* Point 41j: Referral Code section — code + copy + Refer Friends CTA */}
      {(() => {
        const phone = profile?.phone || '';
        // Deterministic 6-char code derived from the customer's phone: readable, non-guessable across users.
        const code = phone ? `HA${(phone.replace(/\D/g, '').slice(-6) || '000000')}` : 'HA000000';
        const shareUrl = `${window.location.origin}/app/welcome?ref=${encodeURIComponent(code)}`;
        const copy = async () => {
          try {
            await navigator.clipboard.writeText(code);
            toast.success('Referral code copied');
          } catch {
            window.prompt('Copy your referral code:', code);
          }
        };
        const refer = async () => {
          const msg = `Join me on CP67 Mall's Homeland Advantage loyalty programme! Use my referral code ${code} when you sign up. ${shareUrl}`;
          if (navigator.share) {
            try { await navigator.share({ title: 'Homeland Advantage', text: msg, url: shareUrl }); return; }
            catch { /* fall through */ }
          }
          window.open(`https://wa.me/?text=${encodeURIComponent(msg)}`, '_blank');
        };
        return (
          <div className="profile-section" data-testid="referral-section">
            <h2 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Users size={16} /> Refer &amp; Earn
            </h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', background: 'rgba(212,175,55,0.08)', border: '1px dashed rgba(212,175,55,0.4)', borderRadius: 12, marginBottom: 10 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', textTransform: 'uppercase', letterSpacing: '0.14em', marginBottom: 2 }}>Your Code</div>
                <div style={{ fontFamily: 'monospace', letterSpacing: '0.05em', fontWeight: 700, fontSize: 18, color: '#D4AF37' }} data-testid="referral-code">{code}</div>
              </div>
              <button
                type="button"
                onClick={copy}
                data-testid="referral-copy-btn"
                style={{ background: 'rgba(212,175,55,0.2)', color: '#D4AF37', border: '1px solid rgba(212,175,55,0.4)', borderRadius: 10, padding: '8px 14px', fontWeight: 600, cursor: 'pointer' }}
              >Copy</button>
            </div>
            <button
              className="profile-nav-btn"
              onClick={refer}
              data-testid="refer-friends-btn"
              style={{ background: 'linear-gradient(135deg, #D4AF37 0%, #F5D65A 100%)', color: '#111', fontWeight: 700 }}
            >
              <Users size={16} /> Refer Friends <ChevronRight size={16} />
            </button>
            <p style={{ fontSize: 11, color: 'rgba(255,255,255,0.55)', marginTop: 8, marginBottom: 0 }}>
              Your friend signs up with your code — you both earn bonus points on their first bill.
            </p>
          </div>
        );
      })()}

      <div className="profile-section">
        <button className="profile-nav-btn" onClick={() => navigate('/app/notification-settings')} data-testid="notif-settings-btn">
          <Bell size={18} /> Notification Preferences <ChevronRight size={16} />
        </button>
      </div>

      <button className="profile-logout" onClick={handleLogout} data-testid="logout-btn">
        <LogOut size={18} /> Sign Out
      </button>

      <button
        className="profile-logout"
        style={{ marginTop: 12, background: 'transparent', color: '#B24A4A', border: '1px solid rgba(178, 74, 74, 0.35)' }}
        onClick={async () => {
          const confirm1 = window.confirm(
            'Delete your Homeland Advantage account?\n\nYour name, email, address and phone will be removed. Bill history is retained (anonymised) for tax and rewards audit.\n\nThis cannot be undone.'
          );
          if (!confirm1) return;
          const confirm2 = window.prompt('Type DELETE to confirm.');
          if (confirm2 !== 'DELETE') { toast.info('Cancelled.'); return; }
          try {
            const res = await fetch(`${API}/account`, {
              method: 'DELETE',
              headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
              toast.success('Account deleted. Signing you out.');
              setTimeout(() => { logout(); navigate('/app/welcome'); }, 1200);
            } else {
              const d = await res.json().catch(() => ({}));
              toast.error(d.detail || 'Delete failed. Please contact support.');
            }
          } catch {
            toast.error('Network error. Please try again.');
          }
        }}
        data-testid="delete-account-btn"
      >
        <Trash2 size={18} /> Delete Account
      </button>

      <div className="home-spacer" />
    </motion.div>
  );
}
