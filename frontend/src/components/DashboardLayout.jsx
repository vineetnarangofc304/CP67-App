import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../App';
import { 
  LayoutDashboard, 
  QrCode, 
  Users, 
  Receipt, 
  MessageCircle, 
  MessageSquare,
  BarChart3, 
  LogOut,
  Menu,
  X,
  ShieldCheck,
  Car,
  ScanLine,
  Store,
  Download,
  Megaphone,
  ImageIcon,
  Tag,
  CalendarDays,
  ShieldOff,
  Type,
  RefreshCw,
  Award,
  Rocket
} from 'lucide-react';
import { Button } from '../components/ui/button';

const PARKING_NAV = [
  { path: '/parking-scanner', label: 'Parking Scanner', icon: ScanLine },
  { path: '/parking-report', label: 'Parking Report', icon: Car },
];

const navItems = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/qr-codes', label: 'QR Codes', icon: QrCode },
  { path: '/users', label: 'Users', icon: Users },
  { path: '/bills', label: 'Bills', icon: Receipt },
  { path: '/brands', label: 'Brands & ATV', icon: Store },
  { path: '/campaigns', label: 'Campaigns', icon: Megaphone },
  { path: '/banners', label: 'Banners', icon: ImageIcon },
  { path: '/offers', label: 'Hot Deals', icon: Tag },
  { path: '/events', label: 'Events', icon: CalendarDays },
  { path: '/reports', label: 'Export Reports', icon: Download },
  { path: '/parking-scanner', label: 'Parking Scanner', icon: ScanLine },
  { path: '/parking-report', label: 'Parking Report', icon: Car },
  { path: '/whatsapp-logs', label: 'WhatsApp Logs', icon: MessageCircle },
  { path: '/whatsapp', label: 'WhatsApp Simulator', icon: MessageSquare },
  { path: '/analytics', label: 'Analytics', icon: BarChart3 },
  { path: '/admin-users', label: 'Admin Users', icon: ShieldCheck },
  { path: '/blocked-users', label: 'Blocked Users', icon: ShieldOff },
  { path: '/fundle-sync', label: 'Fundle Sync', icon: RefreshCw },
  { path: '/staff-incentives', label: 'Staff Incentives', icon: Award },
  { path: '/app-controls', label: 'App Controls', icon: Rocket },
  { path: '/app-settings', label: 'App Settings', icon: Type },
];

const DashboardLayout = ({ children, title }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { logout, user } = useAuth();
  const [sidebarOpen, setSidebarOpen] = React.useState(false);

  const isParkingStaff = user?.role === 'parking_staff';
  const visibleNav = isParkingStaff ? PARKING_NAV : navItems;

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="min-h-screen bg-[#F8FAFC]">
      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside className={`
        fixed top-0 left-0 z-50 h-full w-64 bg-white border-r border-slate-200
        transform transition-transform duration-200 ease-in-out
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        lg:translate-x-0
      `}>
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="p-6 border-b border-slate-200">
            <div className="flex items-center gap-3">
              <img 
                src="/cp67-logo.jpeg" 
                alt="CP67 Homeland Advantage" 
                className="w-12 h-12 rounded-lg object-cover"
              />
              <div>
                <h1 className="text-xl font-bold text-slate-900 font-['Manrope']">CP67 Mall</h1>
                <p className="text-[10px] text-[#D4AF37] font-semibold tracking-wider">HOMELAND ADVANTAGE</p>
              </div>
            </div>
            <button 
              className="lg:hidden absolute top-6 right-4"
              onClick={() => setSidebarOpen(false)}
            >
              <X className="h-5 w-5 text-slate-500" />
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-4 space-y-1">
            {visibleNav.map((item) => {
              const isActive = location.pathname === item.path;
              const Icon = item.icon;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  data-testid={`nav-${item.path.replace('/', '') || 'dashboard'}`}
                  onClick={() => setSidebarOpen(false)}
                  className={`
                    flex items-center gap-3 px-4 py-3 rounded-lg transition-colors
                    ${isActive 
                      ? 'bg-slate-900 text-white' 
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                    }
                  `}
                >
                  <Icon className="h-5 w-5" />
                  <span className="font-medium">{item.label}</span>
                </Link>
              );
            })}
          </nav>

          {/* User & Logout */}
          <div className="p-4 border-t border-slate-200">
            <div className="flex items-center gap-3 mb-4 px-2">
              <div className="w-8 h-8 bg-slate-200 rounded-full flex items-center justify-center">
                <span className="text-slate-600 text-sm font-medium">
                  {user?.username?.charAt(0).toUpperCase() || 'A'}
                </span>
              </div>
              <div>
                <p className="text-sm font-medium text-slate-900">{user?.username || 'Admin'}</p>
                <p className="text-xs text-slate-500">
                  {isParkingStaff 
                    ? `Parking Staff${user?.gate ? ` — ${user.gate === 'gate1' ? 'Gate 1' : 'Gate 2'}` : ''}` 
                    : 'Administrator'}
                </p>
              </div>
            </div>
            <Button 
              variant="outline" 
              className="w-full justify-start gap-2"
              onClick={handleLogout}
              data-testid="logout-btn"
            >
              <LogOut className="h-4 w-4" />
              Logout
            </Button>
          </div>

          {/* Powered by */}
          <div className="p-4 text-center border-t border-slate-200">
            <p className="text-xs text-slate-400 mb-2">Powered by</p>
            <img 
              src="https://customer-assets.emergentagent.com/job_ab4a7875-f86d-4bee-a881-60a939cc5db9/artifacts/ixnrrrmw_WhatsApp%20Image%202026-01-24%20at%2015.10.28.jpeg" 
              alt="Fundle" 
              className="h-6 mx-auto"
            />
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <div className="lg:ml-64">
        {/* Top bar */}
        <header className="sticky top-0 z-30 bg-white/80 backdrop-blur-md border-b border-slate-200">
          <div className="flex items-center justify-between px-6 py-4">
            <div className="flex items-center gap-4">
              <button 
                className="lg:hidden"
                onClick={() => setSidebarOpen(true)}
              >
                <Menu className="h-6 w-6 text-slate-600" />
              </button>
              <h1 className="text-2xl font-bold text-slate-900 font-['Manrope']">{title}</h1>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="p-6 md:p-8">
          {children}
        </main>
      </div>
    </div>
  );
};

export default DashboardLayout;
