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
  Send
} from 'lucide-react';

const Bills = () => {
  const { token, API_URL } = useAuth();
  const [bills, setBills] = useState([]);
  const [pendingBills, setPendingBills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');
  const [pagination, setPagination] = useState({ skip: 0, limit: 20, total: 0 });
  const [selectedBill, setSelectedBill] = useState(null);
  const [showReviewDialog, setShowReviewDialog] = useState(false);
  const [processingBill, setProcessingBill] = useState(false);
  const [rejectionReason, setRejectionReason] = useState('');
  const [adminNotes, setAdminNotes] = useState('');
  const [pointsOverride, setPointsOverride] = useState('');
  const [sendWhatsapp, setSendWhatsapp] = useState(true);
  const [activeTab, setActiveTab] = useState('pending');

  useEffect(() => {
    fetchBills();
    fetchPendingBills();
  }, [pagination.skip, statusFilter]);

  const fetchBills = async () => {
    setLoading(true);
    try {
      let url = `${API_URL}/bills?skip=${pagination.skip}&limit=${pagination.limit}`;
      if (statusFilter && statusFilter !== 'all') url += `&status=${statusFilter}`;
      
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

  const openReviewDialog = (bill) => {
    setSelectedBill(bill);
    setRejectionReason('');
    setAdminNotes('');
    setPointsOverride('');
    setSendWhatsapp(true);
    setShowReviewDialog(true);
  };

  const processBill = async (action) => {
    if (!selectedBill) return;
    
    setProcessingBill(true);
    try {
      const body = { 
        bill_id: selectedBill.id, 
        action,
        send_whatsapp: sendWhatsapp
      };
      
      if (action === 'reject' && rejectionReason) {
        body.rejection_reason = rejectionReason;
      }
      if (adminNotes) {
        body.admin_notes = adminNotes;
      }
      if (action === 'approve' && pointsOverride) {
        body.points_override = parseFloat(pointsOverride);
      }

      const response = await fetch(`${API_URL}/bills/${selectedBill.id}/process`, {
        method: 'POST',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(body)
      });

      if (response.ok) {
        const result = await response.json();
        toast.success(
          action === 'approve' 
            ? `Bill approved! ${result.points_issued} points credited.${result.whatsapp_sent ? ' WhatsApp sent.' : ''}`
            : `Bill rejected.${result.whatsapp_sent ? ' WhatsApp notification sent.' : ''}`
        );
        fetchBills();
        fetchPendingBills();
        setShowReviewDialog(false);
        setSelectedBill(null);
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to process bill');
      }
    } catch (error) {
      toast.error('Failed to process bill');
    } finally {
      setProcessingBill(false);
    }
  };

  const reprocessBill = async (billId) => {
    try {
      const response = await fetch(`${API_URL}/bills/${billId}/reprocess`, {
        method: 'POST',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      const result = await response.json();
      
      if (result.success) {
        toast.success(`Bill reprocessed! ${result.points_earned} points credited.`);
        fetchBills();
        fetchPendingBills();
      } else {
        toast.error(result.error || 'Reprocess failed - brand may still not be in Fundle');
      }
    } catch (error) {
      toast.error('Failed to reprocess bill');
    }
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
          {/* Bill Image */}
          <div className="bg-slate-100 p-4 flex items-center justify-center min-h-[200px]">
            {bill.image_url ? (
              <img 
                src={bill.image_url} 
                alt="Bill" 
                className="max-w-full max-h-[250px] object-contain rounded-lg shadow-md cursor-pointer hover:opacity-90"
                onClick={() => openReviewDialog(bill)}
              />
            ) : (
              <div className="text-slate-400 flex flex-col items-center">
                <ImageIcon className="h-16 w-16 mb-2" />
                <span>No image</span>
              </div>
            )}
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
                <Button 
                  variant="default"
                  className="bg-blue-600 hover:bg-blue-700"
                  onClick={() => reprocessBill(bill.id)}
                  data-testid={`reprocess-${bill.id}`}
                >
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Reprocess
                </Button>
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

          {activeTab === 'all' && (
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
                <SelectItem value="approved">Approved</SelectItem>
                <SelectItem value="rejected">Rejected</SelectItem>
                <SelectItem value="duplicate">Duplicate</SelectItem>
              </SelectContent>
            </Select>
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
                        {/* Thumbnail */}
                        <div className="w-16 h-16 bg-slate-100 rounded-lg overflow-hidden flex-shrink-0">
                          {bill.image_url ? (
                            <img src={bill.image_url} alt="Bill" className="w-full h-full object-cover" />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center">
                              <Receipt className="h-6 w-6 text-slate-400" />
                            </div>
                          )}
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
    </DashboardLayout>
  );
};

export default Bills;
