import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Calendar, MapPin, Users, Clock } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';
import { toast } from 'sonner';

export default function Events() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
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

  if (loading) return <div className="consumer-loading"><div className="consumer-spinner" /></div>;

  return (
    <motion.div
      className="consumer-events"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      data-testid="events-screen"
    >
      <div className="events-header">
        <h1>Events</h1>
        <p>What's happening at CP67</p>
      </div>

      <div className="events-list" data-testid="events-list">
        {events.map(e => (
          <div key={e.id} className="event-card" data-testid={`event-${e.id}`}>
            <div className="event-card-img">
              <img src={e.image_url} alt={e.title} loading="lazy" />
              <div className="event-date-badge">
                <span className="event-day">{new Date(e.date).getDate()}</span>
                <span className="event-month">{new Date(e.date).toLocaleDateString('en-IN', { month: 'short' })}</span>
              </div>
            </div>
            <div className="event-card-body">
              <span className="event-category-tag">{e.category}</span>
              <h3>{e.title}</h3>
              <p className="event-desc">{e.description}</p>
              <div className="event-meta">
                <span><Clock size={14} /> {e.time}</span>
                <span><MapPin size={14} /> {e.venue}</span>
                {e.registration_required && <span><Users size={14} /> {e.registered_count}/{e.max_capacity}</span>}
              </div>
              {e.registration_required && (
                <button className="event-register-btn" onClick={() => register(e.id)} data-testid={`register-${e.id}`}>
                  Register Now
                </button>
              )}
            </div>
          </div>
        ))}
        {events.length === 0 && <p className="no-results">No upcoming events</p>}
      </div>
      <div className="home-spacer" />
    </motion.div>
  );
}
