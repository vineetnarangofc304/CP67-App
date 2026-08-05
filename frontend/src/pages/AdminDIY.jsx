import React, { useEffect, useState } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import { useAuth } from '../App';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Switch } from '../components/ui/switch';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { toast } from 'sonner';
import { Send, Layers, Users, QrCode, Plus, Trash2, RefreshCw, Download } from 'lucide-react';

export default function AdminDIY() {
  const { token, API_URL } = useAuth();
  const [tab, setTab] = useState('push');

  const api = (path, opts = {}) => fetch(`${API_URL}${path}`, {
    ...opts,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', ...(opts.headers || {}) },
  });

  return (
    <DashboardLayout title="App Controls (DIY)">
      <div className="space-y-4">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="push" data-testid="diy-tab-push"><Send size={14} className="mr-1" /> Push Broadcasts</TabsTrigger>
            <TabsTrigger value="popups" data-testid="diy-tab-popups"><Layers size={14} className="mr-1" /> Popups & In-App</TabsTrigger>
            <TabsTrigger value="referral" data-testid="diy-tab-referral"><Users size={14} className="mr-1" /> Referral Config</TabsTrigger>
            <TabsTrigger value="qr" data-testid="diy-tab-qr"><QrCode size={14} className="mr-1" /> App Download QR</TabsTrigger>
          </TabsList>

          <TabsContent value="push"><PushPanel api={api} /></TabsContent>
          <TabsContent value="popups"><PopupsPanel api={api} /></TabsContent>
          <TabsContent value="referral"><ReferralPanel api={api} /></TabsContent>
          <TabsContent value="qr"><QRPanel API_URL={API_URL} /></TabsContent>
        </Tabs>
      </div>
    </DashboardLayout>
  );
}

