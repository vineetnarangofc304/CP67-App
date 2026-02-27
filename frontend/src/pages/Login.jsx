import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../App';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { toast } from 'sonner';
import { Eye, EyeOff, Lock, User } from 'lucide-react';

const Login = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const { login, token } = useAuth();
  const navigate = useNavigate();

  // Redirect if already logged in
  React.useEffect(() => {
    if (token) {
      navigate('/', { replace: true });
    }
  }, [token, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(username, password);
      toast.success('Welcome to CP67 Loyalty Dashboard!');
      navigate('/', { replace: true });
    } catch (error) {
      toast.error(error.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* Left side - Login Form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-white">
        <div className="w-full max-w-md space-y-8">
          {/* Logo */}
          <div className="text-center">
            <div className="flex items-center justify-center gap-3 mb-4">
              <div className="w-12 h-12 bg-slate-900 rounded-xl flex items-center justify-center">
                <span className="text-white font-bold text-xl font-['Manrope']">CP</span>
              </div>
              <div>
                <h1 className="text-3xl font-bold text-slate-900 font-['Manrope']">CP67 Mall</h1>
                <p className="text-xs text-[#D4AF37] font-semibold tracking-wider">HOMELAND ADVANTAGE</p>
              </div>
            </div>
          </div>

          <Card className="border-slate-200 shadow-none">
            <CardHeader className="space-y-1 pb-4">
              <CardTitle className="text-2xl font-['Manrope']">Admin Login</CardTitle>
              <CardDescription>Enter your credentials to access the dashboard</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="username">Username</Label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400 h-4 w-4" />
                    <Input
                      id="username"
                      data-testid="login-username-input"
                      type="text"
                      placeholder="Enter username"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      className="pl-10"
                      required
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password">Password</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400 h-4 w-4" />
                    <Input
                      id="password"
                      data-testid="login-password-input"
                      type={showPassword ? 'text' : 'password'}
                      placeholder="Enter password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="pl-10 pr-10"
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 transform -translate-y-1/2 text-slate-400 hover:text-slate-600"
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>
                <Button
                  type="submit"
                  data-testid="login-submit-btn"
                  className="w-full bg-slate-900 hover:bg-slate-800 btn-press"
                  disabled={loading}
                >
                  {loading ? (
                    <div className="flex items-center gap-2">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      Signing in...
                    </div>
                  ) : (
                    'Sign In'
                  )}
                </Button>
              </form>
            </CardContent>
          </Card>

          {/* Footer */}
          <div className="text-center text-sm text-slate-500">
            <p>Powered by</p>
            <img 
              src="https://customer-assets.emergentagent.com/job_ab4a7875-f86d-4bee-a881-60a939cc5db9/artifacts/ixnrrrmw_WhatsApp%20Image%202026-01-24%20at%2015.10.28.jpeg" 
              alt="Fundle" 
              className="h-8 mx-auto mt-2"
            />
          </div>
        </div>
      </div>

      {/* Right side - Hero Image */}
      <div className="hidden lg:flex flex-1 relative">
        <div 
          className="absolute inset-0 bg-cover bg-center"
          style={{ 
            backgroundImage: `url('https://images.unsplash.com/photo-1761333485882-c60907725574?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1MDV8MHwxfHNlYXJjaHwzfHxtb2Rlcm4lMjBzaG9wcGluZyUyMG1hbGwlMjBpbnRlcmlvcnxlbnwwfHx8fDE3NjkyNDgzNzN8MA&ixlib=rb-4.1.0&q=85')`
          }}
        />
        <div className="absolute inset-0 bg-slate-900/60" />
        <div className="relative z-10 flex flex-col justify-end p-12 text-white">
          <h2 className="text-4xl font-bold font-['Manrope'] mb-4">
            Welcome to CP67 Mall<br />
            <span className="text-[#D4AF37]">Loyalty Management</span>
          </h2>
          <p className="text-lg text-slate-200 max-w-md">
            Manage your mall's loyalty program, track QR code performance, process bills, and analyze customer engagement.
          </p>
        </div>
      </div>
    </div>
  );
};

export default Login;
