import React, { useState, useEffect } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import { useAuth } from '../App';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '../components/ui/dialog';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '../components/ui/table';
import { toast } from 'sonner';
import {
  Megaphone, Plus, Edit, Trash2, ToggleLeft, ToggleRight, Zap, Gift, ShoppingBag, Target
} from 'lucide-react';

const CAMPAIGN_TYPES = [
  { value: 'multiplier', label: 'Points Multiplier', icon: Zap, desc: 'e.g., 2X or 3X points on purchases' },
  { value: 'bonus', label: 'Bonus Points', icon: Gift, desc: 'Flat bonus points on qualifying purchases' },
  { value: 'spend_threshold', label: 'Spend Threshold', icon: ShoppingBag, desc: 'Bonus when spending above a minimum amount' },
  { value: 'first_visit', label: 'First Visit Reward', icon: Target, desc: 'Extra points for first-time visitors' },
];

const FLOORS = ['Ground Floor', 'First Floor', 'Second Floor', 'Food Court', 'Lower Ground'];
const CATEGORIES = ['Fashion', 'Food & Beverage', 'Beauty', 'Electronics', 'Entertainment', 'Sports', 'Kids', 'Accessories', 'Footwear'];

const emptyForm = {
  name: '', description: '', campaign_type: 'multiplier', multiplier: 2,
  bonus_points: 0, min_spend: 0, applicable_floors: null, applicable_categories: null,
  applicable_brand_ids: null, start_date: '', end_date: '', is_active: true,
};

