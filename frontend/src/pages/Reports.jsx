import React, { useState } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import { useAuth } from '../App';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Label } from '../components/ui/label';
import { Input } from '../components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { toast } from 'sonner';
import { 
  Download, 
  FileSpreadsheet, 
  Users, 
  Receipt, 
  Car,
  Store
} from 'lucide-react';

const Reports = () => {
  const { token, API_URL } = useAuth();
  const [loading, setLoading] = useState({});
  
  // Filters
  const [billsStatus, setBillsStatus] = useState('all');
  const [usersType, setUsersType] = useState('all');
  const [parkingStatus, setParkingStatus] = useState('all');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const downloadFile = async (endpoint, filename, filterParams = {}) => {
    setLoading(prev => ({ ...prev, [endpoint]: true }));
    
    try {
      const params = new URLSearchParams();
      Object.entries(filterParams).forEach(([key, value]) => {
        if (value && value !== 'all') {
          params.append(key, value);
        }
      });
      
      const url = `${API_URL}${endpoint}${params.toString() ? '?' + params.toString() : ''}`;
      
      const response = await fetch(url, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (!response.ok) {
        throw new Error('Export failed');
      }
      
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(downloadUrl);
      
      toast.success(`${filename} downloaded successfully`);
    } catch (error) {
      toast.error(`Failed to export: ${error.message}`);
    } finally {
      setLoading(prev => ({ ...prev, [endpoint]: false }));
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Export Reports</h1>
          <p className="text-slate-500">Download data as CSV files for analysis</p>
        </div>

        {/* Date Range Filter */}
        <Card className="border-slate-200 shadow-none">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Date Range (Optional)</CardTitle>
            <CardDescription>Apply to all exports</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col sm:flex-row gap-4">
              <div className="flex-1">
                <Label className="mb-2 block">Start Date</Label>
                <Input 
                  type="date" 
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                />
              </div>
              <div className="flex-1">
                <Label className="mb-2 block">End Date</Label>
                <Input 
                  type="date" 
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Export Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Bills Export */}
          <Card className="border-slate-200 shadow-none">
            <CardHeader className="pb-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                  <Receipt className="h-5 w-5 text-blue-600" />
                </div>
                <div>
                  <CardTitle className="text-lg">Bills</CardTitle>
                  <CardDescription>Export bill records</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label className="mb-2 block">Status Filter</Label>
                <Select value={billsStatus} onValueChange={setBillsStatus}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Status</SelectItem>
                    <SelectItem value="approved">Approved</SelectItem>
                    <SelectItem value="rejected">Rejected</SelectItem>
                    <SelectItem value="pending_review">Pending Review</SelectItem>
                    <SelectItem value="manual_review">Manual Review</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button 
                onClick={() => downloadFile('/export/bills', 'bills_export.csv', {
                  status: billsStatus,
                  start_date: startDate,
                  end_date: endDate
                })}
                disabled={loading['/export/bills']}
                className="w-full"
              >
                <Download className="h-4 w-4 mr-2" />
                {loading['/export/bills'] ? 'Exporting...' : 'Export Bills CSV'}
              </Button>
            </CardContent>
          </Card>

          {/* Users Export */}
          <Card className="border-slate-200 shadow-none">
            <CardHeader className="pb-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
                  <Users className="h-5 w-5 text-green-600" />
                </div>
                <div>
                  <CardTitle className="text-lg">Users</CardTitle>
                  <CardDescription>Export customer records</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label className="mb-2 block">Customer Type</Label>
                <Select value={usersType} onValueChange={setUsersType}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Customers</SelectItem>
                    <SelectItem value="new">New Customers</SelectItem>
                    <SelectItem value="existing">Existing Customers</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button 
                onClick={() => downloadFile('/export/users', 'users_export.csv', {
                  customer_type: usersType,
                  start_date: startDate,
                  end_date: endDate
                })}
                disabled={loading['/export/users']}
                className="w-full"
              >
                <Download className="h-4 w-4 mr-2" />
                {loading['/export/users'] ? 'Exporting...' : 'Export Users CSV'}
              </Button>
            </CardContent>
          </Card>

          {/* Brands Export */}
          <Card className="border-slate-200 shadow-none">
            <CardHeader className="pb-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
                  <Store className="h-5 w-5 text-purple-600" />
                </div>
                <div>
                  <CardTitle className="text-lg">Brands</CardTitle>
                  <CardDescription>Export brand configuration with ATV</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <Button 
                onClick={() => downloadFile('/export/brands', 'brands_export.csv')}
                disabled={loading['/export/brands']}
                className="w-full"
              >
                <Download className="h-4 w-4 mr-2" />
                {loading['/export/brands'] ? 'Exporting...' : 'Export Brands CSV'}
              </Button>
            </CardContent>
          </Card>

          {/* Parking Export */}
          <Card className="border-slate-200 shadow-none">
            <CardHeader className="pb-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-orange-100 rounded-lg flex items-center justify-center">
                  <Car className="h-5 w-5 text-orange-600" />
                </div>
                <div>
                  <CardTitle className="text-lg">Parking Sessions</CardTitle>
                  <CardDescription>Export parking validation records</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label className="mb-2 block">Status Filter</Label>
                <Select value={parkingStatus} onValueChange={setParkingStatus}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Status</SelectItem>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="completed">Completed</SelectItem>
                    <SelectItem value="expired">Expired</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button 
                onClick={() => downloadFile('/export/parking', 'parking_export.csv', {
                  status: parkingStatus,
                  start_date: startDate,
                  end_date: endDate
                })}
                disabled={loading['/export/parking']}
                className="w-full"
              >
                <Download className="h-4 w-4 mr-2" />
                {loading['/export/parking'] ? 'Exporting...' : 'Export Parking CSV'}
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default Reports;
