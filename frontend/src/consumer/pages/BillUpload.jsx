import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowLeft, Camera, ImagePlus, Loader2, CheckCircle, AlertCircle, Upload, X, SwitchCamera, Zap } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';

export default function BillUpload() {
  const [preview, setPreview] = useState(null);
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState(null);
  const [facingMode, setFacingMode] = useState('environment');
  const fileRef = useRef();
  const cameraRef = useRef();
  const videoRef = useRef();
  const canvasRef = useRef();
  const streamRef = useRef(null);
  const navigate = useNavigate();
  const { token } = useConsumerAuth();

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setCameraActive(false);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }
      // Detach native camera callbacks
      try {
        delete window.__cp67OnCameraResult;
        delete window.__cp67OnCameraError;
      } catch { /* noop */ }
    };
  }, []);

  // Detect Android WebView native bridge (v1.8+)
  const hasNativeCamera = typeof window !== 'undefined'
    && window.AndroidBridge
    && typeof window.AndroidBridge.openCamera === 'function';

  // Direct native camera invocation (bypasses <input type="file" capture>
  // which Android WebView often ignores on newer devices).
  const openNativeCamera = () => {
    setCameraError(null);
    // Register one-shot callbacks that the native side will invoke
    window.__cp67OnCameraResult = (dataUrl) => {
      try {
        // dataUrl = "data:image/jpeg;base64,..."
        const arr = dataUrl.split(',');
        const mime = arr[0].match(/:(.*?);/)[1];
        const bstr = atob(arr[1]);
        let n = bstr.length;
        const u8 = new Uint8Array(n);
        while (n--) u8[n] = bstr.charCodeAt(n);
        const capturedFile = new File([u8], `bill_${Date.now()}.jpg`, { type: mime });
        setFile(capturedFile);
        setPreview(dataUrl);
        setResult(null);
      } catch (e) {
        setCameraError('Failed to load captured photo. Please try again.');
      }
    };
    window.__cp67OnCameraError = (reason) => {
      if (reason === 'cancelled') return; // user cancelled — no error UI
      setCameraError('Camera unavailable. Please try the Gallery option.');
    };
    try {
      window.AndroidBridge.openCamera();
    } catch (e) {
      setCameraError('Camera unavailable in this build. Please try Gallery.');
    }
  };

  const startCamera = async () => {
    setCameraError(null);
    try {
      // Stop any existing stream first
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }

      const constraints = {
        video: {
          facingMode: facingMode,
          width: { ideal: 1920 },
          height: { ideal: 1080 }
        },
        audio: false
      };

      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCameraActive(true);
    } catch (err) {
      console.error('Camera error:', err);
      if (err.name === 'NotAllowedError') {
        setCameraError('Camera access denied. Please allow camera permission in your browser settings.');
      } else if (err.name === 'NotFoundError') {
        setCameraError('No camera found on this device.');
      } else if (err.name === 'NotReadableError') {
        setCameraError('Camera is in use by another application.');
      } else {
        setCameraError('Could not access camera. Try uploading from gallery instead.');
      }
    }
  };

  const capturePhoto = () => {
    if (!videoRef.current || !canvasRef.current) return;

    const video = videoRef.current;
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0);

    canvas.toBlob((blob) => {
      if (blob) {
        const capturedFile = new File([blob], `bill_${Date.now()}.jpg`, { type: 'image/jpeg' });
        setFile(capturedFile);
        setPreview(canvas.toDataURL('image/jpeg', 0.9));
        stopCamera();
      }
    }, 'image/jpeg', 0.9);
  };

  const switchCamera = async () => {
    const newMode = facingMode === 'environment' ? 'user' : 'environment';
    setFacingMode(newMode);
    if (cameraActive) {
      stopCamera();
      // Small delay to ensure previous stream is fully released
      setTimeout(async () => {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: newMode, width: { ideal: 1920 }, height: { ideal: 1080 } },
            audio: false
          });
          streamRef.current = stream;
          if (videoRef.current) {
            videoRef.current.srcObject = stream;
            await videoRef.current.play();
          }
          setCameraActive(true);
        } catch (err) {
          setCameraError('Could not switch camera.');
        }
      }, 300);
    }
  };

  const handleFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    setResult(null);
    setCameraError(null);
    const reader = new FileReader();
    reader.onload = () => setPreview(reader.result);
    reader.readAsDataURL(f);
  };

  const uploadBill = async () => {
    if (!file) return;
    setUploading(true);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${API}/bills/upload`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData
      });
      const data = await res.json();
      if (res.ok) {
        setResult({ success: true, message: data.message || 'Bill uploaded successfully!', bill_id: data.bill_id });
      } else {
        setResult({ success: false, message: data.detail || 'Upload failed' });
      }
    } catch {
      setResult({ success: false, message: 'Network error. Please try again.' });
    }
    setUploading(false);
  };

  const reset = () => {
    setFile(null);
    setPreview(null);
    setResult(null);
    setCameraError(null);
    stopCamera();
  };

  return (
    <motion.div
      className="consumer-bill-upload"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      data-testid="bill-upload-screen"
    >
      <div className="bill-upload-header">
        <button className="bill-back" onClick={() => { stopCamera(); navigate(-1); }} data-testid="bill-back-btn">
          <ArrowLeft size={22} />
        </button>
        <h1>Upload Bill</h1>
      </div>

      {/* Hidden canvas for photo capture */}
      <canvas ref={canvasRef} style={{ display: 'none' }} />

      <AnimatePresence mode="wait">
        {/* Camera viewfinder */}
        {cameraActive && !preview && !result && (
          <motion.div className="bill-camera-view" key="camera" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <div className="camera-viewfinder" data-testid="camera-viewfinder">
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                data-testid="camera-video"
                className="camera-video"
              />
              <div className="camera-overlay">
                <div className="camera-frame" />
              </div>
            </div>
            <div className="camera-controls">
              <button className="camera-control-btn" onClick={stopCamera} data-testid="close-camera-btn">
                <X size={24} />
              </button>
              <button className="camera-capture-btn" onClick={capturePhoto} data-testid="capture-btn">
                <div className="capture-ring" />
              </button>
              <button className="camera-control-btn" onClick={switchCamera} data-testid="switch-camera-btn">
                <SwitchCamera size={24} />
              </button>
            </div>
          </motion.div>
        )}

        {/* Initial state - choose camera or gallery */}
        {!cameraActive && !preview && !result && (
          <motion.div className="bill-upload-area" key="capture" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <div className="bill-capture-zone" data-testid="bill-capture-zone">
              <div className="capture-icon">
                <Camera size={40} />
              </div>
              <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: 24, fontWeight: 700, marginBottom: 12 }}>Great Choice!</h2>

              <div style={{ textAlign: 'left', padding: '0 8px', marginBottom: 16, color: 'var(--cp-text)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10, fontSize: 15 }}>
                  <span style={{ color: 'var(--cp-gold)', fontWeight: 600 }}>-</span>
                  <span>Tap the Camera icon. <Camera size={16} style={{ display: 'inline', verticalAlign: 'middle', color: 'var(--cp-gold)' }} /></span>
                </div>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 10, fontSize: 15 }}>
                  <span style={{ color: 'var(--cp-gold)', fontWeight: 600 }}>-</span>
                  <span>Upload your CP67 Shopping Bill using Camera or Gallery.</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10, fontSize: 15 }}>
                  <span style={{ color: 'var(--cp-gold)', fontWeight: 600 }}>-</span>
                  <span>Share it with us.</span>
                </div>
              </div>

              <p style={{ fontSize: 15, fontWeight: 600, color: 'var(--cp-text)', marginBottom: 4 }}>
                Earn your Homeland Advantage Loyalty points instantly!
              </p>
              <p style={{ fontSize: 14, fontWeight: 700, color: 'var(--cp-gold)', letterSpacing: '0.02em' }}>
                More Bills = More Points = More Rewards
              </p>

              {cameraError && (
                <div className="camera-error" data-testid="camera-error">
                  <AlertCircle size={16} />
                  <span>{cameraError}</span>
                </div>
              )}

              <div className="capture-buttons">
                <button
                  className="capture-btn primary"
                  onClick={() => {
                    if (hasNativeCamera) {
                      openNativeCamera();
                    } else {
                      cameraRef.current?.click();
                    }
                  }}
                  data-testid="start-camera-btn"
                >
                  <Camera size={20} /> Open Camera
                </button>
                <button className="capture-btn secondary" onClick={() => fileRef.current?.click()} data-testid="gallery-btn">
                  <ImagePlus size={20} /> Gallery
                </button>
              </div>

              {/* Native Android camera capture — bypasses the flaky WebView
                  <video> srcObject rendering and uses the built-in system
                  camera app, which is reliable across all devices. */}
              <input
                ref={cameraRef}
                type="file"
                accept="image/*"
                capture="environment"
                onChange={handleFile}
                hidden
              />
              <input ref={fileRef} type="file" accept="image/*" onChange={handleFile} hidden />
            </div>
          </motion.div>
        )}

        {/* Preview state */}
        {preview && !result && (
          <motion.div className="bill-preview" key="preview" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}>
            <div className="bill-preview-img">
              <img src={preview} alt="Bill preview" data-testid="bill-preview-image" />
            </div>
            <div className="bill-preview-actions">
              <button className="bill-retake" onClick={reset} data-testid="retake-btn">Retake</button>
              <button className="bill-submit" onClick={uploadBill} disabled={uploading} data-testid="submit-bill-btn">
                {uploading ? <><Loader2 size={18} className="spin" /> Processing...</> : <><Upload size={18} /> Upload Bill</>}
              </button>
            </div>
          </motion.div>
        )}

        {/* Result state */}
        {result && (
          <motion.div className="bill-result" key="result" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
            <div className={`bill-result-icon ${result.success ? 'success' : 'error'}`}>
              {result.success ? <CheckCircle size={48} /> : <AlertCircle size={48} />}
            </div>
            <h2>{result.success ? 'Bill Uploaded!' : 'Upload Failed'}</h2>
            <p>{result.message}</p>
            <div className="bill-result-actions">
              <button className="bill-result-btn primary" onClick={reset} data-testid="upload-another-btn">Upload Another Bill</button>
              <button className="bill-result-btn secondary" onClick={() => navigate('/app/wallet')} data-testid="view-wallet-btn">View Wallet</button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