const Campaigns = () => {
  const { token, API_URL } = useAuth();
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ ...emptyForm });
  const [saving, setSaving] = useState(false);
  const [selectedFloors, setSelectedFloors] = useState([]);
  const [selectedCategories, setSelectedCategories] = useState([]);

  useEffect(() => { fetchCampaigns(); }, []);

  const fetchCampaigns = async () => {
    try {
      const res = await fetch(`${API_URL}/admin/campaigns`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) { const d = await res.json(); setCampaigns(d.campaigns); }
    } catch { toast.error('Failed to fetch campaigns'); }
    setLoading(false);
  };

  const openCreate = () => {
    setEditing(null);
    setForm({ ...emptyForm, start_date: new Date().toISOString().split('T')[0], end_date: new Date(Date.now() + 7 * 86400000).toISOString().split('T')[0] });
    setSelectedFloors([]);
    setSelectedCategories([]);
    setShowDialog(true);
  };

  const openEdit = (c) => {
    setEditing(c);
    setForm({
      name: c.name, description: c.description || '', campaign_type: c.campaign_type,
      multiplier: c.multiplier || 2, bonus_points: c.bonus_points || 0, min_spend: c.min_spend || 0,
      applicable_floors: c.applicable_floors, applicable_categories: c.applicable_categories,
      applicable_brand_ids: c.applicable_brand_ids,
      start_date: c.start_date ? c.start_date.split('T')[0] : '', end_date: c.end_date ? c.end_date.split('T')[0] : '',
      is_active: c.is_active,
    });
    setSelectedFloors(c.applicable_floors || []);
    setSelectedCategories(c.applicable_categories || []);
    setShowDialog(true);
  };

  const handleSave = async () => {
    if (!form.name.trim()) { toast.error('Campaign name is required'); return; }
    if (!form.start_date || !form.end_date) { toast.error('Start and end dates are required'); return; }
    setSaving(true);
    const payload = {
      ...form,
      multiplier: parseFloat(form.multiplier) || 1,
      bonus_points: parseInt(form.bonus_points) || 0,
      min_spend: parseFloat(form.min_spend) || 0,
      applicable_floors: selectedFloors.length > 0 ? selectedFloors : null,
      applicable_categories: selectedCategories.length > 0 ? selectedCategories : null,
    };
    try {
      const url = editing ? `${API_URL}/admin/campaigns/${editing.id}` : `${API_URL}/admin/campaigns`;
      const method = editing ? 'PUT' : 'POST';
      const res = await fetch(url, {
        method, headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        toast.success(editing ? 'Campaign updated' : 'Campaign created');
        setShowDialog(false);
        fetchCampaigns();
      } else {
        const err = await res.json();
        toast.error(err.detail || 'Failed to save');
      }
    } catch { toast.error('Network error'); }
    setSaving(false);
  };

  const handleToggle = async (c) => {
    try {
      const res = await fetch(`${API_URL}/admin/campaigns/${c.id}/toggle`, {
        method: 'PUT', headers: { 'Authorization': `Bearer ${token}` },
      });
      if (res.ok) { fetchCampaigns(); toast.success(`Campaign ${c.is_active ? 'paused' : 'activated'}`); }
    } catch { toast.error('Failed to toggle'); }
  };

  const handleDelete = async (c) => {
    if (!window.confirm(`Delete campaign "${c.name}"?`)) return;
    try {
      const res = await fetch(`${API_URL}/admin/campaigns/${c.id}`, {
        method: 'DELETE', headers: { 'Authorization': `Bearer ${token}` },
      });
      if (res.ok) { fetchCampaigns(); toast.success('Campaign deleted'); }
    } catch { toast.error('Failed to delete'); }
  };

  const toggleFloor = (f) => setSelectedFloors(prev => prev.includes(f) ? prev.filter(x => x !== f) : [...prev, f]);
  const toggleCategory = (c) => setSelectedCategories(prev => prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c]);

  const isActive = (c) => {
    if (!c.is_active) return false;
    const now = new Date().toISOString();
    return c.start_date <= now && c.end_date >= now;
  };

  const getStatusBadge = (c) => {
    if (!c.is_active) return <Badge variant="secondary" data-testid={`campaign-status-${c.id}`}>Paused</Badge>;
    const now = new Date().toISOString();
    if (c.end_date < now) return <Badge variant="destructive" data-testid={`campaign-status-${c.id}`}>Ended</Badge>;
    if (c.start_date > now) return <Badge variant="outline" data-testid={`campaign-status-${c.id}`}>Scheduled</Badge>;
    return <Badge className="bg-emerald-500 hover:bg-emerald-600" data-testid={`campaign-status-${c.id}`}>Live</Badge>;
  };

  const getTypeLabel = (type) => CAMPAIGN_TYPES.find(t => t.value === type)?.label || type;

  const stats = {
    total: campaigns.length,
    active: campaigns.filter(c => isActive(c)).length,
    scheduled: campaigns.filter(c => c.is_active && c.start_date > new Date().toISOString()).length,
  };

  return (
    <DashboardLayout title="Campaigns">
      <div className="space-y-6" data-testid="campaigns-page">
        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card data-testid="stat-total">
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-slate-100 rounded-lg"><Megaphone className="h-5 w-5 text-slate-600" /></div>
                <div><p className="text-sm text-slate-500">Total Campaigns</p><p className="text-2xl font-bold">{stats.total}</p></div>
              </div>
            </CardContent>
          </Card>
          <Card data-testid="stat-active">
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-emerald-100 rounded-lg"><Zap className="h-5 w-5 text-emerald-600" /></div>
                <div><p className="text-sm text-slate-500">Live Now</p><p className="text-2xl font-bold text-emerald-600">{stats.active}</p></div>
              </div>
            </CardContent>
          </Card>
          <Card data-testid="stat-scheduled">
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-100 rounded-lg"><Target className="h-5 w-5 text-blue-600" /></div>
                <div><p className="text-sm text-slate-500">Scheduled</p><p className="text-2xl font-bold text-blue-600">{stats.scheduled}</p></div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Campaigns Table */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2"><Megaphone className="h-5 w-5" /> Campaign Builder</CardTitle>
            <Button onClick={openCreate} data-testid="create-campaign-btn"><Plus className="h-4 w-4 mr-2" /> New Campaign</Button>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="text-center py-12 text-slate-500">Loading...</div>
            ) : campaigns.length === 0 ? (
              <div className="text-center py-12" data-testid="empty-campaigns">
                <Megaphone className="h-12 w-12 mx-auto text-slate-300 mb-4" />
                <p className="text-slate-500 mb-2">No campaigns yet</p>
                <p className="text-sm text-slate-400">Create your first loyalty campaign to boost engagement</p>
              </div>
            ) : (
              <Table data-testid="campaigns-table">
                <TableHeader>
                  <TableRow>
                    <TableHead>Campaign</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Value</TableHead>
                    <TableHead>Duration</TableHead>
                    <TableHead>Scope</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {campaigns.map(c => (
                    <TableRow key={c.id} data-testid={`campaign-row-${c.id}`}>
                      <TableCell>
                        <div><p className="font-medium">{c.name}</p>{c.description && <p className="text-xs text-slate-400">{c.description}</p>}</div>
                      </TableCell>
                      <TableCell><Badge variant="outline">{getTypeLabel(c.campaign_type)}</Badge></TableCell>
                      <TableCell>
                        {c.campaign_type === 'multiplier' && <span className="font-bold text-amber-600">{c.multiplier}X Points</span>}
                        {c.campaign_type === 'bonus' && <span className="font-bold text-emerald-600">+{c.bonus_points} pts</span>}
                        {c.campaign_type === 'spend_threshold' && <span className="font-bold text-blue-600">Min Rs.{c.min_spend}</span>}
                        {c.campaign_type === 'first_visit' && <span className="font-bold text-purple-600">+{c.bonus_points} pts</span>}
                      </TableCell>
                      <TableCell>
                        <div className="text-xs">
                          <p>{c.start_date?.split('T')[0]}</p>
                          <p className="text-slate-400">to {c.end_date?.split('T')[0]}</p>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="text-xs">
                          {c.applicable_floors ? <p>{c.applicable_floors.length} floor(s)</p> : <p className="text-slate-400">All floors</p>}
                          {c.applicable_categories ? <p>{c.applicable_categories.length} category(s)</p> : <p className="text-slate-400">All categories</p>}
                        </div>
                      </TableCell>
                      <TableCell>{getStatusBadge(c)}</TableCell>
                      <TableCell className="text-right">
                        <div className="flex gap-1 justify-end">
                          <Button size="sm" variant="ghost" onClick={() => handleToggle(c)} data-testid={`toggle-campaign-${c.id}`}>
                            {c.is_active ? <ToggleRight className="h-4 w-4 text-emerald-500" /> : <ToggleLeft className="h-4 w-4 text-slate-400" />}
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => openEdit(c)} data-testid={`edit-campaign-${c.id}`}>
                            <Edit className="h-4 w-4" />
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => handleDelete(c)} data-testid={`delete-campaign-${c.id}`}>
                            <Trash2 className="h-4 w-4 text-red-500" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        {/* Create/Edit Dialog */}
        <Dialog open={showDialog} onOpenChange={setShowDialog}>
          <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="campaign-dialog">
            <DialogHeader>
              <DialogTitle>{editing ? 'Edit Campaign' : 'Create New Campaign'}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <Label>Campaign Name *</Label>
                <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g., Weekend Double Points" data-testid="campaign-name-input" />
              </div>
              <div>
                <Label>Description</Label>
                <Input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="Short description for customers" data-testid="campaign-desc-input" />
              </div>

              {/* Campaign Type */}
              <div>
                <Label>Campaign Type</Label>
                <div className="grid grid-cols-2 gap-2 mt-1">
                  {CAMPAIGN_TYPES.map(t => {
                    const Icon = t.icon;
                    return (
                      <button key={t.value} onClick={() => setForm({ ...form, campaign_type: t.value })}
                        className={`flex items-center gap-2 p-3 rounded-lg border text-left text-sm transition-colors ${form.campaign_type === t.value ? 'border-slate-900 bg-slate-50' : 'border-slate-200 hover:border-slate-300'}`}
                        data-testid={`type-${t.value}`}>
                        <Icon className="h-4 w-4 flex-shrink-0" />
                        <div><p className="font-medium">{t.label}</p><p className="text-xs text-slate-400">{t.desc}</p></div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Type-specific fields */}
              {form.campaign_type === 'multiplier' && (
                <div>
                  <Label>Points Multiplier</Label>
                  <div className="flex items-center gap-2 mt-1">
                    {[1.5, 2, 3, 5].map(m => (
                      <button key={m} onClick={() => setForm({ ...form, multiplier: m })}
                        className={`px-4 py-2 rounded-lg border font-bold text-sm ${form.multiplier === m ? 'bg-amber-50 border-amber-400 text-amber-700' : 'border-slate-200 hover:border-slate-300'}`}
                        data-testid={`multiplier-${m}x`}>
                        {m}X
                      </button>
                    ))}
                    <Input type="number" step="0.5" min="1" max="10" className="w-20"
                      value={form.multiplier} onChange={e => setForm({ ...form, multiplier: parseFloat(e.target.value) })}
                      data-testid="multiplier-custom" />
                  </div>
                </div>
              )}
              {(form.campaign_type === 'bonus' || form.campaign_type === 'first_visit') && (
                <div>
                  <Label>Bonus Points</Label>
                  <Input type="number" min="0" value={form.bonus_points} onChange={e => setForm({ ...form, bonus_points: parseInt(e.target.value) || 0 })} data-testid="bonus-points-input" />
                </div>
              )}
              {form.campaign_type === 'spend_threshold' && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label>Min Spend (Rs.)</Label>
                    <Input type="number" min="0" value={form.min_spend} onChange={e => setForm({ ...form, min_spend: parseFloat(e.target.value) || 0 })} data-testid="min-spend-input" />
                  </div>
                  <div>
                    <Label>Bonus Points</Label>
                    <Input type="number" min="0" value={form.bonus_points} onChange={e => setForm({ ...form, bonus_points: parseInt(e.target.value) || 0 })} data-testid="bonus-points-input" />
                  </div>
                </div>
              )}

              {/* Date range */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Start Date *</Label>
                  <Input type="date" value={form.start_date} onChange={e => setForm({ ...form, start_date: e.target.value })} data-testid="start-date-input" />
                </div>
                <div>
                  <Label>End Date *</Label>
                  <Input type="date" value={form.end_date} onChange={e => setForm({ ...form, end_date: e.target.value })} data-testid="end-date-input" />
                </div>
              </div>

              {/* Applicable Floors */}
              <div>
                <Label>Applicable Floors <span className="text-slate-400 text-xs">(none = all floors)</span></Label>
                <div className="flex flex-wrap gap-2 mt-1">
                  {FLOORS.map(f => (
                    <button key={f} onClick={() => toggleFloor(f)}
                      className={`px-3 py-1 rounded-full border text-xs ${selectedFloors.includes(f) ? 'bg-slate-900 text-white border-slate-900' : 'border-slate-200 hover:border-slate-400'}`}
                      data-testid={`floor-chip-${f.replace(/ /g, '-').toLowerCase()}`}>
                      {f}
                    </button>
                  ))}
                </div>
              </div>

              {/* Applicable Categories */}
              <div>
                <Label>Applicable Categories <span className="text-slate-400 text-xs">(none = all categories)</span></Label>
                <div className="flex flex-wrap gap-2 mt-1">
                  {CATEGORIES.map(c => (
                    <button key={c} onClick={() => toggleCategory(c)}
                      className={`px-3 py-1 rounded-full border text-xs ${selectedCategories.includes(c) ? 'bg-slate-900 text-white border-slate-900' : 'border-slate-200 hover:border-slate-400'}`}
                      data-testid={`cat-chip-${c.replace(/ /g, '-').toLowerCase()}`}>
                      {c}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowDialog(false)} data-testid="cancel-campaign-btn">Cancel</Button>
              <Button onClick={handleSave} disabled={saving} data-testid="save-campaign-btn">
                {saving ? 'Saving...' : editing ? 'Update Campaign' : 'Create Campaign'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </DashboardLayout>
  );
};

export default Campaigns;
