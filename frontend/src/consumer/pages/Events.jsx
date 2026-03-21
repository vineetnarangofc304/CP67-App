import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Calendar, MapPin, Users, Clock, Star, Filter } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';
import { toast } from 'sonner';

export default function Events() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const { token } = useConsumerAuth();

  const fetchEvents = useCallback(async () => {
    try {
      const res = await fetch(`${API}/events`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setEvents(data.events || []);
      }
    } catch { /* */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { fetchEvents(); }, [fetchEvents]);

  const register = async (eventId) => {
    try {
      const res = await fetch(`${API}/events/${eventId}/register`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (data.already_registered) {
        toast.info("You're already registered for this event!");
      } else {
        toast.success('Successfully registered!');
        fetchEvents();
      }
    } catch {
      toast.error('Registration failed. Try again.');
    }
  };

  const getDaysUntil = (dateStr) => {
    const diff = Math.ceil((new Date(dateStr) - new Date()) / (1000 * 60 * 60 * 24));
    if (diff === 0) return 'Today';
    if (diff === 1) return 'Tomorrow';
    if (diff < 0) return 'Past';
    return `In ${diff} days`;
  };

  const featured = events.filter(e => e.is_featured);
  const filtered = filter === 'featured' ? featured : events;

  if (loading) return <div className="consumer-loading"><div className="consumer-spinner" /></div>;

  return (
    <motion.div className="consumer-events" initial={{ opacity: 0 }} animate={{ opacity: 1 }} data-testid="events-screen">
      <div className="events-header">
        <h1>Events</h1>
        <p>What's happening at CP67</p>
      </div>

      {/* Filter Tabs */}
      <div className="events-filters" data-testid="events-filters">
        <button className={`events-filter-pill ${filter === 'all' ? 'active' : ''}`}
          onClick={() => setFilter('all')} data-testid="events-filter-all">
          <Calendar size={14} /> All Events ({events.length})
        </button>
        <button className={`events-filter-pill ${filter === 'featured' ? 'active' : ''}`}
          onClick={() => setFilter('featured')} data-testid="events-filter-featured">
          <Star size={14} /> Featured ({featured.length})
        </button>
      </div>

      {/* Featured Hero (only on "all" tab) */}
      {filter === 'all' && featured.length > 0 && (
        <div className="events-featured-hero" data-testid="featured-event-hero">
          {featured.slice(0, 1).map(e => (
            <div key={e.id} className="event-hero-card">
              <div className="event-hero-img">
                <img src={e.image_url} alt={e.title} loading="lazy" />
                <div className="event-hero-overlay">
                  <span className="event-hero-countdown">{getDaysUntil(e.date)}</span>
                  <h2>{e.title}</h2>
                  <div className="event-hero-meta">
                    <span><Calendar size={14} /> {new Date(e.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}</span>
                    <span><Clock size={14} /> {e.time}</span>
                  </div>
                  {e.registration_required && (
                    <button className="event-hero-register" onClick={() => register(e.id)} data-testid={`hero-register-${e.id}`}>
                      Register Now
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Events List */}
      <div className="events-list" data-testid="events-list">
        {filtered.map((e, idx) => (
          <motion.div
            key={e.id}
            className={`event-card ${e.is_featured ? 'featured' : ''}`}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: idx * 0.05 }}
            data-testid={`event-${e.id}`}
          >
            <div className="event-card-img">
              <img src={e.image_url} alt={e.title} loading="lazy" />
              <div className="event-date-badge">
                <span className="event-day">{new Date(e.date).getDate()}</span>
                <span className="event-month">{new Date(e.date).toLocaleDateString('en-IN', { month: 'short' })}</span>
              </div>
              <span className="event-countdown-tag">{getDaysUntil(e.date)}</span>
            </div>
            <div className="event-card-body">
              <div className="event-card-top">
                <span className="event-category-tag">{e.category}</span>
                {e.is_featured && <span className="event-featured-tag"><Star size={10} /> Featured</span>}
              </div>
              <h3>{e.title}</h3>
              <p className="event-desc">{e.description}</p>
              <div className="event-meta">
                <span><Clock size={14} /> {e.time}</span>
                <span><MapPin size={14} /> {e.venue}</span>
                {e.registration_required && (
                  <span><Users size={14} /> {e.registered_count}/{e.max_capacity}</span>
                )}
              </div>
              {e.registration_required && (
                <button className="event-register-btn" onClick={() => register(e.id)} data-testid={`register-${e.id}`}>
                  Register Now
                </button>
              )}
            </div>
          </motion.div>
        ))}
        {filtered.length === 0 && <p className="no-results">{filter === 'featured' ? 'No featured events right now' : 'No upcoming events'}</p>}
      </div>
      <div className="home-spacer" />
    </motion.div>
  );
}
