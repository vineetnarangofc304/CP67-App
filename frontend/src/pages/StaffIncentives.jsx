import React, { useEffect, useMemo, useState } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import { useAuth } from '../App';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from '../components/ui/dialog';
import { toast } from 'sonner';
import { Users, QrCode, Award, Wallet, Settings, Plus, Trophy, RefreshCw, Upload, FileText } from 'lucide-react';

export default function StaffIncentives() {
  const { token, API_URL, logout } = useAuth();
  const [tab, setTab] = useState('staff');
  const [staffList, setStaffList] = useState([]);
  const [config, setConfig] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [leaderboard, setLeaderboard] = useState([]);
  const [redemptions, setRedemptions] = useState([]);
  const [showQR, setShowQR] = useState(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: '', phone: '', brand_name: '', brand_category: '', store_location: '' });
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [pendingImportFile, setPendingImportFile] = useState(null); // file staged after dry-run, waiting for user confirm
  const [managers, setManagers] = useState([]);
  const [mgrForm, setMgrForm] = useState({ name: '', phone: '', brands: '', email: '' });
  const [creatingMgr, setCreatingMgr] = useState(false);
  const [catalog, setCatalog] = useState({ brands: [], categories: [], staff_mapped_brands: [], staff_mapped_categories: [] });   // Point 7: dropdown source; Point 10: staff-mapped subsets
  const [uploadingMapping, setUploadingMapping] = useState(false);
  const [mappingResult, setMappingResult] = useState(null);
  const [pendingMappingFile, setPendingMappingFile] = useState(null);
  // Point 27: search + filter so imported staff are actually findable in a 700+ row table.
  const [staffSearch, setStaffSearch] = useState('');
  const [staffBrandFilter, setStaffBrandFilter] = useState('');
  const [showRecentImportsOnly, setShowRecentImportsOnly] = useState(false);
  const [staffPageSize, setStaffPageSize] = useState(50);
  const [showUnmappedOnly, setShowUnmappedOnly] = useState(false); // Point 35
  const [staffUnmappedCount, setStaffUnmappedCount] = useState(0); // Point 35: server-computed
  const [reassignStaff, setReassignStaff] = useState(null); // Point 35: modal for in-place brand fix
  // Point 12 (Aug 2026): Incentive Reports — separate reg vs bill records with customer mobile.
  const [reportRows, setReportRows] = useState([]);
  const [reportSummary, setReportSummary] = useState({ total: 0, registration_count: 0, bill_upload_count: 0, total_amount: 0, redeemable_amount: 0 });
  const [reportLoading, setReportLoading] = useState(false);
  const [reportType, setReportType] = useState('registration'); // 'registration' | 'bill_upload'
  const [reportBrand, setReportBrand] = useState('');
  const [reportStatus, setReportStatus] = useState('');
  const [reportStart, setReportStart] = useState('');
  const [reportEnd, setReportEnd] = useState('');
  // Point 11 (Aug 2026): test OTP send diagnostics for retailer manager
  const [testOtpPhone, setTestOtpPhone] = useState('');
  const [testOtpResult, setTestOtpResult] = useState(null);
  const [testOtpBusy, setTestOtpBusy] = useState(false);

  const api = (path, opts = {}) => fetch(`${API_URL}${path}`, {
    ...opts,
    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json', ...(opts.headers || {}) },
  });

  const loadAll = async () => {
    try {
      const [s, c, m, l, r, mg, cat] = await Promise.all([
        api('/admin/staff').then(x => x.json()),
        api('/admin/staff/config/current').then(x => x.json()),
        api('/admin/staff/metrics/overview').then(x => x.json()),
        api('/admin/staff/leaderboard?period=monthly').then(x => x.json()),
        api('/admin/staff/redemptions').then(x => x.json()),
        api('/admin/staff/retailer-managers').then(x => x.json()),
        api('/admin/staff/catalog/brands-categories').then(x => x.json()),
      ]);
      setStaffList(s.staff || []);
      setStaffUnmappedCount(s.unmapped_count || 0);
      setConfig(c.config || null);
      setMetrics(m);
      setLeaderboard(l.leaderboard || []);
      setRedemptions(r.redemptions || []);
      setManagers(mg.managers || []);
      setCatalog({
        brands: cat.brands || [],
        categories: cat.categories || [],
        // Point 10: subsets that are actually in use by retail staff
        staff_mapped_brands: cat.staff_mapped_brands || [],
        staff_mapped_categories: cat.staff_mapped_categories || [],
      });
    } catch (e) {
      toast.error('Failed to load staff data');
    }
  };

  useEffect(() => { loadAll(); /* eslint-disable-next-line */ }, []);

  // Point 12 (Aug 2026): Load retailer incentive report (registrations vs bill uploads).
  const loadReport = async () => {
    setReportLoading(true);
    try {
      const params = new URLSearchParams();
      if (reportType) params.set('incentive_type', reportType);
      if (reportBrand) params.set('brand', reportBrand);
      if (reportStatus) params.set('status', reportStatus);
      if (reportStart) params.set('start_date', reportStart);
      if (reportEnd) params.set('end_date', reportEnd);
      params.set('limit', '2000');
      const r = await api(`/admin/staff/incentives/report?${params.toString()}`);
      if (r.status === 401 || r.status === 403) { handle401(); return; }
      const d = await r.json();
      if (r.ok) {
        setReportRows(d.rows || []);
        setReportSummary(d.summary || { total: 0, registration_count: 0, bill_upload_count: 0, total_amount: 0, redeemable_amount: 0 });
      } else if (r.status === 503) {
        toast.error(d.detail || 'Report DB busy — retry in ~10s');
      } else {
        toast.error(d.detail || 'Failed to load report');
      }
    } catch (e) {
      toast.error('Failed to load report');
    } finally {
      setReportLoading(false);
    }
  };

  const downloadReportCsv = () => {
    const params = new URLSearchParams();
    if (reportType) params.set('incentive_type', reportType);
    if (reportBrand) params.set('brand', reportBrand);
    if (reportStatus) params.set('status', reportStatus);
    if (reportStart) params.set('start_date', reportStart);
    if (reportEnd) params.set('end_date', reportEnd);
    params.set('limit', '10000');
    fetch(`${API_URL}/admin/staff/incentives/report.csv?${params.toString()}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(res => {
        if (res.status === 401 || res.status === 403) { handle401(); return null; }
        if (!res.ok) throw new Error('csv fetch failed');
        return res.blob();
      })
      .then(blob => {
        if (!blob) return;
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `retailer_incentives_${reportType || 'all'}.csv`;
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
      })
      .catch(() => toast.error('CSV download failed'));
  };

  const sendTestOtp = async () => {
    const phone = (testOtpPhone || '').replace(/\D/g, '').slice(-10);
    if (phone.length !== 10) { toast.error('Enter a 10-digit phone'); return; }
    setTestOtpBusy(true);
    setTestOtpResult(null);
    try {
      const r = await api('/admin/staff/retailer/test-otp', { method: 'POST', body: JSON.stringify({ phone }) });
      if (r.status === 401 || r.status === 403) { handle401(); return; }
      const d = await r.json();
      setTestOtpResult(d);
      if (d.success) toast.success('OTP dispatched — check WhatsApp + SMS');
      else toast.error(d.message || 'OTP dispatch failed');
    } catch (e) {
      toast.error('Failed to send test OTP');
    } finally {
      setTestOtpBusy(false);
    }
  };

  useEffect(() => { if (tab === 'report') loadReport(); /* eslint-disable-next-line */ }, [tab, reportType]);



  const submitCreate = async () => {
    if (!form.name || !form.phone || !form.brand_name) {
      toast.error('Name, phone, and brand are required');
      return;
    }
    const r = await api('/admin/staff', { method: 'POST', body: JSON.stringify(form) });
    const d = await r.json();
    if (r.ok) {
      toast.success(`Staff added: ${d.staff.staff_code}`);
      setCreating(false);
      setForm({ name: '', phone: '', brand_name: '', brand_category: '', store_location: '' });
      loadAll();
    } else {
      toast.error(d.detail || 'Failed to add staff');
    }
  };

  const toggleActive = async (s) => {
    const r = await api(`/admin/staff/${s.id}`, { method: 'PATCH', body: JSON.stringify({ is_active: !s.is_active }) });
    if (r.ok) { toast.success(!s.is_active ? 'Activated' : 'Deactivated'); loadAll(); }
    else { toast.error('Update failed'); }
  };

  const openQR = async (staffId) => {
    const r = await api(`/admin/staff/${staffId}/qr`);
    if (r.ok) { setShowQR(await r.json()); }
    else { toast.error('QR fetch failed'); }
  };

  const saveConfig = async () => {
    const r = await api('/admin/staff/config/current', { method: 'PUT', body: JSON.stringify(config) });
    if (r.ok) { toast.success('Config saved'); loadAll(); }
    else { toast.error('Save failed'); }
  };

  const updateSlab = (kind, idx, field, value) => {
    setConfig(c => {
      const arr = [...c[kind]];
      arr[idx] = { ...arr[idx], [field]: Number(value) };
      return { ...c, [kind]: arr };
    });
  };

  const settleRedemption = async (id, status) => {
    const ref = status === 'settled' ? window.prompt('Payout reference (UPI txn / cheque # etc.)') : null;
    const r = await api(`/admin/staff/redemptions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status, payout_ref: ref || undefined }),
    });
    if (r.ok) { toast.success(`Marked ${status}`); loadAll(); }
    else { toast.error('Update failed'); }
  };

  const handle401 = (status) => {
    // Point 6: friendly handling of expired admin JWT instead of raw "Invalid token" toast.
    if (status === 401) {
      toast.error('Session expired — please sign in again');
      logout();
      setTimeout(() => { window.location.href = '/'; }, 800);
      return true;
    }
    return false;
  };

  const doBulkImport = async (file, dryRun) => {
    if (!file) return;
    setImporting(true);
    setImportResult(null);
    const fd = new FormData();
    fd.append('file', file);
    fd.append('dry_run', dryRun ? 'true' : 'false');
    try {
      const r = await fetch(`${API_URL}/admin/staff/bulk-import${dryRun ? '?dry_run=true' : ''}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      if (handle401(r.status)) return;
      const data = await r.json();
      if (!r.ok) { toast.error(data.detail || 'Import failed'); return; }
      setImportResult(data);
      if (dryRun) {
        // Stage the file so the user can explicitly confirm the actual import.
        setPendingImportFile(file);
        toast.info(`Preview only: ${data.summary.imported} row(s) will be imported. Click "Confirm & Import" to save.`);
      } else {
        setPendingImportFile(null);
        toast.success(`Imported ${data.summary.imported} staff across ${data.summary.brands_imported} brands.`);
        loadAll();
      }
    } catch (e) {
      toast.error('Import failed: ' + e.message);
    } finally {
      setImporting(false);
    }
  };

  const downloadTemplate = async () => {
    try {
      const r = await fetch(`${API_URL}/admin/staff/bulk-import/template.csv`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (handle401(r.status)) return;
      if (!r.ok) { toast.error('Template download failed'); return; }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'staff-upload-template.csv';
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success('Template downloaded');
    } catch (e) {
      toast.error('Download failed: ' + e.message);
    }
  };

  // Point 7: brand-category mapping CSV upload
  const uploadBrandCategoryMapping = async (file, dryRun) => {
    if (!file) return;
    setUploadingMapping(true);
    setMappingResult(null);
    const fd = new FormData();
    fd.append('file', file);
    fd.append('dry_run', dryRun ? 'true' : 'false');
    try {
      const r = await fetch(`${API_URL}/admin/staff/catalog/brand-category-mapping`, {
        method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: fd,
      });
      if (handle401(r.status)) return;
      const data = await r.json();
      if (!r.ok) { toast.error(data.detail || 'Upload failed'); return; }
      setMappingResult(data);
      if (dryRun) {
        setPendingMappingFile(file);
        toast.info(`Preview only: ${data.summary.updated} update(s), ${data.summary.created} new brand(s). Click "Confirm & Import" to save.`);
      } else {
        setPendingMappingFile(null);
        toast.success(`Mapping applied: ${data.summary.updated} updated, ${data.summary.created} created.`);
        loadAll();
      }
    } catch (e) {
      toast.error('Upload failed: ' + e.message);
    } finally {
      setUploadingMapping(false);
    }
  };

  const downloadMappingTemplate = async () => {
    try {
      const r = await fetch(`${API_URL}/admin/staff/catalog/brand-category-mapping/template.csv`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (handle401(r.status)) return;
      if (!r.ok) { toast.error('Template download failed'); return; }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'brand-category-mapping-template.csv';
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success('Template downloaded');
    } catch (e) {
      toast.error('Download failed: ' + e.message);
    }
  };

  // ---- Point 5: retailer manager admin ops ----
  const submitCreateMgr = async () => {
    const brands = mgrForm.brands.split(',').map(s => s.trim()).filter(Boolean);
    if (!mgrForm.name || !mgrForm.phone || brands.length === 0) {
      toast.error('Name, phone, and at least one brand are required');
      return;
    }
    const body = { name: mgrForm.name, phone: mgrForm.phone, brands, email: mgrForm.email || undefined };
    const r = await api('/admin/staff/retailer-managers', { method: 'POST', body: JSON.stringify(body) });
    const d = await r.json();
    if (r.ok) {
      toast.success('Retailer manager added');
      setCreatingMgr(false);
      setMgrForm({ name: '', phone: '', brands: '', email: '' });
      loadAll();
    } else {
      toast.error(d.detail || 'Failed to add manager');
    }
  };

  const toggleMgrActive = async (m) => {
    const r = await api(`/admin/staff/retailer-managers/${m.id}`, { method: 'PATCH', body: JSON.stringify({ is_active: !m.is_active }) });
    if (r.ok) { toast.success(!m.is_active ? 'Activated' : 'Deactivated'); loadAll(); }
    else { toast.error('Update failed'); }
  };

  const deleteMgr = async (m) => {
    if (!window.confirm(`Remove retailer login for ${m.name}?`)) return;
    const r = await api(`/admin/staff/retailer-managers/${m.id}`, { method: 'DELETE' });
    if (r.ok) { toast.success('Removed'); loadAll(); }
    else { toast.error('Delete failed'); }
  };

  // Point 27: derived filter view so imported rows are findable
  const filteredStaff = useMemo(() => {
    const q = staffSearch.trim().toLowerCase();
    return staffList.filter(s => {
      if (staffBrandFilter && s.brand_name !== staffBrandFilter) return false;
      if (showRecentImportsOnly && s.import_source !== 'csv_bulk') return false;
      if (showUnmappedOnly && s.is_brand_mapped) return false; // Point 35
      if (!q) return true;
      const hay = [s.name, s.phone, s.staff_code, s.brand_name, s.store_location]
        .filter(Boolean).join(' ').toLowerCase();
      return hay.includes(q);
    });
  }, [staffList, staffSearch, staffBrandFilter, showRecentImportsOnly, showUnmappedOnly]);

  // Point 35: in-place reassignment of a staff's brand from the master brand list.
  const submitReassignBrand = async (newBrand) => {
    if (!reassignStaff || !newBrand) return;
    const cat = catalog.brands.find(b => b.brand_name === newBrand)?.category || '';
    const body = { brand_name: newBrand };
    if (cat) body.brand_category = cat;
    const r = await api(`/admin/staff/${reassignStaff.id}`, { method: 'PATCH', body: JSON.stringify(body) });
    if (r.ok) {
      toast.success(`Reassigned to ${newBrand}`);
      setReassignStaff(null);
      loadAll();
    } else {
      const d = await r.json().catch(() => ({}));
      toast.error(d.detail || 'Reassign failed');
    }
  };

  return (
    <DashboardLayout title="Staff Incentive Program">
      <div className="space-y-6" data-testid="staff-incentives-page">
        {/* KPIs */}
        {metrics && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <Card><CardContent className="p-4"><div className="text-xs text-slate-500 uppercase">Total Staff</div><div className="text-3xl font-bold mt-1">{metrics.total_staff}</div></CardContent></Card>
            <Card><CardContent className="p-4"><div className="text-xs text-slate-500 uppercase">Active</div><div className="text-3xl font-bold mt-1 text-emerald-600">{metrics.active_staff}</div></CardContent></Card>
            <Card><CardContent className="p-4"><div className="text-xs text-slate-500 uppercase">Redeemable</div><div className="text-3xl font-bold mt-1">₹{metrics.incentives_by_status?.redeemable?.amount || 0}</div></CardContent></Card>
            <Card><CardContent className="p-4"><div className="text-xs text-slate-500 uppercase">Pending</div><div className="text-3xl font-bold mt-1">₹{(metrics.incentives_by_status?.pending?.amount || 0) + (metrics.incentives_by_status?.pending_verification?.amount || 0)}</div></CardContent></Card>
          </div>
        )}

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="staff" data-testid="tab-staff"><Users size={16} className="mr-1" /> Staff</TabsTrigger>
            <TabsTrigger value="managers" data-testid="tab-managers"><Users size={16} className="mr-1" /> Retailer Logins</TabsTrigger>
            <TabsTrigger value="leaderboard" data-testid="tab-leaderboard"><Trophy size={16} className="mr-1" /> Leaderboard</TabsTrigger>
            <TabsTrigger value="redemptions" data-testid="tab-redemptions"><Wallet size={16} className="mr-1" /> Redemptions</TabsTrigger>
            <TabsTrigger value="report" data-testid="tab-report"><FileText size={16} className="mr-1" /> Reports</TabsTrigger>
            <TabsTrigger value="config" data-testid="tab-config"><Settings size={16} className="mr-1" /> Slabs</TabsTrigger>
          </TabsList>

          {/* STAFF LIST */}
          <TabsContent value="staff">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>Retail Staff ({filteredStaff.length}{filteredStaff.length !== staffList.length ? ` of ${staffList.length}` : ''})</CardTitle>
                <div className="flex gap-2 items-center">
                  <QRCardsPDFButton token={token} API_URL={API_URL} brands={[...new Set(staffList.map(s => s.brand_name).filter(Boolean))].sort()} />
                  <Button variant="outline" size="sm" onClick={downloadTemplate} data-testid="download-template-btn">
                    <FileText size={14} className="mr-1" /> Template
                  </Button>
                  <label className="cursor-pointer" data-testid="bulk-import-label">
                    <input
                      type="file"
                      accept=".csv,text/csv"
                      className="hidden"
                      data-testid="bulk-import-input"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (!f) return;
                        // Auto-run dry-run first — user must explicitly click "Confirm & Import" in the banner below to commit.
                        doBulkImport(f, true);
                        e.target.value = '';
                      }}
                    />
                    <span className="inline-flex items-center gap-1 px-3 py-1.5 text-sm rounded-md border hover:bg-slate-50">
                      <Upload size={14} /> {importing ? 'Importing…' : 'Bulk Import CSV'}
                    </span>
                  </label>
                  <Button variant="outline" size="sm" onClick={loadAll} data-testid="refresh-staff-btn"><RefreshCw size={16} /></Button>
                  <Dialog open={creating} onOpenChange={setCreating}>
                    <DialogTrigger asChild>
                      <Button size="sm" data-testid="add-staff-btn"><Plus size={16} className="mr-1" /> Add Staff</Button>
                    </DialogTrigger>
                    <DialogContent>
                      <DialogHeader><DialogTitle>Onboard Retail Staff</DialogTitle></DialogHeader>
                      <div className="space-y-3">
                        <div><Label>Name *</Label><Input data-testid="staff-form-name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></div>
                        <div><Label>Phone (10 digits) *</Label><Input data-testid="staff-form-phone" value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} /></div>
                        {/* Point 35: brand must come from the master brand list so incentive logic maps cleanly by brand/category */}
                        <div>
                          <Label>Brand Name *</Label>
                          <select
                            data-testid="staff-form-brand"
                            className="w-full h-10 px-3 rounded-md border border-slate-200 bg-white text-sm"
                            value={form.brand_name}
                            onChange={e => {
                              const bn = e.target.value;
                              const cat = catalog.brands.find(b => b.brand_name === bn)?.category || '';
                              setForm({ ...form, brand_name: bn, brand_category: cat || form.brand_category });
                            }}
                          >
                            <option value="">Select a brand…</option>
                            {catalog.brands.map(b => (
                              <option key={b.brand_name} value={b.brand_name}>{b.brand_name}{b.category ? ` — ${b.category}` : ''}</option>
                            ))}
                          </select>
                          <p className="text-[11px] text-slate-500 mt-1">Master brand list from Brand Admin. Missing a brand? Add it in <em>Brand Management</em> first.</p>
                        </div>
                        <div>
                          <Label>Brand Category</Label>
                          <select
                            data-testid="staff-form-brand-category"
                            className="w-full h-10 px-3 rounded-md border border-slate-200 bg-white text-sm"
                            value={form.brand_category}
                            onChange={e => setForm({ ...form, brand_category: e.target.value })}
                          >
                            <option value="">(auto — from brand)</option>
                            {catalog.categories.map(c => <option key={c} value={c}>{c}</option>)}
                          </select>
                        </div>
                        <div><Label>Store Location</Label><Input data-testid="staff-form-store" value={form.store_location} onChange={e => setForm({ ...form, store_location: e.target.value })} /></div>
                      </div>
                      <DialogFooter>
                        <Button onClick={submitCreate} data-testid="staff-form-submit">Create</Button>
                      </DialogFooter>
                    </DialogContent>
                  </Dialog>
                </div>
              </CardHeader>
              <CardContent>
                {/* Point 27: search + filter + recent-import view so freshly imported staff are actually discoverable in a 700+ row table */}
                <div className="mb-3 flex flex-wrap items-center gap-2 p-3 rounded-lg bg-slate-50 border" data-testid="staff-filter-bar">
                  <input
                    type="search"
                    className="h-9 px-3 text-sm rounded-md border border-slate-200 bg-white flex-1 min-w-[200px]"
                    placeholder="Search by name, phone, staff code…"
                    value={staffSearch}
                    onChange={e => setStaffSearch(e.target.value)}
                    data-testid="staff-search-input"
                  />
                  <select
                    className="h-9 px-3 text-sm rounded-md border border-slate-200 bg-white"
                    value={staffBrandFilter}
                    onChange={e => setStaffBrandFilter(e.target.value)}
                    data-testid="staff-brand-filter"
                  >
                    <option value="">All brands ({[...new Set(staffList.map(s => s.brand_name).filter(Boolean))].length})</option>
                    {[...new Set(staffList.map(s => s.brand_name).filter(Boolean))].sort().map(b => (
                      <option key={b} value={b}>{b}</option>
                    ))}
                  </select>
                  <label className="text-xs flex items-center gap-1 cursor-pointer" data-testid="staff-recent-toggle-label">
                    <input
                      type="checkbox"
                      checked={showRecentImportsOnly}
                      onChange={e => setShowRecentImportsOnly(e.target.checked)}
                      data-testid="staff-recent-toggle"
                    />
                    Recent CSV imports only
                  </label>
                  {/* Point 35: quick filter to zero in on staff whose brand isn't in the master list */}
                  <label className="text-xs flex items-center gap-1 cursor-pointer" data-testid="staff-unmapped-toggle-label">
                    <input
                      type="checkbox"
                      checked={showUnmappedOnly}
                      onChange={e => setShowUnmappedOnly(e.target.checked)}
                      data-testid="staff-unmapped-toggle"
                    />
                    Unmapped brand only {staffUnmappedCount > 0 && <span className="ml-1 px-1.5 rounded bg-amber-100 text-amber-800 font-semibold">{staffUnmappedCount}</span>}
                  </label>
                  <select
                    className="h-9 px-3 text-sm rounded-md border border-slate-200 bg-white"
                    value={staffPageSize}
                    onChange={e => setStaffPageSize(Number(e.target.value))}
                    data-testid="staff-page-size"
                  >
                    <option value={50}>Show 50</option>
                    <option value={200}>Show 200</option>
                    <option value={1000}>Show 1000</option>
                    <option value={99999}>Show all</option>
                  </select>
                </div>
                {importResult && (
                  <div className="mb-4 p-3 rounded-lg bg-amber-50 border border-amber-200 text-sm" data-testid="import-result-banner">
                    <div className="font-medium mb-1">
                      {importResult.dry_run ? 'Preview (not saved yet):' : 'Last import result:'}
                      &nbsp;{importResult.summary.imported} {importResult.dry_run ? 'will be imported' : 'imported'} · {importResult.summary.skipped_existing} skipped (already exist) · {importResult.summary.invalid} invalid
                    </div>
                    {importResult.dry_run && pendingImportFile && (
                      <div className="mt-2 mb-2 flex flex-wrap gap-2 items-center p-2 rounded-md bg-white border border-amber-300" data-testid="confirm-import-cta">
                        <span className="text-xs text-slate-600">Nothing has been saved yet. Review the preview above and click Confirm to save {importResult.summary.imported} row(s).</span>
                        <Button
                          size="sm"
                          onClick={() => { const f = pendingImportFile; setPendingImportFile(null); doBulkImport(f, false); }}
                          disabled={importing || importResult.summary.imported === 0}
                          data-testid="confirm-import-btn"
                        >
                          {importing ? 'Saving…' : `Confirm & Import ${importResult.summary.imported} row(s)`}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => { setPendingImportFile(null); setImportResult(null); }}
                          data-testid="cancel-import-btn"
                        >
                          Cancel
                        </Button>
                      </div>
                    )}
                    {!importResult.dry_run && importResult.summary.imported > 0 && (
                      <div className="text-xs mb-1 text-emerald-700" data-testid="import-view-hint">
                        Newly imported staff appear at the top of the table below (sorted by newest first).
                        <button
                          className="ml-2 underline"
                          onClick={() => { setShowRecentImportsOnly(true); setStaffSearch(''); setStaffBrandFilter(''); }}
                          data-testid="filter-recent-imports-btn"
                        >
                          Show only recent CSV imports
                        </button>
                      </div>
                    )}
                    {importResult.invalid_preview?.length > 0 && (
                      <details>
                        <summary className="cursor-pointer text-amber-700">Show {importResult.invalid_preview.length} invalid rows</summary>
                        <ul className="mt-2 text-xs text-slate-600 pl-4 list-disc">
                          {importResult.invalid_preview.map((r, i) => (
                            <li key={i}>Row {r.row}: {r.reason} — {r.name || ''} {r.brand ? `(${r.brand})` : ''} {r.phone_raw ? `phone="${r.phone_raw}"` : ''}</li>
                          ))}
                        </ul>
                      </details>
                    )}
                    <button className="ml-2 text-xs text-slate-500 underline" onClick={() => { setImportResult(null); setPendingImportFile(null); }}>dismiss</button>
                  </div>
                )}
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-left border-b">
                      <tr><th className="py-2 pr-4">Code</th><th className="pr-4">Name</th><th className="pr-4">Brand</th><th className="pr-4">Phone</th><th className="pr-4">Status</th><th>Actions</th></tr>
                    </thead>
                    <tbody data-testid="staff-list-tbody">
                      {filteredStaff.slice(0, staffPageSize).map(s => (
                        <tr key={s.id} className="border-b hover:bg-slate-50">
                          <td className="py-2 pr-4 font-mono text-xs">{s.staff_code}</td>
                          <td className="pr-4 font-medium">{s.name}</td>
                          <td className="pr-4">
                            {s.brand_name}
                            {/* Point 35: warning tag when the staff's brand isn't in the master brand list */}
                            {s.is_brand_mapped === false && (
                              <span className="ml-2 inline-block text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 font-semibold align-middle" data-testid={`staff-unmapped-badge-${s.id}`}>Unmapped</span>
                            )}
                          </td>
                          <td className="pr-4">{s.phone}</td>
                          <td className="pr-4">
                            <span className={s.is_active ? 'text-emerald-600' : 'text-slate-400'}>{s.is_active ? 'Active' : 'Inactive'}</span>
                          </td>
                          <td className="flex gap-2 py-2">
                            <Button size="sm" variant="outline" onClick={() => openQR(s.id)} data-testid={`staff-qr-btn-${s.id}`}><QrCode size={14} /></Button>
                            {s.is_brand_mapped === false && (
                              <Button size="sm" variant="outline" className="text-amber-700 border-amber-300" onClick={() => setReassignStaff(s)} data-testid={`staff-reassign-btn-${s.id}`}>Reassign</Button>
                            )}
                            <Button size="sm" variant="ghost" onClick={() => toggleActive(s)} data-testid={`staff-toggle-btn-${s.id}`}>{s.is_active ? 'Deactivate' : 'Activate'}</Button>
                          </td>
                        </tr>
                      ))}
                      {filteredStaff.length === 0 && staffList.length > 0 && (
                        <tr><td colSpan={6} className="py-8 text-center text-slate-400" data-testid="staff-no-matches">
                          No matches — try clearing the search or brand filter above. Total staff in system: <span className="font-semibold text-slate-700">{staffList.length}</span>.
                        </td></tr>
                      )}
                      {staffList.length === 0 && (
                        <tr><td colSpan={6} className="py-8 text-center text-slate-400">No staff onboarded yet.</td></tr>
                      )}
                    </tbody>
                  </table>
                  {filteredStaff.length > staffPageSize && (
                    <div className="p-3 text-xs text-slate-500 text-center border-t bg-slate-50" data-testid="staff-truncated-hint">
                      Showing {staffPageSize} of {filteredStaff.length} matches. Increase &ldquo;Show&rdquo; size above to see more.
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* LEADERBOARD */}
          <TabsContent value="leaderboard">
            <Card>
              <CardHeader><CardTitle><Trophy size={16} className="inline mr-1" /> Top Performers (30-day)</CardTitle></CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {leaderboard.map((r, i) => (
                    <div key={r.staff_code || i} className="flex items-center justify-between border-b pb-2">
                      <div>
                        <div className="font-medium">#{i + 1} {r.name} <span className="text-xs text-slate-400 ml-2">{r.staff_code} · {r.brand_name}</span></div>
                        <div className="text-xs text-slate-500">{r.registrations} regs · {r.bill_uploads} bills</div>
                      </div>
                      <div className="text-lg font-bold text-amber-600">₹{r.total_amount || 0}</div>
                    </div>
                  ))}
                  {leaderboard.length === 0 && <div className="py-8 text-center text-slate-400">No incentives earned yet.</div>}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* REDEMPTIONS */}
          <TabsContent value="redemptions">
            <Card>
              <CardHeader><CardTitle>Redemption Requests</CardTitle></CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-left border-b">
                      <tr><th className="py-2 pr-4">Ref</th><th className="pr-4">Staff</th><th className="pr-4">Amount</th><th className="pr-4">Status</th><th className="pr-4">Requested</th><th>Actions</th></tr>
                    </thead>
                    <tbody data-testid="redemptions-tbody">
                      {redemptions.map(r => (
                        <tr key={r.id} className="border-b hover:bg-slate-50">
                          <td className="py-2 pr-4 font-mono text-xs">{r.reference}</td>
                          <td className="pr-4">{r.staff_name || '-'} <span className="text-xs text-slate-400 block">{r.staff_phone}</span></td>
                          <td className="pr-4 font-bold">₹{r.amount}</td>
                          <td className="pr-4">
                            <span className={r.status === 'settled' ? 'text-emerald-600' : r.status === 'rejected' ? 'text-red-500' : 'text-amber-600'}>{r.status}</span>
                          </td>
                          <td className="pr-4 text-xs">{r.requested_at?.slice(0, 16).replace('T', ' ')}</td>
                          <td className="py-2 flex gap-2">
                            {r.status === 'requested' && (
                              <>
                                <Button size="sm" onClick={() => settleRedemption(r.id, 'settled')}>Mark Settled</Button>
                                <Button size="sm" variant="outline" onClick={() => settleRedemption(r.id, 'rejected')}>Reject</Button>
                              </>
                            )}
                          </td>
                        </tr>
                      ))}
                      {redemptions.length === 0 && (
                        <tr><td colSpan={6} className="py-8 text-center text-slate-400">No redemption requests yet.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* RETAILER MANAGERS (Point 5) */}
          <TabsContent value="managers">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>Retailer Logins ({managers.length})</CardTitle>
                <Dialog open={creatingMgr} onOpenChange={setCreatingMgr}>
                  <DialogTrigger asChild>
                    <Button size="sm" data-testid="add-manager-btn"><Plus size={16} className="mr-1" /> Add Retailer Login</Button>
                  </DialogTrigger>
                  <DialogContent>
                    <DialogHeader><DialogTitle>Whitelist Retailer Manager</DialogTitle></DialogHeader>
                    <div className="space-y-3">
                      <div><Label>Name *</Label><Input data-testid="mgr-form-name" value={mgrForm.name} onChange={e => setMgrForm({ ...mgrForm, name: e.target.value })} /></div>
                      <div><Label>Phone (10 digits) *</Label><Input data-testid="mgr-form-phone" value={mgrForm.phone} onChange={e => setMgrForm({ ...mgrForm, phone: e.target.value })} /></div>
                      <div><Label>Brands (comma-separated) *</Label><Input data-testid="mgr-form-brands" placeholder="Zara, H&M" value={mgrForm.brands} onChange={e => setMgrForm({ ...mgrForm, brands: e.target.value })} /></div>
                      <div><Label>Email</Label><Input data-testid="mgr-form-email" value={mgrForm.email} onChange={e => setMgrForm({ ...mgrForm, email: e.target.value })} /></div>
                    </div>
                    <DialogFooter>
                      <Button onClick={submitCreateMgr} data-testid="mgr-form-submit">Save</Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap items-center gap-2 mb-3 p-3 rounded-lg bg-slate-50 border">
                  <div className="text-xs text-slate-600 flex-1">
                    <div>Retailer portal URL:</div>
                    <div className="font-mono text-[13px] text-slate-800">{window.location.origin}/staff-app/retailer/login</div>
                    <div className="mt-1">Only whitelisted phones can sign in with OTP. No consumer PII is shown.</div>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => { navigator.clipboard.writeText(`${window.location.origin}/staff-app/retailer/login`); toast.success('Portal URL copied'); }}
                    data-testid="copy-portal-url-btn"
                  >
                    Copy URL
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => window.open('/staff-app/retailer/login', '_blank')}
                    data-testid="open-portal-btn"
                  >
                    Open Portal
                  </Button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-left border-b">
                      <tr><th className="py-2 pr-4">Name</th><th className="pr-4">Phone</th><th className="pr-4">Brands</th><th className="pr-4">Status</th><th>Actions</th></tr>
                    </thead>
                    <tbody data-testid="managers-tbody">
                      {managers.map(m => (
                        <tr key={m.id} className="border-b hover:bg-slate-50">
                          <td className="py-2 pr-4 font-medium">{m.name}</td>
                          <td className="pr-4 font-mono">{m.phone}</td>
                          <td className="pr-4">{(m.brands || []).join(', ')}</td>
                          <td className="pr-4"><span className={m.is_active ? 'text-emerald-600' : 'text-slate-400'}>{m.is_active ? 'Active' : 'Inactive'}</span></td>
                          <td className="py-2 flex gap-2">
                            <Button
                              size="sm"
                              variant="outline"
                              data-testid={`mgr-invite-${m.id}`}
                              onClick={() => {
                                const portal = `${window.location.origin}/staff-app/retailer/login`;
                                const msg = `Hi ${m.name}, your Homeland Advantage retailer portal access is ready.\n\nLogin with your registered phone (${m.phone}) at:\n${portal}\n\nYou'll receive an OTP to sign in.`;
                                const url = `https://wa.me/91${m.phone}?text=${encodeURIComponent(msg)}`;
                                window.open(url, '_blank');
                              }}
                            >
                              WhatsApp Invite
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => toggleMgrActive(m)} data-testid={`mgr-toggle-${m.id}`}>{m.is_active ? 'Deactivate' : 'Activate'}</Button>
                            <Button size="sm" variant="outline" onClick={() => deleteMgr(m)} data-testid={`mgr-delete-${m.id}`}>Remove</Button>
                          </td>
                        </tr>
                      ))}
                      {managers.length === 0 && (
                        <tr><td colSpan={5} className="py-8 text-center text-slate-400">No retailer logins whitelisted yet.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* CONFIG */}
          <TabsContent value="config">
            {config && (
              <Card>
                <CardHeader><CardTitle>Incentive Slabs</CardTitle></CardHeader>
                <CardContent className="space-y-6">
                  <div>
                    <div className="font-medium mb-2 flex items-center gap-2"><Award size={16} /> Default Registration Slabs</div>
                    {config.registration_slabs.map((s, i) => (
                      <div key={i} className="grid grid-cols-3 gap-2 mb-2 items-center">
                        <Input type="number" value={s.min} onChange={e => updateSlab('registration_slabs', i, 'min', e.target.value)} placeholder="Min" />
                        <Input type="number" value={s.max} onChange={e => updateSlab('registration_slabs', i, 'max', e.target.value)} placeholder="Max" />
                        <div className="flex items-center gap-2">₹<Input type="number" value={s.amount} onChange={e => updateSlab('registration_slabs', i, 'amount', e.target.value)} placeholder="Amount" /></div>
                      </div>
                    ))}
                  </div>
                  <div>
                    <div className="font-medium mb-2 flex items-center gap-2"><Award size={16} /> Default Bill Upload Slabs</div>
                    {config.bill_upload_slabs.map((s, i) => (
                      <div key={i} className="grid grid-cols-3 gap-2 mb-2 items-center">
                        <Input type="number" value={s.min} onChange={e => updateSlab('bill_upload_slabs', i, 'min', e.target.value)} placeholder="Min" />
                        <Input type="number" value={s.max} onChange={e => updateSlab('bill_upload_slabs', i, 'max', e.target.value)} placeholder="Max" />
                        <div className="flex items-center gap-2">₹<Input type="number" value={s.amount} onChange={e => updateSlab('bill_upload_slabs', i, 'amount', e.target.value)} placeholder="Amount" /></div>
                      </div>
                    ))}
                  </div>

                  {/* Point 3 / 7: Category-wise & Brand-wise overrides — populated from live brand catalog */}
                  <OverrideEditor
                    title="Category-wise Slabs"
                    kind="category_slabs"
                    config={config}
                    setConfig={setConfig}
                    options={catalog.categories}
                    allowAll={true}
                    placeholder="Pick a category"
                  />
                  <OverrideEditor
                    title="Brand-wise Slabs"
                    kind="brand_slabs"
                    config={config}
                    setConfig={setConfig}
                    options={catalog.brands.map(b => b.brand_name)}
                    placeholder="Pick a brand"
                  />

                  {/* Point 8: Registration incentive — flat amount per category with __ALL__ universal fallback */}
                  {/* Point 10: dropdown limited to categories actually mapped to retailer staff */}
                  <RegistrationByCategoryEditor
                    config={config}
                    setConfig={setConfig}
                    categoryOptions={catalog.staff_mapped_categories}
                  />

                  {/* Point 9: Bill-upload incentive — value-based slabs per category with __ALL__ universal fallback */}
                  {/* Point 10: dropdown limited to categories actually mapped to retailer staff */}
                  <BillValueSlabsEditor
                    config={config}
                    setConfig={setConfig}
                    categoryOptions={catalog.staff_mapped_categories}
                  />

                  {/* Point 7: Brand ↔ Category mapping bulk upload */}
                  <div className="border rounded-lg p-4 bg-slate-50/40" data-testid="brand-category-mapping-block">
                    <div className="font-medium mb-2 flex items-center gap-2"><Upload size={16} /> Brand ↔ Category Mapping</div>
                    <div className="text-xs text-slate-500 mb-3">
                      Upload a CSV (columns: <span className="font-mono">Brand Name, Brand Category</span>) to bulk-set the category for many brands at once. The dropdowns above will refresh from this mapping.
                    </div>
                    <div className="flex flex-wrap gap-2 items-center">
                      <Button size="sm" variant="outline" onClick={downloadMappingTemplate} data-testid="mapping-template-btn">
                        <FileText size={14} className="mr-1" /> Template
                      </Button>
                      <label className="cursor-pointer" data-testid="mapping-upload-label">
                        <input
                          type="file"
                          accept=".csv,text/csv"
                          className="hidden"
                          data-testid="mapping-upload-input"
                          onChange={(e) => {
                            const f = e.target.files?.[0];
                            if (!f) return;
                            uploadBrandCategoryMapping(f, true);
                            e.target.value = '';
                          }}
                        />
                        <span className="inline-flex items-center gap-1 px-3 py-1.5 text-sm rounded-md border hover:bg-slate-50">
                          <Upload size={14} /> {uploadingMapping ? 'Uploading…' : 'Upload Mapping CSV'}
                        </span>
                      </label>
                    </div>
                    {mappingResult && (
                      <div className="mt-3 p-3 rounded-md bg-amber-50 border border-amber-200 text-xs" data-testid="mapping-result-banner">
                        <div className="font-medium">
                          {mappingResult.dry_run ? 'Preview (not saved yet):' : 'Last upload:'}
                          &nbsp;{mappingResult.summary.updated} {mappingResult.dry_run ? 'will be updated' : 'updated'} · {mappingResult.summary.created} new · {mappingResult.summary.invalid} invalid
                        </div>
                        {mappingResult.dry_run && pendingMappingFile && (
                          <div className="mt-2 flex flex-wrap gap-2 items-center" data-testid="confirm-mapping-cta">
                            <Button
                              size="sm"
                              onClick={() => { const f = pendingMappingFile; setPendingMappingFile(null); uploadBrandCategoryMapping(f, false); }}
                              disabled={uploadingMapping}
                              data-testid="confirm-mapping-btn"
                            >
                              {uploadingMapping ? 'Saving…' : 'Confirm & Import'}
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => { setPendingMappingFile(null); setMappingResult(null); }}
                              data-testid="cancel-mapping-btn"
                            >
                              Cancel
                            </Button>
                          </div>
                        )}
                        <button className="mt-1 text-slate-500 underline" onClick={() => { setMappingResult(null); setPendingMappingFile(null); }}>dismiss</button>
                      </div>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label>Attribution Window (minutes)</Label>
                      <Input type="number" value={config.attribution_window_minutes} onChange={e => setConfig({ ...config, attribution_window_minutes: Number(e.target.value) })} />
                    </div>
                    <div>
                      <Label>Registration Validity (days)</Label>
                      <Input type="number" value={config.registration_validity_days} onChange={e => setConfig({ ...config, registration_validity_days: Number(e.target.value) })} />
                    </div>
                  </div>
                  <Button onClick={saveConfig} data-testid="save-config-btn">Save Config</Button>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* POINT 12 · REPORTS TAB */}
          <TabsContent value="report">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>Retailer Incentive Report</CardTitle>
                <div className="flex gap-2 items-center">
                  <Button variant="outline" size="sm" onClick={loadReport} data-testid="refresh-report-btn">
                    <RefreshCw size={16} className="mr-1" /> Refresh
                  </Button>
                  <Button size="sm" onClick={downloadReportCsv} data-testid="download-report-csv-btn">
                    <FileText size={16} className="mr-1" /> Download CSV
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {/* Test OTP diagnostics (Point 11) */}
                <div className="mb-4 p-3 rounded-md bg-amber-50 border border-amber-200">
                  <div className="text-sm font-medium mb-2">Point 11 · Test Retailer OTP (WhatsApp + SMS)</div>
                  <div className="flex gap-2 items-center flex-wrap">
                    <Input
                      placeholder="Retailer manager phone (10 digits)"
                      value={testOtpPhone}
                      onChange={e => setTestOtpPhone(e.target.value)}
                      className="max-w-xs"
                      data-testid="test-otp-phone-input"
                    />
                    <Button size="sm" onClick={sendTestOtp} disabled={testOtpBusy} data-testid="send-test-otp-btn">
                      {testOtpBusy ? 'Sending…' : 'Send Test OTP'}
                    </Button>
                    {testOtpResult && (
                      <div className="text-xs text-slate-700" data-testid="test-otp-result">
                        {testOtpResult.success ? '✅' : '❌'} {testOtpResult.message || (testOtpResult.success ? 'Sent' : 'Failed')}
                        {testOtpResult.delivery && (
                          <span className="ml-2 font-mono">
                            WA: {testOtpResult.delivery.whatsapp?.status_code ?? 'n/a'}, SMS: {testOtpResult.delivery.sms?.status_code ?? 'n/a'}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {/* Filters */}
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-3">
                  <div>
                    <Label>Type</Label>
                    <select
                      value={reportType}
                      onChange={e => setReportType(e.target.value)}
                      className="w-full border rounded px-2 py-1 text-sm"
                      data-testid="report-type-select"
                    >
                      <option value="registration">Registration</option>
                      <option value="bill_upload">Bill Upload</option>
                    </select>
                  </div>
                  <div>
                    <Label>Brand</Label>
                    <select
                      value={reportBrand}
                      onChange={e => setReportBrand(e.target.value)}
                      className="w-full border rounded px-2 py-1 text-sm"
                      data-testid="report-brand-select"
                    >
                      <option value="">All brands</option>
                      {(catalog.staff_mapped_brands || catalog.brands || []).map(b => (
                        <option key={b} value={b}>{b}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <Label>Status</Label>
                    <select
                      value={reportStatus}
                      onChange={e => setReportStatus(e.target.value)}
                      className="w-full border rounded px-2 py-1 text-sm"
                      data-testid="report-status-select"
                    >
                      <option value="">All statuses</option>
                      <option value="pending">Pending</option>
                      <option value="pending_verification">Pending Verification</option>
                      <option value="redeemable">Redeemable</option>
                      <option value="redeemed">Redeemed</option>
                      <option value="cancelled">Cancelled</option>
                    </select>
                  </div>
                  <div>
                    <Label>Start Date</Label>
                    <Input type="date" value={reportStart} onChange={e => setReportStart(e.target.value)} data-testid="report-start-date" />
                  </div>
                  <div>
                    <Label>End Date</Label>
                    <Input type="date" value={reportEnd} onChange={e => setReportEnd(e.target.value)} data-testid="report-end-date" />
                  </div>
                </div>
                <Button size="sm" onClick={loadReport} data-testid="apply-report-filters-btn" className="mb-3">Apply Filters</Button>

                {/* KPI tiles */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                  <div className="p-3 rounded-md bg-blue-50 border border-blue-200">
                    <div className="text-xs text-slate-600">Registration Records</div>
                    <div className="text-2xl font-bold text-blue-700" data-testid="report-reg-count">{reportSummary.registration_count || 0}</div>
                  </div>
                  <div className="p-3 rounded-md bg-emerald-50 border border-emerald-200">
                    <div className="text-xs text-slate-600">Bill Upload Records</div>
                    <div className="text-2xl font-bold text-emerald-700" data-testid="report-bill-count">{reportSummary.bill_upload_count || 0}</div>
                  </div>
                  <div className="p-3 rounded-md bg-amber-50 border border-amber-200">
                    <div className="text-xs text-slate-600">Total Amount</div>
                    <div className="text-2xl font-bold text-amber-700" data-testid="report-total-amount">₹{Math.round(reportSummary.total_amount || 0).toLocaleString()}</div>
                  </div>
                  <div className="p-3 rounded-md bg-purple-50 border border-purple-200">
                    <div className="text-xs text-slate-600">Redeemable Amount</div>
                    <div className="text-2xl font-bold text-purple-700" data-testid="report-redeemable-amount">₹{Math.round(reportSummary.redeemable_amount || 0).toLocaleString()}</div>
                  </div>
                </div>

                {/* Table */}
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50">
                      <tr className="text-left">
                        <th className="p-2">Staff Code</th>
                        <th className="p-2">Staff Name</th>
                        <th className="p-2">Brand</th>
                        <th className="p-2">Customer Mobile</th>
                        <th className="p-2">Amount</th>
                        <th className="p-2">Status</th>
                        {reportType === 'bill_upload' && <th className="p-2">Bill</th>}
                        <th className="p-2">Created</th>
                      </tr>
                    </thead>
                    <tbody data-testid="report-tbody">
                      {reportLoading && (
                        <tr><td colSpan={reportType === 'bill_upload' ? 8 : 7} className="text-center p-6 text-slate-500">Loading…</td></tr>
                      )}
                      {!reportLoading && reportRows.length === 0 && (
                        <tr><td colSpan={reportType === 'bill_upload' ? 8 : 7} className="text-center p-6 text-slate-500">No records match the filters.</td></tr>
                      )}
                      {!reportLoading && reportRows.map(r => (
                        <tr key={r.id} className="border-b hover:bg-slate-50">
                          <td className="p-2 font-mono text-xs">{r.staff_code}</td>
                          <td className="p-2">{r.staff_name}</td>
                          <td className="p-2">{r.staff_brand}{r.staff_brand_category ? <span className="text-xs text-slate-400"> / {r.staff_brand_category}</span> : null}</td>
                          <td className="p-2 font-mono">{r.customer_phone || '—'}</td>
                          <td className="p-2">₹{r.amount || 0}</td>
                          <td className="p-2">
                            <span className={`text-xs px-2 py-0.5 rounded ${r.status === 'redeemable' ? 'bg-emerald-100 text-emerald-800' : r.status === 'cancelled' ? 'bg-red-100 text-red-700' : 'bg-slate-100 text-slate-700'}`}>{r.status}</span>
                          </td>
                          {reportType === 'bill_upload' && (
                            <td className="p-2 text-xs">
                              {r.bill_no ? <div className="font-mono">{r.bill_no}</div> : null}
                              {r.bill_store ? <div className="text-slate-500">{r.bill_store}</div> : null}
                              {r.bill_amount ? <div className="text-slate-500">₹{r.bill_amount}</div> : null}
                            </td>
                          )}
                          <td className="p-2 text-xs text-slate-500">{r.created_at?.split('T')[0]}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </TabsContent>


        </Tabs>

        {/* QR MODAL */}
        <Dialog open={!!showQR} onOpenChange={o => !o && setShowQR(null)}>
          <DialogContent>
            <DialogHeader><DialogTitle>Staff QR Code — {showQR?.staff_code}</DialogTitle></DialogHeader>
            {showQR && (
              <div className="text-center">
                {showQR.qr_image_base64 && <img src={`data:image/png;base64,${showQR.qr_image_base64}`} alt="QR" className="mx-auto max-w-[280px]" data-testid="staff-qr-img" />}
                <div className="mt-3 text-xs text-slate-500 break-all">{showQR.whatsapp_url}</div>
                <div className="mt-2 text-sm">Prefilled: <span className="font-mono">{showQR.prefilled_message}</span></div>
              </div>
            )}
          </DialogContent>
        </Dialog>

        {/* Point 35: Reassign brand modal for legacy/unmapped staff */}
        <Dialog open={!!reassignStaff} onOpenChange={o => !o && setReassignStaff(null)}>
          <DialogContent data-testid="reassign-brand-dialog">
            <DialogHeader><DialogTitle>Reassign Brand — {reassignStaff?.name}</DialogTitle></DialogHeader>
            <div className="space-y-3">
              <div className="text-sm text-slate-600">
                Current brand: <span className="font-medium">{reassignStaff?.brand_name || '(none)'}</span>. This brand isn&apos;t in your master brand list, so incentive attribution may misfire.
              </div>
              <div>
                <Label>Pick a master brand</Label>
                <select
                  data-testid="reassign-brand-select"
                  className="w-full h-10 px-3 rounded-md border border-slate-200 bg-white text-sm"
                  defaultValue=""
                  onChange={e => e.target.value && submitReassignBrand(e.target.value)}
                >
                  <option value="">Select a brand…</option>
                  {catalog.brands.map(b => (
                    <option key={b.brand_name} value={b.brand_name}>{b.brand_name}{b.category ? ` — ${b.category}` : ''}</option>
                  ))}
                </select>
                <p className="text-[11px] text-slate-500 mt-1">Category will be auto-filled from the master brand.</p>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </DashboardLayout>
  );
}

// Sub-component: Category / Brand-wise slab override editor
// Point 7: uses a <select> populated from the actual catalog + optional "ALL" scope
function OverrideEditor({ title, kind, config, setConfig, placeholder, options = [], allowAll = false }) {
  const [newKey, setNewKey] = useState('');
  const map = config[kind] || {};
  const entries = Object.entries(map);
  const usedKeys = new Set(Object.keys(map));

  const setMap = (updater) => {
    const next = { ...(config[kind] || {}) };
    updater(next);
    setConfig({ ...config, [kind]: next });
  };

  const addOverride = () => {
    const k = newKey.trim();
    if (!k) { toast.error('Please pick a value'); return; }
    if (map[k]) { toast.error('Already exists'); return; }
    setMap(m => {
      m[k] = {
        registration_slabs: [{ min: 0, max: 999999, amount: 50 }],
        bill_upload_slabs: [{ min: 0, max: 999999, amount: 20 }],
      };
    });
    setNewKey('');
  };
  const removeOverride = (key) => {
    if (!window.confirm(`Remove ${title} for "${key === '__ALL__' ? 'ALL' : key}"?`)) return;
    setMap(m => { delete m[key]; });
  };
  const updateOverrideSlab = (key, slabKind, idx, field, value) => {
    setMap(m => {
      const arr = [...(m[key][slabKind] || [])];
      arr[idx] = { ...arr[idx], [field]: Number(value) };
      m[key] = { ...m[key], [slabKind]: arr };
    });
  };
  const addSlabRow = (key, slabKind) => {
    setMap(m => {
      const arr = [...(m[key][slabKind] || [])];
      arr.push({ min: 0, max: 999999, amount: 0 });
      m[key] = { ...m[key], [slabKind]: arr };
    });
  };
  const removeSlabRow = (key, slabKind, idx) => {
    setMap(m => {
      const arr = [...(m[key][slabKind] || [])];
      arr.splice(idx, 1);
      m[key] = { ...m[key], [slabKind]: arr };
    });
  };

  // Available options for the picker (exclude already-added)
  const availableOptions = options.filter(o => !usedKeys.has(o));

  return (
    <div className="border rounded-lg p-4 bg-slate-50/40" data-testid={`override-editor-${kind}`}>
      <div className="font-medium mb-2 flex items-center gap-2"><Award size={16} /> {title}</div>
      <div className="text-xs text-slate-500 mb-3">
        Override the default slabs for a specific {kind === 'category_slabs' ? 'brand category' : 'brand'}.
        Priority: <span className="font-mono">brand → category → all → default</span>.
      </div>
      <div className="flex gap-2 mb-3">
        <select
          value={newKey}
          onChange={e => setNewKey(e.target.value)}
          className="flex-1 h-10 px-3 rounded-md border border-slate-200 bg-white text-sm"
          data-testid={`override-new-key-${kind}`}
        >
          <option value="">{placeholder}</option>
          {allowAll && !usedKeys.has('__ALL__') && (
            <option value="__ALL__">All ({kind === 'category_slabs' ? 'categories & brands' : 'brands'})</option>
          )}
          {availableOptions.map(o => (
            <option key={o} value={o}>{o}</option>
          ))}
        </select>
        <Button size="sm" onClick={addOverride} data-testid={`override-add-${kind}`}><Plus size={14} className="mr-1" /> Add</Button>
      </div>
      {options.length === 0 && (
        <div className="text-xs text-amber-600 mb-2">
          No {kind === 'category_slabs' ? 'categories' : 'brands'} configured yet. Add brands (with categories) first.
        </div>
      )}
      {entries.length === 0 && (
        <div className="text-sm text-slate-400 py-3">No overrides — defaults will apply.</div>
      )}
      {entries.map(([key, val]) => (
        <div key={key} className="mb-4 p-3 bg-white border rounded">
          <div className="flex justify-between items-center mb-2">
            <div className="font-semibold">{key === '__ALL__' ? 'ALL (default fallback)' : key}</div>
            <Button size="sm" variant="outline" onClick={() => removeOverride(key)} data-testid={`override-remove-${kind}-${key}`}>Remove</Button>
          </div>
          {['registration_slabs', 'bill_upload_slabs'].map(sk => (
            <div key={sk} className="mb-2">
              <div className="text-xs text-slate-500 mb-1">{sk === 'registration_slabs' ? 'Registration' : 'Bill Upload'}</div>
              {(val[sk] || []).map((s, i) => (
                <div key={i} className="grid grid-cols-[1fr_1fr_1fr_auto] gap-2 mb-1 items-center">
                  <Input type="number" value={s.min} onChange={e => updateOverrideSlab(key, sk, i, 'min', e.target.value)} placeholder="Min" />
                  <Input type="number" value={s.max} onChange={e => updateOverrideSlab(key, sk, i, 'max', e.target.value)} placeholder="Max" />
                  <div className="flex items-center gap-1">₹<Input type="number" value={s.amount} onChange={e => updateOverrideSlab(key, sk, i, 'amount', e.target.value)} placeholder="Amount" /></div>
                  <Button size="sm" variant="ghost" onClick={() => removeSlabRow(key, sk, i)}>×</Button>
                </div>
              ))}
              <Button size="sm" variant="outline" onClick={() => addSlabRow(key, sk)}><Plus size={12} className="mr-1" /> Add row</Button>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

// Point 8: Flat registration reward per category + universal (__ALL__) fallback.
function RegistrationByCategoryEditor({ config, setConfig, categoryOptions }) {
  const map = config.registration_by_category || {};
  const entries = Object.entries(map);
  const [newKey, setNewKey] = useState('');
  const usedKeys = new Set(Object.keys(map));

  const setMap = (updater) => {
    const next = { ...(config.registration_by_category || {}) };
    updater(next);
    setConfig({ ...config, registration_by_category: next });
  };
  const addRow = () => {
    const k = newKey.trim();
    if (!k) { toast.error('Pick a category or ALL'); return; }
    if (usedKeys.has(k)) { toast.error('Already added'); return; }
    setMap(m => { m[k] = 50; });
    setNewKey('');
  };
  const updateAmount = (k, v) => setMap(m => { m[k] = Number(v) || 0; });
  const removeRow = (k) => {
    if (!window.confirm(`Remove registration reward for "${k === '__ALL__' ? 'ALL' : k}"?`)) return;
    setMap(m => { delete m[k]; });
  };

  return (
    <div className="border rounded-lg p-4 bg-emerald-50/40" data-testid="reg-by-category-editor">
      <div className="font-medium mb-2 flex items-center gap-2"><Award size={16} /> Point 8 · Registration Reward per Category</div>
      <div className="text-xs text-slate-600 mb-3">
        Flat ₹ reward per registration, resolved by the staff&apos;s brand category. Priority: <span className="font-mono">category → ALL → legacy slabs</span>.
        {categoryOptions.length === 0 && (
          <div className="mt-1 text-amber-700">
            No retailer-staff-mapped categories yet — add staff whose brand is present in the Brand ↔ Category Mapping to see options here (Point 10).
          </div>
        )}
      </div>
      <div className="flex gap-2 mb-3">
        <select
          value={newKey}
          onChange={e => setNewKey(e.target.value)}
          className="flex-1 h-10 px-3 rounded-md border border-slate-200 bg-white text-sm"
          data-testid="reg-by-category-new-key"
        >
          <option value="">Pick a category</option>
          {!usedKeys.has('__ALL__') && <option value="__ALL__">All (universal fallback)</option>}
          {categoryOptions.filter(c => !usedKeys.has(c)).map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <Button size="sm" onClick={addRow} data-testid="reg-by-category-add"><Plus size={14} className="mr-1" /> Add</Button>
      </div>
      {entries.length === 0 && (
        <div className="text-sm text-slate-400 py-3">No category-specific rewards — old count-based slabs will apply.</div>
      )}
      {entries.map(([k, v]) => (
        <div key={k} className="mb-2 grid grid-cols-[2fr_1fr_auto] gap-2 items-center bg-white p-2 rounded border">
          <div className="font-medium text-sm">{k === '__ALL__' ? 'ALL (universal fallback)' : k}</div>
          <div className="flex items-center gap-1">₹<Input type="number" value={v} onChange={e => updateAmount(k, e.target.value)} data-testid={`reg-by-category-amount-${k}`} /></div>
          <Button size="sm" variant="ghost" onClick={() => removeRow(k)} data-testid={`reg-by-category-remove-${k}`}>×</Button>
        </div>
      ))}
    </div>
  );
}

// Point 9: Bill-upload reward — value-based slabs (min/max ₹) per category + __ALL__ universal fallback.
function BillValueSlabsEditor({ config, setConfig, categoryOptions }) {
  const map = config.bill_upload_value_slabs_by_category || {};
  const entries = Object.entries(map);
  const [newKey, setNewKey] = useState('');
  const usedKeys = new Set(Object.keys(map));

  const setMap = (updater) => {
    const next = { ...(config.bill_upload_value_slabs_by_category || {}) };
    updater(next);
    setConfig({ ...config, bill_upload_value_slabs_by_category: next });
  };
  const addBucket = () => {
    const k = newKey.trim();
    if (!k) { toast.error('Pick a category or ALL'); return; }
    if (usedKeys.has(k)) { toast.error('Already added'); return; }
    setMap(m => { m[k] = [{ min_value: 0, max_value: 999999, amount: 20 }]; });
    setNewKey('');
  };
  const removeBucket = (k) => {
    if (!window.confirm(`Remove bill-value slabs for "${k === '__ALL__' ? 'ALL' : k}"?`)) return;
    setMap(m => { delete m[k]; });
  };
  const updateSlab = (k, idx, field, value) => {
    setMap(m => {
      const arr = [...(m[k] || [])];
      arr[idx] = { ...arr[idx], [field]: Number(value) };
      m[k] = arr;
    });
  };
  const addSlab = (k) => setMap(m => { m[k] = [...(m[k] || []), { min_value: 0, max_value: 999999, amount: 0 }]; });
  const removeSlab = (k, idx) => setMap(m => {
    const arr = [...(m[k] || [])];
    arr.splice(idx, 1);
    m[k] = arr;
  });

  return (
    <div className="border rounded-lg p-4 bg-blue-50/40" data-testid="bill-value-slabs-editor">
      <div className="font-medium mb-2 flex items-center gap-2"><Award size={16} /> Point 9 · Bill Upload Reward by Bill Value</div>
      <div className="text-xs text-slate-600 mb-3">
        ₹ reward per bill-upload picked by the <strong>bill value</strong> uploaded. Priority: <span className="font-mono">category → ALL → legacy slabs</span>.
        {categoryOptions.length === 0 && (
          <div className="mt-1 text-amber-700">
            No retailer-staff-mapped categories yet — add staff whose brand is present in the Brand ↔ Category Mapping to see options here (Point 10).
          </div>
        )}
      </div>
      <div className="flex gap-2 mb-3">
        <select
          value={newKey}
          onChange={e => setNewKey(e.target.value)}
          className="flex-1 h-10 px-3 rounded-md border border-slate-200 bg-white text-sm"
          data-testid="bill-value-slabs-new-key"
        >
          <option value="">Pick a category</option>
          {!usedKeys.has('__ALL__') && <option value="__ALL__">All (universal fallback)</option>}
          {categoryOptions.filter(c => !usedKeys.has(c)).map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <Button size="sm" onClick={addBucket} data-testid="bill-value-slabs-add"><Plus size={14} className="mr-1" /> Add</Button>
      </div>
      {entries.length === 0 && (
        <div className="text-sm text-slate-400 py-3">No value-based slabs — old count-based slabs will apply.</div>
      )}
      {entries.map(([k, rows]) => (
        <div key={k} className="mb-4 p-3 bg-white border rounded">
          <div className="flex justify-between items-center mb-2">
            <div className="font-semibold text-sm">{k === '__ALL__' ? 'ALL (universal fallback)' : k}</div>
            <Button size="sm" variant="outline" onClick={() => removeBucket(k)} data-testid={`bill-value-slabs-remove-${k}`}>Remove</Button>
          </div>
          <div className="grid grid-cols-[1fr_1fr_1fr_auto] gap-2 mb-1 text-xs text-slate-500">
            <div>Bill ≥ ₹</div>
            <div>Bill ≤ ₹</div>
            <div>Reward ₹</div>
            <div></div>
          </div>
          {rows.map((s, i) => (
            <div key={i} className="grid grid-cols-[1fr_1fr_1fr_auto] gap-2 mb-1 items-center">
              <Input type="number" value={s.min_value} onChange={e => updateSlab(k, i, 'min_value', e.target.value)} data-testid={`bill-value-min-${k}-${i}`} />
              <Input type="number" value={s.max_value} onChange={e => updateSlab(k, i, 'max_value', e.target.value)} data-testid={`bill-value-max-${k}-${i}`} />
              <Input type="number" value={s.amount} onChange={e => updateSlab(k, i, 'amount', e.target.value)} data-testid={`bill-value-amt-${k}-${i}`} />
              <Button size="sm" variant="ghost" onClick={() => removeSlab(k, i)}>×</Button>
            </div>
          ))}
          <Button size="sm" variant="outline" onClick={() => addSlab(k)} data-testid={`bill-value-slabs-addrow-${k}`}><Plus size={12} className="mr-1" /> Add row</Button>
        </div>
      ))}
    </div>
  );
}

// Sub-component: PDF QR cards download button + brand filter
function QRCardsPDFButton({ token, API_URL, brands }) {  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [brand, setBrand] = useState('');   // '' = all

  const download = async () => {
    setBusy(true);
    try {
      const qs = brand ? `?brand=${encodeURIComponent(brand)}` : '';
      const r = await fetch(`${API_URL}/admin/staff/qr-cards.pdf${qs}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        toast.error(err.detail || `PDF export failed (HTTP ${r.status})`);
        return;
      }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = brand
        ? `homeland-qrs-${brand.toLowerCase().replace(/\s+/g, '-')}.pdf`
        : 'homeland-qrs-all.pdf';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success('QR cards PDF downloaded');
      setOpen(false);
    } catch (e) {
      toast.error('Download failed: ' + e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline" data-testid="qr-pdf-btn">
          <FileText size={14} className="mr-1" /> QR Cards PDF
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Print QR Cards</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="text-sm text-slate-600">
            One A4 sheet holds 6 laminate-ready cards. Each card has the staff&apos;s QR,
            name, code and brand. Filter to print for a single brand or export all
            active staff in one PDF.
          </div>
          <div>
            <Label>Brand filter</Label>
            <select
              value={brand}
              onChange={(e) => setBrand(e.target.value)}
              className="w-full h-10 px-3 rounded-md border border-slate-200 bg-white text-sm"
              data-testid="qr-pdf-brand-select"
            >
              <option value="">All active staff ({brands.length} brands)</option>
              {brands.map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>
          </div>
        </div>
        <DialogFooter>
          <Button onClick={download} disabled={busy} data-testid="qr-pdf-download-btn">
            {busy ? 'Generating…' : 'Download PDF'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
