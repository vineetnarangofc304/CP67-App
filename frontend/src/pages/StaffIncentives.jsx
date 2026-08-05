import React, { useEffect, useState } from 'react';
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
  const { token, API_URL } = useAuth();
  const [tab, setTab] = useState('staff');
  const [staffList, setStaffList] = useState([]);
  const [config, setConfig] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [leaderboard, setLeaderboard] = useState([]);
  const [redemptions, setRedemptions] = useState([]);
  const [showQR, setShowQR] = useState(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: '', phone: '', brand_name: '', store_location: '' });
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);

  const api = (path, opts = {}) => fetch(`${API_URL}${path}`, {
    ...opts,
    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json', ...(opts.headers || {}) },
  });

  const loadAll = async () => {
    try {
      const [s, c, m, l, r] = await Promise.all([
        api('/admin/staff').then(x => x.json()),
        api('/admin/staff/config/current').then(x => x.json()),
        api('/admin/staff/metrics/overview').then(x => x.json()),
        api('/admin/staff/leaderboard?period=monthly').then(x => x.json()),
        api('/admin/staff/redemptions').then(x => x.json()),
      ]);
      setStaffList(s.staff || []);
      setConfig(c.config || null);
      setMetrics(m);
      setLeaderboard(l.leaderboard || []);
      setRedemptions(r.redemptions || []);
    } catch (e) {
      toast.error('Failed to load staff data');
    }
  };

  useEffect(() => { loadAll(); /* eslint-disable-next-line */ }, []);

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
      setForm({ name: '', phone: '', brand_name: '', store_location: '' });
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
      const data = await r.json();
      if (!r.ok) { toast.error(data.detail || 'Import failed'); return; }
      setImportResult(data);
      if (dryRun) {
        toast.info(`Dry run: ${data.summary.imported} rows will be imported, ${data.summary.invalid} invalid, ${data.summary.skipped_existing} already exist.`);
      } else {
        toast.success(`Imported ${data.summary.imported} staff across ${data.summary.brands_imported} brands.`);
        loadAll();
      }
    } catch (e) {
      toast.error('Import failed: ' + e.message);
    } finally {
      setImporting(false);
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
            <TabsTrigger value="leaderboard" data-testid="tab-leaderboard"><Trophy size={16} className="mr-1" /> Leaderboard</TabsTrigger>
            <TabsTrigger value="redemptions" data-testid="tab-redemptions"><Wallet size={16} className="mr-1" /> Redemptions</TabsTrigger>
            <TabsTrigger value="config" data-testid="tab-config"><Settings size={16} className="mr-1" /> Slabs</TabsTrigger>
          </TabsList>

          {/* STAFF LIST */}
          <TabsContent value="staff">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>Retail Staff ({staffList.length})</CardTitle>
                <div className="flex gap-2 items-center">
                  <QRCardsPDFButton token={token} API_URL={API_URL} brands={[...new Set(staffList.map(s => s.brand_name).filter(Boolean))].sort()} />
                  <label className="cursor-pointer" data-testid="bulk-import-label">
                    <input
                      type="file"
                      accept=".csv,text/csv"
                      className="hidden"
                      data-testid="bulk-import-input"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (!f) return;
                        if (window.confirm(`Import staff from "${f.name}"?\n\nClick OK to run a dry-run first (preview only, nothing saved). Cancel to do a live import.`)) {
                          doBulkImport(f, true);
                        } else {
                          doBulkImport(f, false);
                        }
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
                        <div><Label>Brand Name *</Label><Input data-testid="staff-form-brand" value={form.brand_name} onChange={e => setForm({ ...form, brand_name: e.target.value })} /></div>
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
                {importResult && (
                  <div className="mb-4 p-3 rounded-lg bg-amber-50 border border-amber-200 text-sm" data-testid="import-result-banner">
                    <div className="font-medium mb-1">
                      {importResult.dry_run ? 'Dry-run result:' : 'Last import result:'}
                      &nbsp;{importResult.summary.imported} imported · {importResult.summary.skipped_existing} skipped (already exist) · {importResult.summary.invalid} invalid
                    </div>
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
                    <button className="ml-2 text-xs text-slate-500 underline" onClick={() => setImportResult(null)}>dismiss</button>
                  </div>
                )}
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-left border-b">
                      <tr><th className="py-2 pr-4">Code</th><th className="pr-4">Name</th><th className="pr-4">Brand</th><th className="pr-4">Phone</th><th className="pr-4">Status</th><th>Actions</th></tr>
                    </thead>
                    <tbody data-testid="staff-list-tbody">
                      {staffList.map(s => (
                        <tr key={s.id} className="border-b hover:bg-slate-50">
                          <td className="py-2 pr-4 font-mono text-xs">{s.staff_code}</td>
                          <td className="pr-4 font-medium">{s.name}</td>
                          <td className="pr-4">{s.brand_name}</td>
                          <td className="pr-4">{s.phone}</td>
                          <td className="pr-4">
                            <span className={s.is_active ? 'text-emerald-600' : 'text-slate-400'}>{s.is_active ? 'Active' : 'Inactive'}</span>
                          </td>
                          <td className="flex gap-2 py-2">
                            <Button size="sm" variant="outline" onClick={() => openQR(s.id)} data-testid={`staff-qr-btn-${s.id}`}><QrCode size={14} /></Button>
                            <Button size="sm" variant="ghost" onClick={() => toggleActive(s)} data-testid={`staff-toggle-btn-${s.id}`}>{s.is_active ? 'Deactivate' : 'Activate'}</Button>
                          </td>
                        </tr>
                      ))}
                      {staffList.length === 0 && (
                        <tr><td colSpan={6} className="py-8 text-center text-slate-400">No staff onboarded yet.</td></tr>
                      )}
                    </tbody>
                  </table>
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

          {/* CONFIG */}
          <TabsContent value="config">
            {config && (
              <Card>
                <CardHeader><CardTitle>Incentive Slabs</CardTitle></CardHeader>
                <CardContent className="space-y-6">
                  <div>
                    <div className="font-medium mb-2 flex items-center gap-2"><Award size={16} /> Registration Slabs</div>
                    {config.registration_slabs.map((s, i) => (
                      <div key={i} className="grid grid-cols-3 gap-2 mb-2 items-center">
                        <Input type="number" value={s.min} onChange={e => updateSlab('registration_slabs', i, 'min', e.target.value)} placeholder="Min" />
                        <Input type="number" value={s.max} onChange={e => updateSlab('registration_slabs', i, 'max', e.target.value)} placeholder="Max" />
                        <div className="flex items-center gap-2">₹<Input type="number" value={s.amount} onChange={e => updateSlab('registration_slabs', i, 'amount', e.target.value)} placeholder="Amount" /></div>
                      </div>
                    ))}
                  </div>
                  <div>
                    <div className="font-medium mb-2 flex items-center gap-2"><Award size={16} /> Bill Upload Slabs</div>
                    {config.bill_upload_slabs.map((s, i) => (
                      <div key={i} className="grid grid-cols-3 gap-2 mb-2 items-center">
                        <Input type="number" value={s.min} onChange={e => updateSlab('bill_upload_slabs', i, 'min', e.target.value)} placeholder="Min" />
                        <Input type="number" value={s.max} onChange={e => updateSlab('bill_upload_slabs', i, 'max', e.target.value)} placeholder="Max" />
                        <div className="flex items-center gap-2">₹<Input type="number" value={s.amount} onChange={e => updateSlab('bill_upload_slabs', i, 'amount', e.target.value)} placeholder="Amount" /></div>
                      </div>
                    ))}
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
      </div>
    </DashboardLayout>
  );
}

// Sub-component: PDF QR cards download button + brand filter
function QRCardsPDFButton({ token, API_URL, brands }) {
  const [busy, setBusy] = useState(false);
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
