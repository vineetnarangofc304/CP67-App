import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '../App';
import { toast } from 'sonner';
import DashboardLayout from '../components/DashboardLayout';
import { Plus, Trash2, Edit, Image, ToggleLeft, ToggleRight, Upload, CalendarDays } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL + '/api';

export default function Events() {
  const { token } = useAuth();
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editEvent, setEditEvent] = useState(null);
  const [form, setForm] = useState({ title: '', description: '', date: '', time: '', venue: '', is_active: true });
  const [selectedFile, setSelectedFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef(null);

  const fetchEvents = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/admin/events`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setEvents(data.events || []);
      }
    } catch { /* */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { fetchEvents(); }, [fetchEvents]);

  const handleSave = async () => {
    if (!form.title) { toast.error('Title is required'); return; }
    setSaving(true);
    try {
      const url = editEvent ? `${API_URL}/admin/events/${editEvent.id}` : `${API_URL}/admin/events`;
      const method = editEvent ? 'PUT' : 'POST';
      const res = await fetch(url, {
        method, headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(form)
      });
      const data = await res.json();
      const eventId = editEvent?.id || data.event?.id;

      if (selectedFile && eventId) {
        const fd = new FormData();
        fd.append('file', selectedFile);
        await fetch(`${API_URL}/admin/events/${eventId}/upload-image`, {
          method: 'POST', headers: { 'Authorization': `Bearer ${token}` }, body: fd
        });
      }
      toast.success(editEvent ? 'Event updated' : 'Event created');
      resetForm();
      fetchEvents();
    } catch { toast.error('Save failed'); }
    setSaving(false);
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this event?')) return;
    await fetch(`${API_URL}/admin/events/${id}`, { method: 'DELETE', headers: { 'Authorization': `Bearer ${token}` } });
    toast.success('Deleted');
    fetchEvents();
  };

  const toggleActive = async (ev) => {
    await fetch(`${API_URL}/admin/events/${ev.id}`, {
      method: 'PUT', headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: !ev.is_active })
    });
    fetchEvents();
  };

  const resetForm = () => {
    setForm({ title: '', description: '', date: '', time: '', venue: '', is_active: true });
    setSelectedFile(null); setPreview(null); setEditEvent(null); setShowForm(false);
  };

  const startEdit = (e) => {
    setEditEvent(e);
    setForm({ title: e.title, description: e.description || '', date: e.date || '', time: e.time || '', venue: e.venue || '', is_active: e.is_active });
    setPreview(e.image_url || null);
    setShowForm(true);
  };

  const onFileSelect = (e) => {
    const f = e.target.files[0];
    if (!f) return;
    setSelectedFile(f);
    setPreview(URL.createObjectURL(f));
  };

  return (
    <DashboardLayout title="Upcoming Events">
      <div className="p-6" data-testid="events-page">
        <div className="flex justify-between items-center mb-6">
          <p className="text-sm text-slate-500">Manage events shown in the consumer app</p>
          <button onClick={() => { resetForm(); setShowForm(true); }}
            className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-800"
            data-testid="add-event-btn">
            <Plus size={16} /> Add Event
          </button>
        </div>

        {showForm && (
          <div className="bg-white border rounded-xl p-6 mb-6" data-testid="event-form">
            <h3 className="font-semibold mb-4">{editEvent ? 'Edit Event' : 'New Event'}</h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <label className="block text-xs font-medium text-slate-600 mb-1">Title *</label>
                <input className="w-full border rounded-lg px-3 py-2 text-sm" value={form.title}
                  onChange={e => setForm(f => ({ ...f, title: e.target.value }))} placeholder="Event title" data-testid="event-title" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Date</label>
                <input type="date" className="w-full border rounded-lg px-3 py-2 text-sm" value={form.date}
                  onChange={e => setForm(f => ({ ...f, date: e.target.value }))} data-testid="event-date" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Time</label>
                <input className="w-full border rounded-lg px-3 py-2 text-sm" value={form.time}
                  onChange={e => setForm(f => ({ ...f, time: e.target.value }))} placeholder="e.g. 6:00 PM onwards" data-testid="event-time" />
              </div>
              <div className="col-span-2">
                <label className="block text-xs font-medium text-slate-600 mb-1">Venue</label>
                <input className="w-full border rounded-lg px-3 py-2 text-sm" value={form.venue}
                  onChange={e => setForm(f => ({ ...f, venue: e.target.value }))} placeholder="e.g. CP67 Main Atrium" data-testid="event-venue" />
              </div>
              <div className="col-span-2">
                <label className="block text-xs font-medium text-slate-600 mb-1">Description</label>
                <textarea className="w-full border rounded-lg px-3 py-2 text-sm" rows={2} value={form.description}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))} placeholder="Event details..." data-testid="event-desc" />
              </div>
              <div className="col-span-2">
                <label className="block text-xs font-medium text-slate-600 mb-1">Image</label>
                {/* Point 50 (Sep 2026): show recommended creative size inline so admins upload correctly-sized banners for Upcoming Events */}
                <div className="mb-2 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800" data-testid="event-dimensions-hint">
                  <strong>Recommended:</strong> 1200 × 600 px (2:1) &middot; JPG, PNG or WebP &middot; ≤ 5 MB
                  <div className="text-blue-700 mt-0.5">Displayed in the app's Events &amp; Happenings carousel. Larger images will be centre-cropped.</div>
                </div>
                <div className="border-2 border-dashed rounded-lg p-4 text-center cursor-pointer hover:border-slate-400"
                  onClick={() => fileRef.current?.click()}>
                  {preview ? <img src={preview} alt="preview" className="h-32 mx-auto object-contain rounded" /> :
                    <div className="text-slate-400"><Upload size={24} className="mx-auto mb-1" /><p className="text-xs">Click to upload image</p><p className="text-xs text-slate-300 mt-1">Target: 1200 × 600 px</p></div>}
                  <input ref={fileRef} type="file" accept="image/*" onChange={onFileSelect} className="hidden" />
                </div>
              </div>
            </div>
            <div className="flex gap-3 mt-4">
              <button onClick={handleSave} disabled={saving}
                className="bg-slate-900 text-white px-6 py-2 rounded-lg text-sm hover:bg-slate-800 disabled:opacity-50"
                data-testid="save-event-btn">{saving ? 'Saving...' : 'Save'}</button>
              <button onClick={resetForm} className="border px-6 py-2 rounded-lg text-sm">Cancel</button>
            </div>
          </div>
        )}

        {loading ? <p>Loading...</p> : (
          <div className="grid gap-4">
            {events.length === 0 ? (
              <div className="text-center py-12 text-slate-400">
                <CalendarDays size={40} className="mx-auto mb-2" />
                <p>No events yet. Create your first event!</p>
              </div>
            ) : events.map(ev => (
              <div key={ev.id} className="bg-white border rounded-xl p-4 flex items-center gap-4" data-testid={`event-${ev.id}`}>
                {ev.image_url ? <img src={ev.image_url} alt="" className="w-20 h-20 object-cover rounded-lg" /> :
                  <div className="w-20 h-20 bg-slate-100 rounded-lg flex items-center justify-center"><Image size={24} className="text-slate-300" /></div>}
                <div className="flex-1 min-w-0">
                  <h4 className="font-semibold text-sm">{ev.title}</h4>
                  {ev.date && <p className="text-xs text-slate-500">{ev.date} {ev.time && `at ${ev.time}`}</p>}
                  {ev.venue && <p className="text-xs text-slate-400">{ev.venue}</p>}
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => toggleActive(ev)} className="p-1">
                    {ev.is_active ? <ToggleRight size={22} className="text-green-500" /> : <ToggleLeft size={22} className="text-slate-300" />}
                  </button>
                  <button onClick={() => startEdit(ev)} className="p-1 hover:bg-slate-100 rounded"><Edit size={16} /></button>
                  <button onClick={() => handleDelete(ev.id)} className="p-1 hover:bg-red-50 rounded text-red-500"><Trash2 size={16} /></button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
