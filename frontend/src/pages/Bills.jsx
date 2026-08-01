import React, { useState, useEffect } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import { useAuth } from '../App';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Textarea } from '../components/ui/textarea';
import { Label } from '../components/ui/label';
import { Checkbox } from '../components/ui/checkbox';
import { toast } from 'sonner';
import { 
  Receipt, 
  CheckCircle, 
  XCircle, 
  Clock, 
  AlertTriangle,
  Eye,
  ChevronLeft,
  ChevronRight,
  Store,
  Calendar,
  Hash,
  DollarSign,
  User,
  Phone,
  QrCode,
  RefreshCw,
  MessageCircle,
  Image as ImageIcon,
  AlertCircleIcon,
  Edit,
  Send
} from 'lucide-react';

const Bills = () => {
  const { token, API_URL } = useAuth();
  const [bills, setBills] = useState([]);
  const [pendingBills, setPendingBills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [pagination, setPagination] = useState({ skip: 0, limit: 20, total: 0 });
  const [selectedBill, setSelectedBill] = useState(null);
  const [showReviewDialog, setShowReviewDialog] = useState(false);
  const [processingBill, setProcessingBill] = useState(false);
  const [rejectionReason, setRejectionReason] = useState('');
  const [adminNotes, setAdminNotes] = useState('');
  const [pointsOverride, setPointsOverride] = useState('');
  const [sendWhatsapp, setSendWhatsapp] = useState(true);
  const [activeTab, setActiveTab] = useState('pending');

  // ----- Bulk Reprocess (date-range) state -----
  const todayISO = new Date().toISOString().slice(0, 10);
  const yesterdayISO = (() => { const d = new Date(); d.setDate(d.getDate() - 1); return d.toISOString().slice(0, 10); })();
  // ----- Fix Brand modal state -----
  const [fixBrandOpen, setFixBrandOpen] = useState(false);
  const [fixBrandBill, setFixBrandBill] = useState(null);
  const [brandsList, setBrandsList] = useState([]);
  const [brandSearch, setBrandSearch] = useState('');
  const [fixBrandBusy, setFixBrandBusy] = useState(false);

  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkFrom, setBulkFrom] = useState(yesterdayISO);
  const [bulkTo, setBulkTo] = useState(todayISO);
  const [bulkReOcr, setBulkReOcr] = useState(true);
  const [bulkSendWA, setBulkSendWA] = useState(true);
  const [bulkForceCredit, setBulkForceCredit] = useState(false);
  const [bulkForceCreditPct, setBulkForceCreditPct] = useState('1');
  const [bulkForceOnReject, setBulkForceOnReject] = useState(true);
  const [bulkRunning, setBulkRunning] = useState(false);
  const [bulkDryRun, setBulkDryRun] = useState(null);   // { candidates, bills } or null
  const [bulkResult, setBulkResult] = useState(null);    // { summary, results, total_points_credited }
  const [bulkProgress, setBulkProgress] = useState(null); // { processed, total, summary } during async job

  useEffect(() => {
    fetchBills();
    fetchPendingBills();
  }, [pagination.skip, statusFilter, dateFrom, dateTo]);

  const fetchBills = async () => {
    setLoading(true);
    try {
      let url = `${API_URL}/bills?skip=${pagination.skip}&limit=${pagination.limit}`;
      if (statusFilter && statusFilter !== 'all') url += `&status=${statusFilter}`;
      if (dateFrom) url += `&start_date=${dateFrom}`;
      if (dateTo) url += `&end_date=${dateTo}`;
      
      const response = await fetch(url, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setBills(data.bills);
        setPagination(prev => ({ ...prev, total: data.total }));
      }
    } catch (error) {
      toast.error('Failed to load bills');
    } finally {
      setLoading(false);
    }
  };

  const fetchPendingBills = async () => {
    try {
      const response = await fetch(`${API_URL}/bills/pending-review`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setPendingBills(data);
      }
    } catch (error) {
      console.error('Failed to load pending bills:', error);
    }
  };

  const openReviewDialog = async (bill) => {
    setSelectedBill(bill);
    setRejectionReason('');
    setAdminNotes('');
    setPointsOverride('');
    setSendWhatsapp(true);
    setShowReviewDialog(true);
    // Lazy-load the bill image so the list endpoint stays cheap.
    if (!bill.image_url && bill.id) {
      try {
        const res = await fetch(`${API_URL}/bills/${bill.id}/image`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (res.ok) {
          const d = await res.json();
          if (d.image_url) {
            setSelectedBill(prev => prev && prev.id === bill.id ? { ...prev, image_url: d.image_url } : prev);
          }
        }
      } catch { /* ignore — bill detail still shows even without the image */ }
    }
  };

  const processBill = async (action) => {
    if (!selectedBill) return;

    setProcessingBill(true);
    const body = {
      bill_id: selectedBill.id,
      action,
      send_whatsapp: sendWhatsapp
    };
    if (action === 'reject' && rejectionReason) body.rejection_reason = rejectionReason;
    if (adminNotes) body.admin_notes = adminNotes;
    if (action === 'approve' && pointsOverride) body.points_override = parseFloat(pointsOverride);

    // Use XHR (not fetch) to avoid Cloudflare's "body stream already read" issue
    // on non-2xx responses on production edge (session-13 fix pattern).
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_URL}/bills/${selectedBill.id}/process`, true);
    xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.timeout = 60000;
    xhr.onload = () => {
      setProcessingBill(false);
      let data = {};
      try { data = xhr.responseText ? JSON.parse(xhr.responseText) : {}; } catch { /* keep {} */ }
      if (xhr.status >= 200 && xhr.status < 300) {
        toast.success(
          action === 'approve'
            ? `Bill approved! ${data.points_issued || 0} points credited.${data.whatsapp_sent ? ' WhatsApp sent.' : ''}`
            : `Bill rejected.${data.whatsapp_sent ? ' WhatsApp notification sent.' : ''}`
        );
        fetchBills();
        fetchPendingBills();
        setShowReviewDialog(false);
        setSelectedBill(null);
      } else {
        toast.error(data.detail || `Failed to process bill (HTTP ${xhr.status}). Refreshing list…`);
        fetchBills();
        fetchPendingBills();
      }
    };
    xhr.ontimeout = () => {
      setProcessingBill(false);
      toast.warning('Fundle is slow. Your action was submitted — refreshing the list to see the result.');
      fetchBills();
      fetchPendingBills();
    };
    xhr.onerror = () => {
      setProcessingBill(false);
      toast.error('Network hiccup. Refreshing the list to check if the action went through…');
      fetchBills();
      fetchPendingBills();
    };
    try { xhr.send(JSON.stringify(body)); }
    catch (_) {
      setProcessingBill(false);
      toast.error('Failed to send request');
    }
  };

  const reprocessBill = (billId) => {
    // Point 18: The reprocess endpoint now queues in the background and
    // returns in <1s. We no longer wait 22s+ for Fundle. Frontend refreshes
    // the list twice (10s + 25s) to pick up the completed status.
    const ctrl = new AbortController();
    const timeoutId = setTimeout(() => ctrl.abort(), 15000);
    (async () => {
      try {
        const res = await fetch(`${API_URL}/bills/${billId}/reprocess`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          signal: ctrl.signal,
        });
        clearTimeout(timeoutId);
        const data = await res.json();
        if (data.reprocessed === 'queued') {
          toast.success('Reprocess queued. Refreshing list — result in ~15s.');
        } else if (data.success) {
          toast.success(`Bill reprocessed! ${data.points_earned || 0} points credited.`);
        } else if (data.error) {
          toast.error(`Reprocess failed: ${data.error}`);
        } else {
          toast.error('Reprocess failed — refresh to see the latest status.');
        }
        fetchBills();
        fetchPendingBills();
        setTimeout(() => { fetchBills(); fetchPendingBills(); }, 12000);
        setTimeout(() => { fetchBills(); fetchPendingBills(); }, 28000);
      } catch (err) {
        clearTimeout(timeoutId);
        if (err && err.name === 'AbortError') {
          toast.error('Reprocess timed out. Refresh — the bill may still be processing.');
        } else {
          toast.error('Network hiccup. Refresh — the bill may have been processed.');
        }
        fetchBills();
        fetchPendingBills();
      }
    })();
  };

  // -------- Edit Brand (open searchable dropdown of Fundle-matched brands) --------
  const editBrandBill = async (bill) => {
    setFixBrandBill(bill);
    setBrandSearch(bill.store_name || '');
    setFixBrandOpen(true);
    // Lazy-load master brand list on first open
    if (brandsList.length === 0) {
      try {
        const r = await fetch(`${API_URL}/admin/brands`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (r.ok) {
          const d = await r.json();
          setBrandsList(d.brands || []);
        }
      } catch { /* toast handled in UI */ }
    }
  };

  const submitFixBrand = async (chosenName) => {
    if (!fixBrandBill || !chosenName) return;
    const trimmed = String(chosenName).trim();
    if (!trimmed) return;
    setFixBrandBusy(true);

    // Use XHR (not fetch) to avoid Cloudflare's "body stream already read" bug
    // that surfaces as "Network error while editing brand" on production edge.
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_URL}/admin/bills/${fixBrandBill.id}/edit-brand`, true);
    xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.timeout = 25000;

    const closeAndRefresh = () => {
      setFixBrandOpen(false);
      setFixBrandBill(null);
      fetchBills();
      fetchPendingBills();
    };

    xhr.onload = () => {
      setFixBrandBusy(false);
      let data = {};
      try { data = xhr.responseText ? JSON.parse(xhr.responseText) : {}; } catch { /* keep {} */ }
      if (xhr.status < 200 || xhr.status >= 300) {
        toast.error(data.detail || `Brand edit failed (HTTP ${xhr.status})`);
        return;
      }
      if (data.reprocessed === 'queued') {
        toast.success(`Brand fixed → "${trimmed}". Reprocessing in background — refreshing list in 10s.`);
        closeAndRefresh();
        setTimeout(() => { fetchBills(); fetchPendingBills(); }, 10000);
        setTimeout(() => { fetchBills(); fetchPendingBills(); }, 25000);
      } else if (data.action === 'approved') {
        if (data.fallback === 'force_credit') {
          toast.success(`Brand fixed → "${trimmed}". Fundle rejected but auto force-credited ${data.points || 0} pts locally.`);
        } else {
          toast.success(`Brand fixed → "${trimmed}". Approved with ${data.points || 0} pts`);
        }
        closeAndRefresh();
      } else if (data.error) {
        toast.warning(`Brand updated but Fundle: ${data.error}. Try a different variant.`);
        closeAndRefresh();
      } else {
        toast.success(`Brand updated to "${trimmed}". Status: ${data.status || 'pending'}`);
        closeAndRefresh();
      }
    };

    xhr.ontimeout = () => {
      setFixBrandBusy(false);
      toast.warning('Brand edit is still processing in background. Refreshing the list…');
      closeAndRefresh();
      setTimeout(() => { fetchBills(); fetchPendingBills(); }, 15000);
    };

    xhr.onerror = () => {
      setFixBrandBusy(false);
      // Backend may still have accepted the edit — refresh to check
      toast.warning('Network hiccup. Refreshing the list to check if the brand was updated…');
      closeAndRefresh();
    };

    try {
      xhr.send(JSON.stringify({
        new_store_name: trimmed,
        reprocess: true,
        auto_force_credit_on_fundle_reject: true,
      }));
    } catch (_) {
      setFixBrandBusy(false);
      toast.error('Failed to send request');
    }
  };

  // -------- Force Credit (manual approval, bypassing Fundle) --------
  // Auto-calculates points via brand category + bill amount range
  // (same logic as the consumer-facing tier earn-rate table). Admin just
  // confirms — no manual point entry, so there's no risk of wrong values.
  const forceCreditBill = async (bill) => {
    // Fetch the auto-calculated points first
    let preview;
    try {
      const r = await fetch(`${API_URL}/admin/bills/${bill.id}/force-credit-preview`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!r.ok) { toast.error('Could not calculate points'); return; }
      preview = await r.json();
    } catch {
      toast.error('Network error fetching point calculation');
      return;
    }

    const msg = (
      `Force credit this bill?\n\n` +
      `Store: ${bill.store_name || 'Unknown'}\n` +
      `Amount: ₹${bill.amount || 0}\n` +
      `Category: ${preview.category}${preview.brand_found ? '' : ' (brand not in master — defaulted to retail)'}\n` +
      `Rate: ${preview.rate_pct}% (${preview.rate_basis}, range ₹${preview.range_label})\n` +
      `Points to credit: ${preview.calculated_points}\n\n` +
      `Fundle will be bypassed. Continue?`
    );
    if (!window.confirm(msg)) return;

    try {
      const res = await fetch(`${API_URL}/admin/bills/${bill.id}/force-credit`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (res.ok && data.success) {
        toast.success(`Force credited! ${data.points_issued} pts to ${bill.user_phone}`);
        fetchBills();
        fetchPendingBills();
      } else {
        toast.error(data.detail || data.error || 'Force credit failed');
      }
    } catch {
      toast.error('Network error during force credit');
    }
  };

  // -------- Bulk Reprocess (date range) --------
  const callBulkReprocess = async (dryRun) => {
    setBulkRunning(true);
    if (dryRun) {
      setBulkDryRun(null);
    } else {
      setBulkResult(null);
      setBulkProgress(null);
    }
    try {
      const res = await fetch(`${API_URL}/admin/bills/bulk-reprocess`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          from_date: bulkFrom || null,
          to_date: bulkTo || null,
          statuses: ['manual_review', 'pending_review'],
          re_ocr: bulkReOcr,
          send_whatsapp: bulkSendWA,
          force_credit: bulkForceCredit,
          force_credit_percent: parseFloat(bulkForceCreditPct) || 1,
          force_credit_on_fundle_reject: bulkForceOnReject,
          dry_run: dryRun,
          limit: 300
        })
      });
      const data = await res.json();
      if (!res.ok) {
        toast.error(data.detail || 'Bulk reprocess failed');
        setBulkRunning(false);
        return;
      }
      if (dryRun) {
        setBulkDryRun(data);
        toast.success(`Found ${data.candidates} candidate bill(s)`);
        setBulkRunning(false);
      } else {
        // Async job started — poll for status
        if (data.job_id) {
          toast.success(`Started reprocessing ${data.total} bill(s) in background…`);
          await pollBulkReprocessJob(data.job_id, data.total);
        } else {
          // Backwards-compat: old synchronous response
          setBulkResult(data);
          fetchBills();
          fetchPendingBills();
          setBulkRunning(false);
        }
      }
    } catch {
      toast.error('Network error while bulk reprocessing');
      setBulkRunning(false);
    }
  };

  const pollBulkReprocessJob = async (jobId, totalExpected) => {
    setBulkProgress({ processed: 0, total: totalExpected, summary: {} });
    let attempts = 0;
    const maxAttempts = 600; // 600 * 3s = 30 min upper bound
    while (attempts < maxAttempts) {
      attempts += 1;
      try {
        const res = await fetch(`${API_URL}/admin/bills/bulk-reprocess/${jobId}/status`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (res.ok) {
          const job = await res.json();
          setBulkProgress({
            processed: job.processed || 0,
            total: job.total || totalExpected,
            summary: job.summary || {}
          });
          if (job.status === 'completed') {
            setBulkResult({
              summary: job.summary,
              total_points_credited: job.total_points_credited,
              processed: job.processed,
            });
            setBulkProgress(null);
            setBulkRunning(false);
            const s = job.summary || {};
            toast.success(
              `Done. Approved ${s.approved || 0} • Rejected ${s.rejected || 0} • Pending ${s.kept_pending || 0} • Points: ${job.total_points_credited || 0}`
            );
            fetchBills();
            fetchPendingBills();
            return;
          }
        }
      } catch {
        // transient network error — keep polling
      }
      // Wait 3 seconds before next poll
      await new Promise((r) => setTimeout(r, 3000));
    }
    // Timed out polling — keep dialog open, user can refresh manually
    toast.error('Reprocessing is taking longer than expected. Please refresh the page in a few minutes.');
    setBulkRunning(false);
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const getStatusBadge = (status) => {
    const styles = {
      'auto_approved': { bg: 'bg-green-100 text-green-800', icon: CheckCircle, label: 'Auto Approved' },
      'approved': { bg: 'bg-green-100 text-green-800', icon: CheckCircle, label: 'Approved' },
      'manual_review': { bg: 'bg-yellow-100 text-yellow-800', icon: Clock, label: 'Pending Review' },
      'pending_review': { bg: 'bg-orange-100 text-orange-800', icon: Clock, label: 'Pending Review' },
      'pending': { bg: 'bg-yellow-100 text-yellow-800', icon: Clock, label: 'Pending' },
      'rejected': { bg: 'bg-red-100 text-red-800', icon: XCircle, label: 'Rejected' },
      'duplicate': { bg: 'bg-purple-100 text-purple-800', icon: AlertTriangle, label: 'Duplicate' }
    };
    const style = styles[status] || styles.pending;
    const Icon = style.icon;
    return (
      <Badge className={`${style.bg} gap-1`}>
        <Icon className="h-3 w-3" />
        {style.label}
      </Badge>
    );
  };

  const getSystemRejectionReason = (bill) => {
    const reasons = [];
    const ocr = bill.ocr_raw_data || {};
    
    // OCR-detected issues
    if (ocr.tampering_detected) reasons.push('Tampering Detected');
    if (ocr.image_quality === 'poor') reasons.push('Poor Image Quality');
    if (!ocr.is_valid_bill) reasons.push('Invalid Bill Format');
    if (bill.status === 'duplicate') reasons.push('Duplicate Bill');
    if (ocr.confidence_score && ocr.confidence_score < 0.5) reasons.push('Low OCR Confidence');
    
    // System rejection reason (from backend)
    if (bill.system_rejection_reason) reasons.push(bill.system_rejection_reason);
    
    // Admin/API rejection reason (from Fundle or admin)
    if (bill.rejection_reason) {
      // Parse common rejection reasons for display
      const reason = bill.rejection_reason;
      if (reason.includes('Brand') && reason.includes('not found')) {
        reasons.push(`Brand Not Found: ${bill.store_name}`);
      } else if (reason.includes('older than 30 days')) {
        reasons.push('Bill Date > 30 Days Old');
      } else if (reason.includes('CP67')) {
        reasons.push('Not a CP67 Mall Bill');
      } else if (reason.includes('Duplicate')) {
        reasons.push('Duplicate Bill');
      } else if (reason.includes('Mob No not matched')) {
        reasons.push(
          bill.invoice_mobile
            ? `Mob No not matched with Invoice (${bill.invoice_mobile} vs ${bill.user_phone?.slice(-10)})`
            : 'Mob No not matched with Invoice'
        );
      } else {
        reasons.push(reason.substring(0, 50));
      }
    }
    
    return reasons.length > 0 ? reasons : ['Manual Review Required'];
  };

  const PendingBillCard = ({ bill }) => {
    const systemReasons = getSystemRejectionReason(bill);
    
    return (
      <Card className="border-slate-200 shadow-none overflow-hidden">
        <div className="grid md:grid-cols-3 gap-0">
          {/* Bill Image (lazy-loaded when admin clicks "View") */}
          <div
            className="bg-slate-100 p-4 flex items-center justify-center min-h-[200px] cursor-pointer hover:bg-slate-200/70 transition-colors"
            onClick={() => openReviewDialog(bill)}
            data-testid={`pending-bill-thumb-${bill.id}`}
          >
            <div className="text-slate-500 flex flex-col items-center text-center">
              <ImageIcon className="h-12 w-12 mb-2 text-slate-400" />
              <p className="text-xs font-medium">{bill.has_image === false ? 'No image' : 'Click to view bill image'}</p>
            </div>
          </div>

          {/* Bill Details */}
          <div className="p-4 md:col-span-2">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="font-semibold text-lg text-slate-900">
                  {bill.store_name || 'Unknown Store'}
                </h3>
                <p className="text-sm text-slate-500">Bill #{bill.bill_no || 'N/A'}</p>
              </div>
              {getStatusBadge(bill.status)}
            </div>

            {/* User Info */}
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div className="flex items-center gap-2 text-sm">
                <User className="h-4 w-4 text-slate-400" />
                <span>{bill.user_name || 'Unknown'}</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <Phone className="h-4 w-4 text-slate-400" />
                <span>{bill.user_phone}</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <QrCode className="h-4 w-4 text-slate-400" />
                <span>{bill.user_source?.replace('SRC_', '') || 'Direct'}</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <Calendar className="h-4 w-4 text-slate-400" />
                <span>{formatDate(bill.created_at)}</span>
              </div>
            </div>

            {/* Bill Details Grid */}
            <div className="grid grid-cols-3 gap-3 mb-4 p-3 bg-slate-50 rounded-lg">
              <div>
                <p className="text-xs text-slate-500">Amount</p>
                <p className="font-semibold">₹{bill.amount || 0}</p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Date</p>
                <p className="font-semibold">{bill.bill_date || 'N/A'}</p>
              </div>
              <div>
                <p className="text-xs text-slate-500">OCR Confidence</p>
                <p className={`font-semibold ${(bill.ocr_confidence || 0) >= 0.7 ? 'text-green-600' : (bill.ocr_confidence || 0) >= 0.5 ? 'text-yellow-600' : 'text-red-600'}`}>
                  {Math.round((bill.ocr_confidence || 0) * 100)}%
                </p>
              </div>
            </div>

            {/* System Rejection Reasons */}
            <div className="mb-4">
              <p className="text-xs text-slate-500 mb-2 flex items-center gap-1">
                <AlertCircleIcon className="h-3 w-3" />
                System Flags
              </p>
              <div className="flex flex-wrap gap-2">
                {systemReasons.map((reason, i) => (
                  <Badge key={i} variant="outline" className="bg-red-50 text-red-700 border-red-200">
                    {reason}
                  </Badge>
                ))}
              </div>
            </div>

            {/* OCR Notes */}
            {bill.ocr_raw_data?.extraction_notes && (
              <div className="mb-4 p-2 bg-blue-50 rounded text-sm text-blue-800">
                <strong>OCR Notes:</strong> {bill.ocr_raw_data.extraction_notes}
              </div>
            )}

            {/* Tampering Indicators */}
            {bill.ocr_raw_data?.tampering_indicators?.length > 0 && (
              <div className="mb-4 p-2 bg-red-50 rounded text-sm text-red-800">
                <strong>Tampering Indicators:</strong>
                <ul className="list-disc list-inside mt-1">
                  {bill.ocr_raw_data.tampering_indicators.map((item, i) => (
                    <li key={i}>{item}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-2">
              <Button 
                variant="outline" 
                className="flex-1"
                onClick={() => openReviewDialog(bill)}
              >
                <Eye className="h-4 w-4 mr-2" />
                Review & Process
              </Button>
              {(bill.status === 'pending_review' || bill.status === 'manual_review') && (
                <>
                  <Button 
                    variant="default"
                    className="bg-blue-600 hover:bg-blue-700"
                    onClick={() => reprocessBill(bill.id)}
                    data-testid={`reprocess-${bill.id}`}
                  >
                    <RefreshCw className="h-4 w-4 mr-2" />
                    Reprocess
                  </Button>
                  <Button
                    variant="outline"
                    className="border-purple-300 text-purple-700 hover:bg-purple-50"
                    onClick={() => editBrandBill(bill)}
                    data-testid={`edit-brand-${bill.id}`}
                    title="Fix brand name mismatch and resend to Fundle"
                  >
                    <Edit className="h-4 w-4 mr-2" />
                    Fix Brand
                  </Button>
                </>
              )}
            </div>
          </div>
        </div>
      </Card>
    );
  };

  return (
    <DashboardLayout title="Bill Management">
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <div className="flex items-center justify-between">
          <TabsList>
            <TabsTrigger value="pending" data-testid="tab-pending-bills" className="relative">
              Pending Review
              {pendingBills.length > 0 && (
                <span className="ml-2 px-2 py-0.5 bg-red-500 text-white text-xs rounded-full">
                  {pendingBills.length}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="all" data-testid="tab-all-bills">All Bills</TabsTrigger>
          </TabsList>

          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              className="gap-2 border-blue-300 text-blue-700 hover:bg-blue-50"
              onClick={() => { setBulkOpen(true); setBulkDryRun(null); setBulkResult(null); }}
              data-testid="open-bulk-reprocess-btn"
            >
              <RefreshCw className="h-4 w-4" />
              Bulk Reprocess
            </Button>
          </div>
        </div>
        <div className="flex items-center justify-end -mt-2">
          {activeTab === 'all' && (
            <div className="flex flex-wrap items-center gap-2">
              <Input
                type="date"
                value={dateFrom}
                onChange={(e) => { setDateFrom(e.target.value); setPagination(p => ({ ...p, skip: 0 })); }}
                className="w-[160px]"
                placeholder="From"
                data-testid="bills-date-from"
              />
              <span className="text-sm text-slate-400">→</span>
              <Input
                type="date"
                value={dateTo}
                onChange={(e) => { setDateTo(e.target.value); setPagination(p => ({ ...p, skip: 0 })); }}
                className="w-[160px]"
                placeholder="To"
                data-testid="bills-date-to"
              />
              {(dateFrom || dateTo) && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => { setDateFrom(''); setDateTo(''); setPagination(p => ({ ...p, skip: 0 })); }}
                  data-testid="bills-date-clear"
                >
                  Clear dates
                </Button>
              )}
              <Select value={statusFilter} onValueChange={(value) => {
                setStatusFilter(value);
                setPagination(prev => ({ ...prev, skip: 0 }));
              }}>
                <SelectTrigger className="w-[180px]" data-testid="status-filter">
                  <SelectValue placeholder="Filter by status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="auto_approved">Auto Approved</SelectItem>
                  <SelectItem value="manual_review">Manual Review</SelectItem>
                  <SelectItem value="pending_review">Pending Review</SelectItem>
                  <SelectItem value="approved">Approved</SelectItem>
                  <SelectItem value="rejected">Rejected</SelectItem>
                  <SelectItem value="duplicate">Duplicate</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}
        </div>

        {/* Pending Review Tab */}
        <TabsContent value="pending" className="space-y-4">
          {pendingBills.length === 0 ? (
            <Card className="border-slate-200 shadow-none">
              <CardContent className="py-12 text-center">
                <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-slate-900">All caught up!</h3>
                <p className="text-slate-500">No bills pending review</p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              {pendingBills.map(bill => (
                <PendingBillCard key={bill.id} bill={bill} />
              ))}
            </div>
          )}
        </TabsContent>

        {/* All Bills Tab */}
        <TabsContent value="all" className="space-y-4">
          {loading ? (
            <div className="space-y-4">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-32 skeleton rounded-lg" />
              ))}
            </div>
          ) : bills.length === 0 ? (
            <Card className="border-slate-200 shadow-none">
              <CardContent className="py-12 text-center text-slate-500">
                No bills found
              </CardContent>
            </Card>
          ) : (
            <>
              <div className="space-y-3">
                {bills.map(bill => (
                  <Card key={bill.id} className="border-slate-200 shadow-none">
                    <CardContent className="p-4">
                      <div className="flex items-center gap-4">
                        {/* Thumbnail placeholder — image loads on demand when admin clicks the row */}
                        <div
                          className="w-16 h-16 bg-slate-100 rounded-lg overflow-hidden flex-shrink-0 flex items-center justify-center cursor-pointer hover:bg-slate-200"
                          onClick={() => openReviewDialog(bill)}
                        >
                          <Receipt className="h-6 w-6 text-slate-400" />
                        </div>

                        {/* Details */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <h4 className="font-semibold truncate">{bill.store_name || 'Unknown Store'}</h4>
                            {getStatusBadge(bill.status)}
                          </div>
                          <div className="flex items-center gap-4 text-sm text-slate-500">
                            <span>₹{bill.amount || 0}</span>
                            <span>•</span>
                            <span>{bill.bill_no || 'N/A'}</span>
                            <span>•</span>
                            <span>{bill.user_phone}</span>
                          </div>
                          {/* Show rejection reason for rejected/pending bills */}
                          {(bill.status === 'rejected' || bill.status === 'pending_review' || bill.status === 'manual_review') && bill.rejection_reason && (
                            <div className="mt-1 text-xs text-red-600 flex items-center gap-1">
                              <AlertTriangle className="h-3 w-3" />
                              {bill.rejection_reason.substring(0, 60)}{bill.rejection_reason.length > 60 ? '...' : ''}
                            </div>
                          )}
                        </div>

                        {/* Points & Date */}
                        <div className="text-right">
                          <p className="font-semibold text-[#D4AF37]">+{bill.points_issued || 0} pts</p>
                          {bill.campaign_bonus > 0 && (
                            <p className="text-xs text-emerald-600 font-medium" title={(bill.applied_campaigns || []).map(c => c.name).join(', ')}>
                              incl. +{bill.campaign_bonus} campaign
                            </p>
                          )}
                          <p className="text-xs text-slate-500">{formatDate(bill.created_at)}</p>
                          {bill.processed_by && (
                            <div className="text-xs mt-1">
                              <p className="text-blue-600 font-medium">{bill.processed_by}</p>
                              {bill.processed_by_role && (
                                <p className="text-slate-400 capitalize">{bill.processed_by_role.replace('_', ' ')}</p>
                              )}
                            </div>
                          )}
                        </div>

                        {/* Actions */}
                        <div className="flex gap-2">
                          {(bill.status === 'manual_review' || bill.status === 'pending_review') && (
                            <>
                              <Button variant="outline" size="sm" onClick={() => openReviewDialog(bill)}>
                                Review
                              </Button>
                              <Button 
                                size="sm" 
                                className="bg-blue-600 hover:bg-blue-700"
                                onClick={() => reprocessBill(bill.id)}
                                data-testid={`reprocess-all-${bill.id}`}
                              >
                                <RefreshCw className="h-3 w-3 mr-1" />
                                Reprocess
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                className="border-purple-300 text-purple-700 hover:bg-purple-50"
                                onClick={() => editBrandBill(bill)}
                                data-testid={`edit-brand-all-${bill.id}`}
                                title="Fix brand name mismatch"
                              >
                                <Edit className="h-3 w-3 mr-1" />
                                Fix Brand
                              </Button>
                            </>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>

              {/* Pagination */}
              <div className="flex items-center justify-between pt-4">
                <p className="text-sm text-slate-500">
                  Showing {pagination.skip + 1} to {Math.min(pagination.skip + pagination.limit, pagination.total)} of {pagination.total} bills
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={pagination.skip === 0}
                    onClick={() => setPagination(prev => ({ ...prev, skip: Math.max(0, prev.skip - prev.limit) }))}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={pagination.skip + pagination.limit >= pagination.total}
                    onClick={() => setPagination(prev => ({ ...prev, skip: prev.skip + prev.limit }))}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </>
          )}
        </TabsContent>
      </Tabs>

      {/* Review Dialog */}
      <Dialog open={showReviewDialog} onOpenChange={setShowReviewDialog}>
        <DialogContent className="sm:max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-['Manrope']">Bill Review</DialogTitle>
          </DialogHeader>
          
          {selectedBill && (
            <div className="grid md:grid-cols-2 gap-6">
              {/* Bill Image */}
              <div className="bg-slate-50 rounded-lg p-4">
                {selectedBill.image_url ? (
                  <img 
                    src={selectedBill.image_url} 
                    alt="Bill" 
                    className="w-full max-h-[400px] object-contain rounded-lg"
                  />
                ) : (
                  <div className="h-[300px] flex items-center justify-center text-slate-400">
                    <ImageIcon className="h-16 w-16" />
                  </div>
                )}
              </div>

              {/* Bill Details & Actions */}
              <div className="space-y-4">
                {/* OCR Extracted Data */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-slate-50 rounded-lg p-3">
                    <p className="text-xs text-slate-500 mb-1">Store Name</p>
                    <p className="font-semibold">{selectedBill.store_name || 'N/A'}</p>
                  </div>
                  <div className="bg-slate-50 rounded-lg p-3">
                    <p className="text-xs text-slate-500 mb-1">Bill Number</p>
                    <p className="font-semibold">{selectedBill.bill_no || 'N/A'}</p>
                  </div>
                  <div className="bg-slate-50 rounded-lg p-3">
                    <p className="text-xs text-slate-500 mb-1">Date</p>
                    <p className="font-semibold">{selectedBill.bill_date || 'N/A'}</p>
                  </div>
                  <div className="bg-slate-50 rounded-lg p-3">
                    <p className="text-xs text-slate-500 mb-1">Amount</p>
                    <p className="font-semibold">₹{selectedBill.amount || 0}</p>
                  </div>
                </div>

                {/* User Info */}
                <div className="p-3 bg-blue-50 rounded-lg">
                  <p className="text-xs text-blue-600 mb-2">Customer Info</p>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div><strong>Name:</strong> {selectedBill.user_name || 'N/A'}</div>
                    <div><strong>Phone:</strong> {selectedBill.user_phone}</div>
                    <div><strong>Source:</strong> {selectedBill.user_source?.replace('SRC_', '') || 'Direct'}</div>
                    <div><strong>QR:</strong> {selectedBill.user_qr || 'N/A'}</div>
                  </div>
                </div>

                {/* System Rejection Reasons */}
                <div className="p-3 bg-red-50 rounded-lg">
                  <p className="text-xs text-red-600 mb-2 flex items-center gap-1">
                    <AlertCircleIcon className="h-3 w-3" />
                    System Analysis
                  </p>
                  <div className="flex flex-wrap gap-2 mb-2">
                    {getSystemRejectionReason(selectedBill).map((reason, i) => (
                      <Badge key={i} variant="outline" className="bg-white text-red-700 border-red-200">
                        {reason}
                      </Badge>
                    ))}
                  </div>
                  <p className="text-sm text-slate-600">
                    <strong>OCR Confidence:</strong> {Math.round((selectedBill.ocr_confidence || 0) * 100)}%
                  </p>
                </div>

                {/* Admin Actions */}
                <div className="space-y-3 pt-2 border-t">
                  <div>
                    <Label>Points to Award (optional override)</Label>
                    <Input
                      type="number"
                      placeholder={`Auto: ${Math.round((selectedBill.amount || 0) * 0.01)} pts (1% of ₹${selectedBill.amount || 0})`}
                      value={pointsOverride}
                      onChange={(e) => setPointsOverride(e.target.value)}
                      className="mt-1"
                    />
                  </div>

                  <div>
                    <Label>Rejection Reason (for customer)</Label>
                    <Textarea
                      placeholder="Enter reason to send to customer if rejecting..."
                      value={rejectionReason}
                      onChange={(e) => setRejectionReason(e.target.value)}
                      className="mt-1"
                      rows={2}
                    />
                  </div>

                  <div>
                    <Label>Admin Notes (internal only)</Label>
                    <Textarea
                      placeholder="Internal notes..."
                      value={adminNotes}
                      onChange={(e) => setAdminNotes(e.target.value)}
                      className="mt-1"
                      rows={2}
                    />
                  </div>

                  <div className="flex items-center space-x-2">
                    <Checkbox 
                      id="sendWhatsapp" 
                      checked={sendWhatsapp}
                      onCheckedChange={setSendWhatsapp}
                    />
                    <label htmlFor="sendWhatsapp" className="text-sm text-slate-600 flex items-center gap-1">
                      <MessageCircle className="h-4 w-4" />
                      Send WhatsApp notification to customer
                    </label>
                  </div>
                </div>
              </div>
            </div>
          )}

          <DialogFooter className="gap-2 mt-4">
            <Button
              variant="outline"
              onClick={() => setShowReviewDialog(false)}
              disabled={processingBill}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => processBill('reject')}
              disabled={processingBill}
              className="gap-2"
            >
              {processingBill ? (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
              ) : (
                <XCircle className="h-4 w-4" />
              )}
              Reject Bill
            </Button>
            <Button
              onClick={() => processBill('approve')}
              disabled={processingBill}
              className="gap-2 bg-green-600 hover:bg-green-700"
            >
              {processingBill ? (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
              ) : (
                <CheckCircle className="h-4 w-4" />
              )}
              Approve & Credit Points
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Fix Brand Dialog — searchable dropdown of Fundle-matched master brands */}
      <Dialog open={fixBrandOpen} onOpenChange={(o) => { setFixBrandOpen(o); if (!o) setFixBrandBill(null); }}>
        <DialogContent className="sm:max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-['Manrope']">Fix Brand Name</DialogTitle>
            <p className="text-sm text-slate-500 mt-1">
              Pick the exact brand name from Fundle&apos;s master list. Free-typed names
              often fail because Fundle needs an <strong>exact</strong> match.
            </p>
          </DialogHeader>

          {fixBrandBill && (
            <div className="space-y-3">
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm">
                <div className="grid grid-cols-2 gap-2">
                  <div><span className="text-slate-500">Bill:</span> <strong>{fixBrandBill.bill_no || 'N/A'}</strong></div>
                  <div><span className="text-slate-500">Amount:</span> <strong>₹{fixBrandBill.amount || 0}</strong></div>
                  <div className="col-span-2">
                    <span className="text-slate-500">OCR detected:</span> <strong className="text-amber-800">{fixBrandBill.store_name || 'Unknown'}</strong>
                  </div>
                </div>
              </div>

              <div>
                <Label className="text-xs">Search master brands ({brandsList.length}):</Label>
                <Input
                  autoFocus
                  placeholder="Type to filter…"
                  value={brandSearch}
                  onChange={(e) => setBrandSearch(e.target.value)}
                  data-testid="fix-brand-search"
                />
              </div>

              <div className="border border-slate-200 rounded-lg max-h-64 overflow-y-auto divide-y divide-slate-100" data-testid="fix-brand-list">
                {(() => {
                  const q = brandSearch.trim().toLowerCase();
                  const filtered = q
                    ? brandsList.filter((b) => (b.brand_name || '').toLowerCase().includes(q))
                    : brandsList;
                  if (filtered.length === 0) {
                    return <div className="p-3 text-sm text-slate-500">No matching brand in master. Type differently or use the &quot;Use exact text&quot; option below.</div>;
                  }
                  return filtered.slice(0, 100).map((b) => (
                    <button
                      key={b.brand_name}
                      type="button"
                      className="w-full text-left px-3 py-2 hover:bg-blue-50 flex items-center justify-between"
                      onClick={() => submitFixBrand(b.brand_name)}
                      disabled={fixBrandBusy}
                      data-testid={`fix-brand-pick-${b.brand_name}`}
                    >
                      <span className="text-sm font-medium">{b.brand_name}</span>
                      {b.category && <span className="text-xs text-slate-400">{b.category}</span>}
                    </button>
                  ));
                })()}
              </div>

              {brandSearch.trim() && (
                <div className="pt-2 border-t border-slate-200">
                  <Button
                    variant="outline"
                    className="w-full"
                    onClick={() => submitFixBrand(brandSearch)}
                    disabled={fixBrandBusy}
                    data-testid="fix-brand-use-typed"
                  >
                    Use exact text: <strong className="ml-1">&quot;{brandSearch.trim()}&quot;</strong>
                  </Button>
                  <p className="text-xs text-slate-400 mt-1">
                    Note: If this brand isn&apos;t in Fundle master, the reprocess will fail again.
                    Ask Fundle to add it first, or pick a similar brand above.
                  </p>
                </div>
              )}
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setFixBrandOpen(false)} disabled={fixBrandBusy}>
              Cancel
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Bulk Reprocess Dialog */}
      <Dialog open={bulkOpen} onOpenChange={setBulkOpen}>
        <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-['Manrope']">Bulk Reprocess Failed Bills</DialogTitle>
            <p className="text-sm text-slate-500 mt-1">
              Re-runs OCR + all rules on bills stuck in <strong>Manual Review</strong> or <strong>Pending Review</strong> in the selected window.
              Use this after fixing an outage (e.g. missing OCR key).
            </p>
          </DialogHeader>

          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">From date</Label>
                <Input
                  type="date"
                  value={bulkFrom}
                  onChange={(e) => setBulkFrom(e.target.value)}
                  data-testid="bulk-from-date"
                />
              </div>
              <div>
                <Label className="text-xs">To date</Label>
                <Input
                  type="date"
                  value={bulkTo}
                  onChange={(e) => setBulkTo(e.target.value)}
                  data-testid="bulk-to-date"
                />
              </div>
            </div>

            <div className="flex items-center gap-3 flex-wrap">
              <div className="flex items-center space-x-2">
                <Checkbox id="bulk-re-ocr" checked={bulkReOcr} onCheckedChange={setBulkReOcr} />
                <label htmlFor="bulk-re-ocr" className="text-sm">Re-run OCR on bill image</label>
              </div>
              <div className="flex items-center space-x-2">
                <Checkbox id="bulk-wa" checked={bulkSendWA} onCheckedChange={setBulkSendWA} />
                <label htmlFor="bulk-wa" className="text-sm">Send WhatsApp on approval</label>
              </div>
              <div className="flex items-center space-x-2">
                <Checkbox id="bulk-force-reject" checked={bulkForceOnReject} onCheckedChange={setBulkForceOnReject} data-testid="bulk-force-on-reject" />
                <label htmlFor="bulk-force-reject" className="text-sm font-medium text-amber-700">Auto force-credit if Fundle rejects</label>
              </div>
            </div>
            <p className="text-xs text-slate-500 pl-1">
              Point 10: With &ldquo;Auto force-credit&rdquo; ON, any bill Fundle still rejects (e.g. brand-mismatch) is credited locally using the tier × amount earn-rate — so June&apos;s stuck bills clear in one pass.
            </p>

            {/* Dry-run preview */}
            {bulkDryRun && (
              <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 max-h-60 overflow-y-auto" data-testid="bulk-dry-run-preview">
                <p className="text-sm font-semibold mb-2">
                  Dry-run preview — {bulkDryRun.candidates} candidate bill(s)
                </p>
                {(bulkDryRun.bills || []).slice(0, 50).map((b) => (
                  <div key={b.id} className="text-xs flex items-center justify-between border-b border-slate-100 py-1">
                    <span className="truncate">{b.user_phone} • {b.store_name || 'Unknown'} • ₹{b.amount || 0}</span>
                    <span className="text-slate-400">{(b.created_at || '').slice(0, 10)}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Live progress */}
            {bulkProgress && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3" data-testid="bulk-progress">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-semibold text-blue-800">
                    Processing… {bulkProgress.processed} / {bulkProgress.total}
                  </p>
                  <span className="text-xs text-blue-600">
                    Don’t close this window
                  </span>
                </div>
                <div className="w-full h-2 bg-blue-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-600 transition-all duration-500"
                    style={{ width: `${bulkProgress.total ? Math.round((bulkProgress.processed / bulkProgress.total) * 100) : 0}%` }}
                  />
                </div>
                {bulkProgress.summary && (
                  <div className="grid grid-cols-4 gap-2 mt-3 text-xs">
                    <div><span className="text-slate-500">Approved:</span> <strong className="text-green-700">{bulkProgress.summary.approved || 0}</strong></div>
                    <div><span className="text-slate-500">Rejected:</span> <strong className="text-red-700">{bulkProgress.summary.rejected || 0}</strong></div>
                    <div><span className="text-slate-500">Pending:</span> <strong className="text-amber-700">{bulkProgress.summary.kept_pending || 0}</strong></div>
                    <div><span className="text-slate-500">Skipped:</span> <strong className="text-slate-700">{bulkProgress.summary.skipped || 0}</strong></div>
                  </div>
                )}
              </div>
            )}

            {/* Execution result */}
            {bulkResult && (
              <div className="bg-green-50 border border-green-200 rounded-lg p-3" data-testid="bulk-result">
                <p className="text-sm font-semibold mb-2 text-green-800">Reprocess complete</p>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                  <div><span className="text-slate-500">Approved:</span> <strong>{bulkResult.summary?.approved || 0}</strong></div>
                  <div><span className="text-slate-500">Rejected:</span> <strong>{bulkResult.summary?.rejected || 0}</strong></div>
                  <div><span className="text-slate-500">Pending:</span> <strong>{bulkResult.summary?.kept_pending || 0}</strong></div>
                  <div><span className="text-slate-500">Skipped:</span> <strong>{bulkResult.summary?.skipped || 0}</strong></div>
                </div>
                <p className="text-xs mt-2 text-green-700">
                  Total points credited: <strong>{bulkResult.total_points_credited || 0}</strong>
                </p>
              </div>
            )}
          </div>

          <DialogFooter className="gap-2 mt-4">
            <Button variant="outline" onClick={() => setBulkOpen(false)} disabled={bulkRunning}>
              Close
            </Button>
            <Button
              variant="outline"
              onClick={() => callBulkReprocess(true)}
              disabled={bulkRunning || !bulkFrom}
              data-testid="bulk-dry-run-btn"
              className="gap-2"
            >
              {bulkRunning ? <div className="animate-spin h-4 w-4 border-b-2 border-slate-700 rounded-full" /> : <Eye className="h-4 w-4" />}
              Preview Candidates
            </Button>
            <Button
              onClick={() => callBulkReprocess(false)}
              disabled={bulkRunning || !bulkFrom}
              className="gap-2 bg-blue-600 hover:bg-blue-700"
              data-testid="bulk-run-btn"
            >
              {bulkRunning ? <div className="animate-spin h-4 w-4 border-b-2 border-white rounded-full" /> : <RefreshCw className="h-4 w-4" />}
              Run Reprocess
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  );
};

export default Bills;
