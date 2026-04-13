import React from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, Mail, Phone, MapPin, MessageCircle, HelpCircle } from 'lucide-react';

const faqs = [
  { q: 'How do I earn points?', a: 'Upload your shopping bills from any CP67 Mall store via WhatsApp or the app. Points are credited based on the bill amount.' },
  { q: 'How do I redeem points?', a: 'Go to the Rewards section and choose from available vouchers. 1 point = Rs 1. Redeem directly at participating stores.' },
  { q: 'How long are bills valid for upload?', a: 'Bills must be uploaded within 15 days of purchase. Bills older than 15 days cannot be processed.' },
  { q: 'Why was my bill rejected?', a: 'Bills may be rejected if they are from outside CP67 Mall, are older than 15 days, are duplicates, or if the image is unclear.' },
  { q: 'Do points expire?', a: 'Please check the terms and conditions for point expiry rules. We recommend redeeming points regularly.' },
];

export default function HelpSupport() {
  const navigate = useNavigate();

  return (
    <motion.div className="consumer-help-page" initial={{ opacity: 0 }} animate={{ opacity: 1 }} data-testid="help-screen">
      <div className="bill-upload-header">
        <button className="bill-back" onClick={() => navigate(-1)} data-testid="help-back"><ArrowLeft size={22} /></button>
        <h1>Help & Support</h1>
      </div>

      {/* Contact Cards */}
      <div className="help-section" data-testid="help-contacts">
        <h2>Contact Us</h2>
        <div className="help-contact-cards">
          <a href="https://wa.me/917347576767" target="_blank" rel="noopener noreferrer" className="help-contact-card whatsapp-primary" data-testid="contact-whatsapp">
            <MessageCircle size={22} />
            <div>
              <h4>WhatsApp Support</h4>
              <p>73475 76767 - Chat with us</p>
            </div>
          </a>
          <a href="mailto:advantage@homelandgroup.org" className="help-contact-card" data-testid="contact-email">
            <Mail size={22} />
            <div>
              <h4>Email</h4>
              <p>advantage@homelandgroup.org</p>
            </div>
          </a>
          <a href="tel:9729676767" className="help-contact-card" data-testid="contact-phone">
            <Phone size={22} />
            <div>
              <h4>Phone</h4>
              <p>97296 76767</p>
            </div>
          </a>
          <div className="help-contact-card" data-testid="contact-desk">
            <MapPin size={22} />
            <div>
              <h4>Support Desk</h4>
              <p>Ground Floor, CP67 Mall, Mohali</p>
            </div>
          </div>
        </div>
      </div>

      {/* FAQs */}
      <div className="help-section" data-testid="help-faqs">
        <h2>Frequently Asked Questions</h2>
        <div className="help-faq-list">
          {faqs.map((faq, i) => (
            <details key={i} className="help-faq-item" data-testid={`faq-${i}`}>
              <summary>
                <HelpCircle size={16} />
                <span>{faq.q}</span>
              </summary>
              <p>{faq.a}</p>
            </details>
          ))}
        </div>
      </div>

      <div className="home-spacer" />
    </motion.div>
  );
}
