import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '../components/DashboardLayout';
import { useAuth } from '../App';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { toast } from 'sonner';
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
  Cell,
  AreaChart,
  Area
} from 'recharts';
import { 
  Download, 
  TrendingUp,
  Users,
  Receipt,
  QrCode,
  Calendar,
  ExternalLink,
  Filter
} from 'lucide-react';

const Analytics = () => {
  const { token, API_URL } = useAuth();
  const navigate = useNavigate();
  const [qrPerformance, setQrPerformance] = useState([]);
  const [dailyStats, setDailyStats] = useState([]);
  const [funnelData, setFunnelData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dateRange, setDateRange] = useState('7');
  const [filterMode, setFilterMode] = useState('preset'); // 'preset' or 'custom'
  const [customDateFrom, setCustomDateFrom] = useState('');
  const [customDateTo, setCustomDateTo] = useState('');

  useEffect(() => {
    if (filterMode === 'preset') {
      fetchAnalytics();
    }
  }, [dateRange, filterMode]);

  const fetchAnalytics = async (fromDate = null, toDate = null) => {
    setLoading(true);
    try {
      let daysParam = dateRange;
      let queryParams = `days=${daysParam}`;
      
      if (fromDate && toDate) {
        queryParams = `from_date=${fromDate}&to_date=${toDate}`;
      }
      
      const [qrRes, dailyRes, funnelRes] = await Promise.all([
        fetch(`${API_URL}/analytics/qr-performance?${queryParams}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        }),
        fetch(`${API_URL}/analytics/daily-stats?${queryParams}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        }),
        fetch(`${API_URL}/analytics/user-funnel?${queryParams}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
      ]);

      if (qrRes.ok) setQrPerformance(await qrRes.json());
      if (dailyRes.ok) setDailyStats(await dailyRes.json());
      if (funnelRes.ok) {
        const data = await funnelRes.json();
        setFunnelData(data.funnel || []);
      }
    } catch (error) {
      toast.error('Failed to load analytics');
    } finally {
      setLoading(false);
    }
  };

  const applyCustomDateFilter = () => {
    if (!customDateFrom || !customDateTo) {
      toast.error('Please select both From and To dates');
      return;
    }
    if (new Date(customDateFrom) > new Date(customDateTo)) {
      toast.error('From date cannot be after To date');
      return;
    }
    fetchAnalytics(customDateFrom, customDateTo);
    toast.success(`Showing data from ${customDateFrom} to ${customDateTo}`);
  };

  const clearCustomFilter = () => {
    setFilterMode('preset');
    setCustomDateFrom('');
    setCustomDateTo('');
  };

  const COLORS = ['#0F172A', '#334155', '#64748B', '#D4AF37', '#34C759'];
  const QR_COLORS = ['#AF52DE', '#FF9500', '#007AFF', '#34C759', '#FF3B30'];

  const exportReport = () => {
    const reportData = {
      generated_at: new Date().toISOString(),
      date_range: `${dateRange} days`,
      qr_performance: qrPerformance,
      daily_stats: dailyStats,
      funnel: funnelData
    };

    const blob = new Blob([JSON.stringify(reportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `cp67_analytics_${new Date().toISOString().split('T')[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Report exported!');
  };

  if (loading) {
    return (
      <DashboardLayout title="Analytics">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="h-80 skeleton rounded-lg" />
          ))}
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title="Analytics">
      {/* Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div className="flex flex-wrap items-center gap-4">
          {/* Filter Mode Toggle */}
          <div className="flex items-center gap-2 bg-slate-100 p-1 rounded-lg">
            <Button 
              variant={filterMode === 'preset' ? 'default' : 'ghost'} 
              size="sm"
              onClick={() => setFilterMode('preset')}
            >
              Preset
            </Button>
            <Button 
              variant={filterMode === 'custom' ? 'default' : 'ghost'} 
              size="sm"
              onClick={() => setFilterMode('custom')}
            >
              <Filter className="h-4 w-4 mr-1" />
              Custom
            </Button>
          </div>

          {filterMode === 'preset' ? (
            <Select value={dateRange} onValueChange={setDateRange}>
              <SelectTrigger className="w-[180px]" data-testid="date-range-select">
                <Calendar className="h-4 w-4 mr-2" />
                <SelectValue placeholder="Select range" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="7">Last 7 days</SelectItem>
                <SelectItem value="14">Last 14 days</SelectItem>
                <SelectItem value="30">Last 30 days</SelectItem>
                <SelectItem value="60">Last 60 days</SelectItem>
                <SelectItem value="90">Last 90 days</SelectItem>
              </SelectContent>
            </Select>
          ) : (
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <Label className="text-sm text-slate-500">From:</Label>
                <Input 
                  type="date" 
                  value={customDateFrom}
                  onChange={(e) => setCustomDateFrom(e.target.value)}
                  className="w-40"
                  data-testid="date-from-input"
                />
              </div>
              <div className="flex items-center gap-2">
                <Label className="text-sm text-slate-500">To:</Label>
                <Input 
                  type="date" 
                  value={customDateTo}
                  onChange={(e) => setCustomDateTo(e.target.value)}
                  className="w-40"
                  data-testid="date-to-input"
                />
              </div>
              <Button size="sm" onClick={applyCustomDateFilter} data-testid="apply-filter-btn">
                Apply
              </Button>
              <Button size="sm" variant="outline" onClick={clearCustomFilter}>
                Clear
              </Button>
            </div>
          )}
        </div>
        <Button onClick={exportReport} className="gap-2" data-testid="export-report-btn">
          <Download className="h-4 w-4" />
          Export Report
        </Button>
      </div>

      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="qr">QR Performance</TabsTrigger>
          <TabsTrigger value="funnel">User Funnel</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          {/* Daily Activity Chart */}
          <Card className="border-slate-200 shadow-none">
            <CardHeader>
              <CardTitle className="font-['Manrope'] flex items-center gap-2">
                <TrendingUp className="h-5 w-5 text-[#D4AF37]" />
                Daily Activity Trend
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-[350px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={dailyStats}>
                    <defs>
                      <linearGradient id="colorUsers" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#0F172A" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#0F172A" stopOpacity={0}/>
                      </linearGradient>
                      <linearGradient id="colorBills" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#D4AF37" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#D4AF37" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis 
                      dataKey="date" 
                      stroke="#64748b"
                      tickFormatter={(value) => new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                    />
                    <YAxis stroke="#64748b" />
                    <Tooltip 
                      contentStyle={{ 
                        backgroundColor: 'white', 
                        border: '1px solid #e2e8f0',
                        borderRadius: '8px'
                      }}
                      labelFormatter={(value) => new Date(value).toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' })}
                    />
                    <Area 
                      type="monotone" 
                      dataKey="users" 
                      stroke="#0F172A" 
                      fillOpacity={1}
                      fill="url(#colorUsers)"
                      strokeWidth={2}
                      name="New Users"
                    />
                    <Area 
                      type="monotone" 
                      dataKey="bills" 
                      stroke="#D4AF37" 
                      fillOpacity={1}
                      fill="url(#colorBills)"
                      strokeWidth={2}
                      name="Bills Uploaded"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>

          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <Card className="border-slate-200 shadow-none">
              <CardContent className="pt-6">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 bg-slate-100 rounded-xl flex items-center justify-center">
                    <Users className="h-6 w-6 text-slate-600" />
                  </div>
                  <div>
                    <p className="text-sm text-slate-500">Total New Users</p>
                    <p className="text-2xl font-bold font-['Manrope']">
                      {dailyStats.reduce((sum, d) => sum + d.users, 0)}
                    </p>
                    <p className="text-xs text-slate-400">Last {dateRange} days</p>
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card className="border-slate-200 shadow-none">
              <CardContent className="pt-6">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 bg-green-100 rounded-xl flex items-center justify-center">
                    <Receipt className="h-6 w-6 text-green-600" />
                  </div>
                  <div>
                    <p className="text-sm text-slate-500">Total Bills</p>
                    <p className="text-2xl font-bold font-['Manrope']">
                      {dailyStats.reduce((sum, d) => sum + d.bills, 0)}
                    </p>
                    <p className="text-xs text-slate-400">Last {dateRange} days</p>
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card className="border-slate-200 shadow-none">
              <CardContent className="pt-6">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 bg-purple-100 rounded-xl flex items-center justify-center">
                    <QrCode className="h-6 w-6 text-purple-600" />
                  </div>
                  <div>
                    <p className="text-sm text-slate-500">Avg. Conversion</p>
                    <p className="text-2xl font-bold font-['Manrope']">
                      {(() => {
                        const totalScans = qrPerformance.reduce((sum, q) => sum + q.scans, 0);
                        const totalRegs = qrPerformance.reduce((sum, q) => sum + q.registrations, 0);
                        return totalScans > 0 ? ((totalRegs / totalScans) * 100).toFixed(1) : 0;
                      })()}%
                    </p>
                    <p className="text-xs text-slate-400">QR to Registration</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="qr" className="space-y-6">
          {/* Insights Section */}
          {qrPerformance.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Scans Insight */}
              <Card className="bg-gradient-to-r from-purple-50 to-blue-50 border-purple-200">
                <CardContent className="pt-4 pb-4">
                  <div className="flex items-start gap-3">
                    <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center flex-shrink-0">
                      <TrendingUp className="h-5 w-5 text-purple-600" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-purple-900">📊 Scans Analysis</p>
                      <p className="text-sm text-purple-700 mt-1">
                        {(() => {
                          const sorted = [...qrPerformance].filter(q => q.category !== 'parking').sort((a, b) => b.scans - a.scans);
                          const top = sorted[0];
                          const totalScans = sorted.reduce((sum, q) => sum + q.scans, 0);
                          const topPercent = totalScans > 0 ? ((top?.scans / totalScans) * 100).toFixed(0) : 0;
                          return top ? (
                            <>
                              <strong>{top.location}</strong> leads with <strong>{top.scans} scans</strong> ({topPercent}% of total {totalScans} scans).
                              {sorted[1] && <> Second is <strong>{sorted[1].location}</strong> with {sorted[1].scans} scans.</>}
                            </>
                          ) : 'No scan data available';
                        })()}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
              
              {/* Conversion Insight */}
              <Card className="bg-gradient-to-r from-amber-50 to-orange-50 border-amber-200">
                <CardContent className="pt-4 pb-4">
                  <div className="flex items-start gap-3">
                    <div className="w-10 h-10 bg-amber-100 rounded-lg flex items-center justify-center flex-shrink-0">
                      <Users className="h-5 w-5 text-amber-600" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-amber-900">🎯 Conversion Analysis</p>
                      <p className="text-sm text-amber-700 mt-1">
                        {(() => {
                          const sorted = [...qrPerformance].filter(q => q.category !== 'parking' && q.scans > 0).sort((a, b) => b.conversion_rate - a.conversion_rate);
                          const best = sorted[0];
                          const worst = sorted[sorted.length - 1];
                          const avgConversion = qrPerformance.filter(q => q.category !== 'parking').reduce((sum, q) => sum + q.conversion_rate, 0) / (qrPerformance.filter(q => q.category !== 'parking').length || 1);
                          return best ? (
                            <>
                              <strong>{best.location}</strong> has best conversion at <strong>{best.conversion_rate}%</strong>.
                              {worst && best !== worst && <> <strong>{worst.location}</strong> needs attention at {worst.conversion_rate}%.</>}
                              {' '}Average: {avgConversion.toFixed(1)}%.
                            </>
                          ) : 'No conversion data available';
                        })()}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* QR Scans by Location */}
            <Card className="border-slate-200 shadow-none">
              <CardHeader>
                <CardTitle className="font-['Manrope']">Scans by Location</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-[300px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={qrPerformance.filter(q => q.category !== 'parking')} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis type="number" stroke="#64748b" />
                      <YAxis 
                        type="category" 
                        dataKey="location" 
                        stroke="#64748b"
                        width={100}
                      />
                      <Tooltip 
                        contentStyle={{ 
                          backgroundColor: 'white', 
                          border: '1px solid #e2e8f0',
                          borderRadius: '8px'
                        }}
                      />
                      <Bar dataKey="scans" name="Scans" radius={[0, 4, 4, 0]}>
                        {qrPerformance.filter(q => q.category !== 'parking').map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={QR_COLORS[index % QR_COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            {/* Conversion Rate by Location */}
            <Card className="border-slate-200 shadow-none">
              <CardHeader>
                <CardTitle className="font-['Manrope']">Conversion Rate by Location</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-[300px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={qrPerformance.filter(q => q.category !== 'parking')}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis 
                        dataKey="location" 
                        stroke="#64748b"
                        angle={-45}
                        textAnchor="end"
                        height={80}
                      />
                      <YAxis stroke="#64748b" unit="%" />
                      <Tooltip 
                        contentStyle={{ 
                          backgroundColor: 'white', 
                          border: '1px solid #e2e8f0',
                          borderRadius: '8px'
                        }}
                        formatter={(value) => [`${value}%`, 'Conversion Rate']}
                      />
                      <Bar dataKey="conversion_rate" name="Conversion %" fill="#D4AF37" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* QR Performance Table */}
          <Card className="border-slate-200 shadow-none">
            <CardHeader>
              <CardTitle className="font-['Manrope']">QR Performance Details</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-slate-200">
                      <th className="text-left py-3 px-4 font-semibold text-slate-600">Location</th>
                      <th className="text-left py-3 px-4 font-semibold text-slate-600">QR Code</th>
                      <th className="text-right py-3 px-4 font-semibold text-slate-600">Scans</th>
                      <th className="text-right py-3 px-4 font-semibold text-slate-600">Registrations</th>
                      <th className="text-right py-3 px-4 font-semibold text-slate-600">Bills</th>
                      <th className="text-right py-3 px-4 font-semibold text-slate-600">Conversion</th>
                      <th className="w-10"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {qrPerformance.map((qr, index) => (
                      <tr 
                        key={qr.qr_code_id} 
                        className="border-b border-slate-100 hover:bg-slate-50 cursor-pointer transition-colors"
                        onClick={() => navigate('/qr-codes')}
                      >
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2">
                            <div 
                              className="w-3 h-3 rounded-full"
                              style={{ backgroundColor: QR_COLORS[index % QR_COLORS.length] }}
                            />
                            {qr.location}
                          </div>
                        </td>
                        <td className="py-3 px-4 text-slate-500 text-sm font-mono">{qr.qr_code_id}</td>
                        <td className="py-3 px-4 text-right font-semibold">{qr.scans}</td>
                        <td className="py-3 px-4 text-right">{qr.registrations}</td>
                        <td className="py-3 px-4 text-right">{qr.bill_uploads}</td>
                        <td className="py-3 px-4 text-right">
                          <span className={`font-semibold ${qr.conversion_rate >= 50 ? 'text-green-600' : qr.conversion_rate >= 25 ? 'text-yellow-600' : 'text-red-600'}`}>
                            {qr.conversion_rate}%
                          </span>
                        </td>
                        <td className="py-3 px-4 text-right">
                          <ExternalLink className="h-4 w-4 text-slate-400" />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="funnel" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Funnel Visualization */}
            <Card className="border-slate-200 shadow-none">
              <CardHeader>
                <CardTitle className="font-['Manrope']">User Journey Funnel</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {funnelData.map((stage, index) => {
                    const maxCount = Math.max(...funnelData.map(s => s.count));
                    const width = maxCount > 0 ? (stage.count / maxCount) * 100 : 0;
                    const dropOff = index > 0 && funnelData[index - 1].count > 0 
                      ? ((funnelData[index - 1].count - stage.count) / funnelData[index - 1].count * 100).toFixed(1)
                      : 0;
                    
                    return (
                      <div key={index}>
                        <div className="flex justify-between text-sm mb-2">
                          <span className="font-medium text-slate-700">{stage.stage}</span>
                          <div className="flex items-center gap-3">
                            {index > 0 && (
                              <span className="text-xs text-red-500">-{dropOff}%</span>
                            )}
                            <span className="text-slate-900 font-semibold">{stage.count}</span>
                          </div>
                        </div>
                        <div className="h-10 bg-slate-100 rounded-lg overflow-hidden relative">
                          <div 
                            className="h-full transition-all duration-500 flex items-center justify-end pr-4"
                            style={{ 
                              width: `${width}%`,
                              backgroundColor: COLORS[index % COLORS.length]
                            }}
                          >
                            {width > 20 && (
                              <span className="text-white text-xs font-medium">
                                {width.toFixed(0)}%
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>

            {/* Funnel Metrics */}
            <Card className="border-slate-200 shadow-none">
              <CardHeader>
                <CardTitle className="font-['Manrope']">Funnel Metrics</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-6">
                  {funnelData.length >= 2 && (
                    <>
                      <div className="p-4 bg-slate-50 rounded-lg">
                        <p className="text-sm text-slate-500">Scan to User Rate</p>
                        <p className="text-3xl font-bold text-slate-900 font-['Manrope']">
                          {funnelData[0].count > 0 
                            ? ((funnelData[1].count / funnelData[0].count) * 100).toFixed(1)
                            : 0}%
                        </p>
                        <p className="text-xs text-slate-400 mt-1">
                          {funnelData[1].count} users from {funnelData[0].count} scans
                        </p>
                      </div>

                      {funnelData.length >= 3 && (
                        <div className="p-4 bg-slate-50 rounded-lg">
                          <p className="text-sm text-slate-500">User to Registration Rate</p>
                          <p className="text-3xl font-bold text-[#D4AF37] font-['Manrope']">
                            {funnelData[1].count > 0 
                              ? ((funnelData[2].count / funnelData[1].count) * 100).toFixed(1)
                              : 0}%
                          </p>
                          <p className="text-xs text-slate-400 mt-1">
                            {funnelData[2].count} registered from {funnelData[1].count} users
                          </p>
                        </div>
                      )}

                      {funnelData.length >= 4 && (
                        <div className="p-4 bg-slate-50 rounded-lg">
                          <p className="text-sm text-slate-500">Registration to Bill Upload</p>
                          <p className="text-3xl font-bold text-green-600 font-['Manrope']">
                            {funnelData[2].count > 0 
                              ? ((funnelData[3].count / funnelData[2].count) * 100).toFixed(1)
                              : 0}%
                          </p>
                          <p className="text-xs text-slate-400 mt-1">
                            {funnelData[3].count} uploaded from {funnelData[2].count} registered
                          </p>
                        </div>
                      )}

                      {funnelData.length >= 5 && (
                        <div className="p-4 bg-slate-50 rounded-lg">
                          <p className="text-sm text-slate-500">Overall Conversion (Scan to Points)</p>
                          <p className="text-3xl font-bold text-purple-600 font-['Manrope']">
                            {funnelData[0].count > 0 
                              ? ((funnelData[4].count / funnelData[0].count) * 100).toFixed(1)
                              : 0}%
                          </p>
                          <p className="text-xs text-slate-400 mt-1">
                            {funnelData[4].count} earned points from {funnelData[0].count} initial scans
                          </p>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </DashboardLayout>
  );
};

export default Analytics;
