import React from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, Shield, FileText } from 'lucide-react';

export default function Legal() {
  const navigate = useNavigate();

  return (
    <motion.div className="consumer-legal-page" initial={{ opacity: 0 }} animate={{ opacity: 1 }} data-testid="legal-screen">
      <div className="bill-upload-header">
        <button className="bill-back" onClick={() => navigate(-1)} data-testid="legal-back"><ArrowLeft size={22} /></button>
        <h1>Legal</h1>
      </div>

      <div className="legal-section" data-testid="terms-section">
        <div className="legal-header">
          <FileText size={22} />
          <h2>Terms & Conditions</h2>
        </div>
        <div className="legal-content">
          <p><strong>Homeland Advantage Loyalty Program</strong></p>
          <ol>
            <li>The Homeland Advantage loyalty program is exclusively for shoppers at CP67 Mall, Mohali.</li>
            <li>Points are earned by uploading valid shopping bills from CP67 Mall stores.</li>
            <li>Bills must be uploaded within 15 days of purchase to be eligible for points.</li>
            <li>Points are calculated based on the bill amount and the store's reward rate.</li>
            <li>Bills above Rs 30,000 require manual verification (24-48 hours).</li>
            <li>Duplicate bills will not be processed for rewards.</li>
            <li>1 loyalty point equals Rs 1 in redemption value.</li>
            <li>Points can be redeemed at participating brands within CP67 Mall.</li>
            <li>Redeemed points cannot be reversed or refunded.</li>
            <li>CP67 Mall reserves the right to modify the program terms at any time.</li>
            <li>Points may expire as per the program's expiry policy.</li>
            <li>Any fraudulent activity will result in immediate account suspension.</li>
            <li>E-bills and screenshots of bills are accepted for upload.</li>
            <li>The loyalty program is managed by Homeland Group in partnership with Fundle.ai.</li>
          </ol>
        </div>
      </div>

      <div className="legal-section" data-testid="privacy-section">
        <div className="legal-header">
          <Shield size={22} />
          <h2>Privacy Policy</h2>
        </div>
        <div className="legal-content">
          <p><strong>Data Collection & Usage</strong></p>
          <ol>
            <li>We collect your name, phone number, email, and shopping data to provide loyalty services.</li>
            <li>Bill images are processed using AI for data extraction and are stored securely.</li>
            <li>Your personal information is not shared with third parties without consent.</li>
            <li>We use your shopping data to provide personalized offers and recommendations.</li>
            <li>You can request deletion of your account and data by contacting support.</li>
            <li>Push notifications and marketing messages can be controlled via notification preferences.</li>
            <li>We use industry-standard encryption to protect your data.</li>
            <li>By using the app, you agree to our data collection and usage practices.</li>
          </ol>
          <p>For any privacy concerns, contact us at advantage@homelandgroup.org</p>
        </div>
      </div>

      <div className="home-spacer" />
    </motion.div>
  );
}
