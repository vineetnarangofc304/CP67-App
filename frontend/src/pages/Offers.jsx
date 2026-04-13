import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '../App';
import { toast } from 'sonner';
import DashboardLayout from '../components/DashboardLayout';
import { Plus, Trash2, Edit, Image, ToggleLeft, ToggleRight, Upload, Tag } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL + '/api';

export default function Offers() {
  const { token } = useAuth();
  const [offers, setOffers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editOffer, setEditOffer] = useState(null);
  const [form, setForm] = useState({ title: '', description: '', store_name: '', discount_text: '', is_active: true });
  const [selectedFile, setSelectedFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef(null);

  const fetchOffers = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/admin/offers`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setOffers(data.offers || []);
      }
    } catch { /* */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { fetchOffers(); }, [fetchOffers]);

  const handleSave = async () => {
    if (!form.title) { toast.error('Title is required'); return; }
    setSaving(true);
    try {
      const url = editOffer ? `${API_URL}/admin/offers/${editOffer.id}` : `${API_URL}/admin/offers`;
      const method = editOffer ? 'PUT' : 'POST';
      const res = await fetch(url, {
        method, headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(form)
      });
      const data = await res.json();
      const offerId = editOffer?.id || data.offer?.id;

      if (selectedFile && offerId) {
        const fd = new FormData();
        fd.append('file', selectedFile);
        await fetch(`${API_URL}/admin/offers/${offerId}/upload-image`, {
          method: 'POST', headers: { 'Authorization': `Bearer ${token}` }, body: fd
        });
      }
      toast.success(editOffer ? 'Offer updated' : 'Offer created');
      resetForm();
      fetchOffers();
    } catch { toast.error('Save failed'); }
    setSaving(false);
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this offer?')) return;
    await fetch(`${API_URL}/admin/offers/${id}`, { method: 'DELETE', headers: { 'Authorization': `Bearer ${token}` } });
    toast.success('Deleted');
    fetchOffers();
  };

  const toggleActive = async (offer) => {
    await fetch(`${API_URL}/admin/offers/${offer.id}`, {
      method: 'PUT', headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: !offer.is_active })
    });
    fetchOffers();
  };

  const resetForm = () => {
    setForm({ title: '', description: '', store_name: '', discount_text: '', is_active: true });
    setSelectedFile(null); setPreview(null); setEditOffer(null); setShowForm(false);
  };

  const startEdit = (o) => {
    setEditOffer(o);
    setForm({ title: o.title, description: o.description || '', store_name: o.store_name || '', discount_text: o.discount_text || '', is_active: o.is_active });
    setPreview(o.image_url || null);
    setShowForm(true);
  };

  const onFileSelect = (e) => {
    const f = e.target.files[0];
    if (!f) return;
    setSelectedFile(f);
    setPreview(URL.createObjectURL(f));
  };

  return (
    <DashboardLayout title="Hot Deals & Offers">
      <div className="p-6" data-testid="offers-page">
        <div className="flex justify-between items-center mb-6">
          <p className="text-sm text-slate-500">Manage offers shown in the consumer app</p>
          <button onClick={() => { resetForm(); setShowForm(true); }}
            className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-800"
            data-testid="add-offer-btn">
            <Plus size={16} /> Add Offer
          </button>
        </div>

        {showForm && (
          <div className="bg-white border rounded-xl p-6 mb-6" data-testid="offer-form">
            <h3 className="font-semibold mb-4">{editOffer ? 'Edit Offer' : 'New Offer'}</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Title *</label>
                <input className="w-full border rounded-lg px-3 py-2 text-sm" value={form.title}
                  onChange={e => setForm(f => ({ ...f, title: e.target.value }))} placeholder="e.g. Flat 30% Off" data-testid="offer-title" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Store Name</label>
                <input className="w-full border rounded-lg px-3 py-2 text-sm" value={form.store_name}
                  onChange={e => setForm(f => ({ ...f, store_name: e.target.value }))} placeholder="Brand name" data-testid="offer-store" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Discount Text</label>
                <input className="w-full border rounded-lg px-3 py-2 text-sm" value={form.discount_text}
                  onChange={e => setForm(f => ({ ...f, discount_text: e.target.value }))} placeholder="e.g. Up to 50% Off" data-testid="offer-discount" />
              </div>
              <div className="col-span-2">
                <label className="block text-xs font-medium text-slate-600 mb-1">Description</label>
                <textarea className="w-full border rounded-lg px-3 py-2 text-sm" rows={2} value={form.description}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))} placeholder="Details..." data-testid="offer-desc" />
              </div>
              <div className="col-span-2">
                <label className="block text-xs font-medium text-slate-600 mb-1">Image</label>
                <div className="border-2 border-dashed rounded-lg p-4 text-center cursor-pointer hover:border-slate-400"
                  onClick={() => fileRef.current?.click()}>
                  {preview ? <img src={preview} alt="preview" className="h-32 mx-auto object-contain rounded" /> :
                    <div className="text-slate-400"><Upload size={24} className="mx-auto mb-1" /><p className="text-xs">Click to upload image</p></div>}
                  <input ref={fileRef} type="file" accept="image/*" onChange={onFileSelect} className="hidden" />
                </div>
              </div>
            </div>
            <div className="flex gap-3 mt-4">
              <button onClick={handleSave} disabled={saving}
                className="bg-slate-900 text-white px-6 py-2 rounded-lg text-sm hover:bg-slate-800 disabled:opacity-50"
                data-testid="save-offer-btn">{saving ? 'Saving...' : 'Save'}</button>
              <button onClick={resetForm} className="border px-6 py-2 rounded-lg text-sm">Cancel</button>
            </div>
          </div>
        )}

        {loading ? <p>Loading...</p> : (
          <div className="grid gap-4">
            {offers.length === 0 ? (
              <div className="text-center py-12 text-slate-400">
                <Tag size={40} className="mx-auto mb-2" />
                <p>No offers yet. Create your first hot deal!</p>
              </div>
            ) : offers.map(o => (
              <div key={o.id} className="bg-white border rounded-xl p-4 flex items-center gap-4" data-testid={`offer-${o.id}`}>
                {o.image_url ? <img src={o.image_url} alt="" className="w-20 h-20 object-cover rounded-lg" /> :
                  <div className="w-20 h-20 bg-slate-100 rounded-lg flex items-center justify-center"><Image size={24} className="text-slate-300" /></div>}
                <div className="flex-1 min-w-0">
                  <h4 className="font-semibold text-sm">{o.title}</h4>
                  {o.store_name && <p className="text-xs text-slate-500">{o.store_name}</p>}
                  {o.discount_text && <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">{o.discount_text}</span>}
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => toggleActive(o)} className="p-1" title={o.is_active ? 'Active' : 'Inactive'}>
                    {o.is_active ? <ToggleRight size={22} className="text-green-500" /> : <ToggleLeft size={22} className="text-slate-300" />}
                  </button>
                  <button onClick={() => startEdit(o)} className="p-1 hover:bg-slate-100 rounded"><Edit size={16} /></button>
                  <button onClick={() => handleDelete(o.id)} className="p-1 hover:bg-red-50 rounded text-red-500"><Trash2 size={16} /></button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
