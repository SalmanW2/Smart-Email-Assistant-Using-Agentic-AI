import { useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Lock, Mail, ShieldCheck } from 'lucide-react';

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
    try {
      const response = await fetch(`${import.meta.env.VITE_BACKEND_URL}/api/admin/login`, {
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
      alert('Network Error: Check Backend Status');
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = () => {
    window.location.href = `${import.meta.env.VITE_BACKEND_URL}/api/auth/admin_google_login`;
  };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
      <div className="w-full max-w-[400px] space-y-8">
        <div className="text-center">
          <div className="inline-flex p-3 bg-indigo-600 rounded-2xl mb-4 shadow-xl shadow-indigo-100">
            <ShieldCheck className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-3xl font-black tracking-tighter text-slate-900">Admin Control</h1>
          <p className="text-slate-500 font-medium mt-2">Sign in to manage the assistant ecosystem.</p>
        </div>

        {error && <div className="bg-red-50 text-red-600 p-4 rounded-xl text-sm font-bold border border-red-100 text-center">{error}</div>}

        <div className="bg-white p-8 rounded-[32px] shadow-sm border border-slate-200">
          <button onClick={handleGoogleLogin} className="w-full flex items-center justify-center gap-3 bg-white border-2 border-slate-100 p-4 rounded-2xl hover:bg-slate-50 transition-all font-bold text-slate-700 mb-6">
            <img src="https://www.google.com/favicon.ico" className="w-5 h-5" alt="G" />
            Sign in with Google
          </button>

          <div className="relative flex items-center mb-6">
            <div className="flex-grow border-t border-slate-100"></div>
            <span className="px-4 text-xs font-black text-slate-300 uppercase tracking-widest">or secure login</span>
            <div className="flex-grow border-t border-slate-100"></div>
          </div>

          <form onSubmit={handlePasswordLogin} className="space-y-4">
            <div className="relative">
              <Mail className="absolute left-4 top-4 w-5 h-5 text-slate-400" />
              <input type="email" placeholder="Admin Email" value={email} onChange={(e) => setEmail(e.target.value)} required className="w-full pl-12 pr-4 py-4 bg-slate-50 border-transparent rounded-2xl focus:bg-white focus:ring-2 focus:ring-indigo-600 transition-all outline-none font-medium" />
            </div>
            <div className="relative">
              <Lock className="absolute left-4 top-4 w-5 h-5 text-slate-400" />
              <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required className="w-full pl-12 pr-4 py-4 bg-slate-50 border-transparent rounded-2xl focus:bg-white focus:ring-2 focus:ring-indigo-600 transition-all outline-none font-medium" />
            </div>
            <button type="submit" disabled={loading} className="w-full bg-slate-950 text-white py-4 rounded-2xl font-bold hover:bg-slate-800 transition-all disabled:opacity-50 shadow-xl shadow-slate-200">
              {loading ? 'Authenticating...' : 'Access Dashboard'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default AdminLogin;