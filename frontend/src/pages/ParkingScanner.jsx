import React, { useState, useEffect, useRef } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import { useAuth } from '../App';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { toast } from 'sonner';
import { Camera, CheckCircle2, XCircle, Clock, Car, QrCode, AlertTriangle, RefreshCw } from 'lucide-react';

const ParkingScanner = () => {
  const { API_URL, token } = useAuth();
  const [scanning, setScanning] = useState(false);
  const [manualCode, setManualCode] = useState('');
  const [validationResult, setValidationResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);

  // Start camera for QR scanning
  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' }
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.play();
      }
      setScanning(true);
      toast.success('Camera started! Point at a parking QR code.');
    } catch (err) {
      console.error('Camera error:', err);
      toast.error('Could not access camera. Please use manual entry.');
    }
  };

  // Stop camera
  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    setScanning(false);
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }
    };
  }, []);

  // Validate parking code
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
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ scanned_by: 'counter_staff' })
      });
      
      const data = await response.json();
      setValidationResult(data);
      
      if (data.valid) {
        toast.success('Parking validated successfully!');
        stopCamera();
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

  // Handle manual code submission
  const handleManualSubmit = (e) => {
    e.preventDefault();
    validateCode(manualCode);
  };

  // Reset for new scan
  const resetScanner = () => {
    setValidationResult(null);
    setManualCode('');
  };

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
              <Badge variant="outline" className="border-white/30 text-white">
                {scanning ? 'Camera Active' : 'Ready'}
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
                {scanning ? (
                  <div className="relative">
                    <video 
                      ref={videoRef} 
                      className="w-full rounded-lg bg-slate-900"
                      autoPlay 
                      playsInline
                      data-testid="camera-video"
                    />
                    <canvas ref={canvasRef} className="hidden" />
                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                      <div className="w-48 h-48 border-2 border-white/50 rounded-lg"></div>
                    </div>
                    <Button 
                      variant="destructive" 
                      className="mt-4 w-full"
                      onClick={stopCamera}
                      data-testid="stop-camera-btn"
                    >
                      Stop Camera
                    </Button>
                    <p className="text-center text-sm text-slate-500 mt-2">
                      <AlertTriangle className="inline h-4 w-4 mr-1" />
                      Camera scanning requires manual code entry. Please use the form below.
                    </p>
                  </div>
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
              <li>Enter the session code (PKG-...) in the manual entry field</li>
              <li>Click "Validate" to mark their parking exit</li>
              <li>Confirm the validation result shows "EXIT APPROVED"</li>
            </ol>
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
};

export default ParkingScanner;
