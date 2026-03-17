import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowLeft, Camera, ImagePlus, Loader2, CheckCircle, AlertCircle, Upload } from 'lucide-react';
import { useConsumerAuth, API } from '../ConsumerApp';

export default function BillUpload() {
  const [preview, setPreview] = useState(null);
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const fileRef = useRef();
  const cameraRef = useRef();
  const navigate = useNavigate();
  const { token } = useConsumerAuth();

  const handleFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    setResult(null);
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
  };

  return (
    <motion.div
      className="consumer-bill-upload"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      data-testid="bill-upload-screen"
    >
      <div className="bill-upload-header">
        <button className="bill-back" onClick={() => navigate(-1)} data-testid="bill-back-btn">
          <ArrowLeft size={22} />
        </button>
        <h1>Upload Bill</h1>
      </div>

      <AnimatePresence mode="wait">
        {!preview && !result && (
          <motion.div className="bill-upload-area" key="capture" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <div className="bill-capture-zone" data-testid="bill-capture-zone">
              <div className="capture-icon">
                <Camera size={40} />
              </div>
              <h2>Scan your bill</h2>
              <p>Take a photo or select from gallery</p>

              <div className="capture-buttons">
                <button className="capture-btn primary" onClick={() => cameraRef.current?.click()} data-testid="take-photo-btn">
                  <Camera size={20} /> Take Photo
                </button>
                <button className="capture-btn secondary" onClick={() => fileRef.current?.click()} data-testid="gallery-btn">
                  <ImagePlus size={20} /> Gallery
                </button>
              </div>

              <input ref={cameraRef} type="file" accept="image/*" capture="environment" onChange={handleFile} hidden />
              <input ref={fileRef} type="file" accept="image/*" onChange={handleFile} hidden />
            </div>

            <div className="bill-tips">
              <h3>Tips for best results</h3>
              <ul>
                <li>Ensure the entire bill is visible</li>
                <li>Avoid glare and shadows</li>
                <li>Bill should be from CP67 Mall stores</li>
                <li>Bill should not be older than 15 days</li>
              </ul>
            </div>
          </motion.div>
        )}

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
