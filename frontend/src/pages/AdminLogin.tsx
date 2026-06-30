import { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Lock, Mail, ShieldCheck, AlertCircle, Info } from 'lucide-react';
import Navbar from '../components/Navbar';

const backendUrl = import.meta.env.VITE_BACKEND_URL || '';

const AdminLogin = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const error = searchParams.get('error');
  
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [loginError, setLoginError] = useState('');

  useEffect(() => {
    const savedToken = localStorage.getItem('admin_token');
    if (savedToken) navigate('/admin/dashboard');
  }, [navigate]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setLoginError('');

    try {
      const response = await fetch(`${backendUrl}/api/admin/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      if (response.ok) {
        const data = await response.json();
        localStorage.setItem('admin_token', data.token || 'manual_session');
        localStorage.setItem('admin_email', data.email);
        navigate('/admin/dashboard');
      } else {
        const data = await response.json();
        setLoginError(data.detail || 'Invalid email or password');
      }
    } catch (err) {
      setLoginError('Network Error. Please try again later.');
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = () => {
    window.location.href = `${backendUrl}/api/auth/admin_google_login`;
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-50 via-white to-blue-50 dark:from-slate-950 dark:via-slate-900 dark:to-indigo-950/20 font-sans flex flex-col transition-colors duration-500 selection:bg-blue-500/30">
      
      {/* Global Navbar Integration */}
      <Navbar />

      <div className="flex-1 flex items-center justify-center p-4">
        <div className="w-full max-w-md animate-in fade-in slide-in-from-bottom-8 duration-700">
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-600 to-indigo-600 shadow-xl shadow-blue-500/20 mb-6 group hover:scale-110 transition-transform">
              <ShieldCheck className="w-8 h-8 text-white group-hover:animate-pulse" />
            </div>
            <h1 className="text-3xl font-black text-slate-900 dark:text-white tracking-tight">Admin Portal</h1>
            <p className="text-slate-500 dark:text-slate-400 font-medium mt-2">Secure JWT Authorized Access.</p>
          </div>

          <div className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl rounded-3xl p-6 sm:p-8 shadow-xl shadow-slate-200/50 dark:shadow-none border border-slate-200/50 dark:border-slate-800/50 transition-colors">
            {(error || loginError) && (
              <div className="mb-6 p-4 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 flex items-start gap-3 animate-in fade-in">
                <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
                <p className="text-sm font-bold text-red-600 dark:text-red-400">{error ? error.replace(/\+/g, ' ') : loginError}</p>
              </div>
            )}

            <form onSubmit={handleLogin} className="space-y-4">
              <div className="relative group">
                <Mail className="absolute left-4 top-4 w-5 h-5 text-slate-400 dark:text-slate-500 group-focus-within:text-blue-500 transition-colors" />
                <input 
                  type="email" 
                  placeholder="Email Address" 
                  value={email} 
                  onChange={(e) => setEmail(e.target.value)} 
                  required 
                  className="w-full pl-12 pr-4 py-4 bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white rounded-2xl focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all outline-none font-medium placeholder:text-slate-400 dark:placeholder:text-slate-600 shadow-sm" 
                />
              </div>
              <div className="relative group">
                <Lock className="absolute left-4 top-4 w-5 h-5 text-slate-400 dark:text-slate-500 group-focus-within:text-blue-500 transition-colors" />
                <input 
                  type="password" 
                  placeholder="Password" 
                  value={password} 
                  onChange={(e) => setPassword(e.target.value)} 
                  required 
                  className="w-full pl-12 pr-4 py-4 bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white rounded-2xl focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all outline-none font-medium placeholder:text-slate-400 dark:placeholder:text-slate-600 shadow-sm" 
                />
              </div>
              <button 
                type="submit" 
                disabled={loading} 
                className="w-full bg-blue-600 text-white py-4 rounded-2xl font-bold hover:bg-blue-700 transition-all disabled:opacity-50 shadow-lg hover:shadow-blue-500/30 hover:-translate-y-0.5"
              >
                {loading ? 'Authenticating...' : 'Login Securely'}
              </button>
            </form>

            <div className="mt-8">
              <div className="relative">
                <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-slate-200 dark:border-slate-800"></div></div>
                <div className="relative flex justify-center text-sm"><span className="px-4 bg-white dark:bg-slate-900 text-slate-400 font-bold uppercase tracking-widest rounded-full">Or</span></div>
              </div>

              <div className="mt-6 mb-4 p-4 bg-blue-50 dark:bg-blue-500/10 rounded-xl border border-blue-100 dark:border-blue-500/20 flex items-start gap-3">
                <Info className="w-5 h-5 text-blue-600 dark:text-blue-400 shrink-0 mt-0.5" />
                <p className="text-xs sm:text-sm font-medium text-blue-800 dark:text-blue-300">
                  <strong className="block mb-1 text-blue-900 dark:text-blue-200">First time or forgot password?</strong>
                  Use Google Login to authenticate securely. You can set a manual password later in the dashboard.
                </p>
              </div>

              <button 
                onClick={handleGoogleLogin} 
                className="w-full bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white py-4 rounded-2xl font-bold hover:bg-slate-50 dark:hover:bg-slate-800 transition-all flex items-center justify-center gap-3 shadow-sm hover:-translate-y-0.5"
              >
                <svg viewBox="0 0 24 24" className="w-5 h-5"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
                Continue with Google
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AdminLogin;
