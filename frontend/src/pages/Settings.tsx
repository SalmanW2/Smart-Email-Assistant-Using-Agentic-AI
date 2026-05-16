import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Navbar from '../components/Navbar';
import { KeyRound, AlertCircle, CheckCircle2 } from 'lucide-react';

const backendUrl = import.meta.env.VITE_BACKEND_URL || 'https://smart-email-assistant-using-agentic-ai.onrender.com';

const Settings = () => {
  const navigate = useNavigate();
  
  // FIX: Switched from adminToken to adminEmail for consistent Google Login validation
  const adminEmail = localStorage.getItem('admin_email');
  
  // States
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passError, setPassError] = useState('');
  
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState({ text: '', type: '' });

  // Redirect to login ONLY if the email session is completely gone
  useEffect(() => {
    if (!adminEmail) navigate('/admin/login');
  }, [adminEmail, navigate]);

  // Live Password Validation
  const validatePassword = (pass: string) => {
    if (pass.length === 0) return '';
    if (pass.length < 6) return 'Password must be at least 6 characters.';
    if (!/[A-Za-z]/.test(pass)) return 'Must include at least one English letter.';
    if (!/\d/.test(pass)) return 'Must include at least one number.';
    return '';
  };

  const handlePasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setPassword(val);
    setPassError(validatePassword(val));
  };

  const handleSetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirmPassword) return;
    if (passError) return;
    
    setLoading(true);

    try {
      const res = await fetch(`${backendUrl}/api/admin/set-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-admin-email': adminEmail || '' },
        body: JSON.stringify({ email: adminEmail, password }),
      });
      if (res.ok) {
        setMsg({ text: 'Manual Password Set Successfully!', type: 'success' });
        setPassword('');
        setConfirmPassword('');
      } else {
        setMsg({ text: 'Failed to update password. You may not have permission.', type: 'error' });
      }
    } catch (err) { 
      setMsg({ text: 'Network Error. Check your connection.', type: 'error' }); 
    } finally { 
      setLoading(false); 
    }
  };

  const isMismatch = confirmPassword.length > 0 && password !== confirmPassword;
  const isInvalid = password.length === 0 || confirmPassword.length === 0 || !!passError || isMismatch;

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 pb-20 transition-colors duration-500">
      <Navbar />
      <div className="max-w-xl mx-auto px-4 py-12 animate-in fade-in slide-in-from-bottom-4 duration-500">
        
        <div className="mb-8">
          <h1 className="text-3xl font-black text-slate-900 dark:text-white tracking-tight">Security Settings</h1>
          <p className="text-slate-500 dark:text-slate-400 mt-2 font-medium">Manage your portal access and authentication credentials.</p>
        </div>

        <div className="bg-white dark:bg-slate-900 p-6 sm:p-8 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm transition-colors duration-500">
          <div className="flex items-center gap-3 mb-6 pb-6 border-b border-slate-100 dark:border-slate-800/50">
            <div className="bg-blue-100 dark:bg-blue-500/20 p-3 rounded-2xl">
              <KeyRound className="w-6 h-6 text-blue-700 dark:text-blue-400" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">Manual Login Password</h2>
              <p className="text-sm text-slate-500 dark:text-slate-400">Set a password for faster email login</p>
            </div>
          </div>

          {msg.text && (
            <div className={`p-4 rounded-xl mb-6 font-bold text-sm flex items-center gap-2 ${msg.type === 'success' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400' : 'bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400'}`}>
              {msg.type === 'success' ? <CheckCircle2 className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}
              {msg.text}
            </div>
          )}

          <form onSubmit={handleSetPassword} className="space-y-5">
            <div className="space-y-2">
              <label className="block text-xs font-black text-slate-400 uppercase tracking-widest ml-1">New Password</label>
              <input 
                type="password" 
                value={password}
                onChange={handlePasswordChange}
                className={`w-full p-4 bg-slate-50 dark:bg-slate-950 border rounded-2xl outline-none font-medium transition-all dark:text-white ${passError ? 'border-amber-300 focus:ring-2 focus:ring-amber-500/20' : 'border-slate-200 dark:border-slate-800 focus:ring-2 focus:ring-blue-500/20'}`} 
                placeholder="Enter new password"
                required
              />
              {passError && <p className="text-[11px] text-amber-600 dark:text-amber-400 font-bold flex items-center gap-1 ml-1 mt-1"><AlertCircle className="w-3 h-3" /> {passError}</p>}
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
              className="w-full bg-slate-900 dark:bg-blue-600 text-white py-4 rounded-2xl font-black text-sm uppercase tracking-widest hover:bg-slate-800 dark:hover:bg-blue-700 transition-all disabled:opacity-30 disabled:hover:bg-slate-900 shadow-lg mt-2"
            >
              {loading ? 'Saving...' : 'Save Password'}
            </button>
          </form>
        </div>
        
      </div>
    </div>
  );
};

export default Settings;