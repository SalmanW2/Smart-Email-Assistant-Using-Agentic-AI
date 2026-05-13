import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Navbar from '../components/Navbar';
import { KeyRound, ShieldCheck, AlertCircle, CheckCircle2 } from 'lucide-react';

const backendUrl = import.meta.env.VITE_BACKEND_URL || 'https://smart-email-assistant-using-agentic-ai.onrender.com';

const Settings = () => {
  const navigate = useNavigate();
  const adminEmail = localStorage.getItem('admin_email');
  const adminToken = localStorage.getItem('admin_token'); // JWT Token
  
  // States
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passError, setPassError] = useState('');
  
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState({ text: '', type: '' });

  useEffect(() => {
    if (!adminToken) navigate('/admin/login');
  }, [adminToken, navigate]);

  // Live Password Validation
  const validatePassword = (pass: string) => {
    if (pass.length === 0) return '';
    if (pass.length < 6) return 'Password must be at least 6 characters.';
    if (!/[A-Za-z]/.test(pass)) return 'Must include at least one English letter.';
    if (!/\d/.test(pass)) return 'Must include at least one number.';
    return '';
  };

  const handlePassChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setPassword(val);
    setPassError(validatePassword(val));
  };

  const isMismatch = confirmPassword.length > 0 && password !== confirmPassword;
  const isInvalid = !!passError || isMismatch || !password || !confirmPassword;

  const handleUpdatePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isInvalid) return;

    setLoading(true);
    setMsg({ text: '', type: '' });

    try {
      const response = await fetch(`${backendUrl}/api/admin/set-password`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': adminToken ? `Bearer ${adminToken}` : '' // FIXED: JWT Auth
        },
        body: JSON.stringify({ email: adminEmail, password }),
      });
      
      if (response.ok) {
        setMsg({ text: 'Unique password set successfully! You can now login manually.', type: 'success' });
        setPassword('');
        setConfirmPassword('');
        setPassError('');
        localStorage.setItem('password_setup_dismissed', 'true');
      } else {
        const data = await response.json();
        setMsg({ text: data.detail || 'Failed to update password.', type: 'error' });
      }
    } catch (error) {
      setMsg({ text: 'Network Error. Backend unreachable.', type: 'error' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 transition-colors duration-300">
      <Navbar />
      
      <div className="max-w-4xl mx-auto px-4 py-12">
        <div className="mb-10">
          <h1 className="text-3xl font-black text-slate-900 dark:text-white tracking-tight">Security Settings</h1>
          <p className="text-slate-500 dark:text-slate-400 font-medium">Manage your manual authentication credentials.</p>
        </div>
        
        <div className="bg-white dark:bg-slate-900 rounded-3xl shadow-xl shadow-slate-200/50 dark:shadow-none border border-slate-200 dark:border-slate-800 p-6 sm:p-10 transition-all">
          <div className="flex items-center gap-4 mb-8">
            <div className="bg-blue-100 dark:bg-blue-600/20 p-3 rounded-2xl">
              <KeyRound className="w-6 h-6 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">Manual Password</h2>
              <p className="text-sm text-slate-500 dark:text-slate-400">Set this to bypass Google Login next time.</p>
            </div>
          </div>

          {msg.text && (
            <div className={`p-4 rounded-2xl mb-8 flex items-center gap-3 text-sm font-bold border animate-in fade-in duration-300 ${msg.type === 'success' ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20' : 'bg-red-50 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20'}`}>
              {msg.type === 'success' ? <CheckCircle2 className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}
              {msg.text}
            </div>
          )}

          <form onSubmit={handleUpdatePassword} className="space-y-6 max-w-md">
            <div className="space-y-2">
              <label className="block text-xs font-black text-slate-400 uppercase tracking-widest ml-1">New Password</label>
              <input 
                type="password" 
                value={password}
                onChange={handlePassChange}
                className={`w-full p-4 bg-slate-50 dark:bg-slate-950 border rounded-2xl outline-none font-medium transition-all dark:text-white ${passError ? 'border-red-300 focus:ring-2 focus:ring-red-500/20' : 'border-slate-200 dark:border-slate-800 focus:ring-2 focus:ring-blue-500/20'}`} 
                placeholder="At least 6 chars, 1 letter, 1 number"
                required
              />
              {passError && <p className="text-[11px] text-red-500 font-bold flex items-center gap-1 ml-1 mt-1"><AlertCircle className="w-3 h-3" /> {passError}</p>}
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-black text-slate-400 uppercase tracking-widest ml-1">Confirm Password</label>
              <input 
                type="password" 
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className={`w-full p-4 bg-slate-50 dark:bg-slate-950 border rounded-2xl outline-none font-medium transition-all dark:text-white ${isMismatch ? 'border-red-300 focus:ring-2 focus:ring-red-500/20' : 'border-slate-200 dark:border-slate-800 focus:ring-2 focus:ring-blue-500/20'}`} 
                placeholder="Retype password"
                required
              />
              {isMismatch && <p className="text-[11px] text-red-500 font-bold flex items-center gap-1 ml-1 mt-1"><AlertCircle className="w-3 h-3" /> Passwords do not match!</p>}
            </div>

            <button 
              type="submit" 
              disabled={loading || isInvalid} 
              className="w-full bg-slate-900 dark:bg-blue-600 text-white py-4 rounded-2xl font-black text-sm uppercase tracking-widest hover:bg-slate-800 dark:hover:bg-blue-700 transition-all disabled:opacity-30 disabled:cursor-not-allowed shadow-lg shadow-blue-500/10"
            >
              {loading ? 'Processing Request...' : 'Update Credentials'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default Settings;