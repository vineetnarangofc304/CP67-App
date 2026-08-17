import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '../App';
import { toast } from 'sonner';
import { Plus, Trash2, Edit, Image, ToggleLeft, ToggleRight, Upload } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL + '/api';

export default function Banners() {
  const { token } = useAuth();
  const [banners, setBanners] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editBanner, setEditBanner] = useState(null);
  const [form, setForm] = useState({ title: '', subtitle: '', position: 1, is_active: true });
  const [selectedFile, setSelectedFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [saving, setSaving] = useState(false);
  const [dimWarning, setDimWarning] = useState('');
  const fileRef = useRef(null);

  const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchBanners = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/admin/banners`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setBanners(data.banners || []);
      }
    } catch { /* */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { fetchBanners(); }, [fetchBanners]);

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { toast.error('Image must be under 5MB'); return; }
    // Point 29: verify dimensions match the recommended 1200 × 400 (3:1) hero-banner aspect.
    const img = new window.Image();
    img.onload = () => {
      const w = img.naturalWidth;
      const h = img.naturalHeight;
      const targetRatio = 1200 / 400; // 3:1
      const actualRatio = w / h;
      const off = Math.abs(actualRatio - targetRatio) / targetRatio;
      if (off > 0.1 || w < 900) {
        setDimWarning(`This image is ${w} × ${h}px (aspect ${actualRatio.toFixed(2)}). Recommended is 1200 × 400 px (3:1). It will still upload, but may crop on the app.`);
      } else {
        setDimWarning('');
      }
    };
    img.src = URL.createObjectURL(file);
    setSelectedFile(file);
    setPreview(URL.createObjectURL(file));
  };

  const uploadImage = async (bannerId, file) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_URL}/admin/banners/${bannerId}/upload-image`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
      body: formData
    });
    return res.ok;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!editBanner && !selectedFile) { toast.error('Please select an image'); return; }
    setSaving(true);
    try {
      if (editBanner) {
        const res = await fetch(`${API_URL}/admin/banners/${editBanner.id}`, {
          method: 'PUT', headers, body: JSON.stringify(form)
        });
        if (!res.ok) throw new Error();
        if (selectedFile) await uploadImage(editBanner.id, selectedFile);
        toast.success('Banner updated!');
      } else {
        const res = await fetch(`${API_URL}/admin/banners`, {
          method: 'POST', headers, body: JSON.stringify(form)
        });
        if (!res.ok) throw new Error();
        const data = await res.json();
        if (selectedFile) await uploadImage(data.banner.id, selectedFile);
        toast.success('Banner created!');
      }
      resetForm();
      fetchBanners();
    } catch { toast.error('Failed to save banner'); }
    setSaving(false);
  };

  const resetForm = () => {
    setShowForm(false);
    setEditBanner(null);
    setForm({ title: '', subtitle: '', position: 1, is_active: true });
    setSelectedFile(null);
    setPreview(null);
  };

  const deleteBanner = async (id) => {
    if (!window.confirm('Delete this banner?')) return;
    try {
      await fetch(`${API_URL}/admin/banners/${id}`, { method: 'DELETE', headers: { 'Authorization': `Bearer ${token}` } });
      toast.success('Banner deleted');
      fetchBanners();
    } catch { toast.error('Delete failed'); }
  };

  const toggleActive = async (banner) => {
    try {
      await fetch(`${API_URL}/admin/banners/${banner.id}`, {
        method: 'PUT', headers,
        body: JSON.stringify({ is_active: !banner.is_active })
      });
      fetchBanners();
    } catch { /* */ }
  };

  const openEdit = (b) => {
    setEditBanner(b);
    setForm({ title: b.title, subtitle: b.subtitle, position: b.position, is_active: b.is_active });
    setSelectedFile(null);
    setPreview(b.image_url || null);
    setShowForm(true);
  };

  if (loading) return <div style={{ padding: 40, textAlign: 'center' }}>Loading...</div>;

  return (
    <div style={{ padding: '24px', maxWidth: 1000, margin: '0 auto' }} data-testid="admin-banners-page">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700 }}>Banner Management</h1>
        <button
          onClick={() => { setShowForm(true); setEditBanner(null); setForm({ title: '', subtitle: '', position: banners.length + 1, is_active: true }); setSelectedFile(null); setPreview(null); }}
          style={{ background: '#2c1810', color: '#fff', padding: '10px 20px', borderRadius: 8, border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}
          data-testid="add-banner-btn"
        >
          <Plus size={18} /> Add Banner
        </button>
      </div>

      {showForm && (
        <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12, padding: 24, marginBottom: 24 }} data-testid="banner-form">
          <h2 style={{ fontSize: 18, marginBottom: 16 }}>{editBanner ? 'Edit Banner' : 'New Banner'}</h2>
          <form onSubmit={handleSubmit}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div>
                <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 4 }}>Title</label>
                <input value={form.title} onChange={e => setForm(f => ({...f, title: e.target.value}))}
                  style={{ width: '100%', padding: 10, border: '1px solid #d1d5db', borderRadius: 8, boxSizing: 'border-box' }}
                  placeholder="Banner title" data-testid="banner-title-input" />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 4 }}>Position</label>
                <input type="number" value={form.position} onChange={e => setForm(f => ({...f, position: parseInt(e.target.value) || 1}))}
                  style={{ width: '100%', padding: 10, border: '1px solid #d1d5db', borderRadius: 8, boxSizing: 'border-box' }}
                  data-testid="banner-position-input" />
              </div>
              <div style={{ gridColumn: '1/3' }}>
                <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 4 }}>Subtitle</label>
                <input value={form.subtitle} onChange={e => setForm(f => ({...f, subtitle: e.target.value}))}
                  style={{ width: '100%', padding: 10, border: '1px solid #d1d5db', borderRadius: 8, boxSizing: 'border-box' }}
                  placeholder="Banner subtitle" data-testid="banner-subtitle-input" />
              </div>
              <div style={{ gridColumn: '1/3' }}>
                <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Banner Image {!editBanner && <span style={{ color: '#ef4444' }}>*</span>}</label>
                {/* Point 29: display exact recommended banner dimensions inline for admins */}
                <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 8, padding: '8px 12px', marginBottom: 8, fontSize: 12, color: '#1e40af' }} data-testid="banner-dimensions-hint">
                  <strong>Recommended:</strong> 1200 × 400 px (3:1) &middot; JPG, PNG or WebP &middot; ≤ 5 MB
                </div>
                <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={handleFileSelect} data-testid="banner-file-input" />
                <div
                  onClick={() => fileRef.current?.click()}
                  style={{
                    border: '2px dashed #d1d5db', borderRadius: 12, padding: preview ? 0 : 32,
                    textAlign: 'center', cursor: 'pointer', background: '#fafafa',
                    overflow: 'hidden', position: 'relative', minHeight: 140
                  }}
                  data-testid="banner-upload-zone"
                >
                  {preview ? (
                    <img src={preview} alt="Preview" style={{ width: '100%', height: 180, objectFit: 'cover', display: 'block' }} />
                  ) : (
                    <>
                      <Upload size={32} color="#9ca3af" />
                      <p style={{ color: '#6b7280', marginTop: 8, fontSize: 14 }}>Click to upload image</p>
                      <p style={{ color: '#9ca3af', fontSize: 12, marginTop: 4 }}>Target: 1200 × 400 px (JPG, PNG, WebP · Max 5MB)</p>
                    </>
                  )}
                </div>
                {selectedFile && <p style={{ fontSize: 12, color: '#22c55e', marginTop: 4 }}>{selectedFile.name}</p>}
                {dimWarning && <p style={{ fontSize: 12, color: '#b45309', background: '#fef3c7', border: '1px solid #fcd34d', padding: '6px 10px', borderRadius: 6, marginTop: 6 }} data-testid="banner-dim-warning">⚠️ {dimWarning}</p>}
              </div>
              <div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input type="checkbox" checked={form.is_active} onChange={e => setForm(f => ({...f, is_active: e.target.checked}))} />
                  Active
                </label>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
              <button type="submit" disabled={saving}
                style={{ background: '#2c1810', color: '#fff', padding: '10px 24px', borderRadius: 8, border: 'none', cursor: saving ? 'wait' : 'pointer', opacity: saving ? 0.7 : 1 }}
                data-testid="save-banner-btn">
                {saving ? 'Saving...' : editBanner ? 'Update' : 'Create'}
              </button>
              <button type="button" onClick={resetForm}
                style={{ padding: '10px 24px', borderRadius: 8, border: '1px solid #d1d5db', background: '#fff', cursor: 'pointer' }}>
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      <div style={{ display: 'grid', gap: 16 }}>
        {banners.map(b => (
          <div key={b.id} style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12, overflow: 'hidden', display: 'flex', opacity: b.is_active ? 1 : 0.6 }}
            data-testid={`banner-card-${b.id}`}>
            <div style={{ width: 200, height: 120, flexShrink: 0, background: '#f3f4f6' }}>
              {b.image_url ? (
                <img src={b.image_url} alt={b.title} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
                  <Image size={32} color="#9ca3af" />
                </div>
              )}
            </div>
            <div style={{ flex: 1, padding: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h3 style={{ fontSize: 16, fontWeight: 600 }}>{b.title || '(No title)'}</h3>
                <p style={{ fontSize: 14, color: '#6b7280', marginTop: 4 }}>{b.subtitle || ''}</p>
                <span style={{ fontSize: 12, color: '#9ca3af' }}>Position: {b.position}</span>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <button onClick={() => toggleActive(b)} style={{ background: 'none', border: 'none', cursor: 'pointer' }}
                  title={b.is_active ? 'Deactivate' : 'Activate'} data-testid={`toggle-banner-${b.id}`}>
                  {b.is_active ? <ToggleRight size={22} color="#22c55e" /> : <ToggleLeft size={22} color="#9ca3af" />}
                </button>
                <button onClick={() => openEdit(b)} style={{ background: 'none', border: 'none', cursor: 'pointer' }}
                  data-testid={`edit-banner-${b.id}`}>
                  <Edit size={18} color="#6b7280" />
                </button>
                <button onClick={() => deleteBanner(b.id)} style={{ background: 'none', border: 'none', cursor: 'pointer' }}
                  data-testid={`delete-banner-${b.id}`}>
                  <Trash2 size={18} color="#ef4444" />
                </button>
              </div>
            </div>
          </div>
        ))}
        {banners.length === 0 && (
          <div style={{ textAlign: 'center', padding: 40, color: '#9ca3af' }}>
            No banners yet. Click "Add Banner" to create one.
          </div>
        )}
      </div>
    </div>
  );
}
