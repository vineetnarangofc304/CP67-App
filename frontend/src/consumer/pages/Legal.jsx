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

      <div className="legal-section" data-testid="points-value-section" style={{ background: 'linear-gradient(135deg, #2c1810, #5D3A1A)', color: '#fff', borderRadius: 12, padding: '16px 20px', margin: '0 16px 16px' }}>
        <p style={{ fontSize: 16, fontWeight: 700, textAlign: 'center', margin: 0 }}>10 Points = INR 1</p>
      </div>

      <div className="legal-section" data-testid="terms-section">
        <div className="legal-header">
          <FileText size={22} />
          <h2>Terms of Use</h2>
        </div>
        <div className="legal-content">
          <p><strong>1. Acceptance of Terms</strong></p>
          <p>By accessing this Website, you agree to comply with these Terms, Privacy Policy, and any additional terms that may apply to specific sections, services, or features of the Website.</p>

          <p><strong>2. Use of Website</strong></p>
          <ul>
            <li>You may use this Website for lawful purposes only.</li>
            <li>You agree not to misuse the Website in any way, including attempting to gain unauthorized access to systems, interfering with functionality, or uploading harmful content.</li>
            <li>The Website is intended for informational purposes regarding CP67, its services, and offerings.</li>
          </ul>

          <p><strong>3. Intellectual Property Rights</strong></p>
          <ul>
            <li>All content, logos, graphics, images, software, text, designs, and other materials on the Website are the property of CP67 or its licensors.</li>
            <li>You may not copy, reproduce, distribute, display, or use any content without prior written consent from CP67.</li>
          </ul>

          <p><strong>4. Third-Party Links</strong></p>
          <ul>
            <li>This Website may contain links to third-party websites for your convenience.</li>
            <li>CP67 is not responsible for the content, privacy practices, or terms of such third-party sites. Accessing them is at your own risk.</li>
          </ul>

          <p><strong>5. Disclaimer of Warranties</strong></p>
          <ul>
            <li>The Website and its content are provided on an "as is" and "as available" basis.</li>
            <li>CP67 does not warrant that the Website will be error-free, uninterrupted, secure, or free from viruses.</li>
            <li>Information provided is for general informational purposes only and should not be relied upon for legal, financial, or investment decisions.</li>
          </ul>

          <p><strong>6. Limitation of Liability</strong></p>
          <p>To the maximum extent permitted by law:</p>
          <ul>
            <li>CP67 shall not be liable for any direct, indirect, incidental, consequential, or punitive damages arising from your use of the Website.</li>
            <li>This includes, but is not limited to, damages for loss of profits, data, or goodwill.</li>
          </ul>

          <p><strong>7. Notification and Communication Consent</strong></p>
          <p>By accepting this policy, you acknowledge and consent to receiving notifications and promotional communications from us through various channels, including but not limited to email, mobile push notifications, SMS, RCS (Rich Communication Services), WhatsApp, or any other digital communication platforms.</p>

          <p><strong>8. Indemnification</strong></p>
          <p>You agree to indemnify, defend, and hold harmless CP67, its affiliates, employees, and partners from any claims, damages, liabilities, or expenses arising out of your use of the Website or violation of these Terms.</p>

          <p><strong>9. Privacy Policy</strong></p>
          <p>Use of the Website is also governed by our Privacy Policy, which explains how we collect, use, and protect your personal information.</p>

          <p><strong>10. Changes to Terms</strong></p>
          <p>CP67 reserves the right to update or modify these Terms at any time without prior notice. Your continued use of the Website after such changes indicates your acceptance of the updated Terms.</p>

          <p><strong>11. Governing Law & Jurisdiction</strong></p>
          <p>These Terms shall be governed by and construed in accordance with the laws of India. Any disputes shall be subject to the exclusive jurisdiction of the courts located in SAS Nagar (Mohali), Punjab.</p>
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
