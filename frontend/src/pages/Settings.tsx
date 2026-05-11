import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Navbar from '../components/Navbar';
import { KeyRound } from 'lucide-react';

const Settings = () => {
  const navigate = useNavigate();
  const adminEmail = localStorage.getItem('admin_email');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState({ text: '', type: '' });

  useEffect(() => {
    if (!adminEmail) navigate('/admin/login');
  }, [adminEmail, navigate]);

  const handleUpdatePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password.length < 6) {
      setMsg({ text: 'Password must be at least 6 characters.', type: 'error' });
      return;
    }
    
    setLoading(true);
    try {
      const response = await fetch(`${import.meta.env.VITE_BACKEND_URL}/api/admin/set-password`, {
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
      } else {
        setMsg({ text: 'Not authorized to change password.', type: 'error' });
      }
    } catch (err) {
      setMsg({ text: 'Network Error.', type: 'error' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />
      <div className="max-w-3xl mx-auto px-6 py-10">
        <h1 className="text-3xl font-black text-slate-900 mb-8">Security Settings</h1>
        
        <div className="bg-white p-8 rounded-2xl shadow-sm border border-slate-200">
          <div className="flex items-center gap-4 mb-6">
            <div className="bg-indigo-100 p-3 rounded-xl"><KeyRound className="w-6 h-6 text-indigo-600" /></div>
            <div>
              <h2 className="text-xl font-bold text-slate-900">Manual Login Password</h2>
              <p className="text-slate-500 text-sm">Set a secure password for manual admin access (Fallback for Google SSO).</p>
            </div>
          </div>

          {msg.text && (
            <div className={`p-4 rounded-xl mb-6 font-bold text-sm border ${msg.type === 'success' ? 'bg-green-50 text-green-700 border-green-100' : 'bg-red-50 text-red-600 border-red-100'}`}>
              {msg.text}
            </div>
          )}

          <form onSubmit={handleUpdatePassword} className="space-y-4 max-w-md">
            <div>
              <label className="block text-sm font-bold text-slate-700 mb-2">New Password</label>
              <input 
                type="password" 
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full p-4 bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:ring-2 focus:ring-indigo-600 outline-none font-medium" 
                placeholder="Minimum 6 characters"
                required
              />
            </div>
            <button 
              type="submit" 
              disabled={loading}
              className="bg-slate-900 text-white px-6 py-4 rounded-xl font-bold hover:bg-slate-800 transition-all disabled:opacity-50"
            >
              {loading ? 'Updating...' : 'Update Password'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default Settings;