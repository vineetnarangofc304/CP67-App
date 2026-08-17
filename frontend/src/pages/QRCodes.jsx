import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '../components/DashboardLayout';
import { useAuth } from '../App';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { toast } from 'sonner';
import { 
  QrCode, 
  Download, 
  ExternalLink, 
  MapPin,
  Eye,
  Users,
  Receipt,
  TrendingUp,
  ArrowLeft,
  X,
  Phone,
  Calendar,
  Car,
  CheckCircle2,
  Clock
} from 'lucide-react';

const QRCodes = () => {
  const { token, API_URL } = useAuth();
  const navigate = useNavigate();
  const [qrCodes, setQrCodes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedQR, setSelectedQR] = useState(null);
  const [qrImage, setQrImage] = useState(null);
  const [generatingQR, setGeneratingQR] = useState(false);
  const [showFullScreen, setShowFullScreen] = useState(false);
  const [qrUsers, setQrUsers] = useState([]);
  const [loadingUsers, setLoadingUsers] = useState(false);

  const [appQrStats, setAppQrStats] = useState(null);
  const [appQrRefreshedAt, setAppQrRefreshedAt] = useState(null);

  useEffect(() => {
    fetchQRCodes();
    fetchAppQrStats();
  }, []);

  const fetchAppQrStats = async () => {
    // Point 31: pull scan count for the Play Store QR
    try {
      const res = await fetch(`${API_URL}/admin/app-download-qr/stats`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        setAppQrStats(await res.json());
        setAppQrRefreshedAt(new Date());
      }
    } catch { /* ignore */ }
  };

  const fetchQRCodes = async () => {
    try {
      const response = await fetch(`${API_URL}/qr-codes`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setQrCodes(data);
      }
    } catch (error) {
      toast.error('Failed to load QR codes');
    } finally {
      setLoading(false);
    }
  };

  const generateQRImage = async (qrCodeId) => {
    setGeneratingQR(true);
    try {
      const response = await fetch(`${API_URL}/qr-codes/${qrCodeId}/generate`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setQrImage(data);
      }
    } catch (error) {
      toast.error('Failed to generate QR code');
    } finally {
      setGeneratingQR(false);
    }
  };

  const downloadQR = () => {
    if (!qrImage) return;
    const link = document.createElement('a');
    link.href = qrImage.image_base64;
    link.download = `${qrImage.qr_code_id}_${qrImage.location.replace(/\s+/g, '_')}.png`;
    link.click();
    toast.success('QR code downloaded!');
  };

  const copyWhatsAppLink = (link) => {
    navigator.clipboard.writeText(link);
    toast.success('WhatsApp link copied!');
  };

  const [qrBills, setQrBills] = useState([]);
  const [loadingBills, setLoadingBills] = useState(false);
  const [showBillsModal, setShowBillsModal] = useState(false);

  const openQRDetails = async (qr) => {
    setSelectedQR(qr);
    setShowFullScreen(true);
    generateQRImage(qr.qr_code_id);
    fetchQRUsers(qr.source_code);
  };

  const fetchQRUsers = async (sourceCode) => {
    setLoadingUsers(true);
    try {
      const response = await fetch(`${API_URL}/users?source=${sourceCode}&limit=50`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setQrUsers(data.users || []);
      }
    } catch (error) {
      console.error('Failed to fetch QR users:', error);
    } finally {
      setLoadingUsers(false);
    }
  };

  const fetchQRBills = async (qrCodeId) => {
    setLoadingBills(true);
    setShowBillsModal(true);
    try {
      const response = await fetch(`${API_URL}/bills/by-qr/${qrCodeId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setQrBills(data.bills || []);
      }
    } catch (error) {
      console.error('Failed to fetch QR bills:', error);
      toast.error('Failed to load bills');
    } finally {
      setLoadingBills(false);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric'
    });
  };

  if (loading) {
    return (
      <DashboardLayout title="QR Codes">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3, 4, 5].map(i => (
            <div key={i} className="h-48 bg-white rounded-lg skeleton" />
          ))}
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title="QR Codes">
      {/* Point 31: App Install QR + scan tracking */}
      <Card className="mb-6 border-emerald-200 bg-emerald-50/50 shadow-none" data-testid="app-install-qr-card">
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row items-start gap-6">
            <div className="flex-shrink-0 bg-white p-3 rounded-lg border border-emerald-200">
              {appQrStats?.qr_image_url ? (
                <img
                  src={appQrStats.qr_image_url}
                  alt="App Install QR"
                  width="160"
                  height="160"
                  data-testid="app-install-qr-image"
                />
              ) : (
                <div className="w-40 h-40 flex items-center justify-center text-slate-300"><QrCode size={40} /></div>
              )}
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-slate-900 text-lg">Play Store App Install QR</h3>
                <Badge className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100">Tracked</Badge>
              </div>
              <p className="text-sm text-slate-600 mt-1">
                Scans are redirected to the Play Store and counted below. Print this QR on flyers, standees or brand touchpoints.
              </p>
              <div className="grid grid-cols-2 gap-4 mt-4 max-w-md" data-testid="app-install-qr-stats">
                <div className="bg-white rounded-lg p-3 border border-emerald-200">
                  <div className="text-xs text-slate-500 uppercase">Total scans</div>
                  <div className="text-2xl font-bold text-emerald-700" data-testid="app-install-qr-total">{appQrStats?.total_scans ?? '—'}</div>
                </div>
                <div className="bg-white rounded-lg p-3 border border-emerald-200">
                  <div className="text-xs text-slate-500 uppercase">Today</div>
                  <div className="text-2xl font-bold text-emerald-700" data-testid="app-install-qr-today">{appQrStats?.today_scans ?? '—'}</div>
                </div>
              </div>
              <div className="flex flex-wrap gap-2 mt-4">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    if (!appQrStats?.qr_image_url) return;
                    const a = document.createElement('a');
                    a.href = appQrStats.qr_image_url;
                    a.download = 'cp67-app-install-qr.png';
                    document.body.appendChild(a); a.click(); a.remove();
                  }}
                  data-testid="download-app-qr-btn"
                >
                  <Download size={14} className="mr-1" /> Download PNG
                </Button>
                <Button size="sm" variant="outline" onClick={fetchAppQrStats} data-testid="refresh-app-qr-btn">
                  Refresh
                </Button>
                {appQrStats?.play_store_url && (
                  <a
                    href={appQrStats.play_store_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-sm text-emerald-700 underline px-3 py-1.5"
                    data-testid="open-play-store-link"
                  >
                    <ExternalLink size={14} /> Open Play Store
                  </a>
                )}
              </div>
              {appQrStats?.daily?.length > 0 && (
                <details className="mt-3 text-xs text-slate-600">
                  <summary className="cursor-pointer">Daily scans (last 30 days)</summary>
                  <ul className="mt-2 grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-1">
                    {appQrStats.daily.map(d => <li key={d.day}>{d.day}: <strong>{d.count}</strong></li>)}
                  </ul>
                </details>
              )}
              {appQrRefreshedAt && <p className="text-[11px] text-slate-400 mt-2">Last refreshed: {appQrRefreshedAt.toLocaleTimeString()}</p>}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Info Banner */}
      <Card className="mb-6 border-[#D4AF37] bg-[#D4AF37]/5 shadow-none">
        <CardContent className="pt-6">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 bg-[#D4AF37]/20 rounded-lg flex items-center justify-center flex-shrink-0">
              <QrCode className="h-5 w-5 text-[#D4AF37]" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-900 font-['Manrope']">QR Code Attribution System</h3>
              <p className="text-sm text-slate-600 mt-1">
                Each QR code contains a unique source code that tracks where users first scanned. 
                This data is permanently stored and used for analytics.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* QR Code Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {qrCodes.map((qr) => {
          const isParking = qr.category === 'parking';
          const conversionRate = qr.scans > 0 ? ((qr.registrations / qr.scans) * 100).toFixed(1) : 0;
          
          return (
            <Card 
              key={qr.qr_code_id} 
              className={`card-hover border-slate-200 shadow-none cursor-pointer ${isParking ? 'border-blue-300 bg-blue-50/30' : ''}`}
              data-testid={`qr-card-${qr.qr_code_id}`}
              onClick={() => openQRDetails(qr)}
            >
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <Badge variant="outline" className={`text-xs ${isParking ? 'border-blue-400 text-blue-600' : ''}`}>
                        {qr.qr_code_id}
                      </Badge>
                      {isParking && (
                        <Badge className="bg-blue-500 text-white text-xs">
                          <Car className="h-3 w-3 mr-1" />
                          Parking
                        </Badge>
                      )}
                    </div>
                    <CardTitle className="font-['Manrope'] text-lg flex items-center gap-2">
                      {isParking ? <Car className="h-4 w-4 text-blue-500" /> : <MapPin className="h-4 w-4 text-slate-400" />}
                      {qr.location}
                    </CardTitle>
                  </div>
                  {!isParking && (
                    <div className="text-right">
                      <p className="text-2xl font-bold text-slate-900">{conversionRate}%</p>
                      <p className="text-xs text-slate-500">Conversion</p>
                    </div>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                {/* Stats Grid - Different for parking vs loyalty */}
                {isParking ? (
                  <div className="grid grid-cols-3 gap-3 mb-4 py-4 border-y border-blue-100">
                    <div className="text-center">
                      <p className="text-lg font-semibold text-slate-900">{qr.scans}</p>
                      <p className="text-xs text-slate-500 flex items-center justify-center gap-1">
                        <Car className="h-3 w-3" /> Total
                      </p>
                    </div>
                    <div className="text-center">
                      <p className="text-lg font-semibold text-blue-600">{qr.parking_active || 0}</p>
                      <p className="text-xs text-slate-500 flex items-center justify-center gap-1">
                        <Clock className="h-3 w-3" /> Active
                      </p>
                    </div>
                    <div className="text-center">
                      <p className="text-lg font-semibold text-green-600">{qr.parking_completed || 0}</p>
                      <p className="text-xs text-slate-500 flex items-center justify-center gap-1">
                        <CheckCircle2 className="h-3 w-3" /> Done
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-4 gap-3 mb-4 py-4 border-y border-slate-100">
                    <div className="text-center">
                      <p className="text-lg font-semibold text-slate-900">{qr.scans}</p>
                      <p className="text-xs text-slate-500 flex items-center justify-center gap-1">
                        <Eye className="h-3 w-3" /> Scans
                      </p>
                    </div>
                    <div className="text-center">
                      <p className="text-lg font-semibold text-green-600">{qr.registrations}</p>
                      <p className="text-xs text-slate-500 flex items-center justify-center gap-1">
                        <Users className="h-3 w-3" /> New
                      </p>
                    </div>
                    <div className="text-center">
                      <p className="text-lg font-semibold text-blue-600">{qr.existing_customers || 0}</p>
                      <p className="text-xs text-slate-500 flex items-center justify-center gap-1">
                        <Users className="h-3 w-3" /> Existing
                      </p>
                    </div>
                    <div className="text-center">
                      <p className="text-lg font-semibold text-slate-900">{qr.bill_uploads}</p>
                      <p className="text-xs text-slate-500 flex items-center justify-center gap-1">
                        <Receipt className="h-3 w-3" /> Bills
                      </p>
                    </div>
                  </div>
                )}

                {/* Source Code */}
                <div className={`rounded-lg p-3 mb-4 ${isParking ? 'bg-blue-50' : 'bg-slate-50'}`}>
                  <p className="text-xs text-slate-500 mb-1">Source Code</p>
                  <code className="text-sm font-mono text-slate-900">{qr.source_code}</code>
                </div>
                
                {/* Parking Note */}
                {isParking && (
                  <div className="text-xs text-blue-600 mb-4 bg-blue-100/50 p-2 rounded">
                    ℹ️ This QR is for parking validation only. It does not affect loyalty registrations or points.
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className={`flex-1 ${isParking ? 'border-blue-300 hover:bg-blue-50' : ''}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      openQRDetails(qr);
                    }}
                    data-testid={`view-qr-${qr.qr_code_id}`}
                  >
                    <QrCode className="h-4 w-4 mr-2" />
                    View Details
                  </Button>
                  <Button 
                    variant="outline" 
                    size="sm"
                    className={isParking ? 'border-blue-300 hover:bg-blue-50' : ''}
                    onClick={(e) => {
                      e.stopPropagation();
                      copyWhatsAppLink(qr.whatsapp_link);
                    }}
                    data-testid={`copy-link-${qr.qr_code_id}`}
                  >
                    <ExternalLink className="h-4 w-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Summary Stats - Only for Loyalty QRs */}
      <Card className="mt-6 border-slate-200 shadow-none">
        <CardHeader>
          <CardTitle className="font-['Manrope']">Overall QR Performance (Loyalty Only)</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <div className="text-center p-4 bg-slate-50 rounded-lg">
              <p className="text-3xl font-bold text-slate-900 font-['Manrope']">
                {qrCodes.filter(qr => qr.category !== 'parking').reduce((sum, qr) => sum + qr.scans, 0)}
              </p>
              <p className="text-sm text-slate-500">Total Scans</p>
            </div>
            <div className="text-center p-4 bg-slate-50 rounded-lg">
              <p className="text-3xl font-bold text-slate-900 font-['Manrope']">
                {qrCodes.filter(qr => qr.category !== 'parking').reduce((sum, qr) => sum + qr.registrations, 0)}
              </p>
              <p className="text-sm text-slate-500">Total Registrations</p>
            </div>
            <div className="text-center p-4 bg-slate-50 rounded-lg">
              <p className="text-3xl font-bold text-slate-900 font-['Manrope']">
                {qrCodes.filter(qr => qr.category !== 'parking').reduce((sum, qr) => sum + qr.bill_uploads, 0)}
              </p>
              <p className="text-sm text-slate-500">Total Bill Uploads</p>
            </div>
            <div className="text-center p-4 bg-slate-50 rounded-lg">
              <p className="text-3xl font-bold text-[#D4AF37] font-['Manrope']">
                {(() => {
                  const loyaltyQRs = qrCodes.filter(qr => qr.category !== 'parking');
                  const totalScans = loyaltyQRs.reduce((sum, qr) => sum + qr.scans, 0);
                  const totalRegs = loyaltyQRs.reduce((sum, qr) => sum + qr.registrations, 0);
                  return totalScans > 0 ? ((totalRegs / totalScans) * 100).toFixed(1) : 0;
                })()}%
              </p>
              <p className="text-sm text-slate-500">Avg. Conversion Rate</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Full Screen QR Details View */}
      {showFullScreen && selectedQR && (
        <div className="fixed inset-0 z-50 bg-white overflow-y-auto">
          <div className="sticky top-0 bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between z-10">
            <div className="flex items-center gap-4">
              <Button 
                variant="ghost" 
                size="sm"
                onClick={() => {
                  setShowFullScreen(false);
                  setSelectedQR(null);
                  setQrImage(null);
                  setQrUsers([]);
                }}
              >
                <ArrowLeft className="h-4 w-4 mr-2" />
                Back to QR Codes
              </Button>
              <h2 className="text-xl font-bold font-['Manrope']">{selectedQR.location} - QR Details</h2>
            </div>
            <Button 
              variant="ghost" 
              size="icon"
              onClick={() => {
                setShowFullScreen(false);
                setSelectedQR(null);
                setQrImage(null);
                setQrUsers([]);
              }}
            >
              <X className="h-5 w-5" />
            </Button>
          </div>
          
          <div className="p-6 max-w-6xl mx-auto">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              {/* QR Code Display */}
              <div className="lg:col-span-1">
                <Card className="border-slate-200 shadow-none">
                  <CardHeader>
                    <CardTitle className="font-['Manrope']">QR Code</CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-col items-center">
                    {generatingQR ? (
                      <div className="w-48 h-48 bg-slate-100 rounded-lg animate-pulse flex items-center justify-center">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-900"></div>
                      </div>
                    ) : qrImage ? (
                      <>
                        <img src={qrImage.image_base64} alt="QR Code" className="w-48 h-48" />
                        <div className="flex gap-2 mt-4">
                          <Button onClick={downloadQR} size="sm" className="gap-2">
                            <Download className="h-4 w-4" />
                            Download
                          </Button>
                          <Button 
                            variant="outline" 
                            size="sm"
                            onClick={() => copyWhatsAppLink(qrImage.whatsapp_link)}
                            className="gap-2"
                          >
                            <ExternalLink className="h-4 w-4" />
                            Copy Link
                          </Button>
                        </div>
                      </>
                    ) : null}
                  </CardContent>
                </Card>

                {/* Stats */}
                <Card className="border-slate-200 shadow-none mt-6">
                  <CardHeader>
                    <CardTitle className="font-['Manrope']">Performance Stats</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex justify-between items-center p-3 bg-slate-50 rounded-lg">
                      <span className="text-slate-600">Total Scans</span>
                      <span className="text-2xl font-bold">{selectedQR.scans}</span>
                    </div>
                    <div className="flex justify-between items-center p-3 bg-slate-50 rounded-lg">
                      <span className="text-slate-600">Registrations</span>
                      <span className="text-2xl font-bold">{selectedQR.registrations}</span>
                    </div>

                {/* WhatsApp Link - for website embedding */}
                <Card className="border-green-200 shadow-none mt-6 bg-green-50">
                  <CardHeader>
                    <CardTitle className="font-['Manrope'] text-green-800 flex items-center gap-2">
                      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
                      </svg>
                      WhatsApp Link for Website
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm text-green-700 mb-3">Use this link on your website to start the WhatsApp registration flow:</p>
                    <div className="bg-white p-3 rounded-lg border border-green-200 break-all">
                      <code className="text-xs text-slate-700">{selectedQR.whatsapp_link}</code>
                    </div>
                    <Button 
                      className="mt-3 w-full bg-green-600 hover:bg-green-700"
                      onClick={() => copyWhatsAppLink(selectedQR.whatsapp_link)}
                    >
                      <ExternalLink className="h-4 w-4 mr-2" />
                      Copy Link
                    </Button>
                  </CardContent>
                </Card>
                    <div 
                      className="flex justify-between items-center p-3 bg-slate-50 rounded-lg cursor-pointer hover:bg-slate-100 transition-colors"
                      onClick={() => fetchQRBills(selectedQR.qr_code_id)}
                      data-testid="view-bills-btn"
                    >
                      <span className="text-slate-600 flex items-center gap-2">
                        Bill Uploads
                        <span className="text-xs text-blue-600">(Click to view)</span>
                      </span>
                      <span className="text-2xl font-bold text-blue-600">{selectedQR.bill_uploads}</span>
                    </div>
                    <div className="flex justify-between items-center p-3 bg-[#D4AF37]/10 rounded-lg">
                      <span className="text-slate-600">Conversion Rate</span>
                      <span className="text-2xl font-bold text-[#D4AF37]">
                        {selectedQR.scans > 0 ? ((selectedQR.registrations / selectedQR.scans) * 100).toFixed(1) : 0}%
                      </span>
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Users from this QR */}
              <div className="lg:col-span-2">
                <Card className="border-slate-200 shadow-none">
                  <CardHeader>
                    <CardTitle className="font-['Manrope'] flex items-center gap-2">
                      <Users className="h-5 w-5" />
                      Users from {selectedQR.location} ({qrUsers.length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {loadingUsers ? (
                      <div className="flex items-center justify-center py-8">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-900"></div>
                      </div>
                    ) : qrUsers.length > 0 ? (
                      <div className="space-y-3 max-h-[500px] overflow-y-auto">
                        {qrUsers.map((user) => (
                          <div key={user.id} className="flex items-center justify-between p-4 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors">
                            <div className="flex items-center gap-4">
                              <div className="w-10 h-10 bg-slate-200 rounded-full flex items-center justify-center">
                                <Users className="h-5 w-5 text-slate-500" />
                              </div>
                              <div>
                                <p className="font-semibold">{user.name || 'Unknown'}</p>
                                <p className="text-sm text-slate-500 flex items-center gap-2">
                                  <Phone className="h-3 w-3" />
                                  {user.phone}
                                </p>
                              </div>
                            </div>
                            <div className="text-right">
                              <p className="font-semibold text-[#D4AF37]">{Math.round(user.balance_points || 0).toLocaleString()} pts</p>
                              <p className="text-xs text-slate-500 flex items-center gap-1 justify-end">
                                <Calendar className="h-3 w-3" />
                                {formatDate(user.created_at)}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-slate-500 text-center py-8">No users registered from this QR code yet</p>
                    )}
                  </CardContent>
                </Card>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Bills Modal */}
      {showBillsModal && (
        <div className="fixed inset-0 z-[60] bg-black/50 flex items-center justify-center p-4" onClick={() => setShowBillsModal(false)}>
          <div className="bg-white rounded-xl max-w-4xl w-full max-h-[80vh] overflow-hidden" onClick={(e) => e.stopPropagation()}>
            <div className="p-4 border-b border-slate-200 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold">Bills from {selectedQR?.location}</h3>
                <p className="text-sm text-slate-500">{qrBills.length} bills uploaded</p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setShowBillsModal(false)}>
                <X className="h-5 w-5" />
              </Button>
            </div>
            <div className="p-4 overflow-y-auto max-h-[60vh]">
              {loadingBills ? (
                <div className="flex justify-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-900"></div>
                </div>
              ) : qrBills.length > 0 ? (
                <div className="space-y-3">
                  {qrBills.map((bill, index) => (
                    <div key={bill.id || index} className="border border-slate-200 rounded-lg p-4 hover:bg-slate-50">
                      <div className="flex items-start justify-between">
                        <div>
                          <p className="font-semibold text-slate-900">{bill.store_name || 'Unknown Store'}</p>
                          <p className="text-sm text-slate-500">Bill No: {bill.bill_no || 'N/A'}</p>
                          <p className="text-sm text-slate-500">
                            <Phone className="h-3 w-3 inline mr-1" />
                            {bill.user_phone || bill.user_name || 'N/A'}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-lg font-bold text-slate-900">₹{(bill.amount || 0).toLocaleString()}</p>
                          <p className="text-xs text-slate-500">{formatDate(bill.bill_date || bill.created_at)}</p>
                          <Badge className={`text-xs mt-1 ${
                            bill.status === 'approved' ? 'bg-green-100 text-green-700' :
                            bill.status === 'rejected' ? 'bg-red-100 text-red-700' :
                            'bg-yellow-100 text-yellow-700'
                          }`}>
                            {bill.status || 'pending'}
                          </Badge>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-slate-500 text-center py-8">No bills uploaded from this QR code yet</p>
              )}
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
};

export default QRCodes;
