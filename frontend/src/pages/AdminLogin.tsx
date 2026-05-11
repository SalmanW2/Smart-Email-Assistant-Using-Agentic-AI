import { useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Lock, Mail, ShieldCheck, AlertCircle } from 'lucide-react';

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
    
    const backendUrl = import.meta.env.VITE_BACKEND_URL;
    if (!backendUrl) {
      alert('System Setup Incomplete: VITE_BACKEND_URL is missing in Vercel settings.');
      setLoading(false);
      return;
    }

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
    const backendUrl = import.meta.env.VITE_BACKEND_URL;
    if (!backendUrl) {
      alert('System Setup Incomplete: VITE_BACKEND_URL is missing in Vercel settings. Please add it to Vercel Environment Variables.');
      return;
    }
    // Directs strictly to the Render backend!
    window.location.href = `${backendUrl}/api/auth/admin_google_login`;
  };

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-6 selection:bg-indigo-500/30">
      
      {/* Background Glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[400px] h-[400px] bg-indigo-600/20 blur-[120px] rounded-full pointer-events-none"></div>

      <div className="relative z-10 w-full max-w-[400px] space-y-8">
        <div className="text-center">
          <div className="inline-flex p-3 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-2xl mb-4 shadow-[0_0_20px_rgba(99,102,241,0.4)]">
            <ShieldCheck className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-3xl font-black tracking-tighter text-white">Admin Control</h1>
          <p className="text-slate-400 font-medium mt-2">Sign in to manage the ecosystem.</p>
        </div>

        {error && (
          <div className="flex items-center gap-3 bg-red-500/10 text-red-400 p-4 rounded-xl text-sm font-bold border border-red-500/20">
            <AlertCircle className="w-5 h-5" /> {error}
          </div>
        )}

        <div className="bg-slate-900/50 p-8 rounded-[32px] backdrop-blur-xl border border-slate-800 shadow-2xl">
          <button 
            onClick={handleGoogleLogin} 
            className="w-full flex items-center justify-center gap-3 bg-white hover:bg-slate-100 text-slate-900 p-4 rounded-2xl transition-all font-bold mb-6"
          >
            <img src="https://www.google.com/favicon.ico" className="w-5 h-5" alt="Google" />
            Sign in with Google
          </button>

          <div className="relative flex items-center mb-6">
            <div className="flex-grow border-t border-slate-800"></div>
            <span className="px-4 text-xs font-black text-slate-500 uppercase tracking-widest">or</span>
            <div className="flex-grow border-t border-slate-800"></div>
          </div>

          <form onSubmit={handlePasswordLogin} className="space-y-4">
            <div className="relative">
              <Mail className="absolute left-4 top-4 w-5 h-5 text-slate-500" />
              <input 
                type="email" 
                placeholder="Admin Email" 
                value={email} 
                onChange={(e) => setEmail(e.target.value)} 
                required 
                className="w-full pl-12 pr-4 py-4 bg-slate-950 border border-slate-800 text-white rounded-2xl focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all outline-none font-medium placeholder:text-slate-600" 
              />
            </div>
            <div className="relative">
              <Lock className="absolute left-4 top-4 w-5 h-5 text-slate-500" />
              <input 
                type="password" 
                placeholder="Password" 
                value={password} 
                onChange={(e) => setPassword(e.target.value)} 
                required 
                className="w-full pl-12 pr-4 py-4 bg-slate-950 border border-slate-800 text-white rounded-2xl focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all outline-none font-medium placeholder:text-slate-600" 
              />
            </div>
            <button 
              type="submit" 
              disabled={loading} 
              className="w-full bg-gradient-to-r from-indigo-500 to-purple-600 text-white py-4 rounded-2xl font-bold hover:shadow-[0_0_20px_rgba(99,102,241,0.4)] transition-all disabled:opacity-50"
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