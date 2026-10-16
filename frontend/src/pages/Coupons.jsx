import React, { useEffect, useMemo, useState } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import { useAuth } from '../App';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { toast } from 'sonner';
import { Ticket, Upload, FileText, RefreshCw } from 'lucide-react';

// Point 26: Registration Coupon Inventory
// Admin uploads coupon codes tied to a registration source (RWA / OFFICE / etc.).
// When new customers register through that source's QR, the next available coupon
// is atomically issued to them and delivered on WhatsApp.

const SOURCE_OPTIONS = [
  { code: 'SRC_RWA', label: 'RWA (Resident Welfare)' },
  { code: 'SRC_OFFICE', label: 'Offices' },
  // Point 54: allow optional coupon inventory per volunteer QR too
  { code: 'SRC_VOLUNTEER_1', label: 'Volunteer 1' },
  { code: 'SRC_VOLUNTEER_2', label: 'Volunteer 2' },
];

export default function Coupons() {
  const { token, API_URL, logout } = useAuth();
  const [tab, setTab] = useState('inventory');
  const [source, setSource] = useState('SRC_RWA');
  const [inventory, setInventory] = useState({ inventory: [], totals: {} });
  const [issued, setIssued] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [pendingUploadFile, setPendingUploadFile] = useState(null);
  // Point 28: All-coupons list view + search/filter so freshly uploaded codes are actually findable
  const [allCoupons, setAllCoupons] = useState([]);
  const [couponSearch, setCouponSearch] = useState('');
  const [couponBrandFilter, setCouponBrandFilter] = useState('');
  const [couponStatusFilter, setCouponStatusFilter] = useState('');
  const [couponPageSize, setCouponPageSize] = useState(100);

  const api = (path, opts = {}) => fetch(`${API_URL}${path}`, {
    ...opts,
    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json', ...(opts.headers || {}) },
  });

  const handle401 = (status) => {
    if (status === 401) {
      toast.error('Session expired — please sign in again');
      logout();
      setTimeout(() => { window.location.href = '/'; }, 800);
      return true;
    }
    return false;
  };

  const loadAll = async () => {
    try {
      const invR = await api(`/admin/coupons/inventory?source_code=${source}`);
      if (handle401(invR.status)) return;
      const inv = await invR.json();
      setInventory(inv);
      const isR = await api(`/admin/coupons/issued?source_code=${source}`);
      if (handle401(isR.status)) return;
      const is = await isR.json();
      setIssued(is.issued || []);
      // Point 28: also load the flat list so admin can see individual codes
      const listR = await api(`/admin/coupons/list?source_code=${source}&limit=5000`);
      if (handle401(listR.status)) return;
      const list = await listR.json();
      setAllCoupons(list.coupons || []);
    } catch (e) {
      toast.error('Failed to load coupon data');
    }
  };

  useEffect(() => { loadAll(); /* eslint-disable-next-line */ }, [source]);

  const downloadTemplate = async () => {
    try {
      const r = await fetch(`${API_URL}/admin/coupons/template.csv`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (handle401(r.status)) return;
      if (!r.ok) { toast.error('Template download failed'); return; }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'coupon-upload-template.csv';
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success('Template downloaded');
    } catch (e) {
      toast.error('Download failed: ' + e.message);
    }
  };

  const uploadCsv = async (file, dryRun) => {
    if (!file) return;
    setUploading(true);
    setUploadResult(null);
    const fd = new FormData();
    fd.append('file', file);
    fd.append('source_code', source);
    fd.append('dry_run', dryRun ? 'true' : 'false');
    try {
      const r = await fetch(`${API_URL}/admin/coupons/bulk-upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      if (handle401(r.status)) return;
      const data = await r.json();
      if (!r.ok) { toast.error(data.detail || 'Upload failed'); return; }
      setUploadResult(data);
      if (dryRun) {
        setPendingUploadFile(file);
        toast.info(`Preview only: ${data.summary.imported} coupon(s) will be imported. Click "Confirm & Import" to save.`);
      } else {
        setPendingUploadFile(null);
        toast.success(`Imported ${data.summary.imported} coupon(s) for ${data.source_code}.`);
        loadAll();
      }
    } catch (e) {
      toast.error('Upload failed: ' + e.message);
    } finally { setUploading(false); }
  };

  // Group inventory rows into a table per brand with columns for each status.
  const inventoryByBrand = useMemo(() => {
    const byBrand = {};
    (inventory.inventory || []).forEach(r => {
      const key = r.brand_name || '—';
      if (!byBrand[key]) byBrand[key] = { brand: key, available: 0, issued: 0, expired: 0, void: 0, total_value: 0 };
      byBrand[key][r.status] = (byBrand[key][r.status] || 0) + r.count;
      byBrand[key].total_value += r.total_value || 0;
    });
    return Object.values(byBrand).sort((a, b) => a.brand.localeCompare(b.brand));
  }, [inventory]);

  const totals = inventory.totals || {};

  // Point 28: derive filtered flat coupons list
  const filteredCoupons = useMemo(() => {
    const q = couponSearch.trim().toLowerCase();
    return allCoupons.filter(c => {
      if (couponBrandFilter && c.brand_name !== couponBrandFilter) return false;
      if (couponStatusFilter && c.status !== couponStatusFilter) return false;
      if (!q) return true;
      const hay = [c.code, c.brand_name, c.issued_to_phone, c.source_code]
        .filter(Boolean).join(' ').toLowerCase();
      return hay.includes(q);
    });
  }, [allCoupons, couponSearch, couponBrandFilter, couponStatusFilter]);

  const couponBrands = useMemo(
    () => [...new Set(allCoupons.map(c => c.brand_name).filter(Boolean))].sort(),
    [allCoupons],
  );

  return (
    <DashboardLayout title="Registration Coupons">
      <div className="space-y-6" data-testid="coupons-page">
        {/* KPIs */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card><CardContent className="p-4"><div className="text-xs text-slate-500 uppercase">Available</div><div className="text-3xl font-bold mt-1 text-emerald-600">{totals.available || 0}</div></CardContent></Card>
          <Card><CardContent className="p-4"><div className="text-xs text-slate-500 uppercase">Issued</div><div className="text-3xl font-bold mt-1">{totals.issued || 0}</div></CardContent></Card>
          <Card><CardContent className="p-4"><div className="text-xs text-slate-500 uppercase">Expired</div><div className="text-3xl font-bold mt-1 text-slate-400">{totals.expired || 0}</div></CardContent></Card>
          <Card><CardContent className="p-4"><div className="text-xs text-slate-500 uppercase">Source</div>
            <select
              value={source}
              onChange={e => setSource(e.target.value)}
              className="mt-1 w-full h-10 px-3 rounded-md border border-slate-200 bg-white text-sm"
              data-testid="coupon-source-select"
            >
              {SOURCE_OPTIONS.map(o => <option key={o.code} value={o.code}>{o.label}</option>)}
            </select>
          </CardContent></Card>
        </div>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="inventory" data-testid="tab-inventory"><Ticket size={16} className="mr-1" /> Inventory</TabsTrigger>
            <TabsTrigger value="all" data-testid="tab-all"><Ticket size={16} className="mr-1" /> All Coupons</TabsTrigger>
            <TabsTrigger value="issued" data-testid="tab-issued"><Ticket size={16} className="mr-1" /> Issued</TabsTrigger>
          </TabsList>

          <TabsContent value="inventory">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>Inventory · {source}</CardTitle>
                <div className="flex gap-2 items-center">
                  <Button variant="outline" size="sm" onClick={downloadTemplate} data-testid="coupon-template-btn">
                    <FileText size={14} className="mr-1" /> Template
                  </Button>
                  <label className="cursor-pointer" data-testid="coupon-upload-label">
                    <input
                      type="file"
                      accept=".csv,text/csv"
                      className="hidden"
                      data-testid="coupon-upload-input"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (!f) return;
                        // Auto-run dry-run first — user must explicitly click "Confirm & Import" in the banner below to commit.
                        uploadCsv(f, true);
                        e.target.value = '';
                      }}
                    />
                    <span className="inline-flex items-center gap-1 px-3 py-1.5 text-sm rounded-md border hover:bg-slate-50">
                      <Upload size={14} /> {uploading ? 'Uploading…' : 'Upload Coupons CSV'}
                    </span>
                  </label>
                  <Button variant="outline" size="sm" onClick={loadAll} data-testid="coupon-refresh-btn"><RefreshCw size={16} /></Button>
                </div>
              </CardHeader>
              <CardContent>
                {uploadResult && (
                  <div className="mb-4 p-3 rounded-lg bg-amber-50 border border-amber-200 text-sm" data-testid="coupon-upload-result-banner">
                    <div className="font-medium mb-1">
                      {uploadResult.dry_run ? 'Preview (not saved yet):' : 'Last upload:'}
                      &nbsp;{uploadResult.summary.imported} {uploadResult.dry_run ? 'will be imported' : 'imported'} · {uploadResult.summary.skipped_duplicates} duplicates · {uploadResult.summary.invalid} invalid
                    </div>
                    {uploadResult.dry_run && pendingUploadFile && (
                      <div className="mt-2 mb-2 flex flex-wrap gap-2 items-center p-2 rounded-md bg-white border border-amber-300" data-testid="confirm-coupon-cta">
                        <span className="text-xs text-slate-600">Nothing has been saved yet. Review the preview above and click Confirm to save {uploadResult.summary.imported} coupon(s).</span>
                        <Button
                          size="sm"
                          onClick={() => { const f = pendingUploadFile; setPendingUploadFile(null); uploadCsv(f, false); }}
                          disabled={uploading || uploadResult.summary.imported === 0}
                          data-testid="confirm-coupon-btn"
                        >
                          {uploading ? 'Saving…' : `Confirm & Import ${uploadResult.summary.imported} coupon(s)`}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => { setPendingUploadFile(null); setUploadResult(null); }}
                          data-testid="cancel-coupon-btn"
                        >
                          Cancel
                        </Button>
                      </div>
                    )}
                    {!uploadResult.dry_run && uploadResult.summary.imported > 0 && (
                      <div className="text-xs mb-1 text-emerald-700" data-testid="coupon-upload-view-hint">
                        Newly uploaded coupons are in the &ldquo;All Coupons&rdquo; tab.
                        <button
                          className="ml-2 underline"
                          onClick={() => { setTab('all'); setCouponStatusFilter('available'); setCouponSearch(''); setCouponBrandFilter(''); }}
                          data-testid="view-uploaded-coupons-btn"
                        >
                          Show me the codes
                        </button>
                      </div>
                    )}
                    {uploadResult.invalid_preview?.length > 0 && (
                      <details>
                        <summary className="cursor-pointer text-amber-700">Show {uploadResult.invalid_preview.length} invalid rows</summary>
                        <ul className="mt-2 text-xs text-slate-600 pl-4 list-disc">
                          {uploadResult.invalid_preview.map((r, i) => (
                            <li key={i}>Row {r.row}: {r.reason} — {r.brand || ''} {r.code ? `[${r.code}]` : ''} {r.raw_expiry ? `expiry="${r.raw_expiry}"` : ''}</li>
                          ))}
                        </ul>
                      </details>
                    )}
                    <button className="ml-2 text-xs text-slate-500 underline" onClick={() => { setUploadResult(null); setPendingUploadFile(null); }}>dismiss</button>
                  </div>
                )}
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-left border-b">
                      <tr>
                        <th className="py-2 pr-4">Brand</th>
                        <th className="pr-4">Available</th>
                        <th className="pr-4">Issued</th>
                        <th className="pr-4">Expired</th>
                        <th className="pr-4">Face Value (₹)</th>
                      </tr>
                    </thead>
                    <tbody data-testid="coupon-inventory-tbody">
                      {inventoryByBrand.map(r => (
                        <tr key={r.brand} className="border-b hover:bg-slate-50">
                          <td className="py-2 pr-4 font-medium">{r.brand}</td>
                          <td className="pr-4 text-emerald-600 font-bold">{r.available}</td>
                          <td className="pr-4">{r.issued}</td>
                          <td className="pr-4 text-slate-400">{r.expired}</td>
                          <td className="pr-4">₹{Math.round(r.total_value)}</td>
                        </tr>
                      ))}
                      {inventoryByBrand.length === 0 && (
                        <tr><td colSpan={5} className="py-8 text-center text-slate-400">
                          No coupons uploaded yet for {source}. Upload a CSV to get started.
                        </td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
                <div className="mt-4 p-3 rounded-md bg-slate-50 text-xs text-slate-600">
                  <div className="font-medium mb-1">How it works</div>
                  <ol className="list-decimal ml-5 space-y-1">
                    <li>Upload coupon codes tied to a registration source (RWA / Office / etc.).</li>
                    <li>When a NEW customer registers through that source&apos;s QR, the next available coupon is atomically issued and sent on WhatsApp.</li>
                    <li>Once inventory is empty, registrations still succeed but no coupon is issued.</li>
                  </ol>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Point 28: All-coupons flat view with search + brand + status filters */}
          <TabsContent value="all">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>
                  All Coupons · {source} ({filteredCoupons.length}{filteredCoupons.length !== allCoupons.length ? ` of ${allCoupons.length}` : ''})
                </CardTitle>
                <Button variant="outline" size="sm" onClick={loadAll} data-testid="coupon-all-refresh-btn"><RefreshCw size={16} /></Button>
              </CardHeader>
              <CardContent>
                <div className="mb-3 flex flex-wrap items-center gap-2 p-3 rounded-lg bg-slate-50 border" data-testid="coupon-filter-bar">
                  <input
                    type="search"
                    className="h-9 px-3 text-sm rounded-md border border-slate-200 bg-white flex-1 min-w-[200px]"
                    placeholder="Search by code, brand, issued phone…"
                    value={couponSearch}
                    onChange={e => setCouponSearch(e.target.value)}
                    data-testid="coupon-search-input"
                  />
                  <select
                    className="h-9 px-3 text-sm rounded-md border border-slate-200 bg-white"
                    value={couponBrandFilter}
                    onChange={e => setCouponBrandFilter(e.target.value)}
                    data-testid="coupon-brand-filter"
                  >
                    <option value="">All brands ({couponBrands.length})</option>
                    {couponBrands.map(b => (<option key={b} value={b}>{b}</option>))}
                  </select>
                  <select
                    className="h-9 px-3 text-sm rounded-md border border-slate-200 bg-white"
                    value={couponStatusFilter}
                    onChange={e => setCouponStatusFilter(e.target.value)}
                    data-testid="coupon-status-filter"
                  >
                    <option value="">All statuses</option>
                    <option value="available">Available</option>
                    <option value="issued">Issued</option>
                    <option value="expired">Expired</option>
                    <option value="void">Void</option>
                  </select>
                  <select
                    className="h-9 px-3 text-sm rounded-md border border-slate-200 bg-white"
                    value={couponPageSize}
                    onChange={e => setCouponPageSize(Number(e.target.value))}
                    data-testid="coupon-page-size"
                  >
                    <option value={100}>Show 100</option>
                    <option value={500}>Show 500</option>
                    <option value={99999}>Show all</option>
                  </select>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-left border-b">
                      <tr>
                        <th className="py-2 pr-4">Brand</th>
                        <th className="pr-4">Code</th>
                        <th className="pr-4">Value</th>
                        <th className="pr-4">Expiry</th>
                        <th className="pr-4">Status</th>
                        <th className="pr-4">Issued To</th>
                        <th>Uploaded</th>
                      </tr>
                    </thead>
                    <tbody data-testid="coupon-all-tbody">
                      {filteredCoupons.slice(0, couponPageSize).map(c => (
                        <tr key={c.id} className="border-b hover:bg-slate-50">
                          <td className="py-2 pr-4 font-medium">{c.brand_name}</td>
                          <td className="pr-4 font-mono">{c.code}</td>
                          <td className="pr-4">₹{c.value}</td>
                          <td className="pr-4">{c.expiry}</td>
                          <td className="pr-4">
                            <span className={
                              c.status === 'available' ? 'text-emerald-600' :
                              c.status === 'issued' ? 'text-slate-700' :
                              'text-slate-400'
                            }>{c.status}</span>
                          </td>
                          <td className="pr-4 font-mono">{c.issued_to_phone || '—'}</td>
                          <td className="text-xs">{c.created_at?.slice(0, 10)}</td>
                        </tr>
                      ))}
                      {filteredCoupons.length === 0 && allCoupons.length > 0 && (
                        <tr><td colSpan={7} className="py-8 text-center text-slate-400" data-testid="coupon-no-matches">
                          No matches — try clearing search or filters. Total codes for {source}: <span className="font-semibold text-slate-700">{allCoupons.length}</span>.
                        </td></tr>
                      )}
                      {allCoupons.length === 0 && (
                        <tr><td colSpan={7} className="py-8 text-center text-slate-400">No coupons uploaded yet for {source}.</td></tr>
                      )}
                    </tbody>
                  </table>
                  {filteredCoupons.length > couponPageSize && (
                    <div className="p-3 text-xs text-slate-500 text-center border-t bg-slate-50" data-testid="coupon-truncated-hint">
                      Showing {couponPageSize} of {filteredCoupons.length} matches. Increase &ldquo;Show&rdquo; size above to see more.
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="issued">
            <Card>
              <CardHeader><CardTitle>Issued Coupons · {source}</CardTitle></CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-left border-b">
                      <tr>
                        <th className="py-2 pr-4">Brand</th>
                        <th className="pr-4">Code</th>
                        <th className="pr-4">Value</th>
                        <th className="pr-4">Issued To</th>
                        <th className="pr-4">Issued At</th>
                        <th>Expiry</th>
                      </tr>
                    </thead>
                    <tbody data-testid="coupon-issued-tbody">
                      {issued.map(c => (
                        <tr key={c.id} className="border-b hover:bg-slate-50">
                          <td className="py-2 pr-4 font-medium">{c.brand_name}</td>
                          <td className="pr-4 font-mono">{c.code}</td>
                          <td className="pr-4">₹{c.value}</td>
                          <td className="pr-4 font-mono">{c.issued_to_phone}</td>
                          <td className="pr-4 text-xs">{c.issued_at?.slice(0, 16).replace('T', ' ')}</td>
                          <td>{c.expiry}</td>
                        </tr>
                      ))}
                      {issued.length === 0 && (
                        <tr><td colSpan={6} className="py-8 text-center text-slate-400">No coupons issued yet for {source}.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </DashboardLayout>
  );
}
