import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Navbar from '../components/Navbar';
import { KeyRound, ShieldCheck, AlertCircle } from 'lucide-react';

const backendUrl = import.meta.env.VITE_BACKEND_URL || 'https://smart-email-assistant-using-agentic-ai.onrender.com';

const Settings = () => {
  const navigate = useNavigate();
  const adminEmail = localStorage.getItem('admin_email');
  
  // States
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passError, setPassError] = useState('');
  
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState({ text: '', type: '' });

  useEffect(() => {
    if (!adminEmail) navigate('/admin/login');
  }, [adminEmail, navigate]);

  // FIX: Live Password Validation (At least 1 Letter, 1 Number, Min 6 Chars)
  const validatePassword = (pass: string) => {
    if (pass.length === 0) return '';
    if (pass.length < 6) return 'Password must be at least 6 characters.';
    if (!/[A-Za-z]/.test(pass)) return 'Password must contain at least one English letter.';
    if (!/\d/.test(pass)) return 'Password must contain at least one number.';
    return '';
  };

  const handlePassChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setPassword(val);
    setPassError(validatePassword(val));
  };

  const handleUpdatePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setMsg({ text: '', type: '' });

    // Final Validations Before Submit
    const vError = validatePassword(password);
    if (vError) {
      setPassError(vError);
      return;
    }
    if (password !== confirmPassword) {
      setPassError('Passwords do not match!');
      return;
    }
    
    setLoading(true);
    try {
      const response = await fetch(`${backendUrl}/api/admin/set-password`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'x-admin-email': adminEmail || ''
        },
        body: JSON.stringify({ email: adminEmail, password }),
      });
      
      if (response.ok) {
        setMsg({ text: 'Fallback password updated successfully.', type: 'success' });
        setPassword('');
        setConfirmPassword('');
        setPassError('');
        localStorage.setItem('password_setup_dismissed', 'true');
      } else {
        const data = await response.json();
        setMsg({ text: data.detail || 'Failed to set password', type: 'error' });
      }
    } catch (error) {
      setMsg({ text: 'Network Error. Could not connect to backend.', type: 'error' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 transition-colors duration-300">
      <Navbar />
      
      <div className="max-w-4xl mx-auto px-4 py-10">
        <h1 className="text-3xl font-black text-slate-900 dark:text-white mb-8 tracking-tight">Platform Settings</h1>
        
        <div className="bg-white dark:bg-slate-900 rounded-3xl shadow-sm border border-slate-200 dark:border-slate-800 p-6 sm:p-8 transition-colors">
          <div className="flex items-center gap-4 mb-6">
            <div className="bg-blue-100 dark:bg-blue-900/30 p-3 rounded-2xl">
              <KeyRound className="w-6 h-6 text-blue-700 dark:text-blue-400" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-900 dark:text-white tracking-tight">Manual Authentication</h2>
              <p className="text-slate-500 dark:text-slate-400 text-sm font-medium">Set a secure password for manual admin access.</p>
            </div>
          </div>

          {msg.text && (
            <div className={`p-4 rounded-xl mb-6 font-bold text-sm border flex items-center gap-2 ${msg.type === 'success' ? 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800' : 'bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 border-red-200 dark:border-red-800'}`}>
              {msg.type === 'success' ? <ShieldCheck className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}
              {msg.text}
            </div>
          )}

          <form onSubmit={handleUpdatePassword} className="space-y-5 max-w-md">
            <div>
              <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">New Password</label>
              <input 
                type="password" 
                value={password}
                onChange={handlePassChange}
                className={`w-full p-4 bg-slate-50 dark:bg-slate-950 border text-slate-900 dark:text-white rounded-xl outline-none font-medium transition-colors focus:ring-2 ${passError ? 'border-red-400 focus:border-red-500 focus:ring-red-500/20' : 'border-slate-200 dark:border-slate-800 focus:border-blue-500 focus:ring-blue-500/20'}`} 
                placeholder="e.g. Admin123"
                required
              />
            </div>
            
            {/* FIX: New Confirm Password Field */}
            <div>
              <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Confirm Password</label>
              <input 
                type="password" 
                value={confirmPassword}
                onChange={(e) => {
                  setConfirmPassword(e.target.value);
                  if (passError === 'Passwords do not match!') setPassError('');
                }}
                className={`w-full p-4 bg-slate-50 dark:bg-slate-950 border text-slate-900 dark:text-white rounded-xl outline-none font-medium transition-colors focus:ring-2 ${passError === 'Passwords do not match!' ? 'border-red-400 focus:border-red-500 focus:ring-red-500/20' : 'border-slate-200 dark:border-slate-800 focus:border-blue-500 focus:ring-blue-500/20'}`} 
                placeholder="Retype password"
                required
              />
            </div>

            {/* FIX: Red Validation Text */}
            {passError && (
              <p className="text-red-500 dark:text-red-400 text-sm font-bold flex items-center gap-1.5 animate-in fade-in">
                <AlertCircle className="w-4 h-4" /> {passError}
              </p>
            )}

            <button type="submit" disabled={loading || !!passError} className="bg-blue-600 text-white w-full py-4 rounded-xl font-bold hover:bg-blue-700 transition-all disabled:opacity-50 shadow-md hover:shadow-blue-500/30">
              {loading ? 'Processing...' : 'Save Password'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default Settings;