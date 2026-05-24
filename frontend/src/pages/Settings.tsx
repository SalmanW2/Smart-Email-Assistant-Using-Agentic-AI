import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Lock, Save, ArrowLeft } from 'lucide-react';
import Navbar from '../components/Navbar';

const backendUrl = import.meta.env.VITE_BACKEND_URL || 'https://smart-email-assistant-using-agentic-ai.onrender.com';

const Settings = () => {
  const navigate = useNavigate();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const token = localStorage.getItem('admin_token') || '';

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);

    if (newPassword !== confirmPassword) {
      setMessage({ type: 'error', text: 'New passwords do not match.' });
      return;
    }

    if (newPassword.length < 8) {
      setMessage({ type: 'error', text: 'Password must be at least 8 characters.' });
      return;
    }

    setLoading(true);

    try {
      const res = await fetch(`${backendUrl}/api/admin/change-password`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });

      if (res.ok) {
        setMessage({ type: 'success', text: 'Password changed successfully!' });
        setCurrentPassword('');
        setNewPassword('');
        setConfirmPassword('');
      } else {
        const data = await res.json();
        setMessage({ type: 'error', text: data.detail || 'Failed to change password.' });
      }
    } catch {
      setMessage({ type: 'error', text: 'Network error. Please try again.' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white font-sans">
      <Navbar />

      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
        
        <div className="mb-8">
          <button
            onClick={() => navigate('/admin/dashboard')}
            className="flex items-center gap-2 text-slate-400 hover:text-white transition-colors font-bold mb-4"
          >
            <ArrowLeft className="w-5 h-5" /> Back to Dashboard
          </button>
          <h1 className="text-3xl font-black text-white">Settings</h1>
          <p className="text-slate-400 mt-1 font-medium">Manage your admin account preferences.</p>
        </div>

        <div className="bg-slate-900 rounded-2xl border border-slate-800 overflow-hidden">
          
          <div className="p-6 border-b border-slate-800">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 bg-blue-600 rounded-xl flex items-center justify-center">
                <Lock className="w-6 h-6" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-white">Change Password</h2>
                <p className="text-sm text-slate-400 font-medium">Update your account security credentials</p>
              </div>
            </div>
          </div>

          <form onSubmit={handlePasswordChange} className="p-6 space-y-6">
            
            {message && (
              <div className={`p-4 rounded-xl font-bold text-sm ${
                message.type === 'success' 
                  ? 'bg-emerald-600/20 text-emerald-400 border border-emerald-600/30' 
                  : 'bg-red-600/20 text-red-400 border border-red-600/30'
              }`}>
                {message.text}
              </div>
            )}

            <div>
              <label className="block text-sm font-bold text-slate-300 mb-2">Current Password</label>
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
                className="w-full px-4 py-3 bg-slate-800 border border-slate-700 rounded-xl outline-none focus:ring-2 focus:ring-blue-500 transition-all text-white font-medium"
                placeholder="Enter your current password"
              />
            </div>

            <div>
              <label className="block text-sm font-bold text-slate-300 mb-2">New Password</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                minLength={8}
                className="w-full px-4 py-3 bg-slate-800 border border-slate-700 rounded-xl outline-none focus:ring-2 focus:ring-blue-500 transition-all text-white font-medium"
                placeholder="Enter new password (min 8 characters)"
              />
            </div>

            <div>
              <label className="block text-sm font-bold text-slate-300 mb-2">Confirm New Password</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                minLength={8}
                className="w-full px-4 py-3 bg-slate-800 border border-slate-700 rounded-xl outline-none focus:ring-2 focus:ring-blue-500 transition-all text-white font-medium"
                placeholder="Re-enter new password"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white py-3.5 rounded-xl font-black text-sm uppercase tracking-widest transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Save className="w-5 h-5" />
              {loading ? 'Saving...' : 'Update Password'}
            </button>

          </form>
        </div>

      </div>
    </div>
  );
};

export default Settings;