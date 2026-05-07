import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '../App';
import { toast } from 'sonner';
import DashboardLayout from '../components/DashboardLayout';
import { ShieldOff, ShieldCheck, Search, Phone, AlertTriangle, Upload } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL + '/api';

export default function BlockedUsers() {
  const { token } = useAuth();
  const [blocked, setBlocked] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);
  const [newPhone, setNewPhone] = useState('');
  const [newReason, setNewReason] = useState('');
  const [adding, setAdding] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const fileInputRef = useRef(null);

  const fetchBlocked = useCallback(async () => {
    try {
      const url = `${API_URL}/admin/blocked-users?limit=100${search ? `&search=${search}` : ''}`;
      const res = await fetch(url, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setBlocked(data.blocked_users || []);
        setTotal(data.total || 0);
      }
    } catch { /* */ }
    setLoading(false);
  }, [token, search]);

  useEffect(() => { fetchBlocked(); }, [fetchBlocked]);

  const handleBlock = async () => {
    if (!newPhone || newPhone.length < 10) { toast.error('Enter valid 10-digit phone'); return; }
    setAdding(true);
    try {
      const res = await fetch(`${API_URL}/admin/block-user`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: newPhone, reason: newReason || 'Blocked by admin' })
      });
      const data = await res.json();
      if (res.ok) {
        toast.success(data.message);
        setNewPhone(''); setNewReason(''); setShowAddForm(false);
        fetchBlocked();
      } else {
        toast.error(data.detail || 'Failed');
      }
    } catch { toast.error('Failed to block'); }
    setAdding(false);
  };

  const handleUnblock = async (phone) => {
    if (!window.confirm(`Are you sure you want to ACTIVATE ${phone}? This user will be able to use all services again.`)) return;
    try {
      const res = await fetch(`${API_URL}/admin/unblock-user`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone })
      });
      const data = await res.json();
      if (res.ok) {
        toast.success(data.message);
        fetchBlocked();
      } else {
        toast.error(data.detail || 'Failed');
      }
    } catch { toast.error('Failed'); }
  };

  const handleBulkUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadResult(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${API_URL}/admin/blocked-users/bulk-upload`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData
      });
      const data = await res.json();
      if (res.ok) {
        setUploadResult(data);
        toast.success(`Uploaded ${data.file}: ${data.newly_blocked} newly blocked, ${data.already_blocked} already blocked`);
        fetchBlocked();
      } else {
        toast.error(data.detail || 'Upload failed');
      }
    } catch (err) {
      toast.error('Upload failed: ' + (err.message || 'unknown error'));
    }
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <DashboardLayout title="Blocked Users">
      <div className="p-6" data-testid="blocked-users-page">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
          <div>
            <p className="text-sm text-slate-500">
              {total} blocked number{total !== 1 ? 's' : ''}. Blocked users cannot interact via WhatsApp, app, or QR scan.
            </p>
          </div>
          <button onClick={() => setShowAddForm(true)}
            className="flex items-center gap-2 bg-red-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-red-700"
            data-testid="block-user-btn">
            <ShieldOff size={16} /> Block Number
          </button>
        </div>

        {/* Upload Excel / CSV */}
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3" data-testid="bulk-upload-card">
          <div>
            <p className="text-sm font-semibold text-blue-900 flex items-center gap-2">
              <Upload size={16} /> Bulk block from Excel / CSV
            </p>
            <p className="text-xs text-blue-700 mt-1">
              Upload a sheet with columns like <span className="font-mono">Brand Name, Staff Name, Designation, Contact No.</span> Existing entries are skipped automatically.
            </p>
            {uploadResult && (
              <p className="text-xs text-blue-900 mt-2" data-testid="bulk-upload-result">
                {uploadResult.file}: parsed <b>{uploadResult.parsed_rows}</b>, unique <b>{uploadResult.unique_phones}</b>,
                newly blocked <b>{uploadResult.newly_blocked}</b>, already blocked <b>{uploadResult.already_blocked}</b>
                {uploadResult.enriched_existing ? `, enriched ${uploadResult.enriched_existing}` : ''}.
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xlsm,.xltx,.xltm,.csv"
              onChange={handleBulkUpload}
              className="hidden"
              data-testid="bulk-upload-file"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50"
              data-testid="bulk-upload-btn">
              <Upload size={16} /> {uploading ? 'Uploading…' : 'Upload Excel / CSV'}
            </button>
          </div>
        </div>

        {/* Search */}
        <div className="relative mb-4">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            className="w-full pl-10 pr-4 py-2.5 border rounded-lg text-sm"
            placeholder="Search by phone number..."
            value={search} onChange={e => setSearch(e.target.value)}
            data-testid="search-blocked"
          />
        </div>

        {/* Add block form */}
        {showAddForm && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-5 mb-6" data-testid="block-form">
            <h3 className="font-semibold text-red-800 mb-3 flex items-center gap-2">
              <AlertTriangle size={16} /> Block a Phone Number
            </h3>
            <div className="grid sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Phone Number *</label>
                <div className="flex items-center gap-2">
                  <Phone size={14} className="text-slate-400" />
                  <input className="flex-1 border rounded-lg px-3 py-2 text-sm" placeholder="10-digit number"
                    value={newPhone} onChange={e => setNewPhone(e.target.value.replace(/\D/g, '').slice(0, 10))}
                    maxLength={10} inputMode="numeric" data-testid="block-phone-input" />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Reason</label>
                <input className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="e.g. Fraudulent activity"
                  value={newReason} onChange={e => setNewReason(e.target.value)} data-testid="block-reason-input" />
              </div>
            </div>
            <div className="flex gap-3 mt-4">
              <button onClick={handleBlock} disabled={adding}
                className="bg-red-600 text-white px-6 py-2 rounded-lg text-sm hover:bg-red-700 disabled:opacity-50"
                data-testid="confirm-block-btn">{adding ? 'Blocking...' : 'Block This Number'}</button>
              <button onClick={() => { setShowAddForm(false); setNewPhone(''); setNewReason(''); }}
                className="border px-6 py-2 rounded-lg text-sm">Cancel</button>
            </div>
          </div>
        )}

        {/* Blocked list */}
        {loading ? <p>Loading...</p> : (
          <div className="bg-white border rounded-xl overflow-hidden">
            {blocked.length === 0 ? (
              <div className="text-center py-12 text-slate-400">
                <ShieldCheck size={40} className="mx-auto mb-2 text-green-400" />
                <p>No blocked users{search ? ' matching your search' : ''}</p>
              </div>
            ) : (
              <table className="w-full">
                <thead className="bg-slate-50 border-b">
                  <tr>
                    <th className="text-left text-xs font-medium text-slate-500 px-4 py-3">Phone</th>
                    <th className="text-left text-xs font-medium text-slate-500 px-4 py-3">Brand / Staff</th>
                    <th className="text-left text-xs font-medium text-slate-500 px-4 py-3">Reason</th>
                    <th className="text-left text-xs font-medium text-slate-500 px-4 py-3">Blocked By</th>
                    <th className="text-left text-xs font-medium text-slate-500 px-4 py-3">Blocked On</th>
                    <th className="text-right text-xs font-medium text-slate-500 px-4 py-3">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {blocked.map((b, i) => (
                    <tr key={b.phone || i} className="border-b last:border-0 hover:bg-slate-50" data-testid={`blocked-row-${b.phone}`}>
                      <td className="px-4 py-3 font-mono text-sm font-medium">{b.phone}</td>
                      <td className="px-4 py-3 text-sm text-slate-700">
                        {b.brand || b.staff_name ? (
                          <div>
                            {b.brand && <div className="font-medium">{b.brand}</div>}
                            {(b.staff_name || b.designation) && (
                              <div className="text-xs text-slate-500">
                                {[b.staff_name, b.designation].filter(Boolean).join(' · ')}
                              </div>
                            )}
                          </div>
                        ) : '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-slate-600">{b.reason || '-'}</td>
                      <td className="px-4 py-3 text-sm text-slate-500">{b.blocked_by || '-'}</td>
                      <td className="px-4 py-3 text-sm text-slate-500">
                        {b.blocked_at ? new Date(b.blocked_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '-'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button onClick={() => handleUnblock(b.phone)}
                          className="inline-flex items-center gap-1.5 bg-green-50 text-green-700 border border-green-200 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-green-100"
                          data-testid={`activate-btn-${b.phone}`}>
                          <ShieldCheck size={14} /> Activate
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
