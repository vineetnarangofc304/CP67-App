import React, { useState, useEffect, useRef, useCallback } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import { useAuth } from '../App';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { toast } from 'sonner';
import { Camera, CheckCircle2, XCircle, Clock, Car, QrCode, RefreshCw, StopCircle, Loader2 } from 'lucide-react';

const SCANNER_CONTAINER_ID = 'parking-qr-reader';

const ParkingScanner = () => {
  const { API_URL, token } = useAuth();
  const [scannerState, setScannerState] = useState('idle'); // idle | starting | active | error
  const [manualCode, setManualCode] = useState('');
  const [validationResult, setValidationResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [cameraError, setCameraError] = useState(null);
  const scannerRef = useRef(null);
  const mountedRef = useRef(true);

  // Cleanup on unmount
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (scannerRef.current) {
        try { scannerRef.current.stop().catch(() => {}); } catch (e) {}
        try { scannerRef.current.clear(); } catch (e) {}
        scannerRef.current = null;
      }
    };
  }, []);

  // When scannerState becomes 'starting', the container is now visible in DOM.
  // We use this effect to actually initialize the scanner AFTER React renders the visible container.
  useEffect(() => {
    if (scannerState !== 'starting') return;

    let cancelled = false;

    const initScanner = async () => {
      try {
        const { Html5Qrcode } = await import('html5-qrcode');

        // Ensure container exists in DOM
        const container = document.getElementById(SCANNER_CONTAINER_ID);
        if (!container) {
          throw new Error('Scanner container not found in DOM');
        }

        if (cancelled) return;

        const scanner = new Html5Qrcode(SCANNER_CONTAINER_ID);
        scannerRef.current = scanner;

        const qrboxFunction = (viewfinderWidth, viewfinderHeight) => {
          const minEdge = Math.min(viewfinderWidth, viewfinderHeight);
          const size = Math.floor(minEdge * 0.7);
          return { width: size, height: size };
        };

        await scanner.start(
          { facingMode: 'environment' },
          {
            fps: 10,
            qrbox: qrboxFunction,
            rememberLastUsedCamera: true,
            showTorchButtonIfSupported: true
          },
          (decodedText) => {
            if (!mountedRef.current) return;
            const code = extractParkingCode(decodedText);
            if (code) {
              toast.success(`QR Code scanned: ${code}`);
              doStopCamera();
              validateCode(code);
            }
          },
          () => {} // ignore per-frame scan miss
        );

        if (!cancelled && mountedRef.current) {
          setScannerState('active');
          toast.success('Camera ready! Point at a parking QR code.');
        }
      } catch (err) {
        console.error('Camera init error:', err);
        if (cancelled || !mountedRef.current) return;

        const errStr = String(err);
        let msg = 'Could not access camera. Please use manual entry below.';
        if (errStr.includes('NotAllowed') || errStr.includes('Permission')) {
          msg = 'Camera access denied. Please allow camera permission in your browser settings and reload.';
        } else if (errStr.includes('NotFound') || errStr.includes('Requested device not found')) {
          msg = 'No camera found on this device.';
        } else if (errStr.includes('NotReadable') || errStr.includes('Could not start video source')) {
          msg = 'Camera is in use by another app. Close other apps using the camera and try again.';
        }

        setCameraError(msg);
        setScannerState('error');
        toast.error('Could not access camera');
      }
    };

    // Small delay ensures React has committed the DOM with the visible container
    const timer = setTimeout(initScanner, 150);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [scannerState]);

  const doStopCamera = useCallback(() => {
    if (scannerRef.current) {
      scannerRef.current.stop().then(() => {
        try { scannerRef.current?.clear(); } catch (e) {}
        scannerRef.current = null;
      }).catch(() => {
        scannerRef.current = null;
      });
    }
    setScannerState('idle');
  }, []);

  const startCamera = () => {
    setCameraError(null);
    // Set to 'starting' — this makes the container div visible in DOM.
    // The useEffect above will then init the scanner after React renders.
    setScannerState('starting');
  };

  const extractParkingCode = (text) => {
    const match = text.match(/PKG-[\w]+-[\w]+/i);
    if (match) return match[0].toUpperCase();
    const urlMatch = text.match(/code=(PKG-[\w]+-[\w]+)/i);
    if (urlMatch) return urlMatch[1].toUpperCase();
    if (text.startsWith('PKG')) return text.toUpperCase();
    return text;
  };

  const validateCode = async (code) => {
    if (!code || code.trim() === '') {
      toast.error('Please enter a parking code');
      return;
    }
    setLoading(true);
    setValidationResult(null);
    try {
      const response = await fetch(`${API_URL}/parking/validate/${code.trim()}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scanned_by: 'counter_staff' })
      });
      const data = await response.json();
      setValidationResult(data);
      if (data.valid) {
        toast.success('Parking validated successfully!');
      } else {
        toast.error(data.message || 'Validation failed');
      }
    } catch (err) {
      console.error('Validation error:', err);
      toast.error('Failed to validate parking code');
    } finally {
      setLoading(false);
    }
  };

  const handleManualSubmit = (e) => {
    e.preventDefault();
    validateCode(manualCode);
  };

  const resetScanner = () => {
    setValidationResult(null);
    setManualCode('');
  };

  const isCameraVisible = scannerState === 'starting' || scannerState === 'active';

  return (
    <DashboardLayout title="Parking Scanner">
      <div className="max-w-2xl mx-auto space-y-6">
        {/* Scanner Status Card */}
        <Card className="bg-gradient-to-br from-slate-900 to-slate-800 text-white border-0">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 bg-white/10 rounded-xl flex items-center justify-center">
                  <Car className="h-6 w-6" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold">Exit Validation Scanner</h2>
                  <p className="text-sm text-slate-300">Scan customer QR at parking exit</p>
                </div>
              </div>
              <Badge variant="outline" className="border-white/30 text-white" data-testid="scanner-status">
                {scannerState === 'active' ? 'Camera Active' : scannerState === 'starting' ? 'Starting...' : 'Ready'}
              </Badge>
            </div>
          </CardContent>
        </Card>

        {/* Validation Result */}
        {validationResult && (
          <Card className={`border-2 ${validationResult.valid ? 'border-green-500 bg-green-50' : 'border-red-500 bg-red-50'}`}>
            <CardContent className="pt-6">
              <div className="flex items-start gap-4">
                {validationResult.valid ? (
                  <CheckCircle2 className="h-12 w-12 text-green-600 flex-shrink-0" />
                ) : (
                  <XCircle className="h-12 w-12 text-red-600 flex-shrink-0" />
                )}
                <div className="flex-1">
                  <h3 className={`text-xl font-bold ${validationResult.valid ? 'text-green-700' : 'text-red-700'}`}>
                    {validationResult.valid ? 'EXIT APPROVED' : 'VALIDATION FAILED'}
                  </h3>
                  <p className={`text-sm ${validationResult.valid ? 'text-green-600' : 'text-red-600'}`}>
                    {validationResult.message}
                  </p>
                  {validationResult.valid && (
                    <div className="mt-4 grid grid-cols-2 gap-4">
                      <div className="bg-white rounded-lg p-3">
                        <p className="text-xs text-slate-500">Session Code</p>
                        <p className="font-mono font-bold text-slate-900">{validationResult.session_code}</p>
                      </div>
                      <div className="bg-white rounded-lg p-3">
                        <p className="text-xs text-slate-500">Mobile Number</p>
                        <p className="font-mono font-bold text-slate-900">{validationResult.mobile_number || 'N/A'}</p>
                      </div>
                      <div className="bg-white rounded-lg p-3">
                        <p className="text-xs text-slate-500">Entry Time</p>
                        <p className="font-semibold text-slate-900">{validationResult.entry_time_display}</p>
                      </div>
                      <div className="bg-white rounded-lg p-3">
                        <p className="text-xs text-slate-500">Exit Time</p>
                        <p className="font-semibold text-slate-900">{validationResult.exit_time_display}</p>
                      </div>
                      <div className="col-span-2 bg-white rounded-lg p-3 text-center">
                        <p className="text-xs text-slate-500">Duration</p>
                        <p className="text-2xl font-bold text-slate-900">{validationResult.duration_display}</p>
                      </div>
                    </div>
                  )}
                  <Button
                    onClick={resetScanner}
                    className="mt-4 w-full"
                    variant={validationResult.valid ? "default" : "destructive"}
                    data-testid="scan-next-btn"
                  >
                    <RefreshCw className="h-4 w-4 mr-2" />
                    Scan Next Vehicle
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Scanner Interface */}
        {!validationResult && (
          <>
            {/* Camera View */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Camera className="h-5 w-5" />
                  Camera Scanner
                </CardTitle>
                <CardDescription>
                  Point the camera at the customer's parking QR code
                </CardDescription>
              </CardHeader>
              <CardContent>
                {cameraError && (
                  <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700" data-testid="camera-error">
                    {cameraError}
                  </div>
                )}

                {/* 
                  QR Scanner container — MUST be visible in DOM before html5-qrcode starts.
                  We show it when scannerState is 'starting' or 'active'.
                  When idle, it's not rendered at all.
                */}
                {isCameraVisible && (
                  <div
                    id={SCANNER_CONTAINER_ID}
                    data-testid="qr-scanner-container"
                    style={{ width: '100%', minHeight: '300px' }}
                    className="rounded-lg overflow-hidden bg-black"
                  />
                )}

                {scannerState === 'starting' && (
                  <div className="flex items-center justify-center gap-2 mt-4 text-sm text-slate-500">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Starting camera...
                  </div>
                )}

                {isCameraVisible ? (
                  <Button
                    variant="destructive"
                    className="mt-4 w-full"
                    onClick={doStopCamera}
                    data-testid="stop-camera-btn"
                  >
                    <StopCircle className="h-4 w-4 mr-2" />
                    Stop Camera
                  </Button>
                ) : (
                  <Button
                    className="w-full h-24 text-lg"
                    onClick={startCamera}
                    data-testid="start-camera-btn"
                  >
                    <Camera className="h-6 w-6 mr-3" />
                    Start Camera Scanner
                  </Button>
                )}
              </CardContent>
            </Card>

            {/* Manual Entry */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <QrCode className="h-5 w-5" />
                  Manual Code Entry
                </CardTitle>
                <CardDescription>
                  Enter the parking session code manually (e.g., PKG-143022-A1B2C3)
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleManualSubmit} className="flex gap-3">
                  <Input
                    placeholder="PKG-XXXXXX-XXXXXX"
                    value={manualCode}
                    onChange={(e) => setManualCode(e.target.value.toUpperCase())}
                    className="font-mono text-lg"
                    data-testid="manual-code-input"
                  />
                  <Button
                    type="submit"
                    disabled={loading || !manualCode}
                    className="px-8"
                    data-testid="validate-btn"
                  >
                    {loading ? (
                      <>
                        <Clock className="h-4 w-4 mr-2 animate-spin" />
                        Validating...
                      </>
                    ) : (
                      'Validate'
                    )}
                  </Button>
                </form>
              </CardContent>
            </Card>
          </>
        )}

        {/* Instructions */}
        <Card className="bg-slate-50 border-slate-200">
          <CardContent className="pt-6">
            <h4 className="font-semibold text-slate-700 mb-2">Instructions:</h4>
            <ol className="text-sm text-slate-600 space-y-1 list-decimal list-inside">
              <li>Ask the customer to show their parking QR code on WhatsApp</li>
              <li>Click "Start Camera Scanner" and point at the QR code</li>
              <li>The code will be detected automatically and validated</li>
              <li>Or enter the session code (PKG-...) manually below</li>
              <li>Confirm the validation result shows "EXIT APPROVED"</li>
            </ol>
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
};

export default ParkingScanner;
