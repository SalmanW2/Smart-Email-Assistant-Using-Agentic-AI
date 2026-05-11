import { useState, useEffect } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import { Lock, Mail, ShieldCheck, AlertCircle, Sun, Moon, ArrowLeft } from 'lucide-react';

const ThemeToggle = () => {
  const [theme, setTheme] = useState(localStorage.getItem('theme') || 'light');

  useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    localStorage.setItem('theme', theme);
  }, [theme]);

  return (
    <button
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
      className="p-2.5 rounded-full bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-blue-600 dark:text-blue-400 hover:border-blue-500 transition-all shadow-inner"
    >
      {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
    </button>
  );
};

const AdminLogin = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const error = searchParams.get('error');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    
    // BACKEND FALLBACK URL ADDED HERE
    const backendUrl = import.meta.env.VITE_BACKEND_URL || 'https://smart-email-assistant-using-agentic-ai.onrender.com';

    try {
      const response = await fetch(`${backendUrl}/api/admin/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      
      if (response.ok) {
        localStorage.setItem('admin_email', email);
        navigate('/admin/dashboard');
      } else {
        alert('Access Denied: Invalid Credentials');
      }
    } catch (err) {
      alert('Network Error: Make sure Render backend is awake.');
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = () => {
    // BACKEND FALLBACK URL ADDED HERE
    const backendUrl = import.meta.env.VITE_BACKEND_URL || 'https://smart-email-assistant-using-agentic-ai.onrender.com';
    window.location.href = `${backendUrl}/api/auth/admin_google_login`;
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center p-6 selection:bg-blue-500/30 transition-colors duration-300">
      
      {/* Top Navigation for Login Page */}
      <div className="absolute top-6 left-6 right-6 flex justify-between items-center z-50">
        <Link to="/" className="flex items-center gap-2 text-sm font-bold text-slate-600 dark:text-slate-400 hover:text-blue-600 dark:hover:text-white transition-colors">
          <ArrowLeft className="w-4 h-4" /> Back to Home
        </Link>
        <ThemeToggle />
      </div>

      {/* Background Glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[400px] h-[400px] bg-blue-600/10 blur-[120px] rounded-full pointer-events-none transition-colors"></div>

      <div className="relative z-10 w-full max-w-[400px] space-y-8">
        <div className="text-center">
          <div className="inline-flex p-3 bg-gradient-to-br from-blue-500 to-sky-600 rounded-2xl mb-4 shadow-[0_4px_12px_rgba(59,130,246,0.3)]">
            <ShieldCheck className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-3xl font-black tracking-tighter text-slate-950 dark:text-white">Admin Control</h1>
          <p className="text-slate-600 dark:text-slate-400 font-medium mt-2">Sign in to manage the ecosystem.</p>
        </div>

        {error && (
          <div className="flex items-center gap-3 bg-red-100 dark:bg-red-500/10 text-red-600 dark:text-red-400 p-4 rounded-xl text-sm font-bold border border-red-200 dark:border-red-500/20">
            <AlertCircle className="w-5 h-5 flex-shrink-0" /> {error}
          </div>
        )}

        <div className="bg-white dark:bg-slate-900/50 p-8 rounded-[32px] backdrop-blur-xl border border-slate-200 dark:border-slate-800 shadow-xl dark:shadow-2xl transition-colors">
          <button 
            onClick={handleGoogleLogin} 
            className="w-full flex items-center justify-center gap-3 bg-slate-50 dark:bg-white hover:bg-slate-100 dark:hover:bg-slate-200 text-slate-900 p-4 rounded-2xl transition-all font-bold mb-6 border border-slate-200 dark:border-transparent"
          >
            <img src="https://www.google.com/favicon.ico" className="w-5 h-5" alt="Google" />
            Sign in with Google
          </button>

          <div className="relative flex items-center mb-6">
            <div className="flex-grow border-t border-slate-200 dark:border-slate-800"></div>
            <span className="px-4 text-xs font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">or</span>
            <div className="flex-grow border-t border-slate-200 dark:border-slate-800"></div>
          </div>

          <form onSubmit={handlePasswordLogin} className="space-y-4">
            <div className="relative">
              <Mail className="absolute left-4 top-4 w-5 h-5 text-slate-400 dark:text-slate-500" />
              <input 
                type="email" 
                placeholder="Admin Email" 
                value={email} 
                onChange={(e) => setEmail(e.target.value)} 
                required 
                className="w-full pl-12 pr-4 py-4 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white rounded-2xl focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all outline-none font-medium placeholder:text-slate-400 dark:placeholder:text-slate-600" 
              />
            </div>
            <div className="relative">
              <Lock className="absolute left-4 top-4 w-5 h-5 text-slate-400 dark:text-slate-500" />
              <input 
                type="password" 
                placeholder="Password" 
                value={password} 
                onChange={(e) => setPassword(e.target.value)} 
                required 
                className="w-full pl-12 pr-4 py-4 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white rounded-2xl focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all outline-none font-medium placeholder:text-slate-400 dark:placeholder:text-slate-600" 
              />
            </div>
            <button 
              type="submit" 
              disabled={loading} 
              className="w-full bg-blue-600 text-white py-4 rounded-2xl font-bold hover:bg-blue-700 hover:shadow-[0_4px_12px_rgba(59,130,246,0.3)] transition-all disabled:opacity-50 mt-2"
            >
              {loading ? 'Authenticating...' : 'Access Dashboard'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default AdminLogin;