import React, { useState, useEffect } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import { useAuth } from '../App';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../components/ui/dialog';
import { toast } from 'sonner';
import { 
  Users, 
  UserPlus, 
  Shield, 
  ShieldCheck,
  Trash2,
  Clock,
  Mail,
  Key,
  User,
  AlertTriangle,
  RefreshCw,
  Database,
  CheckCircle,
  Upload,
  FileSpreadsheet,
  ClipboardPaste
} from 'lucide-react';

const AdminUsers = () => {
  const { token, API_URL, user } = useAuth();
  const [admins, setAdmins] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [selectedAdmin, setSelectedAdmin] = useState(null);
  const [creating, setCreating] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [uploadProgress, setUploadProgress] = useState('');
  const [showPasteModal, setShowPasteModal] = useState(false);
  const [pasteText, setPasteText] = useState('');
  const fileInputRef = React.useRef(null);
  
  // Form state
  const [formData, setFormData] = useState({
    username: '',
    password: '',
    name: '',
    role: 'bill_operator'
  });

  useEffect(() => {
    fetchAdmins();
  }, []);

  const fetchAdmins = async () => {
    try {
      const response = await fetch(`${API_URL}/admin/users`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setAdmins(data);
      } else if (response.status === 403) {
        toast.error('Only super admins can manage users');
      }
    } catch (error) {
      toast.error('Failed to fetch admin users');
    } finally {
      setLoading(false);
    }
  };

  const createAdmin = async () => {
    if (!formData.username || !formData.password || !formData.name) {
      toast.error('Please fill all required fields');
      return;
    }

    setCreating(true);
    try {
      const form = new FormData();
      form.append('username', formData.username);
      form.append('password', formData.password);
      form.append('name', formData.name);
      form.append('role', formData.role);

      const response = await fetch(`${API_URL}/admin/users`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: form
      });

      if (response.ok) {
        toast.success(`Admin user "${formData.username}" created successfully`);
        setShowCreateDialog(false);
        setFormData({ username: '', password: '', name: '', role: 'admin' });
        fetchAdmins();
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to create admin');
      }
    } catch (error) {
      toast.error('Failed to create admin user');
    } finally {
      setCreating(false);
    }
  };

  const deleteAdmin = async () => {
    if (!selectedAdmin) return;

    try {
      const response = await fetch(`${API_URL}/admin/users/${selectedAdmin.id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        toast.success(`Admin user "${selectedAdmin.username}" deactivated`);
        setShowDeleteDialog(false);
        setSelectedAdmin(null);
        fetchAdmins();
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to deactivate admin');
      }
    } catch (error) {
      toast.error('Failed to deactivate admin user');
    }
  };

  const syncFundleCustomers = async () => {
    setSyncing(true);
    setSyncResult(null);
    try {
      const response = await fetch(`${API_URL}/admin/sync-fundle-customers`, {
        method: 'POST',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        setSyncResult(data);
        toast.success(`Sync complete! ${data.updated_to_existing} users updated to 'existing'`);
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to sync customers');
      }
    } catch (error) {
      toast.error('Failed to sync Fundle customers');
    } finally {
      setSyncing(false);
    }
  };

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    // Validate file type
    const validTypes = ['.xlsx', '.xls', '.csv', '.txt'];
    const fileExt = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (!validTypes.includes(fileExt)) {
      toast.error('Please upload a CSV or TXT file');
      return;
    }

    setUploading(true);
    toast.loading('Reading file...');

    try {
      const phoneNumbers = await extractPhoneNumbersFromFile(file);
      await uploadPhoneNumbers(phoneNumbers);
    } catch (error) {
      toast.error(`Failed to read file: ${error.message}`);
      setUploading(false);
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // Extract phone numbers from file client-side
  const extractPhoneNumbersFromFile = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      
      reader.onload = (e) => {
        try {
          const content = e.target.result;
          const phoneNumbers = extractPhonesFromText(content);
          resolve(phoneNumbers);
        } catch (err) {
          reject(err);
        }
      };

      reader.onerror = () => reject(new Error('Failed to read file'));
      reader.readAsText(file);
    });
  };

  // Extract phones from any text
  const extractPhonesFromText = (text) => {
    const phoneNumbers = [];
    const phoneSet = new Set();

    const extractPhone = (value) => {
      if (!value) return null;
      let str = String(value).trim();
      
      // Handle scientific notation
      if (str.toLowerCase().includes('e+') || str.toLowerCase().includes('e-')) {
        try { str = String(parseInt(parseFloat(str))); } catch {}
      }
      
      // Clean the string
      str = str.replace(/[+\-\s.]/g, '');
      
      // Remove leading 91 for Indian numbers
      if (str.startsWith('91') && str.length === 12) {
        str = str.substring(2);
      }
      
      const digits = str.replace(/\D/g, '');
      
      // Validate Indian mobile (10 digits starting with 6-9)
      if (digits.length === 10 && '6789'.includes(digits[0])) {
        return digits;
      }
      return null;
    };

    // Parse text - split by common delimiters
    const lines = text.split(/\r?\n/);
    for (const line of lines) {
      const cells = line.split(/[,\t;|]/);
      for (const cell of cells) {
        const phone = extractPhone(cell);
        if (phone && !phoneSet.has(phone)) {
          phoneSet.add(phone);
          phoneNumbers.push(phone);
        }
      }
    }

    return phoneNumbers;
  };

  // Upload phone numbers (used by both file and paste)
  const uploadPhoneNumbers = async (phoneNumbers) => {
    if (phoneNumbers.length === 0) {
      toast.error('No valid phone numbers found');
      setUploadResult({ success: false, message: 'No valid phone numbers found' });
      return;
    }

    setUploading(true);
    setUploadResult(null);
    const toastId = toast.loading(`Uploading ${phoneNumbers.length.toLocaleString()} numbers...`);

    try {
      // Upload in chunks of 2000
      const chunkSize = 2000;
      let totalImported = 0;
      const totalChunks = Math.ceil(phoneNumbers.length / chunkSize);

      for (let i = 0; i < phoneNumbers.length; i += chunkSize) {
        const chunk = phoneNumbers.slice(i, i + chunkSize);
        const chunkNum = Math.floor(i / chunkSize) + 1;
        
        toast.loading(`Chunk ${chunkNum}/${totalChunks}...`, { id: toastId });
        setUploadProgress(`${chunkNum}/${totalChunks} (${totalImported.toLocaleString()} done)`);

        try {
          const response = await fetch(`${API_URL}/admin/upload-fundle-chunk`, {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({ phone_numbers: chunk })
          });

          if (response.ok) {
            const data = await response.json();
            totalImported += data.imported;
          } else {
            console.error(`Chunk ${chunkNum} failed:`, response.status);
          }
        } catch (chunkError) {
          console.error(`Chunk ${chunkNum} error:`, chunkError);
        }
        
        await new Promise(r => setTimeout(r, 200));
      }

      // Get final count
      try {
        const finalResponse = await fetch(`${API_URL}/admin/fundle-count`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        const finalData = await finalResponse.json();
        
        setUploadResult({
          success: true,
          imported: totalImported,
          total_in_database: finalData.count,
          phones_in_file: phoneNumbers.length
        });
        toast.success(`Done! Imported ${totalImported.toLocaleString()} numbers`, { id: toastId });
      } catch {
        setUploadResult({
          success: true,
          imported: totalImported,
          phones_in_file: phoneNumbers.length
        });
        toast.success(`Imported ${totalImported.toLocaleString()} numbers`, { id: toastId });
      }
    } catch (error) {
      console.error('Upload error:', error);
      toast.error(`Upload failed: ${error.message}`, { id: toastId });
      setUploadResult({ success: false, message: error.message });
    } finally {
      setUploading(false);
      setUploadProgress('');
    }
  };

  // Handle paste submit
  const handlePasteSubmit = async () => {
    if (!pasteText.trim()) {
      toast.error('Please paste some phone numbers');
      return;
    }

    const phoneNumbers = extractPhonesFromText(pasteText);
    setShowPasteModal(false);
    setPasteText('');
    await uploadPhoneNumbers(phoneNumbers);
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'Never';
    return new Date(dateStr).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const roleConfig = {
    super_admin: { label: 'Super Admin', color: 'bg-purple-100 text-purple-800 border-purple-200', icon: ShieldCheck },
    admin: { label: 'Admin', color: 'bg-blue-100 text-blue-800 border-blue-200', icon: Shield },
    bill_operator: { label: 'Bill Operator', color: 'bg-green-100 text-green-800 border-green-200', icon: Shield },
    app_manager: { label: 'App Manager', color: 'bg-indigo-100 text-indigo-800 border-indigo-200', icon: Shield },
    call_centre: { label: 'Call Centre', color: 'bg-orange-100 text-orange-800 border-orange-200', icon: Shield },
    support_officer: { label: 'Support Officer', color: 'bg-pink-100 text-pink-800 border-pink-200', icon: Shield }
  };

  const getRoleBadge = (role) => {
    const config = roleConfig[role] || roleConfig.admin;
    const Icon = config.icon;
    return (
      <Badge className={config.color}>
        <Icon className="h-3 w-3 mr-1" />
        {config.label}
      </Badge>
    );
  };

  return (
    <DashboardLayout title="Admin User Management">
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-slate-900">Admin Users</h2>
            <p className="text-slate-500">Manage admin accounts and permissions</p>
          </div>
          <Button 
            onClick={() => setShowCreateDialog(true)}
            className="bg-slate-900 hover:bg-slate-800"
            data-testid="create-admin-btn"
          >
            <UserPlus className="h-4 w-4 mr-2" />
            Add New Admin
          </Button>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card className="border-slate-200 shadow-none">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                  <Users className="h-5 w-5 text-blue-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{admins.length}</p>
                  <p className="text-sm text-slate-500">Total Admins</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-slate-200 shadow-none">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
                  <ShieldCheck className="h-5 w-5 text-purple-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{admins.filter(a => a.role === 'super_admin').length}</p>
                  <p className="text-sm text-slate-500">Super Admins</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-slate-200 shadow-none">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
                  <Shield className="h-5 w-5 text-green-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{admins.filter(a => a.is_active).length}</p>
                  <p className="text-sm text-slate-500">Active Admins</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* System Tools */}
        <Card className="border-orange-200 bg-orange-50 shadow-none">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg font-semibold flex items-center gap-2">
              <Database className="h-5 w-5 text-orange-600" />
              System Tools - Fundle Customer Import
            </CardTitle>
            <CardDescription>
              Import and sync existing Fundle customers to mark them as "Existing" in the system
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Step 1: Upload Excel */}
            <div className="p-4 bg-white rounded-lg border border-orange-200">
              <div className="flex items-start gap-3 mb-3">
                <div className="w-8 h-8 bg-orange-100 rounded-full flex items-center justify-center flex-shrink-0">
                  <span className="text-orange-600 font-bold text-sm">1</span>
                </div>
                <div className="flex-1">
                  <h4 className="font-medium text-slate-900">Upload CSV with Phone Numbers</h4>
                  <p className="text-sm text-slate-600 mt-1">
                    Upload a CSV file with Fundle customer phone numbers. For large files (30k+ rows), CSV format is recommended.
                    Phone numbers can be in any column - the system will find all valid 10-digit Indian mobile numbers.
                  </p>
                </div>
              </div>
              
              <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 ml-11">
                <input
                  type="file"
                  ref={fileInputRef}
                  accept=".xlsx,.xls,.csv"
                  onChange={handleFileUpload}
                  className="hidden"
                  id="excel-upload"
                />
                <Button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                  variant="outline"
                  className="border-orange-300 hover:bg-orange-100"
                  data-testid="upload-excel-btn"
                >
                  {uploading ? (
                    <>
                      <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                      {uploadProgress || 'Processing...'}
                    </>
                  ) : (
                    <>
                      <Upload className="h-4 w-4 mr-2" />
                      Upload CSV
                    </>
                  )}
                </Button>
                
                <Button
                  onClick={() => setShowPasteModal(true)}
                  disabled={uploading}
                  variant="outline"
                  className="border-blue-300 hover:bg-blue-100"
                  data-testid="paste-numbers-btn"
                >
                  <ClipboardPaste className="h-4 w-4 mr-2" />
                  Paste Numbers
                </Button>
                
                {uploadResult && (
                  <div className={`flex flex-col gap-1 text-sm ${uploadResult.success ? 'text-green-700' : 'text-orange-700'}`}>
                    <div className="flex items-center gap-2">
                      {uploadResult.success ? (
                        <CheckCircle className="h-4 w-4 text-green-600" />
                      ) : (
                        <AlertTriangle className="h-4 w-4 text-orange-600" />
                      )}
                      <span>
                        {uploadResult.success 
                          ? <>Imported <strong>{uploadResult.imported?.toLocaleString()}</strong> numbers (Total: <strong>{uploadResult.total_in_database?.toLocaleString()}</strong>)</>
                          : uploadResult.message || 'No valid phone numbers found'
                        }
                      </span>
                    </div>
                    {uploadResult.sample_values && uploadResult.sample_values.length > 0 && (
                      <div className="text-xs text-slate-500 ml-6">
                        Sample data found: {uploadResult.sample_values.slice(0, 3).join(', ')}...
                      </div>
                    )}
                    {uploadResult.hint && (
                      <div className="text-xs text-orange-600 ml-6">
                        {uploadResult.hint}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Step 2: Sync */}
            <div className="p-4 bg-white rounded-lg border border-orange-200">
              <div className="flex items-start gap-3 mb-3">
                <div className="w-8 h-8 bg-orange-100 rounded-full flex items-center justify-center flex-shrink-0">
                  <span className="text-orange-600 font-bold text-sm">2</span>
                </div>
                <div className="flex-1">
                  <h4 className="font-medium text-slate-900">Sync Users to "Existing"</h4>
                  <p className="text-sm text-slate-600 mt-1">
                    After uploading, click Sync to update all registered users whose phone numbers 
                    match the uploaded list to "Existing" customer type. No conditions - just hard converts.
                  </p>
                </div>
              </div>
              
              <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 ml-11">
                <Button
                  onClick={syncFundleCustomers}
                  disabled={syncing}
                  className="bg-orange-600 hover:bg-orange-700"
                  data-testid="sync-fundle-btn"
                >
                  {syncing ? (
                    <>
                      <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                      Syncing...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="h-4 w-4 mr-2" />
                      Sync Now
                    </>
                  )}
                </Button>
                
                {syncResult && (
                  <div className="flex items-center gap-4 text-sm">
                    <CheckCircle className="h-4 w-4 text-green-600" />
                    <span>Fundle List: <strong>{syncResult.fundle_customers_count?.toLocaleString()}</strong></span>
                    <span>Users: <strong>{syncResult.total_users?.toLocaleString()}</strong></span>
                    <span className="text-green-700">Updated: <strong>{syncResult.updated_to_existing}</strong></span>
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Admin List */}
        <Card className="border-slate-200 shadow-none">
          <CardHeader className="border-b border-slate-200">
            <CardTitle className="text-lg font-semibold">All Admin Users</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-900" />
              </div>
            ) : admins.length === 0 ? (
              <div className="text-center py-12 text-slate-500">
                <Users className="h-12 w-12 mx-auto mb-4 text-slate-300" />
                <p>No admin users found</p>
              </div>
            ) : (
              <div className="divide-y divide-slate-200">
                {admins.map((admin) => (
                  <div 
                    key={admin.id} 
                    className={`p-4 flex items-center justify-between hover:bg-slate-50 ${!admin.is_active ? 'opacity-50' : ''}`}
                  >
                    <div className="flex items-center gap-4">
                      <div className={`w-12 h-12 rounded-full flex items-center justify-center ${
                        admin.role === 'super_admin' ? 'bg-purple-100' : 'bg-blue-100'
                      }`}>
                        <User className={`h-6 w-6 ${
                          admin.role === 'super_admin' ? 'text-purple-600' : 'text-blue-600'
                        }`} />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="font-semibold text-slate-900">{admin.name}</h4>
                          {getRoleBadge(admin.role)}
                          {!admin.is_active && (
                            <Badge variant="outline" className="text-red-600 border-red-200">
                              Inactive
                            </Badge>
                          )}
                        </div>
                        <p className="text-sm text-slate-500">@{admin.username}</p>
                      </div>
                    </div>

                    <div className="flex items-center gap-6">
                      <div className="text-right">
                        <p className="text-xs text-slate-500">Last Login</p>
                        <p className="text-sm font-medium flex items-center gap-1">
                          <Clock className="h-3 w-3 text-slate-400" />
                          {formatDate(admin.last_login)}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-xs text-slate-500">Created</p>
                        <p className="text-sm">{formatDate(admin.created_at)}</p>
                      </div>
                      {admin.is_active && admin.role !== 'super_admin' && (
                        <Button
                          variant="outline"
                          size="sm"
                          className="text-red-600 hover:text-red-700 hover:bg-red-50"
                          onClick={() => {
                            setSelectedAdmin(admin);
                            setShowDeleteDialog(true);
                          }}
                          data-testid={`delete-admin-${admin.username}`}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Create Admin Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <UserPlus className="h-5 w-5" />
              Create New Admin
            </DialogTitle>
            <DialogDescription>
              Add a new administrator to the system
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="name">Full Name *</Label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
                <Input
                  id="name"
                  placeholder="Enter full name"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="pl-10"
                  data-testid="admin-name-input"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="username">Username *</Label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
                <Input
                  id="username"
                  placeholder="Enter username"
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value.toLowerCase().replace(/\s/g, '') })}
                  className="pl-10"
                  data-testid="admin-username-input"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password *</Label>
              <div className="relative">
                <Key className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
                <Input
                  id="password"
                  type="password"
                  placeholder="Enter password"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  className="pl-10"
                  data-testid="admin-password-input"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="role">Role</Label>
              <Select value={formData.role} onValueChange={(value) => setFormData({ ...formData, role: value })}>
                <SelectTrigger data-testid="admin-role-select">
                  <SelectValue placeholder="Select role" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="bill_operator">
                    <div className="flex items-center gap-2">
                      <Shield className="h-4 w-4 text-green-600" />
                      Bill Operator
                    </div>
                  </SelectItem>
                  <SelectItem value="app_manager">
                    <div className="flex items-center gap-2">
                      <Shield className="h-4 w-4 text-indigo-600" />
                      App Manager
                    </div>
                  </SelectItem>
                  <SelectItem value="call_centre">
                    <div className="flex items-center gap-2">
                      <Shield className="h-4 w-4 text-orange-600" />
                      Call Centre
                    </div>
                  </SelectItem>
                  <SelectItem value="support_officer">
                    <div className="flex items-center gap-2">
                      <Shield className="h-4 w-4 text-pink-600" />
                      Support Officer
                    </div>
                  </SelectItem>
                  <SelectItem value="admin">
                    <div className="flex items-center gap-2">
                      <Shield className="h-4 w-4 text-blue-600" />
                      Admin
                    </div>
                  </SelectItem>
                  <SelectItem value="super_admin">
                    <div className="flex items-center gap-2">
                      <ShieldCheck className="h-4 w-4 text-purple-600" />
                      Super Admin
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreateDialog(false)}>
              Cancel
            </Button>
            <Button 
              onClick={createAdmin} 
              disabled={creating}
              className="bg-slate-900 hover:bg-slate-800"
              data-testid="confirm-create-admin"
            >
              {creating ? (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
              ) : (
                <>
                  <UserPlus className="h-4 w-4 mr-2" />
                  Create Admin
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-600">
              <AlertTriangle className="h-5 w-5" />
              Deactivate Admin
            </DialogTitle>
            <DialogDescription>
              Are you sure you want to deactivate this admin account?
            </DialogDescription>
          </DialogHeader>

          {selectedAdmin && (
            <div className="py-4">
              <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg">
                <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center">
                  <User className="h-5 w-5 text-blue-600" />
                </div>
                <div>
                  <p className="font-semibold">{selectedAdmin.name}</p>
                  <p className="text-sm text-slate-500">@{selectedAdmin.username}</p>
                </div>
              </div>
              <p className="text-sm text-slate-500 mt-3">
                This admin will no longer be able to log in. This action can be reversed by a super admin.
              </p>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteDialog(false)}>
              Cancel
            </Button>
            <Button 
              variant="destructive"
              onClick={deleteAdmin}
              data-testid="confirm-delete-admin"
            >
              <Trash2 className="h-4 w-4 mr-2" />
              Deactivate
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Paste Phone Numbers Modal */}
      <Dialog open={showPasteModal} onOpenChange={setShowPasteModal}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Paste Phone Numbers</DialogTitle>
            <DialogDescription>
              Paste phone numbers below (one per line, or comma/tab separated). 
              The system will extract all valid 10-digit Indian mobile numbers.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <textarea
              className="w-full h-64 p-3 border rounded-lg font-mono text-sm"
              placeholder="9876543210
8765432109
7654321098
...or paste from Excel"
              value={pasteText}
              onChange={(e) => setPasteText(e.target.value)}
            />
            <p className="text-sm text-slate-500 mt-2">
              {pasteText ? `${extractPhonesFromText(pasteText).length.toLocaleString()} valid numbers found` : 'Paste your phone numbers above'}
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowPasteModal(false)}>
              Cancel
            </Button>
            <Button 
              onClick={handlePasteSubmit}
              disabled={!pasteText.trim()}
              className="bg-blue-600 hover:bg-blue-700"
            >
              Upload Numbers
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  );
};

export default AdminUsers;
