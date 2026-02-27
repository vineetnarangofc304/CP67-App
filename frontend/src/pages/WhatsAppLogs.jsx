import React, { useState, useEffect, useRef } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import { useAuth } from '../App';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { toast } from 'sonner';
import { 
  MessageCircle, 
  Search, 
  User,
  ArrowLeft,
  Phone,
  Clock,
  CheckCheck
} from 'lucide-react';

const WhatsAppLogs = () => {
  const { token, API_URL } = useAuth();
  const [conversations, setConversations] = useState([]);
  const [selectedPhone, setSelectedPhone] = useState(null);
  const [messages, setMessages] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const messagesEndRef = useRef(null);

  useEffect(() => {
    fetchConversations();
  }, []);

  useEffect(() => {
    if (selectedPhone) {
      fetchConversation(selectedPhone);
    }
  }, [selectedPhone]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const fetchConversations = async () => {
    try {
      const response = await fetch(`${API_URL}/whatsapp/conversations`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setConversations(data);
      }
    } catch (error) {
      toast.error('Failed to fetch conversations');
    } finally {
      setLoading(false);
    }
  };

  const fetchConversation = async (phone) => {
    try {
      const response = await fetch(`${API_URL}/whatsapp/conversation/${phone}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setMessages(data.messages || []);
        setSelectedUser(data.user);
      }
    } catch (error) {
      toast.error('Failed to fetch conversation');
    }
  };

  const formatTime = (timestamp) => {
    const date = new Date(timestamp);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    if (date.toDateString() === today.toDateString()) {
      return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    } else if (date.toDateString() === yesterday.toDateString()) {
      return 'Yesterday';
    } else {
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }
  };

  const formatFullTime = (timestamp) => {
    return new Date(timestamp).toLocaleString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      day: 'numeric',
      month: 'short'
    });
  };

  const filteredConversations = conversations.filter(conv => 
    conv.phone?.includes(searchQuery) || 
    conv.user_name?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <DashboardLayout title="WhatsApp Conversations">
      <div className="grid lg:grid-cols-3 gap-0 h-[calc(100vh-180px)] border border-slate-200 rounded-lg overflow-hidden">
        {/* Conversations List */}
        <div className={`bg-white border-r border-slate-200 flex flex-col overflow-hidden ${selectedPhone ? 'hidden lg:flex' : 'flex'}`}>
          {/* Search Header */}
          <div className="p-4 border-b border-slate-200 bg-slate-50 flex-shrink-0">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
              <Input
                placeholder="Search by phone or name..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
                data-testid="search-conversations"
              />
            </div>
          </div>

          {/* Conversations */}
          <div className="flex-1 overflow-y-auto min-h-0">
            {loading ? (
              <div className="flex items-center justify-center h-32">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-900" />
              </div>
            ) : filteredConversations.length === 0 ? (
              <div className="text-center py-12 text-slate-500">
                <MessageCircle className="h-12 w-12 mx-auto mb-4 text-slate-300" />
                <p>No conversations found</p>
              </div>
            ) : (
              filteredConversations.map((conv, index) => (
                <div
                  key={index}
                  onClick={() => setSelectedPhone(conv.phone)}
                  className={`p-4 border-b border-slate-100 cursor-pointer hover:bg-slate-50 transition-colors ${
                    selectedPhone === conv.phone ? 'bg-slate-100' : ''
                  }`}
                  data-testid={`conversation-${index}`}
                >
                  <div className="flex items-start gap-3">
                    <div className="w-12 h-12 bg-gradient-to-br from-green-400 to-green-600 rounded-full flex items-center justify-center flex-shrink-0">
                      <User className="h-6 w-6 text-white" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex justify-between items-start">
                        <p className="font-semibold text-slate-900 truncate">
                          {conv.user_name || conv.phone}
                        </p>
                        <span className="text-xs text-slate-500 flex-shrink-0 ml-2">
                          {formatTime(conv.last_timestamp)}
                        </span>
                      </div>
                      {conv.user_name && (
                        <p className="text-xs text-slate-500">{conv.phone}</p>
                      )}
                      <p className="text-sm text-slate-600 truncate mt-1">
                        {conv.last_message}
                      </p>
                    </div>
                    <Badge variant="secondary" className="bg-green-100 text-green-800 text-xs">
                      {conv.message_count}
                    </Badge>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Chat View */}
        <div className={`lg:col-span-2 flex flex-col overflow-hidden bg-slate-50 ${!selectedPhone ? 'hidden lg:flex' : 'flex'}`}>
          {selectedPhone ? (
            <>
              {/* Chat Header */}
              <div className="p-4 border-b border-slate-200 bg-[#075e54] text-white flex items-center gap-3 flex-shrink-0">
                <Button
                  variant="ghost"
                  size="icon"
                  className="lg:hidden text-white hover:bg-white/20"
                  onClick={() => setSelectedPhone(null)}
                >
                  <ArrowLeft className="h-5 w-5" />
                </Button>
                <div className="w-10 h-10 bg-white/20 rounded-full flex items-center justify-center">
                  <User className="h-5 w-5" />
                </div>
                <div className="flex-1">
                  <p className="font-semibold">{selectedUser?.name || selectedPhone}</p>
                  <p className="text-xs text-white/70 flex items-center gap-1">
                    <Phone className="h-3 w-3" />
                    {selectedPhone}
                  </p>
                </div>
                {selectedUser && (
                  <Badge className="bg-white/20 text-white">
                    {Math.round(selectedUser.balance_points || 0)} pts
                  </Badge>
                )}
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto min-h-0 p-4 space-y-3" style={{
                backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23e2e8f0' fill-opacity='0.4'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`,
                backgroundColor: '#e5ddd5'
              }}>
                {messages.map((msg, index) => {
                  const isOutbound = msg.direction === 'outbound';
                  const showDate = index === 0 || 
                    new Date(msg.timestamp).toDateString() !== new Date(messages[index - 1]?.timestamp).toDateString();
                  
                  return (
                    <React.Fragment key={msg.id || index}>
                      {showDate && (
                        <div className="flex justify-center my-4">
                          <span className="bg-white/80 text-slate-600 text-xs px-3 py-1 rounded-full shadow-sm">
                            {new Date(msg.timestamp).toLocaleDateString('en-US', {
                              weekday: 'long',
                              month: 'short',
                              day: 'numeric'
                            })}
                          </span>
                        </div>
                      )}
                      <div className={`flex ${isOutbound ? 'justify-end' : 'justify-start'}`}>
                        <div
                          className={`max-w-[75%] p-3 rounded-lg shadow-sm ${
                            isOutbound 
                              ? 'bg-[#dcf8c6] text-slate-900 rounded-tr-none' 
                              : 'bg-white text-slate-900 rounded-tl-none'
                          }`}
                        >
                          {/* Direction indicator */}
                          <div className={`text-[10px] font-semibold mb-1 ${
                            isOutbound ? 'text-green-700' : 'text-blue-700'
                          }`}>
                            {isOutbound ? '🤖 SYSTEM' : '👤 CUSTOMER'}
                          </div>
                          
                          <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                          
                          <div className="flex items-center justify-end gap-1 mt-2">
                            <span className="text-[10px] text-slate-500">
                              {new Date(msg.timestamp).toLocaleTimeString('en-US', {
                                hour: '2-digit',
                                minute: '2-digit'
                              })}
                            </span>
                            {isOutbound && (
                              <CheckCheck className="h-3 w-3 text-blue-500" />
                            )}
                          </div>
                          
                          {msg.source_code && (
                            <Badge variant="outline" className="mt-2 text-[10px]">
                              Source: {msg.source_code}
                            </Badge>
                          )}
                        </div>
                      </div>
                    </React.Fragment>
                  );
                })}
                <div ref={messagesEndRef} />
              </div>

              {/* Info Footer */}
              <div className="p-3 border-t border-slate-200 bg-white text-center text-xs text-slate-500 flex-shrink-0">
                <Clock className="h-3 w-3 inline mr-1" />
                {messages.length} messages in this conversation
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-500">
              <div className="w-20 h-20 bg-slate-200 rounded-full flex items-center justify-center mb-4">
                <MessageCircle className="h-10 w-10 text-slate-400" />
              </div>
              <h3 className="text-xl font-semibold text-slate-700">WhatsApp Conversations</h3>
              <p className="text-sm mt-2 max-w-md text-center">
                Select a conversation from the list to view the complete chat history between the customer and the system.
              </p>
              <div className="mt-6 flex gap-2">
                <Badge className="bg-[#dcf8c6] text-green-800">🤖 System Messages</Badge>
                <Badge className="bg-white text-blue-800 border">👤 Customer Messages</Badge>
              </div>
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
};

export default WhatsAppLogs;
