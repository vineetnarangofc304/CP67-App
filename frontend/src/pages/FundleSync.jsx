import React, { useState, useEffect, useRef } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import { useAuth } from '../App';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Progress } from '../components/ui/progress';
import { toast } from 'sonner';
import { RefreshCw, PlayCircle, CheckCircle2, XCircle, Clock } from 'lucide-react';

export default function FundleSync() {
  const { token, API_URL } = useAuth();
  const [job, setJob] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [starting, setStarting] = useState(false);
  const pollRef = useRef(null);

  const loadHistory = async () => {
    try {
      const r = await fetch(`${API_URL}/admin/sync/jobs`, { headers: { Authorization: `Bearer ${token}` } });
      if (r.ok) setJobs((await r.json()).jobs || []);
    } catch { /* silent */ }
  };

  useEffect(() => { loadHistory(); }, [token, API_URL]); // eslint-disable-line react-hooks/exhaustive-deps

  const pollJob = async (jobId) => {
    try {
      const r = await fetch(`${API_URL}/admin/sync/status/${jobId}`, { headers: { Authorization: `Bearer ${token}` } });
      if (!r.ok) return;
      const data = await r.json();
      setJob(data);
      if (data.status === 'completed') {
        clearInterval(pollRef.current);
        toast.success(`Sync complete — ${data.registered} newly registered, ${data.already} already synced, ${data.failed} failed.`);
        loadHistory();
      }
    } catch { /* silent */ }
  };

  const startLegacy154 = async () => {
    if (!window.confirm('Start syncing all 154 legacy phone numbers to Fundle? This will register each user and re-sync their bills.')) return;
    setStarting(true);
    try {
      const r = await fetch(`${API_URL}/admin/sync/legacy-154?include_bills=true`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (r.ok) {
        const d = await r.json();
        toast.success(`Sync queued (${d.total} numbers). Polling for progress…`);
        pollRef.current = setInterval(() => pollJob(d.job_id), 2500);
        pollJob(d.job_id);
      } else {
        toast.error('Failed to start sync');
      }
    } catch { toast.error('Network error'); }
    setStarting(false);
  };

  const runNightlyNow = async () => {
    try {
      const r = await fetch(`${API_URL}/admin/sync/nightly/run-now`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (r.ok) toast.success('Nightly sync triggered. Refresh history in ~30 seconds.');
      else toast.error('Failed to trigger nightly sync');
    } catch { toast.error('Network error'); }
  };

  const pct = job ? Math.round((job.processed / Math.max(job.total, 1)) * 100) : 0;

  return (
    <DashboardLayout title="Fundle Sync">
      <div className="space-y-6" data-testid="fundle-sync-page">

        {/* Legacy 154 batch */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><PlayCircle className="h-5 w-5" /> One-Time: Sync 154 Legacy Numbers</CardTitle>
            <p className="text-sm text-slate-500">Sync the 154 numbers identified as registered on new platform but missing from Fundle. Registers each user on Fundle + re-syncs their bills (approved locally, missing on Fundle).</p>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button onClick={startLegacy154} disabled={starting || (job && job.status === 'running')} data-testid="start-legacy-sync-btn">
              <PlayCircle className="h-4 w-4 mr-2" /> {starting ? 'Starting…' : 'Start Legacy Sync'}
            </Button>

            {job && (
              <div className="border rounded-lg p-4 bg-slate-50 space-y-2" data-testid="sync-progress">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">Job: {job.status}</span>
                  <span className="text-slate-500">{job.processed || 0} / {job.total || 0}</span>
                </div>
                <Progress value={pct} />
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs mt-2">
                  <span className="text-emerald-700">Registered: {job.registered || 0}</span>
                  <span className="text-slate-500">Already: {job.already || 0}</span>
                  <span className="text-rose-600">Failed: {job.failed || 0}</span>
                  <span className="text-emerald-700">Bills OK: {job.bills_synced || 0}</span>
                  <span className="text-rose-600">Bills fail: {job.bills_failed || 0}</span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Nightly sync trigger */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Clock className="h-5 w-5" /> Nightly Auto-Sync (1:00 AM IST)</CardTitle>
            <p className="text-sm text-slate-500">A cron job runs every night at 1 AM IST and syncs newly-registered app users to Fundle. Use the button below to trigger it manually for testing.</p>
          </CardHeader>
          <CardContent>
            <Button variant="outline" onClick={runNightlyNow} data-testid="run-nightly-btn">
              <RefreshCw className="h-4 w-4 mr-2" /> Run Nightly Sync Now
            </Button>
          </CardContent>
        </Card>

        {/* History */}
        <Card>
          <CardHeader>
            <CardTitle>Recent Sync Jobs</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {jobs.length === 0 && <p className="text-sm text-slate-400">No sync jobs yet.</p>}
              {jobs.map(j => (
                <div key={j.id} className="border rounded p-3 text-sm flex flex-wrap items-center gap-3">
                  <span className={`inline-flex items-center gap-1 ${j.status === 'completed' ? 'text-emerald-700' : j.status === 'failed' ? 'text-rose-600' : 'text-slate-500'}`}>
                    {j.status === 'completed' ? <CheckCircle2 className="h-4 w-4" /> : j.status === 'failed' ? <XCircle className="h-4 w-4" /> : <Clock className="h-4 w-4" />}
                    {j.status}
                  </span>
                  <span className="font-medium">{j.type}</span>
                  <span className="text-slate-500">{new Date(j.run_at).toLocaleString()}</span>
                  {j.counters && (
                    <span className="text-xs text-slate-500">
                      {JSON.stringify(j.counters)}
                    </span>
                  )}
                  {j.total && (
                    <span className="text-xs text-slate-500">
                      processed {j.processed || 0}/{j.total} · reg {j.registered || 0} · already {j.already || 0} · failed {j.failed || 0}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

      </div>
    </DashboardLayout>
  );
}
