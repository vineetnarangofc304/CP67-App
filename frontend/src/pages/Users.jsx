import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '../components/DashboardLayout';
import { useAuth } from '../App';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { toast } from 'sonner';
import { 
  Search, 
  User,
  Phone,
  Calendar,
  Star,
  Receipt,
  MessageCircle,
  ChevronLeft,
  ChevronRight,
  Filter,
  ArrowLeft,
  X,
  UserPlus,
  Users as UsersIcon
} from 'lucide-react';

const Users = () => {
  const { token, API_URL } = useAuth();
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [customerTypeFilter, setCustomerTypeFilter] = useState('all');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [pagination, setPagination] = useState({ skip: 0, limit: 20, total: 0 });
  const [selectedUser, setSelectedUser] = useState(null);
  const [userDetails, setUserDetails] = useState(null);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [showFullScreen, setShowFullScreen] = useState(false);

  useEffect(() => {
    fetchUsers();
  }, [pagination.skip, sourceFilter, customerTypeFilter]);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      let url = `${API_URL}/users?skip=${pagination.skip}&limit=${pagination.limit}`;
      if (search) url += `&search=${encodeURIComponent(search)}`;
      if (sourceFilter && sourceFilter !== 'all') url += `&source=${sourceFilter}`;
      if (customerTypeFilter && customerTypeFilter !== 'all') url += `&customer_type=${customerTypeFilter}`;
      if (dateFrom) url += `&from_date=${dateFrom}`;
      if (dateTo) url += `&to_date=${dateTo}`;
      
      const response = await fetch(url, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setUsers(data.users);
        setPagination(prev => ({ ...prev, total: data.total }));
      }
    } catch (error) {
      toast.error('Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    setPagination(prev => ({ ...prev, skip: 0 }));
    fetchUsers();
  };

  const applyDateFilter = () => {
    setPagination(prev => ({ ...prev, skip: 0 }));
    fetchUsers();
  };

  const clearFilters = () => {
    setSourceFilter('all');
    setCustomerTypeFilter('all');
    setDateFrom('');
    setDateTo('');
    setSearch('');
    setPagination(prev => ({ ...prev, skip: 0 }));
  };

  const fetchUserDetails = async (userId) => {
    setLoadingDetails(true);
    try {
      const response = await fetch(`${API_URL}/users/${userId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setUserDetails(data);
      }
    } catch (error) {
      toast.error('Failed to load user details');
    } finally {
      setLoadingDetails(false);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const sourceColors = {
    'SRC_BRANDS': 'bg-purple-100 text-purple-800',
    'SRC_FOODCOURT': 'bg-orange-100 text-orange-800',
    'SRC_PARKING': 'bg-blue-100 text-blue-800',
    'SRC_DIGITAL': 'bg-green-100 text-green-800',
    'SRC_SOCIAL': 'bg-pink-100 text-pink-800',
    'SRC_WEBSITE': 'bg-cyan-100 text-cyan-800'
  };

  return (
    <DashboardLayout title="Users">
      {/* Filters */}
      <Card className="mb-6 border-slate-200 shadow-none">
        <CardContent className="pt-6">
          <div className="flex flex-col gap-4">
            {/* Row 1: Search and Source Filter */}
            <div className="flex flex-col md:flex-row gap-4">
              <form onSubmit={handleSearch} className="flex-1 flex gap-2">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
                  <Input
                    placeholder="Search by phone or name..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="pl-10"
                    data-testid="user-search-input"
                  />
                </div>
                <Button type="submit" data-testid="user-search-btn">Search</Button>
              </form>
              <div className="flex items-center gap-2">
                <Filter className="h-4 w-4 text-slate-400" />
                <Select value={sourceFilter} onValueChange={(value) => {
                  setSourceFilter(value);
                  setPagination(prev => ({ ...prev, skip: 0 }));
                }}>
                  <SelectTrigger className="w-[180px]" data-testid="source-filter">
                    <SelectValue placeholder="Filter by source" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Sources</SelectItem>
                    <SelectItem value="SRC_BRANDS">Retailer</SelectItem>
                    <SelectItem value="SRC_FOODCOURT">Food Court</SelectItem>
                    <SelectItem value="SRC_PARKING">Parking</SelectItem>
                    <SelectItem value="SRC_DIGITAL">Digital Screens</SelectItem>
                    <SelectItem value="SRC_SOCIAL">Social</SelectItem>
                    <SelectItem value="SRC_WEBSITE">Website</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            
            {/* Row 2: Customer Type and Date Filters */}
            <div className="flex flex-wrap items-center gap-4 pt-2 border-t border-slate-100">
              <div className="flex items-center gap-2">
                <UsersIcon className="h-4 w-4 text-slate-400" />
                <Select value={customerTypeFilter} onValueChange={(value) => {
                  setCustomerTypeFilter(value);
                  setPagination(prev => ({ ...prev, skip: 0 }));
                }}>
                  <SelectTrigger className="w-[150px]" data-testid="customer-type-filter">
                    <SelectValue placeholder="Customer Type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Customers</SelectItem>
                    <SelectItem value="new">
                      <span className="flex items-center gap-2">
                        <UserPlus className="h-3 w-3 text-green-600" />
                        New
                      </span>
                    </SelectItem>
                    <SelectItem value="existing">
                      <span className="flex items-center gap-2">
                        <User className="h-3 w-3 text-blue-600" />
                        Existing
                      </span>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
              
              <div className="flex items-center gap-2">
                <Calendar className="h-4 w-4 text-slate-400" />
                <Label className="text-sm text-slate-500">From:</Label>
                <Input
                  type="date"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                  className="w-36"
                  data-testid="date-from"
                />
              </div>
              <div className="flex items-center gap-2">
                <Label className="text-sm text-slate-500">To:</Label>
                <Input
                  type="date"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                  className="w-36"
                  data-testid="date-to"
                />
              </div>
              <Button size="sm" onClick={applyDateFilter} data-testid="apply-date-filter">
                Apply
              </Button>
              <Button size="sm" variant="outline" onClick={clearFilters}>
                Clear All
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Users Table */}
      <Card className="border-slate-200 shadow-none">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="bg-slate-50">
                <TableHead>User</TableHead>
                <TableHead>Phone</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Points</TableHead>
                <TableHead>Joined</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                [...Array(5)].map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={7}>
                      <div className="h-12 skeleton rounded" />
                    </TableCell>
                  </TableRow>
                ))
              ) : users.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8 text-slate-500">
                    No users found
                  </TableCell>
                </TableRow>
              ) : (
                users.map((user) => (
                  <TableRow key={user.id} className="table-row-hover">
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 bg-slate-100 rounded-full flex items-center justify-center">
                          <User className="h-4 w-4 text-slate-500" />
                        </div>
                        <div>
                          <span className="font-medium">{user.name || 'Not registered'}</span>
                          <div className="flex items-center gap-1 mt-0.5">
                            {user.customer_type === 'existing' ? (
                              <Badge className="bg-blue-100 text-blue-700 text-[10px] px-1.5 py-0">Existing</Badge>
                            ) : (
                              <Badge className="bg-green-100 text-green-700 text-[10px] px-1.5 py-0">New</Badge>
                            )}
                          </div>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2 text-slate-600">
                        <Phone className="h-3 w-3" />
                        {user.phone}
                      </div>
                    </TableCell>
                    <TableCell>
                      {user.first_touch_source ? (
                        <Badge className={sourceColors[user.first_touch_source] || 'bg-slate-100 text-slate-800'}>
                          {user.first_touch_source.replace('SRC_', '')}
                        </Badge>
                      ) : (
                        <span className="text-slate-400">-</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant={user.kyc_status ? 'default' : 'outline'} className={user.kyc_status ? 'bg-green-100 text-green-800' : ''}>
                        {user.kyc_status ? 'Registered' : 'Pending'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1 text-slate-400">
                        <Star className="h-4 w-4" />
                        <span className="text-xs">View</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-slate-500 text-sm">
                      {formatDate(user.created_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button 
                        variant="outline" 
                        size="sm"
                        onClick={() => {
                          setSelectedUser(user);
                          setShowFullScreen(true);
                          fetchUserDetails(user.id);
                        }}
                        data-testid={`view-user-${user.id}`}
                      >
                        View
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>

          {/* Pagination */}
          <div className="flex items-center justify-between p-4 border-t border-slate-200">
            <p className="text-sm text-slate-500">
              Showing {pagination.skip + 1} to {Math.min(pagination.skip + pagination.limit, pagination.total)} of {pagination.total} users
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={pagination.skip === 0}
                onClick={() => setPagination(prev => ({ ...prev, skip: Math.max(0, prev.skip - prev.limit) }))}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={pagination.skip + pagination.limit >= pagination.total}
                onClick={() => setPagination(prev => ({ ...prev, skip: prev.skip + prev.limit }))}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Full Screen User Details View */}
      {showFullScreen && (
        <div className="fixed inset-0 z-50 bg-white overflow-y-auto">
          <div className="sticky top-0 bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between z-10">
            <div className="flex items-center gap-4">
              <Button 
                variant="ghost" 
                size="sm"
                onClick={() => {
                  setShowFullScreen(false);
                  setUserDetails(null);
                  setSelectedUser(null);
                }}
              >
                <ArrowLeft className="h-4 w-4 mr-2" />
                Back to Users
              </Button>
              <h2 className="text-xl font-bold font-['Manrope']">User Details</h2>
            </div>
            <Button 
              variant="ghost" 
              size="icon"
              onClick={() => {
                setShowFullScreen(false);
                setUserDetails(null);
                setSelectedUser(null);
              }}
            >
              <X className="h-5 w-5" />
            </Button>
          </div>
          
          <div className="p-6 max-w-6xl mx-auto">
            {loadingDetails ? (
              <div className="flex items-center justify-center py-16">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-slate-900"></div>
              </div>
            ) : userDetails ? (
              <div className="space-y-8">
                {/* User Info Header */}
                <div className="flex items-center gap-6 p-6 bg-slate-50 rounded-xl">
                  <div className="w-20 h-20 bg-slate-200 rounded-full flex items-center justify-center">
                    <User className="h-10 w-10 text-slate-500" />
                  </div>
                  <div>
                    <h3 className="text-2xl font-bold font-['Manrope']">{userDetails.user.name || 'Not registered'}</h3>
                    <p className="text-slate-500 flex items-center gap-2 mt-1">
                      <Phone className="h-4 w-4" />
                      {userDetails.user.phone}
                    </p>
                    <div className="flex items-center gap-4 mt-2">
                      <Badge variant={userDetails.user.kyc_status ? 'default' : 'outline'} className={userDetails.user.kyc_status ? 'bg-green-100 text-green-800' : ''}>
                        {userDetails.user.kyc_status ? 'Registered' : 'Pending KYC'}
                      </Badge>
                      {userDetails.user.first_touch_source && (
                        <Badge className={sourceColors[userDetails.user.first_touch_source] || 'bg-slate-100 text-slate-800'}>
                          {userDetails.user.first_touch_source.replace('SRC_', '')}
                        </Badge>
                      )}
                    </div>
                  </div>
                </div>

                {/* Stats Grid */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-slate-50 rounded-xl p-6">
                    <p className="text-sm text-slate-500 mb-1">Balance Points</p>
                    <p className="text-3xl font-bold text-[#D4AF37]">{Math.round(userDetails.user.balance_points || 0).toLocaleString()}</p>
                    {userDetails.user.total_customer_spend > 0 && (
                      <p className="text-xs text-slate-500 mt-1">
                        Spend: ₹{Math.round(userDetails.user.total_customer_spend || 0).toLocaleString()}
                      </p>
                    )}
                    <p className="text-xs text-green-600 mt-1">Live from Fundle</p>
                  </div>
                  <div className="bg-slate-50 rounded-xl p-6">
                    <p className="text-sm text-slate-500 mb-1">Total Earned</p>
                    <p className="text-3xl font-bold text-slate-900">{Math.round(userDetails.user.total_earned_points || 0).toLocaleString()}</p>
                  </div>
                  <div className="bg-slate-50 rounded-xl p-6">
                    <p className="text-sm text-slate-500 mb-1">Total Bills</p>
                    <p className="text-3xl font-bold text-slate-900">{userDetails.bills.length}</p>
                  </div>
                  <div className="bg-slate-50 rounded-xl p-6">
                    <p className="text-sm text-slate-500 mb-1">Messages</p>
                    <p className="text-3xl font-bold text-slate-900">{userDetails.whatsapp_logs.length}</p>
                  </div>
                </div>

                {/* Additional Info */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="bg-slate-50 rounded-lg p-4">
                    <p className="text-xs text-slate-500 mb-1">First Touch Source</p>
                    <p className="font-semibold">{userDetails.user.first_touch_source || 'N/A'}</p>
                  </div>
                  <div className="bg-slate-50 rounded-lg p-4">
                    <p className="text-xs text-slate-500 mb-1">First Touch QR</p>
                    <p className="font-semibold">{userDetails.user.first_touch_qr || 'N/A'}</p>
                  </div>
                  <div className="bg-slate-50 rounded-lg p-4">
                    <p className="text-xs text-slate-500 mb-1">Registered On</p>
                    <p className="font-semibold">{formatDate(userDetails.user.created_at)}</p>
                  </div>
                </div>

                {/* Bills Section */}
                <Card className="border-slate-200 shadow-none">
                  <CardHeader>
                    <CardTitle className="font-['Manrope'] flex items-center gap-2">
                      <Receipt className="h-5 w-5" /> 
                      Bills ({userDetails.bills.length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {userDetails.bills.length > 0 ? (
                      <div className="space-y-3">
                        {userDetails.bills.map((bill) => (
                          <div key={bill.id} className="flex items-center justify-between p-4 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors">
                            <div className="flex-1">
                              <p className="font-semibold text-lg">{bill.store_name || 'Unknown Store'}</p>
                              <p className="text-sm text-slate-500">Bill No: {bill.bill_no || 'N/A'} • Date: {bill.bill_date || 'N/A'}</p>
                              {bill.rejection_reason && (
                                <p className="text-xs text-red-500 mt-1">{bill.rejection_reason}</p>
                              )}
                            </div>
                            <div className="text-center px-4">
                              <p className="text-2xl font-bold">₹{bill.amount || 0}</p>
                            </div>
                            <div className="text-right">
                              <Badge variant="outline" className={
                                bill.status === 'auto_approved' || bill.status === 'approved' ? 'bg-green-100 text-green-800' :
                                bill.status === 'rejected' ? 'bg-red-100 text-red-800' :
                                bill.status === 'duplicate' ? 'bg-purple-100 text-purple-800' :
                                'bg-yellow-100 text-yellow-800'
                              }>
                                {bill.status}
                              </Badge>
                              <p className="text-sm text-[#D4AF37] font-semibold mt-1">+{bill.points_issued || 0} pts</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-slate-500 text-center py-8">No bills uploaded yet</p>
                    )}
                  </CardContent>
                </Card>

                {/* WhatsApp Logs Section */}
                <Card className="border-slate-200 shadow-none">
                  <CardHeader>
                    <CardTitle className="font-['Manrope'] flex items-center gap-2">
                      <MessageCircle className="h-5 w-5" /> 
                      WhatsApp Conversations ({userDetails.whatsapp_logs.length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {userDetails.whatsapp_logs.length > 0 ? (
                      <div className="space-y-3 max-h-96 overflow-y-auto">
                        {userDetails.whatsapp_logs.map((log) => (
                          <div key={log.id} className={`p-4 rounded-lg ${log.direction === 'inbound' ? 'bg-slate-50 mr-12' : 'bg-green-50 ml-12'}`}>
                            <div className="flex items-center justify-between mb-2">
                              <Badge variant="outline" className={log.direction === 'inbound' ? 'bg-slate-100' : 'bg-green-100'}>
                                {log.direction === 'inbound' ? '← Received' : '→ Sent'}
                              </Badge>
                              <span className="text-xs text-slate-500">{formatDate(log.timestamp)}</span>
                            </div>
                            <p className="text-slate-700">{log.content}</p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-slate-500 text-center py-8">No conversation history</p>
                    )}
                  </CardContent>
                </Card>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </DashboardLayout>
  );
};

export default Users;
