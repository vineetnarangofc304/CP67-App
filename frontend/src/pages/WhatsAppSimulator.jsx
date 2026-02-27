import React, { useState, useRef, useEffect } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import { useAuth } from '../App';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { toast } from 'sonner';
import { 
  MessageCircle, 
  Send, 
  Upload, 
  Phone,
  User,
  Image as ImageIcon,
  RefreshCw,
  CheckCheck,
  Clock
} from 'lucide-react';

const WhatsAppSimulator = () => {
  const { token, API_URL } = useAuth();
  const [phone, setPhone] = useState('');
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploadingBill, setUploadingBill] = useState(false);
  const [userState, setUserState] = useState(null);
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const sendMessage = async (customMessage = null) => {
    const msgToSend = customMessage || message;
    if (!phone.trim() || !msgToSend.trim()) {
      toast.error('Please enter phone number and message');
      return;
    }

    setLoading(true);
    
    // Add user message to chat
    const userMsg = {
      id: Date.now(),
      type: 'user',
      content: msgToSend,
      timestamp: new Date().toISOString()
    };
    setMessages(prev => [...prev, userMsg]);
    setMessage('');

    try {
      const response = await fetch(`${API_URL}/whatsapp/simulate`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          phone,
          message: msgToSend,
          message_type: 'text'
        })
      });

      if (response.ok) {
        const data = await response.json();
        
        // Add bot response
        const botMsg = {
          id: Date.now() + 1,
          type: 'bot',
          content: data.response,
          timestamp: new Date().toISOString()
        };
        setMessages(prev => [...prev, botMsg]);

        // Update user state
        if (data.user_id) {
          fetchUserState(data.user_id);
        }
      } else {
        toast.error('Failed to send message');
      }
    } catch (error) {
      toast.error('Failed to send message');
    } finally {
      setLoading(false);
    }
  };

  const handleBillUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !phone.trim()) {
      toast.error('Please enter phone number first');
      return;
    }

    setUploadingBill(true);

    // Add upload message
    const uploadMsg = {
      id: Date.now(),
      type: 'user',
      content: `📎 Uploading bill: ${file.name}`,
      timestamp: new Date().toISOString(),
      isImage: true
    };
    setMessages(prev => [...prev, uploadMsg]);

    try {
      const formData = new FormData();
      formData.append('phone', phone);
      formData.append('file', file);

      const response = await fetch(`${API_URL}/whatsapp/simulate-bill-upload`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        
        // Add bot response
        const botMsg = {
          id: Date.now() + 1,
          type: 'bot',
          content: data.response,
          timestamp: new Date().toISOString(),
          billStatus: data.status,
          ocrData: data.ocr_data
        };
        setMessages(prev => [...prev, botMsg]);

        // Refresh user state
        if (userState?.id) {
          fetchUserState(userState.id);
        }
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to upload bill');
      }
    } catch (error) {
      toast.error('Failed to upload bill');
    } finally {
      setUploadingBill(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const fetchUserState = async (userId) => {
    try {
      const response = await fetch(`${API_URL}/users/${userId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setUserState(data.user);
      }
    } catch (error) {
      console.error('Failed to fetch user state:', error);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const startNewSession = () => {
    setMessages([]);
    setUserState(null);
    setPhone('');
    setMessage('');
  };

  const qrPresets = [
    { label: 'Brands QR', message: 'Hi! I want to join CP67 Loyalty Program | SRC_BRANDS' },
    { label: 'Food Court QR', message: 'Hi! Register me in CP67 Loyalty Program | SRC_FOODCOURT' },
    { label: 'Parking QR', message: 'Hi! Sign up for CP67 Loyalty Program | SRC_PARKING' },
    { label: 'Digital Screens QR', message: 'Hi! Add me to CP67 Loyalty Program | SRC_DIGITAL' },
    { label: 'Social QR', message: 'Hi! Enroll in CP67 Loyalty Program | SRC_SOCIAL' },
  ];

  return (
    <DashboardLayout title="WhatsApp Simulator">
      <div className="grid lg:grid-cols-3 gap-6 h-[calc(100vh-200px)]">
        {/* Chat Interface */}
        <Card className="lg:col-span-2 border-slate-200 shadow-none flex flex-col">
          {/* Chat Header */}
          <CardHeader className="border-b border-slate-200 bg-[#075e54] text-white rounded-t-lg py-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-white/20 rounded-full flex items-center justify-center">
                  <MessageCircle className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="font-semibold">CP67 Mall</h3>
                  <p className="text-xs text-white/70">Homeland Advantage</p>
                </div>
              </div>
              <Button 
                variant="ghost" 
                size="sm" 
                className="text-white hover:bg-white/20"
                onClick={startNewSession}
                data-testid="new-session-btn"
              >
                <RefreshCw className="h-4 w-4 mr-2" />
                New Session
              </Button>
            </div>
          </CardHeader>

          {/* Phone Number Input */}
          <div className="p-4 border-b border-slate-200 bg-slate-50">
            <div className="flex gap-4 items-end">
              <div className="flex-1">
                <Label className="text-xs text-slate-500">Customer Phone Number</Label>
                <div className="relative mt-1">
                  <Phone className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
                  <Input
                    placeholder="Enter 10-digit mobile number"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value.replace(/\D/g, '').slice(0, 10))}
                    className="pl-10"
                    data-testid="phone-input"
                  />
                </div>
              </div>
              <div className="flex gap-2 flex-wrap">
                {qrPresets.slice(0, 3).map((preset, i) => (
                  <Button
                    key={i}
                    variant="outline"
                    size="sm"
                    onClick={() => sendMessage(preset.message)}
                    disabled={!phone || loading}
                    className="text-xs"
                    data-testid={`qr-preset-${i}`}
                  >
                    {preset.label}
                  </Button>
                ))}
              </div>
            </div>
          </div>

          {/* Chat Messages */}
          <CardContent className="flex-1 overflow-y-auto whatsapp-bg p-4">
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center text-slate-500">
                <MessageCircle className="h-16 w-16 mb-4 text-slate-300" />
                <h3 className="text-lg font-semibold text-slate-700">WhatsApp Flow Simulator</h3>
                <p className="text-sm max-w-md mt-2">
                  Enter a phone number and click a QR preset to simulate a customer scanning a QR code and joining the loyalty program.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[80%] p-3 ${
                        msg.type === 'user' ? 'message-bubble-sent' : 'message-bubble-received'
                      }`}
                    >
                      <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                      <div className="flex items-center justify-end gap-1 mt-1">
                        <span className="text-[10px] text-slate-500">
                          {new Date(msg.timestamp).toLocaleTimeString('en-US', { 
                            hour: '2-digit', 
                            minute: '2-digit' 
                          })}
                        </span>
                        {msg.type === 'user' && (
                          <CheckCheck className="h-3 w-3 text-blue-500" />
                        )}
                      </div>
                      {msg.billStatus && (
                        <Badge 
                          className={`mt-2 ${
                            msg.billStatus === 'auto_approved' ? 'bg-green-100 text-green-800' :
                            msg.billStatus === 'duplicate' ? 'bg-purple-100 text-purple-800' :
                            'bg-yellow-100 text-yellow-800'
                          }`}
                        >
                          {msg.billStatus}
                        </Badge>
                      )}
                    </div>
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </div>
            )}
          </CardContent>

          {/* Message Input */}
          <div className="p-4 border-t border-slate-200 bg-slate-50">
            <div className="flex gap-2">
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleBillUpload}
                accept="image/*"
                className="hidden"
              />
              <Button
                variant="outline"
                size="icon"
                onClick={() => fileInputRef.current?.click()}
                disabled={!phone || uploadingBill}
                data-testid="upload-bill-btn"
              >
                {uploadingBill ? (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-slate-900" />
                ) : (
                  <ImageIcon className="h-4 w-4" />
                )}
              </Button>
              <Input
                placeholder="Type a message..."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyPress={handleKeyPress}
                disabled={!phone || loading}
                className="flex-1"
                data-testid="message-input"
              />
              <Button 
                onClick={() => sendMessage()}
                disabled={!phone || !message || loading}
                className="bg-[#075e54] hover:bg-[#064e46]"
                data-testid="send-message-btn"
              >
                {loading ? (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </Button>
            </div>
            <p className="text-xs text-slate-500 mt-2">
              Upload a bill image to simulate the bill scan and points earning flow
            </p>
          </div>
        </Card>

        {/* Debug Panel */}
        <Card className="border-slate-200 shadow-none">
          <CardHeader className="border-b border-slate-200">
            <CardTitle className="font-['Manrope'] text-lg">Session State</CardTitle>
          </CardHeader>
          <CardContent className="p-4 space-y-4">
            {/* User State */}
            {userState ? (
              <div className="space-y-3">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 bg-slate-100 rounded-full flex items-center justify-center">
                    <User className="h-5 w-5 text-slate-500" />
                  </div>
                  <div>
                    <p className="font-semibold">{userState.name || 'Not registered'}</p>
                    <p className="text-sm text-slate-500">{userState.phone}</p>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-slate-50 rounded-lg p-3">
                    <p className="text-xs text-slate-500">Status</p>
                    <Badge className={userState.kyc_status ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}>
                      {userState.kyc_status ? 'Registered' : 'Pending'}
                    </Badge>
                  </div>
                  <div className="bg-slate-50 rounded-lg p-3">
                    <p className="text-xs text-slate-500">Points Balance</p>
                    <p className="font-semibold text-[#D4AF37]">{Math.round(userState.balance_points || 0)}</p>
                  </div>
                  <div className="bg-slate-50 rounded-lg p-3">
                    <p className="text-xs text-slate-500">Source</p>
                    <p className="font-semibold text-sm">{userState.first_touch_source?.replace('SRC_', '') || 'N/A'}</p>
                  </div>
                  <div className="bg-slate-50 rounded-lg p-3">
                    <p className="text-xs text-slate-500">QR Code</p>
                    <p className="font-semibold text-sm">{userState.first_touch_qr || 'N/A'}</p>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-8 text-slate-500">
                <User className="h-12 w-12 mx-auto mb-4 text-slate-300" />
                <p>No user session active</p>
                <p className="text-xs mt-1">Start a conversation to see user state</p>
              </div>
            )}

            {/* Quick Actions */}
            <div className="pt-4 border-t border-slate-200">
              <p className="text-sm font-medium text-slate-700 mb-3">Quick Actions</p>
              <div className="space-y-2">
                <Button 
                  variant="outline" 
                  size="sm" 
                  className="w-full justify-start"
                  onClick={() => setMessage('1')}
                  disabled={!phone}
                >
                  📤 Upload Bill (Reply "1")
                </Button>
                <Button 
                  variant="outline" 
                  size="sm" 
                  className="w-full justify-start"
                  onClick={() => setMessage('2')}
                  disabled={!phone}
                >
                  💰 Check Points (Reply "2")
                </Button>
              </div>
            </div>

            {/* Webhook Info */}
            <div className="pt-4 border-t border-slate-200">
              <p className="text-sm font-medium text-slate-700 mb-2">Webhook URL</p>
              <code className="block text-xs bg-slate-100 p-3 rounded-lg break-all">
                {API_URL}/whatsapp/webhook
              </code>
              <p className="text-xs text-slate-500 mt-2">
                Configure this URL in your WhatsApp Business API provider (Interakt/Gupshup)
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
};

export default WhatsAppSimulator;
