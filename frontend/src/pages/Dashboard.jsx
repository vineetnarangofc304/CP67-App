import React, { useState, useEffect } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import { useAuth } from '../App';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { 
  Users, 
  Receipt, 
  QrCode, 
  MessageCircle,
  TrendingUp,
  Clock,
  CheckCircle,
  AlertCircle,
  Footprints,
  UserPlus,
  FileText,
  Plus
} from 'lucide-react';
import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell
} from 'recharts';

const Dashboard = () => {
  const { token, API_URL } = useAuth();
  const [stats, setStats] = useState(null);
  const [dailyStats, setDailyStats] = useState([]);
  const [funnelData, setFunnelData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [footfallDate, setFootfallDate] = useState(new Date().toISOString().split('T')[0]);
  const [footfallCount, setFootfallCount] = useState('');
  const [showFootfallInput, setShowFootfallInput] = useState(false);

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      const [statsRes, dailyRes, funnelRes] = await Promise.all([
        fetch(`${API_URL}/analytics/dashboard`, {
          headers: { 'Authorization': `Bearer ${token}` }
        }),
        fetch(`${API_URL}/analytics/daily-stats?days=7`, {
          headers: { 'Authorization': `Bearer ${token}` }
        }),
        fetch(`${API_URL}/analytics/user-funnel`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
      ]);

      if (statsRes.ok) setStats(await statsRes.json());
      if (dailyRes.ok) setDailyStats(await dailyRes.json());
      if (funnelRes.ok) {
        const data = await funnelRes.json();
        setFunnelData(data.funnel || []);
      }
    } catch (error) {
      console.error('Error fetching dashboard data:', error);
    } finally {
      setLoading(false);
    }
  };

  const COLORS = ['#0F172A', '#334155', '#64748B', '#D4AF37', '#34C759'];

  const submitFootfall = async () => {
    if (!footfallCount || parseInt(footfallCount) <= 0) return;
    try {
      await fetch(`${API_URL}/admin/footfall`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ date: footfallDate, count: parseInt(footfallCount) })
      });
      setFootfallCount('');
      setShowFootfallInput(false);
      fetchDashboardData();
    } catch { }
  };

  const billStatusData = stats ? [
    { name: 'Auto Approved', value: stats.bills.auto_approved, color: '#34C759' },
    { name: 'Manual Review', value: stats.bills.manual_review, color: '#FFCC00' },
    { name: 'Approved', value: stats.bills.approved, color: '#0F172A' },
    { name: 'Rejected', value: stats.bills.rejected, color: '#FF3B30' },
    { name: 'Duplicate', value: stats.bills.duplicate, color: '#AF52DE' }
  ].filter(d => d.value > 0) : [];

  if (loading) {
    return (
      <DashboardLayout title="Dashboard">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="h-32 bg-white rounded-lg skeleton" />
          ))}
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title="Dashboard">
      {/* Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <Card 
          className="metric-card card-hover border-slate-200 shadow-none cursor-pointer" 
          data-testid="metric-total-users"
          onClick={() => window.location.href = '/users'}
        >
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-500">Total Customers</p>
                <p className="text-3xl font-bold text-slate-900 font-['Manrope'] mt-1">
                  {stats?.users.total || 0}
                </p>
                <div className="flex gap-3 mt-1">
                  <p className="text-xs text-green-600 flex items-center gap-1">
                    <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                    {stats?.users.new_customers || 0} new
                  </p>
                  <p className="text-xs text-blue-600 flex items-center gap-1">
                    <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
                    {stats?.users.existing_customers || 0} existing
                  </p>
                </div>
              </div>
              <div className="w-12 h-12 bg-slate-100 rounded-xl flex items-center justify-center">
                <Users className="h-6 w-6 text-slate-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card 
          className="metric-card card-hover border-slate-200 shadow-none cursor-pointer" 
          data-testid="metric-total-bills"
          onClick={() => window.location.href = '/bills'}
        >
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-500">Total Bills</p>
                <p className="text-3xl font-bold text-slate-900 font-['Manrope'] mt-1">
                  {stats?.bills.total || 0}
                </p>
                <p className="text-xs text-green-600 mt-1 flex items-center gap-1">
                  <TrendingUp className="h-3 w-3" />
                  +{stats?.bills.today || 0} today
                </p>
              </div>
              <div className="w-12 h-12 bg-green-100 rounded-xl flex items-center justify-center">
                <Receipt className="h-6 w-6 text-green-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card 
          className="metric-card card-hover border-slate-200 shadow-none cursor-pointer" 
          data-testid="metric-qr-scans"
          onClick={() => window.location.href = '/qr-codes'}
        >
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-500">QR Scans</p>
                <p className="text-3xl font-bold text-slate-900 font-['Manrope'] mt-1">
                  {stats?.qr.total_scans || 0}
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  Across all locations
                </p>
              </div>
              <div className="w-12 h-12 bg-purple-100 rounded-xl flex items-center justify-center">
                <QrCode className="h-6 w-6 text-purple-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card 
          className="metric-card card-hover border-slate-200 shadow-none cursor-pointer" 
          data-testid="metric-points-issued"
          onClick={() => window.location.href = '/analytics'}
        >
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-500">Points Issued</p>
                <p className="text-3xl font-bold text-slate-900 font-['Manrope'] mt-1">
                  {Math.round(stats?.points.total_issued || 0).toLocaleString()}
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  Total loyalty points
                </p>
              </div>
              <div className="w-12 h-12 bg-[#D4AF37]/20 rounded-xl flex items-center justify-center">
                <span className="text-[#D4AF37] text-xl font-bold">★</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Footfall & Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <Card className="metric-card border-slate-200 shadow-none" data-testid="metric-footfall">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-500">Total Footfall</p>
                <p className="text-3xl font-bold text-slate-900 font-['Manrope'] mt-1">
                  {(stats?.footfall?.total || 0).toLocaleString()}
                </p>
                <p className="text-xs text-slate-400 mt-1">Last 30 days</p>
              </div>
              <div className="w-12 h-12 bg-amber-100 rounded-xl flex items-center justify-center">
                <Footprints className="h-6 w-6 text-amber-600" />
              </div>
            </div>
            {!showFootfallInput ? (
              <button onClick={() => setShowFootfallInput(true)} className="mt-3 flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800">
                <Plus className="h-3 w-3" /> Add daily count
              </button>
            ) : (
              <div className="mt-3 flex gap-2 items-center">
                <input type="date" value={footfallDate} onChange={e => setFootfallDate(e.target.value)} className="border rounded px-2 py-1 text-xs w-28" />
                <input type="number" value={footfallCount} onChange={e => setFootfallCount(e.target.value)} placeholder="Count" className="border rounded px-2 py-1 text-xs w-20" data-testid="footfall-count-input" />
                <button onClick={submitFootfall} className="bg-slate-900 text-white text-xs px-3 py-1 rounded" data-testid="submit-footfall-btn">Save</button>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="metric-card border-slate-200 shadow-none" data-testid="metric-registrations">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-500">Total Registrations</p>
                <p className="text-3xl font-bold text-slate-900 font-['Manrope'] mt-1">
                  {stats?.users?.total || 0}
                </p>
                <p className="text-xs text-green-600 mt-1 flex items-center gap-1">
                  <TrendingUp className="h-3 w-3" />
                  +{stats?.users?.today || 0} today
                </p>
              </div>
              <div className="w-12 h-12 bg-blue-100 rounded-xl flex items-center justify-center">
                <UserPlus className="h-6 w-6 text-blue-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="metric-card border-slate-200 shadow-none" data-testid="metric-bill-uploads">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-500">Total Bill Uploads</p>
                <p className="text-3xl font-bold text-slate-900 font-['Manrope'] mt-1">
                  {stats?.bills?.total || 0}
                </p>
                <p className="text-xs text-green-600 mt-1 flex items-center gap-1">
                  <TrendingUp className="h-3 w-3" />
                  +{stats?.bills?.today || 0} today
                </p>
              </div>
              <div className="w-12 h-12 bg-emerald-100 rounded-xl flex items-center justify-center">
                <FileText className="h-6 w-6 text-emerald-600" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Daily Activity Chart */}
        <Card className="border-slate-200 shadow-none">
          <CardHeader>
            <CardTitle className="font-['Manrope']">Daily Activity (Last 7 Days)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={dailyStats}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis 
                    dataKey="date" 
                    stroke="#64748b"
                    tickFormatter={(value) => new Date(value).toLocaleDateString('en-US', { weekday: 'short' })}
                  />
                  <YAxis stroke="#64748b" />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: 'white', 
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px'
                    }}
                  />
                  <Line 
                    type="monotone" 
                    dataKey="users" 
                    stroke="#0F172A" 
                    strokeWidth={2}
                    dot={{ fill: '#0F172A' }}
                    name="New Users"
                  />
                  <Line 
                    type="monotone" 
                    dataKey="bills" 
                    stroke="#D4AF37" 
                    strokeWidth={2}
                    dot={{ fill: '#D4AF37' }}
                    name="Bills Uploaded"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Bill Status Distribution */}
        <Card className="border-slate-200 shadow-none">
          <CardHeader>
            <CardTitle className="font-['Manrope']">Bill Status Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              {billStatusData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={billStatusData}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={100}
                      paddingAngle={2}
                      dataKey="value"
                    >
                      {billStatusData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip 
                      contentStyle={{ 
                        backgroundColor: 'white', 
                        border: '1px solid #e2e8f0',
                        borderRadius: '8px'
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-slate-500">
                  No bill data yet
                </div>
              )}
            </div>
            {/* Legend */}
            <div className="flex flex-wrap justify-center gap-4 mt-4">
              {billStatusData.map((item, index) => (
                <div key={index} className="flex items-center gap-2">
                  <div 
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: item.color }}
                  />
                  <span className="text-sm text-slate-600">{item.name}: {item.value}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* User Funnel & Quick Stats */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* User Funnel */}
        <Card className="lg:col-span-2 border-slate-200 shadow-none">
          <CardHeader>
            <CardTitle className="font-['Manrope']">User Funnel</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {funnelData.map((stage, index) => {
                const maxCount = Math.max(...funnelData.map(s => s.count));
                const width = maxCount > 0 ? (stage.count / maxCount) * 100 : 0;
                return (
                  <div key={index} className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="font-medium text-slate-700">{stage.stage}</span>
                      <span className="text-slate-500">{stage.count}</span>
                    </div>
                    <div className="h-8 bg-slate-100 rounded-lg overflow-hidden">
                      <div 
                        className={`h-full funnel-stage-${index + 1} transition-all duration-500`}
                        style={{ width: `${width}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>

        {/* Quick Stats */}
        <Card className="border-slate-200 shadow-none">
          <CardHeader>
            <CardTitle className="font-['Manrope']">Quick Stats</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
              <div className="flex items-center gap-3">
                <CheckCircle className="h-5 w-5 text-green-500" />
                <span className="text-sm text-slate-600">Registered Users</span>
              </div>
              <span className="font-semibold text-slate-900">{stats?.users.registered || 0}</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
              <div className="flex items-center gap-3">
                <Clock className="h-5 w-5 text-yellow-500" />
                <span className="text-sm text-slate-600">Pending Reviews</span>
              </div>
              <span className="font-semibold text-slate-900">{stats?.bills.manual_review || 0}</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
              <div className="flex items-center gap-3">
                <MessageCircle className="h-5 w-5 text-blue-500" />
                <span className="text-sm text-slate-600">WhatsApp Messages</span>
              </div>
              <span className="font-semibold text-slate-900">{stats?.whatsapp.total_messages || 0}</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
              <div className="flex items-center gap-3">
                <AlertCircle className="h-5 w-5 text-red-500" />
                <span className="text-sm text-slate-600">Duplicate Bills</span>
              </div>
              <span className="font-semibold text-slate-900">{stats?.bills.duplicate || 0}</span>
            </div>
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
};

export default Dashboard;
