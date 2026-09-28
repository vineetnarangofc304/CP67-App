import React, { useState, useEffect, useRef } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import { useAuth } from '../App';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '../components/ui/dialog';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '../components/ui/table';
import { toast } from 'sonner';
import { 
  Store, Plus, Edit, Trash2, Search, IndianRupee, TrendingUp, Upload, History,
  FileSpreadsheet, RefreshCw, Image, MapPin, Clock, Star, QrCode, Smartphone, ArrowUpFromLine, ToggleLeft, ToggleRight, Filter
} from 'lucide-react';

const CATEGORIES = ['Fashion', 'Food & Beverage', 'Beauty', 'Electronics', 'Entertainment', 'Sports', 'Kids', 'Accessories', 'Footwear', 'Home & Living', 'Lifestyle', 'Jewellery', 'Grooming', 'Fragrance', 'Department Store', 'Supermarket', 'Cafe', 'General'];
const FLOORS = ['Ground Floor', 'First Floor', 'Second Floor', 'Third Floor', 'Food Court', 'Lower Ground'];

const Brands = () => {
  const { token, API_URL } = useAuth();
  const [brands, setBrands] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterFloor, setFilterFloor] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [showHistoryDialog, setShowHistoryDialog] = useState(false);
  const [showQRDialog, setShowQRDialog] = useState(false);
  const [selectedBrand, setSelectedBrand] = useState(null);
  const [formData, setFormData] = useState({ brand_name: '', atv: '', category: '', aliases: '' });
  const [storeData, setStoreData] = useState({ description: '', floor: '', timing: '11:00 AM - 9:00 PM', unit_no: '', tags: '', is_featured: false, hidden_from_app: false });
  const [uploading, setUploading] = useState(false);
  const [uploadHistory, setUploadHistory] = useState([]);
  const [editTab, setEditTab] = useState('basic');
  const [uploadingImage, setUploadingImage] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const fileInputRef = useRef(null);
  const categoryInputRef = useRef(null);
  const logoInputRef = useRef(null);
  const coverInputRef = useRef(null);

  useEffect(() => { fetchBrands(); }, []);

  const fetchBrands = async () => {
    try {
      const res = await fetch(`${API_URL}/admin/brands`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) { const d = await res.json(); setBrands(d.brands); }
    } catch { toast.error('Failed to fetch brands'); }
    setLoading(false);
  };

  const handleAdd = async () => {
    if (!formData.brand_name.trim()) { toast.error('Brand name is required'); return; }
    try {
      const res = await fetch(`${API_URL}/admin/brands`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ brand_name: formData.brand_name.trim(), atv: parseFloat(formData.atv) || 0, category: formData.category.trim() || null, aliases: formData.aliases ? formData.aliases.split(',').map(s => s.trim()).filter(Boolean) : [] })
      });
      if (res.ok) { toast.success('Brand added'); setShowAddDialog(false); setFormData({ brand_name: '', atv: '', category: '', aliases: '' }); fetchBrands(); }
      else { const e = await res.json(); toast.error(e.detail || 'Failed'); }
    } catch { toast.error('Failed'); }
  };

  const handleEdit = async () => {
    if (!selectedBrand) return;
    try {
      const body = {
        brand_name: formData.brand_name.trim(),
        atv: parseFloat(formData.atv) || 0,
        category: formData.category.trim() || null,
        aliases: formData.aliases ? formData.aliases.split(',').map(s => s.trim()).filter(Boolean) : [],
        description: storeData.description,
        floor: storeData.floor,
        timing: storeData.timing,
        unit_no: storeData.unit_no,
        tags: storeData.tags ? storeData.tags.split(',').map(t => t.trim()).filter(Boolean) : [],
        is_featured: storeData.is_featured,
        hidden_from_app: storeData.hidden_from_app,
      };
      const res = await fetch(`${API_URL}/admin/brands/${selectedBrand.id}`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      if (res.ok) { toast.success('Brand updated & synced to app'); setShowEditDialog(false); fetchBrands(); }
      else { const e = await res.json(); toast.error(e.detail || 'Failed'); }
    } catch { toast.error('Failed'); }
  };

  const handleDelete = async (brand) => {
    if (!window.confirm(`Delete "${brand.brand_name}"?`)) return;
    try {
      const res = await fetch(`${API_URL}/admin/brands/${brand.id}`, { method: 'DELETE', headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) { toast.success('Deleted'); fetchBrands(); }
    } catch { toast.error('Failed'); }
  };

  // Point 21 (Sep 2026): inline-editable category + aliases directly on the brands table
  const [inlineSavingId, setInlineSavingId] = useState(null);
  const [aliasDrafts, setAliasDrafts] = useState({}); // { [brandId]: "a, b, c" }

  const saveInline = async (brand, patch) => {
    setInlineSavingId(brand.id);
    try {
      const res = await fetch(`${API_URL}/admin/brands/${brand.id}`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      });
      if (res.ok) { toast.success('Saved'); fetchBrands(); }
      else { const e = await res.json().catch(() => ({})); toast.error(e.detail || 'Save failed'); }
    } catch { toast.error('Save failed'); }
    setInlineSavingId(null);
  };

  const handleInlineCategory = (brand, next) => {
    if ((next || '') === (brand.category || '')) return;
    saveInline(brand, { category: next || null });
  };

  const handleInlineAliasesBlur = (brand) => {
    const draft = aliasDrafts[brand.id];
    if (draft === undefined) return;
    const nextArr = draft.split(',').map(s => s.trim()).filter(Boolean);
    const curArr = brand.aliases || [];
    if (nextArr.length === curArr.length && nextArr.every((v, i) => v === curArr[i])) {
      setAliasDrafts(prev => { const n = { ...prev }; delete n[brand.id]; return n; });
      return;
    }
    saveInline(brand, { aliases: nextArr });
    setAliasDrafts(prev => { const n = { ...prev }; delete n[brand.id]; return n; });
  };

  const openEditDialog = (brand) => {
    setSelectedBrand(brand);
    setFormData({ brand_name: brand.brand_name, atv: (brand.atv || '').toString(), category: brand.category || '', aliases: (brand.aliases || []).join(', ') });
    setStoreData({
      description: brand.description || '',
      floor: brand.floor || '',
      timing: brand.timing || '11:00 AM - 9:00 PM',
      unit_no: brand.unit_no || '',
      tags: (brand.tags || []).join(', '),
      is_featured: brand.is_featured || false,
      hidden_from_app: brand.hidden_from_app || false,
    });
    setEditTab('basic');
    setShowEditDialog(true);
  };

  const handleImageUpload = async (brandId, imageType, file) => {
    setUploadingImage(imageType);
    const fd = new FormData();
    fd.append('file', file);
    fd.append('image_type', imageType);
    try {
      const res = await fetch(`${API_URL}/admin/brands/${brandId}/upload-image`, {
        method: 'POST', headers: { 'Authorization': `Bearer ${token}` }, body: fd
      });
      if (res.ok) {
        const d = await res.json();
        toast.success(`${imageType === 'logo' ? 'Logo' : 'Cover'} uploaded!`);
        setSelectedBrand(prev => ({ ...prev, [d.field]: d.image_url }));
        fetchBrands();
      } else { toast.error('Upload failed'); }
    } catch { toast.error('Upload failed'); }
    setUploadingImage(null);
  };

  const toggleEligibility = async (brand) => {
    const newVal = brand.is_eligible === false ? true : false;
    try {
      const res = await fetch(`${API_URL}/admin/brands/${brand.id}`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ brand_name: brand.brand_name, is_eligible: newVal })
      });
      if (res.ok) {
        toast.success(`${brand.brand_name} ${newVal ? 'enabled' : 'disabled'} for redemption`);
        fetchBrands();
      }
    } catch { toast.error('Failed to update eligibility'); }
  };

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    setUploading(true);
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await fetch(`${API_URL}/admin/brands/upload-excel`, {
        method: 'POST', headers: { 'Authorization': `Bearer ${token}` }, body: fd
      });
      const d = await res.json();
      if (res.ok && d.success) { toast.success(`Imported ${d.imported} new, updated ${d.updated} existing`); fetchBrands(); }
      else { toast.error(d.message || d.detail || 'Upload failed'); }
    } catch { toast.error('Failed'); }
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleCategoryUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    setUploading(true);
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await fetch(`${API_URL}/admin/brands/upload-categories-excel`, {
        method: 'POST', headers: { 'Authorization': `Bearer ${token}` }, body: fd
      });
      const d = await res.json();
      if (res.ok && d.success) { toast.success(`Imported ${d.imported} new brands, updated categories on ${d.updated} existing`); fetchBrands(); }
      else { toast.error(d.message || d.detail || 'Upload failed'); }
    } catch { toast.error('Failed'); }
    setUploading(false);
    if (categoryInputRef.current) categoryInputRef.current.value = '';
  };

  const syncToStores = async () => {
    setSyncing(true);
    try {
      const res = await fetch(`${API_URL}/admin/brands/sync-to-stores`, {
        method: 'POST', headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) { const d = await res.json(); toast.success(`Synced ${d.synced} brands to consumer app`); }
    } catch { toast.error('Sync failed'); }
    setSyncing(false);
  };

  const fetchUploadHistory = async () => {
    try {
      const res = await fetch(`${API_URL}/admin/brands/upload-history`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) { const d = await res.json(); setUploadHistory(d.history || []); }
    } catch {}
  };

  const filteredBrands = brands.filter(b => {
    if (searchQuery && !b.brand_name.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    if (filterFloor && b.floor !== filterFloor) return false;
    if (filterCategory && b.category !== filterCategory) return false;
    return true;
  });
  const totalAtv = brands.reduce((s, b) => s + (b.atv || 0), 0);
  const avgAtv = brands.length > 0 ? totalAtv / brands.length : 0;
  const appReadyCount = brands.filter(b => b.description).length;
  const eligibleCount = brands.filter(b => b.is_eligible !== false).length;
  const uniqueFloors = [...new Set(brands.map(b => b.floor).filter(Boolean))].sort();
  const uniqueCategories = [...new Set(brands.map(b => b.category).filter(Boolean))].sort();

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-900" data-testid="brands-title">Brand & Store Management</h1>
            <p className="text-slate-500">Manage brands, ATV, store details, and images for the consumer app</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <input type="file" ref={fileInputRef} accept=".xlsx,.xls,.csv" onChange={handleFileUpload} className="hidden" />
            <input type="file" ref={categoryInputRef} accept=".xlsx,.xls,.csv" onChange={handleCategoryUpload} className="hidden" />
            <Button variant="outline" onClick={() => fileInputRef.current?.click()} disabled={uploading} data-testid="upload-excel-btn">
              {uploading ? <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Uploading...</> : <><Upload className="h-4 w-4 mr-2" />Upload ATV Sheet</>}
            </Button>
            <Button variant="outline" onClick={() => categoryInputRef.current?.click()} disabled={uploading} data-testid="upload-categories-btn">
              <Upload className="h-4 w-4 mr-2" />Upload Category Sheet
            </Button>
            <Button variant="outline" onClick={() => { fetchUploadHistory(); setShowHistoryDialog(true); }}>
              <History className="h-4 w-4 mr-2" />History
            </Button>
            <Button variant="outline" onClick={syncToStores} disabled={syncing} data-testid="sync-stores-btn">
              {syncing ? <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Syncing...</> : <><Smartphone className="h-4 w-4 mr-2" />Sync to App</>}
            </Button>
            <Button variant="outline" onClick={() => setShowQRDialog(true)} data-testid="app-qr-btn">
              <QrCode className="h-4 w-4 mr-2" />App QR
            </Button>
            <Button onClick={() => setShowAddDialog(true)} className="bg-blue-600 hover:bg-blue-700" data-testid="add-brand-btn">
              <Plus className="h-4 w-4 mr-2" />Add Brand
            </Button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card className="border-slate-200 shadow-none">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center"><Store className="h-5 w-5 text-blue-600" /></div>
                <div><p className="text-2xl font-bold">{brands.length}</p><p className="text-sm text-slate-500">Total Brands</p></div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-slate-200 shadow-none">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center"><IndianRupee className="h-5 w-5 text-green-600" /></div>
                <div><p className="text-2xl font-bold">₹{avgAtv.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</p><p className="text-sm text-slate-500">Average ATV</p></div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-slate-200 shadow-none">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center"><Smartphone className="h-5 w-5 text-purple-600" /></div>
                <div><p className="text-2xl font-bold">{appReadyCount}</p><p className="text-sm text-slate-500">App-Ready Stores</p></div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-slate-200 shadow-none">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-amber-100 rounded-lg flex items-center justify-center"><TrendingUp className="h-5 w-5 text-amber-600" /></div>
                <div><p className="text-2xl font-bold">₹{brands.length > 0 ? Math.max(...brands.map(b => b.atv || 0)).toLocaleString('en-IN', { maximumFractionDigits: 0 }) : 0}</p><p className="text-sm text-slate-500">Highest ATV</p></div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Table */}
        <Card className="border-slate-200 shadow-none">
          <CardHeader className="pb-4">
            <div className="flex flex-col gap-4">
              <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <CardTitle className="text-lg">All Brands ({filteredBrands.length})</CardTitle>
                <div className="relative w-full sm:w-64">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                  <Input placeholder="Search brands..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="pl-9" data-testid="brand-search" />
                </div>
              </div>
              <div className="flex flex-wrap gap-2 items-center">
                <Filter className="h-4 w-4 text-slate-400" />
                <select className="h-9 px-3 border rounded-md text-sm bg-white" value={filterFloor} onChange={e => setFilterFloor(e.target.value)} data-testid="admin-floor-filter">
                  <option value="">All Floors</option>
                  {uniqueFloors.map(f => <option key={f} value={f}>{f}</option>)}
                </select>
                <select className="h-9 px-3 border rounded-md text-sm bg-white" value={filterCategory} onChange={e => setFilterCategory(e.target.value)} data-testid="admin-category-filter">
                  <option value="">All Categories</option>
                  {uniqueCategories.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
                {(filterFloor || filterCategory) && (
                  <Button variant="ghost" size="sm" onClick={() => { setFilterFloor(''); setFilterCategory(''); }} className="text-red-500 h-9">Clear Filters</Button>
                )}
                <span className="text-xs text-slate-400 ml-auto">{eligibleCount} eligible for redemption</span>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="text-center py-8 text-slate-500">Loading...</div>
            ) : (
              <div className="rounded-md border overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-12"></TableHead>
                      <TableHead>Brand Name</TableHead>
                      <TableHead className="text-right">ATV (₹)</TableHead>
                      <TableHead>Category</TableHead>
                      <TableHead>Aliases</TableHead>
                      <TableHead>Floor</TableHead>
                      <TableHead>Eligible</TableHead>
                      <TableHead>App</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredBrands.length === 0 ? (
                      <TableRow><TableCell colSpan={10} className="text-center py-8 text-slate-500">{searchQuery ? 'No brands match' : 'No brands'}</TableCell></TableRow>
                    ) : filteredBrands.map((brand) => (
                      <TableRow key={brand.id} data-testid={`brand-row-${brand.id}`}>
                        <TableCell>
                          {brand.logo_url ? (
                            <img src={brand.logo_url} alt="" className="w-8 h-8 rounded-md object-cover" />
                          ) : (
                            <div className="w-8 h-8 rounded-md bg-slate-100 flex items-center justify-center text-xs font-bold text-slate-400">
                              {brand.brand_name[0]}
                            </div>
                          )}
                        </TableCell>
                        <TableCell className="font-medium">{brand.brand_name}</TableCell>
                        <TableCell className="text-right font-mono">{brand.atv ? `₹${brand.atv.toLocaleString('en-IN')}` : '-'}</TableCell>
                        <TableCell>
                          {/* Point 21: inline-editable category dropdown */}
                          <select
                            value={brand.category || ''}
                            disabled={inlineSavingId === brand.id}
                            onChange={(e) => handleInlineCategory(brand, e.target.value)}
                            className="h-8 px-2 rounded border border-slate-200 bg-white text-sm w-full min-w-[130px] disabled:opacity-60"
                            data-testid={`inline-category-${brand.id}`}
                          >
                            <option value="">— pick —</option>
                            {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                            {brand.category && !CATEGORIES.includes(brand.category) && (
                              <option value={brand.category}>{brand.category}</option>
                            )}
                          </select>
                        </TableCell>
                        <TableCell className="min-w-[220px]">
                          {/* Point 21: inline-editable aliases (comma-separated, save on blur) */}
                          <input
                            type="text"
                            disabled={inlineSavingId === brand.id}
                            value={aliasDrafts[brand.id] !== undefined ? aliasDrafts[brand.id] : (brand.aliases || []).join(', ')}
                            placeholder="e.g. Dominos, Dominos Pizza"
                            onChange={(e) => setAliasDrafts(prev => ({ ...prev, [brand.id]: e.target.value }))}
                            onBlur={() => handleInlineAliasesBlur(brand)}
                            className="h-8 px-2 rounded border border-slate-200 bg-white text-xs w-full disabled:opacity-60"
                            data-testid={`inline-aliases-${brand.id}`}
                          />
                        </TableCell>
                        <TableCell className="text-sm text-slate-500">{brand.floor || '-'}</TableCell>
                        <TableCell>
                          <button onClick={() => toggleEligibility(brand)} className="flex items-center" data-testid={`eligibility-${brand.id}`}>
                            {brand.is_eligible !== false ? (
                              <ToggleRight className="h-6 w-6 text-emerald-500" />
                            ) : (
                              <ToggleLeft className="h-6 w-6 text-red-400" />
                            )}
                          </button>
                        </TableCell>
                        <TableCell>
                          {brand.description ? (
                            <Badge className="bg-green-100 text-green-700 hover:bg-green-100">Live</Badge>
                          ) : (
                            <Badge variant="outline" className="text-slate-400">Not Set</Badge>
                          )}
                        </TableCell>
                        <TableCell>
                          <div className="flex gap-1 items-center">
                            <Badge variant={brand.is_active !== false ? 'default' : 'secondary'}>{brand.is_active !== false ? 'Active' : 'Inactive'}</Badge>
                            {brand.is_featured && <Badge className="bg-amber-100 text-amber-800 hover:bg-amber-100" data-testid={`brand-featured-badge-${brand.id}`}><Star className="h-3 w-3 mr-0.5" />Featured</Badge>}
                            {brand.hidden_from_app && <Badge variant="outline" className="text-slate-500 border-slate-300" data-testid={`brand-hidden-badge-${brand.id}`}>Hidden</Badge>}
                          </div>
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1">
                            <Button variant="ghost" size="sm" onClick={() => openEditDialog(brand)} data-testid={`edit-brand-${brand.id}`}>
                              <Edit className="h-4 w-4" />
                            </Button>
                            <Button variant="ghost" size="sm" className="text-red-600 hover:text-red-700" onClick={() => handleDelete(brand)}>
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Add Brand Dialog */}
      <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add New Brand</DialogTitle>
            <DialogDescription>Add a new brand with ATV. You can add store details later.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2"><Label>Brand Name *</Label><Input value={formData.brand_name} onChange={e => setFormData({...formData, brand_name: e.target.value})} placeholder="Enter brand name" /></div>
            <div className="space-y-2"><Label>ATV (₹)</Label><Input type="number" value={formData.atv} onChange={e => setFormData({...formData, atv: e.target.value})} placeholder="0" /></div>
            <div className="space-y-2"><Label>Category</Label>
              <select className="w-full h-10 px-3 border rounded-md text-sm" value={formData.category} onChange={e => setFormData({...formData, category: e.target.value})}>
                <option value="">Select category</option>
                {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="space-y-2">
              <Label>Aliases <span className="text-xs text-slate-400 font-normal">(comma-separated, matches bill OCR variants)</span></Label>
              <Input value={formData.aliases} onChange={e => setFormData({...formData, aliases: e.target.value})} placeholder="e.g. Dominos, Dominos Pizza, Jubilant Foodworks" data-testid="add-brand-aliases" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddDialog(false)}>Cancel</Button>
            <Button onClick={handleAdd} data-testid="save-brand-btn">Add Brand</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Brand Dialog - Full Store Management */}
      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Store className="h-5 w-5" />
              {selectedBrand?.brand_name}
            </DialogTitle>
            <DialogDescription>Edit brand details, store info, and images for the consumer app</DialogDescription>
          </DialogHeader>

          {/* Tabs */}
          <div className="flex gap-1 bg-slate-100 p-1 rounded-lg">
            {[
              { key: 'basic', label: 'Basic Info', icon: Store },
              { key: 'store', label: 'Store Details', icon: MapPin },
              { key: 'images', label: 'Images', icon: Image },
            ].map(t => (
              <button key={t.key} onClick={() => setEditTab(t.key)}
                className={`flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-md text-sm font-medium transition-colors ${editTab === t.key ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500 hover:text-slate-700'}`}>
                <t.icon className="h-4 w-4" />{t.label}
              </button>
            ))}
          </div>

          <div className="space-y-4 py-2">
            {editTab === 'basic' && (
              <>
                <div className="space-y-2"><Label>Brand Name *</Label><Input value={formData.brand_name} onChange={e => setFormData({...formData, brand_name: e.target.value})} /></div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2"><Label>ATV (₹)</Label><Input type="number" value={formData.atv} onChange={e => setFormData({...formData, atv: e.target.value})} /></div>
                  <div className="space-y-2"><Label>Category</Label>
                    <select className="w-full h-10 px-3 border rounded-md text-sm" value={formData.category} onChange={e => setFormData({...formData, category: e.target.value})}>
                      <option value="">Select</option>
                      {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label>Aliases <span className="text-xs text-slate-400 font-normal">(comma-separated bill-OCR variants — Point 20)</span></Label>
                  <Input value={formData.aliases} onChange={e => setFormData({...formData, aliases: e.target.value})} placeholder="e.g. Dominos, Dominos Pizza, Jubilant Foodworks" data-testid="edit-brand-aliases" />
                </div>
              </>
            )}

            {editTab === 'store' && (
              <>
                <div className="space-y-2"><Label>Description</Label>
                  <textarea className="w-full min-h-[80px] px-3 py-2 border rounded-md text-sm resize-none" value={storeData.description} onChange={e => setStoreData({...storeData, description: e.target.value})} placeholder="Brief description shown on the consumer app" data-testid="brand-description" />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2"><Label><MapPin className="h-3 w-3 inline mr-1" />Floor</Label>
                    <select className="w-full h-10 px-3 border rounded-md text-sm" value={storeData.floor} onChange={e => setStoreData({...storeData, floor: e.target.value})} data-testid="brand-floor">
                      <option value="">Select floor</option>
                      {FLOORS.map(f => <option key={f} value={f}>{f}</option>)}
                    </select>
                  </div>
                  <div className="space-y-2"><Label>Unit No</Label><Input value={storeData.unit_no} onChange={e => setStoreData({...storeData, unit_no: e.target.value})} placeholder="e.g., G-05" data-testid="brand-unit" /></div>
                </div>
                <div className="space-y-2"><Label><Clock className="h-3 w-3 inline mr-1" />Timing</Label><Input value={storeData.timing} onChange={e => setStoreData({...storeData, timing: e.target.value})} placeholder="11:00 AM - 9:00 PM" /></div>
                <div className="space-y-2"><Label>Tags (comma-separated)</Label><Input value={storeData.tags} onChange={e => setStoreData({...storeData, tags: e.target.value})} placeholder="fashion, casual, premium" /></div>
                <div className="flex items-center gap-2">
                  <input type="checkbox" id="is_featured" checked={storeData.is_featured} onChange={e => setStoreData({...storeData, is_featured: e.target.checked})} className="rounded" data-testid="brand-featured-toggle" />
                  <label htmlFor="is_featured" className="text-sm font-medium flex items-center gap-1"><Star className="h-3 w-3 text-amber-500" />Featured on Home Screen</label>
                </div>
                {/* Point 32: Hide from consumer app without deleting the brand */}
                <div className="flex items-center gap-2">
                  <input type="checkbox" id="hidden_from_app" checked={storeData.hidden_from_app} onChange={e => setStoreData({...storeData, hidden_from_app: e.target.checked})} className="rounded" data-testid="brand-hidden-toggle" />
                  <label htmlFor="hidden_from_app" className="text-sm font-medium text-slate-700">Hide from consumer app (kept in admin only)</label>
                </div>
              </>
            )}

            {editTab === 'images' && selectedBrand && (
              <div className="space-y-6">
                {/* Logo Upload */}
                <div className="space-y-3">
                  <Label className="flex items-center gap-2"><Image className="h-4 w-4" />Brand Logo</Label>
                  <div className="flex items-center gap-4">
                    <div className="w-20 h-20 rounded-lg border-2 border-dashed border-slate-200 flex items-center justify-center overflow-hidden bg-slate-50">
                      {selectedBrand.logo_url ? (
                        <img src={selectedBrand.logo_url} alt="Logo" className="w-full h-full object-cover" data-testid="brand-logo-preview" />
                      ) : (
                        <Store className="h-8 w-8 text-slate-300" />
                      )}
                    </div>
                    <div>
                      <input ref={logoInputRef} type="file" accept="image/*" onChange={e => e.target.files[0] && handleImageUpload(selectedBrand.id, 'logo', e.target.files[0])} className="hidden" />
                      <Button variant="outline" size="sm" onClick={() => logoInputRef.current?.click()} disabled={uploadingImage === 'logo'} data-testid="upload-logo-btn">
                        {uploadingImage === 'logo' ? <><RefreshCw className="h-3 w-3 mr-1 animate-spin" />Uploading...</> : <><ArrowUpFromLine className="h-3 w-3 mr-1" />Upload Logo</>}
                      </Button>
                      <p className="text-xs text-slate-400 mt-1">Square image, max 5MB</p>
                    </div>
                  </div>
                </div>

                {/* Cover Upload */}
                <div className="space-y-3">
                  <Label className="flex items-center gap-2"><Image className="h-4 w-4" />Cover Image</Label>
                  <div className="space-y-3">
                    <div className="w-full h-40 rounded-lg border-2 border-dashed border-slate-200 flex items-center justify-center overflow-hidden bg-slate-50">
                      {selectedBrand.cover_image_url ? (
                        <img src={selectedBrand.cover_image_url} alt="Cover" className="w-full h-full object-cover" data-testid="brand-cover-preview" />
                      ) : (
                        <div className="text-center text-slate-300"><Image className="h-10 w-10 mx-auto mb-1" /><p className="text-xs">No cover image</p></div>
                      )}
                    </div>
                    <input ref={coverInputRef} type="file" accept="image/*" onChange={e => e.target.files[0] && handleImageUpload(selectedBrand.id, 'cover', e.target.files[0])} className="hidden" />
                    <Button variant="outline" size="sm" onClick={() => coverInputRef.current?.click()} disabled={uploadingImage === 'cover'} data-testid="upload-cover-btn">
                      {uploadingImage === 'cover' ? <><RefreshCw className="h-3 w-3 mr-1 animate-spin" />Uploading...</> : <><ArrowUpFromLine className="h-3 w-3 mr-1" />Upload Cover</>}
                    </Button>
                    <p className="text-xs text-slate-400">Landscape image (16:9), max 5MB</p>
                  </div>
                </div>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEditDialog(false)}>Cancel</Button>
            <Button onClick={handleEdit} data-testid="save-brand-changes-btn">Save & Sync to App</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* App QR Dialog */}
      <Dialog open={showQRDialog} onOpenChange={setShowQRDialog}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><QrCode className="h-5 w-5" />CP67 App Download QR</DialogTitle>
            <DialogDescription>Scan this QR code to open the CP67 consumer app</DialogDescription>
          </DialogHeader>
          <div className="flex justify-center py-4">
            <img src={`${API_URL}/app-download-qr`} alt="App QR Code" className="w-64 h-64" data-testid="app-qr-code" />
          </div>
          <p className="text-center text-sm text-slate-500">Place this QR at mall entrances, parking, and in-store</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowQRDialog(false)}>Close</Button>
            <Button onClick={() => { const a = document.createElement('a'); a.href = `${API_URL}/app-download-qr`; a.download = 'cp67-app-qr.png'; a.click(); }} data-testid="download-qr-btn">
              <QrCode className="h-4 w-4 mr-2" />Download QR
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Upload History Dialog */}
      <Dialog open={showHistoryDialog} onOpenChange={setShowHistoryDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><History className="h-5 w-5" />Upload History</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            {uploadHistory.length === 0 ? (
              <p className="text-center text-slate-500 py-8">No upload history</p>
            ) : (
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {uploadHistory.map(r => (
                  <div key={r.id} className="p-3 border rounded-lg bg-slate-50">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2"><FileSpreadsheet className="h-4 w-4 text-green-600" /><span className="font-medium">{r.filename}</span></div>
                      <Badge variant="outline">{r.brands_in_file} brands</Badge>
                    </div>
                    <div className="mt-2 text-sm text-slate-600 grid grid-cols-2 gap-2">
                      <div>New: <span className="font-semibold text-green-600">{r.imported}</span></div>
                      <div>Updated: <span className="font-semibold text-blue-600">{r.updated}</span></div>
                      <div>By: {r.uploaded_by}</div>
                      <div>{new Date(r.uploaded_at).toLocaleString()}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setShowHistoryDialog(false)}>Close</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  );
};

export default Brands;
