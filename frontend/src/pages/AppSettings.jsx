import React, { useState, useEffect } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import { useAuth } from '../App';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { toast } from 'sonner';
import { Type, Save, RotateCcw } from 'lucide-react';

const FONT_OPTIONS = [
  { value: 'Antique Olive', label: 'Antique Olive (default)' },
  { value: 'Playfair Display', label: 'Playfair Display (serif elegant)' },
  { value: 'Manrope', label: 'Manrope (modern sans)' },
  { value: 'Outfit', label: 'Outfit (modern sans)' },
  { value: 'Inter', label: 'Inter (neutral sans)' },
  { value: 'Poppins', label: 'Poppins (rounded sans)' },
  { value: 'Roboto', label: 'Roboto (system sans)' },
  { value: 'Merriweather', label: 'Merriweather (serif)' },
  { value: 'Georgia', label: 'Georgia (serif)' },
  { value: 'Cormorant Garamond', label: 'Cormorant Garamond (serif luxury)' },
];

const WEIGHTS = [
  { value: 300, label: '300 Light' },
  { value: 400, label: '400 Regular' },
  { value: 500, label: '500 Medium' },
  { value: 600, label: '600 Semibold' },
  { value: 700, label: '700 Bold' },
  { value: 800, label: '800 Extra Bold' },
];

const DEFAULTS = {
  heading_font_family: 'Antique Olive',
  heading_font_size_scale: 1.0,
  heading_font_weight: 700,
  content_font_family: 'Antique Olive',
  content_font_size_scale: 1.0,
  content_font_weight: 400,
};

export default function AppSettings() {
  const { token, API_URL } = useAuth();
  const [form, setForm] = useState(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${API_URL}/admin/app-settings`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (r.ok) {
          const d = await r.json();
          setForm({ ...DEFAULTS, ...(d.settings || {}) });
        }
      } catch { /* silent */ }
      setLoading(false);
    })();
  }, [API_URL, token]);

  const save = async () => {
    setSaving(true);
    try {
      const r = await fetch(`${API_URL}/admin/app-settings`, {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (r.ok) toast.success('App settings saved. Consumer PWA will pick up on next load.');
      else toast.error('Failed to save');
    } catch { toast.error('Network error'); }
    setSaving(false);
  };

  const reset = () => setForm(DEFAULTS);

  const previewStyle = (which) => ({
    fontFamily: `'${which === 'heading' ? form.heading_font_family : form.content_font_family}', sans-serif`,
    fontSize: `${(which === 'heading' ? 28 : 16) * (which === 'heading' ? form.heading_font_size_scale : form.content_font_size_scale)}px`,
    fontWeight: which === 'heading' ? form.heading_font_weight : form.content_font_weight,
  });

  if (loading) return <DashboardLayout title="App Settings"><div className="p-8 text-slate-500">Loading…</div></DashboardLayout>;

  return (
    <DashboardLayout title="App Settings">
      <div className="space-y-6" data-testid="app-settings-page">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Type className="h-5 w-5" /> Consumer App Font Customisation</CardTitle>
            <p className="text-sm text-slate-500">Change heading and content fonts separately. Changes apply on the consumer PWA on next page load.</p>
          </CardHeader>
          <CardContent className="space-y-8">

            {/* HEADING */}
            <section className="space-y-3">
              <h3 className="font-semibold text-slate-700 border-b border-slate-200 pb-1">Heading Font</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <Label>Font Family</Label>
                  <select
                    className="w-full border rounded-md px-3 py-2 text-sm mt-1"
                    value={form.heading_font_family}
                    onChange={e => setForm({ ...form, heading_font_family: e.target.value })}
                    data-testid="heading-font-family"
                  >
                    {FONT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
                <div>
                  <Label>Size Scale ({form.heading_font_size_scale.toFixed(2)}x)</Label>
                  <Input
                    type="range" min="0.7" max="1.8" step="0.05"
                    value={form.heading_font_size_scale}
                    onChange={e => setForm({ ...form, heading_font_size_scale: parseFloat(e.target.value) })}
                    data-testid="heading-size-scale"
                  />
                </div>
                <div>
                  <Label>Weight</Label>
                  <select
                    className="w-full border rounded-md px-3 py-2 text-sm mt-1"
                    value={form.heading_font_weight}
                    onChange={e => setForm({ ...form, heading_font_weight: parseInt(e.target.value) })}
                    data-testid="heading-font-weight"
                  >
                    {WEIGHTS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
              </div>
              <div className="mt-3 p-4 rounded-lg bg-slate-50 border" data-testid="heading-preview">
                <p style={previewStyle('heading')}>Welcome to Homeland Advantage</p>
              </div>
            </section>

            {/* CONTENT */}
            <section className="space-y-3">
              <h3 className="font-semibold text-slate-700 border-b border-slate-200 pb-1">Content / Body Font</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <Label>Font Family</Label>
                  <select
                    className="w-full border rounded-md px-3 py-2 text-sm mt-1"
                    value={form.content_font_family}
                    onChange={e => setForm({ ...form, content_font_family: e.target.value })}
                    data-testid="content-font-family"
                  >
                    {FONT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
                <div>
                  <Label>Size Scale ({form.content_font_size_scale.toFixed(2)}x)</Label>
                  <Input
                    type="range" min="0.7" max="1.6" step="0.05"
                    value={form.content_font_size_scale}
                    onChange={e => setForm({ ...form, content_font_size_scale: parseFloat(e.target.value) })}
                    data-testid="content-size-scale"
                  />
                </div>
                <div>
                  <Label>Weight</Label>
                  <select
                    className="w-full border rounded-md px-3 py-2 text-sm mt-1"
                    value={form.content_font_weight}
                    onChange={e => setForm({ ...form, content_font_weight: parseInt(e.target.value) })}
                    data-testid="content-font-weight"
                  >
                    {WEIGHTS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
              </div>
              <div className="mt-3 p-4 rounded-lg bg-slate-50 border" data-testid="content-preview">
                <p style={previewStyle('content')}>
                  Shop across 100+ premium brands at CP67. Earn rewards on every purchase and redeem exclusive offers.
                </p>
              </div>
            </section>

            <div className="flex justify-end gap-3 pt-4 border-t">
              <Button variant="outline" onClick={reset} data-testid="reset-fonts-btn">
                <RotateCcw className="h-4 w-4 mr-2" /> Reset to defaults
              </Button>
              <Button onClick={save} disabled={saving} data-testid="save-fonts-btn">
                <Save className="h-4 w-4 mr-2" /> {saving ? 'Saving…' : 'Save Settings'}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
}