// ==================== PUSH PANEL ====================
const PushPanel = ({ api }) => {
  const [form, setForm] = useState({ title: '', body: '', target: 'all', tier: 'Bronze' });
  const [dryRun, setDryRun] = useState(null);
  const [history, setHistory] = useState([]);
  const [busy, setBusy] = useState(false);

  const loadHistory = async () => {
    const r = await api('/admin/diy/push/history');
    if (r.ok) setHistory((await r.json()).broadcasts || []);
  };
  useEffect(() => { loadHistory(); /* eslint-disable-next-line */ }, []);

  const doDryRun = async () => {
    if (!form.title || !form.body) { toast.error('Title + body required'); return; }
    const r = await api('/admin/diy/push/broadcast', { method: 'POST', body: JSON.stringify({ ...form, dry_run: true }) });
    if (r.ok) setDryRun(await r.json()); else toast.error('Dry-run failed');
  };
  const doSend = async () => {
    if (!form.title || !form.body) { toast.error('Title + body required'); return; }
    if (!window.confirm(`Send this push to ${dryRun?.matched_users || '?'} users?`)) return;
    setBusy(true);
    const r = await api('/admin/diy/push/broadcast', { method: 'POST', body: JSON.stringify({ ...form, dry_run: false }) });
    setBusy(false);
    if (r.ok) {
      const d = await r.json();
      toast.success(`Sent to ${d.ios_sent} iOS + ${d.web_devices} web devices`);
      setForm({ title: '', body: '', target: 'all', tier: 'Bronze' });
      setDryRun(null); loadHistory();
    } else {
      toast.error('Broadcast failed');
    }
  };

  return (
    <div className="grid md:grid-cols-2 gap-4">
      <Card>
        <CardHeader><CardTitle>Compose Push Notification</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div><Label>Title *</Label><Input data-testid="push-title" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="You have new rewards!" /></div>
          <div><Label>Body *</Label><Textarea data-testid="push-body" rows={3} value={form.body} onChange={e => setForm({ ...form, body: e.target.value })} placeholder="Upload a bill and earn 2x points this weekend." /></div>
          <div>
            <Label>Target</Label>
            <Select value={form.target} onValueChange={v => setForm({ ...form, target: v })}>
              <SelectTrigger data-testid="push-target"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All users</SelectItem>
                <SelectItem value="opted_in">Push-opted-in only</SelectItem>
                <SelectItem value="tier">By tier</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {form.target === 'tier' && (
            <div>
              <Label>Tier</Label>
              <Select value={form.tier} onValueChange={v => setForm({ ...form, tier: v })}>
                <SelectTrigger data-testid="push-tier"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {['Bronze','Silver','Gold','Platinum','Titanium','Diamond','Privilege'].map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="flex gap-2 pt-2">
            <Button variant="outline" onClick={doDryRun} data-testid="push-dryrun">Preview Audience</Button>
            <Button onClick={doSend} disabled={!dryRun || busy} data-testid="push-send"><Send size={14} className="mr-1" /> {busy ? 'Sending…' : 'Send Broadcast'}</Button>
          </div>
          {dryRun && (
            <div className="mt-2 p-3 bg-slate-50 rounded text-sm">
              Will reach <b>{dryRun.matched_users}</b> users · <b>{dryRun.ios_devices}</b> iPhone · <b>{dryRun.web_devices}</b> web
            </div>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between"><CardTitle>Recent Broadcasts</CardTitle><Button size="sm" variant="ghost" onClick={loadHistory}><RefreshCw size={14} /></Button></CardHeader>
        <CardContent>
          {history.length === 0 && <div className="text-slate-400 text-sm py-6 text-center">No broadcasts yet.</div>}
          {history.map(h => (
            <div key={h.id} className="border-b py-2 text-sm">
              <div className="font-medium">{h.title}</div>
              <div className="text-slate-500 text-xs">{h.body}</div>
              <div className="text-xs mt-1">
                {h.sent_at?.slice(0,16).replace('T',' ')} · {h.matched_users} users · iOS {h.ios_sent}/{h.ios_sent+h.ios_failed} · Web {h.web_devices}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
};

// ==================== POPUP PANEL ====================
const PopupsPanel = ({ api }) => {
  const [rows, setRows] = useState([]);
  const [creating, setCreating] = useState(false);
  const emptyForm = { title: '', body: '', image_url: '', cta_label: '', cta_url: '', target_tier: '', show_frequency: 'once', priority: 0, active: true, starts_at: '', ends_at: '' };
  const [form, setForm] = useState(emptyForm);

  const load = async () => {
    const r = await api('/admin/diy/popups');
    if (r.ok) setRows((await r.json()).popups || []);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const save = async () => {
    if (!form.title || !form.body) { toast.error('Title + body required'); return; }
    const payload = { ...form };
    ['target_tier','starts_at','ends_at','image_url','cta_label','cta_url'].forEach(k => { if (!payload[k]) payload[k] = null; });
    const r = await api('/admin/diy/popups', { method: 'POST', body: JSON.stringify(payload) });
    if (r.ok) { toast.success('Popup created'); setCreating(false); setForm(emptyForm); load(); }
    else toast.error('Create failed');
  };

  const toggleActive = async (p) => {
    const r = await api(`/admin/diy/popups/${p.id}`, { method: 'PATCH', body: JSON.stringify({ active: !p.active }) });
    if (r.ok) { toast.success(!p.active ? 'Activated' : 'Deactivated'); load(); }
  };
  const del = async (p) => {
    if (!window.confirm(`Delete popup "${p.title}"?`)) return;
    const r = await api(`/admin/diy/popups/${p.id}`, { method: 'DELETE' });
    if (r.ok) { toast.success('Deleted'); load(); }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row justify-between items-center">
        <CardTitle>Popups & In-App Messages ({rows.length})</CardTitle>
        <Button size="sm" onClick={() => setCreating(!creating)} data-testid="popup-new-btn"><Plus size={14} className="mr-1" /> {creating ? 'Cancel' : 'New Popup'}</Button>
      </CardHeader>
      <CardContent>
        {creating && (
          <div className="border rounded-lg p-4 mb-4 bg-slate-50 space-y-3">
            <div className="grid md:grid-cols-2 gap-3">
              <div><Label>Title *</Label><Input data-testid="popup-title" value={form.title} onChange={e => setForm({...form,title:e.target.value})} /></div>
              <div><Label>Image URL (optional)</Label><Input value={form.image_url} onChange={e => setForm({...form,image_url:e.target.value})} placeholder="https://..." /></div>
            </div>
            <div><Label>Body *</Label><Textarea data-testid="popup-body" rows={2} value={form.body} onChange={e => setForm({...form,body:e.target.value})} /></div>
            <div className="grid md:grid-cols-3 gap-3">
              <div><Label>CTA Label</Label><Input value={form.cta_label} onChange={e => setForm({...form,cta_label:e.target.value})} placeholder="Upload Bill" /></div>
              <div><Label>CTA URL</Label><Input value={form.cta_url} onChange={e => setForm({...form,cta_url:e.target.value})} placeholder="/app/upload" /></div>
              <div>
                <Label>Show Frequency</Label>
                <Select value={form.show_frequency} onValueChange={v => setForm({...form,show_frequency:v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="once">Once per user</SelectItem>
                    <SelectItem value="daily">Once per day</SelectItem>
                    <SelectItem value="every_session">Every session</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid md:grid-cols-3 gap-3">
              <div><Label>Target Tier (blank = all)</Label>
                <Select value={form.target_tier || 'all'} onValueChange={v => setForm({...form,target_tier: v === 'all' ? '' : v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All tiers</SelectItem>
                    {['Bronze','Silver','Gold','Platinum','Titanium','Diamond','Privilege'].map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div><Label>Priority</Label><Input type="number" value={form.priority} onChange={e => setForm({...form,priority: Number(e.target.value)})} /></div>
              <div><Label>Start (optional)</Label><Input type="datetime-local" value={form.starts_at} onChange={e => setForm({...form,starts_at:e.target.value ? new Date(e.target.value).toISOString() : ''})} /></div>
            </div>
            <Button onClick={save} data-testid="popup-save">Save Popup</Button>
          </div>
        )}
        <div className="space-y-2">
          {rows.length === 0 && !creating && <div className="text-slate-400 py-8 text-center">No popups. Create your first campaign.</div>}
          {rows.map(p => (
            <div key={p.id} className="flex justify-between items-center border-b py-2">
              <div className="flex-1">
                <div className="font-medium">{p.title} <span className={`text-xs ml-2 ${p.active?'text-emerald-600':'text-slate-400'}`}>{p.active?'active':'inactive'}</span></div>
                <div className="text-xs text-slate-500">{p.body}</div>
                <div className="text-xs text-slate-400 mt-1">{p.show_frequency} · Tier: {p.target_tier || 'all'} · Priority {p.priority}</div>
              </div>
              <div className="flex gap-2">
                <Switch checked={p.active} onCheckedChange={() => toggleActive(p)} data-testid={`popup-toggle-${p.id}`} />
                <Button size="sm" variant="ghost" onClick={() => del(p)}><Trash2 size={14} /></Button>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

// ==================== REFERRAL PANEL ====================
const ReferralPanel = ({ api }) => {
  const [cfg, setCfg] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    const r = await api('/admin/diy/referral-config');
    if (r.ok) setCfg((await r.json()).config);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const save = async () => {
    setSaving(true);
    const r = await api('/admin/diy/referral-config', {
      method: 'PUT',
      body: JSON.stringify({
        referrer_points: Number(cfg.referrer_points),
        referee_points: Number(cfg.referee_points),
        per_month_cap: Number(cfg.per_month_cap),
        active: cfg.active,
        message: cfg.message,
      }),
    });
    setSaving(false);
    if (r.ok) toast.success('Referral config saved');
    else toast.error('Save failed');
  };

  if (!cfg) return <div className="text-slate-400 p-4">Loading…</div>;

  return (
    <Card>
      <CardHeader><CardTitle>Referral Program Configuration</CardTitle></CardHeader>
      <CardContent className="space-y-4 max-w-md">
        <div>
          <Label>Referrer points (earned by the person who invited)</Label>
          <Input type="number" value={cfg.referrer_points} onChange={e => setCfg({...cfg, referrer_points: e.target.value})} data-testid="ref-referrer-points" />
        </div>
        <div>
          <Label>Referee points (bonus for new user who signs up via code)</Label>
          <Input type="number" value={cfg.referee_points} onChange={e => setCfg({...cfg, referee_points: e.target.value})} data-testid="ref-referee-points" />
        </div>
        <div>
          <Label>Monthly cap on referrer earnings (referrals × points)</Label>
          <Input type="number" value={cfg.per_month_cap} onChange={e => setCfg({...cfg, per_month_cap: e.target.value})} />
        </div>
        <div>
          <Label>In-app share message</Label>
          <Textarea rows={2} value={cfg.message || ''} onChange={e => setCfg({...cfg, message: e.target.value})} data-testid="ref-message" />
        </div>
        <div className="flex items-center gap-2">
          <Switch checked={cfg.active} onCheckedChange={v => setCfg({...cfg, active: v})} data-testid="ref-active" />
          <span className="text-sm">Program active</span>
        </div>
        <Button onClick={save} disabled={saving} data-testid="ref-save">{saving ? 'Saving…' : 'Save'}</Button>
        {cfg.updated_at && <div className="text-xs text-slate-400">Last updated: {cfg.updated_at.slice(0,16).replace('T',' ')}</div>}
      </CardContent>
    </Card>
  );
};

// ==================== QR PANEL ====================
const QRPanel = ({ API_URL }) => {
  const qrURL = `${API_URL}/downloads/play-store-qr?size=800`;
  const smartURL = `${window.location.origin}/api/download-app`;
  return (
    <div className="grid md:grid-cols-2 gap-4">
      <Card>
        <CardHeader><CardTitle><QrCode size={16} className="inline mr-2" />Play Store QR</CardTitle></CardHeader>
        <CardContent className="text-center">
          <img src={qrURL} alt="Play Store QR" className="mx-auto max-w-[280px]" data-testid="play-store-qr-img" />
          <div className="text-xs text-slate-500 mt-2 break-all">Scan → opens Play Store listing</div>
          <a href={qrURL} download="homeland-play-store.png" className="inline-block mt-3">
            <Button data-testid="download-play-qr"><Download size={14} className="mr-1" /> Download PNG</Button>
          </a>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Smart Universal QR (auto-detect device)</CardTitle></CardHeader>
        <CardContent className="text-center">
          <img
            src={`${API_URL}/downloads/play-store-qr?size=600`}
            alt="Smart QR"
            className="mx-auto max-w-[240px]"
          />
          <div className="text-xs text-slate-500 mt-2 break-all">
            Point future QR codes here: <br /><b>{smartURL}</b>
          </div>
          <div className="text-xs text-slate-400 mt-2">
            Android → Play Store · iPhone → App Store (once live) · Desktop → Play Store
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
