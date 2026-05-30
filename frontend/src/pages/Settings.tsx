import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Lock, Save, ArrowLeft, CheckCircle } from 'lucide-react';
import Navbar from '../components/Navbar';

const backendUrl = import.meta.env.VITE_BACKEND_URL || import.meta.env.VITE_BACKEND || 'https://smart-email-assistant-using-agentic-ai.onrender.com';

const Settings = () => {
  const navigate = useNavigate();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Auto-detect Google Login via local storage flag
  const [isGoogleSetup, setIsGoogleSetup] = useState(
    localStorage.getItem('prompt_easy_password') === 'true'
  );

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
          current_password: isGoogleSetup ? "" : currentPassword,
          new_password: newPassword,
        }),
      });

      if (res.ok) {
        // Success hote hi instantly flag aur state clear kardo
        const wasGoogleSetup = isGoogleSetup;
        localStorage.removeItem('prompt_easy_password');
        setIsGoogleSetup(false);

        setMessage({ type: 'success', text: 'Password changed successfully!' });
        setCurrentPassword('');
        setNewPassword('');
        setConfirmPassword('');

        // Google flow tha toh redirect maro
        if (wasGoogleSetup) {
          setTimeout(() => navigate('/admin/dashboard'), 1500);
        }
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
    <div className="min-h-screen bg-slate-950 text-white font-sans selection:bg-blue-500/30">
      <Navbar />

      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
        
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

        <div className="bg-slate-900 rounded-2xl border border-slate-800 overflow-hidden shadow-2xl">
          
          <div className="p-6 border-b border-slate-800 bg-slate-900/50">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 bg-blue-600 rounded-xl flex items-center justify-center shadow-lg shadow-blue-500/20">
                <Lock className="w-6 h-6" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-white">Change Password</h2>
                <p className="text-sm text-slate-400 font-medium">Update your account security credentials</p>
              </div>
            </div>
          </div>

          <form onSubmit={handlePasswordChange} className="p-6 space-y-6">
            
            {/* Google Login Banner */}
            {isGoogleSetup && (
              <div className="bg-blue-500/10 text-blue-400 border border-blue-500/20 p-4 rounded-xl text-sm font-medium flex items-center gap-2">
                <Lock className="w-4 h-4 shrink-0" /> 
                Set your unique password for easy login.
              </div>
            )}

            {message && (
              <div className={`p-4 rounded-xl font-bold text-sm flex items-center gap-2 ${
                message.type === 'success' 
                  ? 'bg-emerald-600/20 text-emerald-400 border border-emerald-600/30' 
                  : 'bg-red-600/20 text-red-400 border border-red-600/30'
              }`}>
                {message.type === 'success' && <CheckCircle className="w-5 h-5" />}
                {message.text}
              </div>
            )}

            {/* Manual Login Current Password Field (Hidden during Google Setup) */}
            {!isGoogleSetup && (
              <div>
                <label className="block text-sm font-bold text-slate-300 mb-2">Current Password</label>
                <input
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  required={!isGoogleSetup}
                  className="w-full px-4 py-3.5 bg-slate-950 border border-slate-800 rounded-xl outline-none focus:ring-2 focus:ring-blue-500 transition-all text-white font-medium shadow-inner"
                  placeholder="Enter current password"
                />
              </div>
            )}

            <div>
              <label className="block text-sm font-bold text-slate-300 mb-2">New Password</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                minLength={8}
                className="w-full px-4 py-3.5 bg-slate-950 border border-slate-800 rounded-xl outline-none focus:ring-2 focus:ring-blue-500 transition-all text-white font-medium shadow-inner"
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
                className="w-full px-4 py-3.5 bg-slate-950 border border-slate-800 rounded-xl outline-none focus:ring-2 focus:ring-blue-500 transition-all text-white font-medium shadow-inner"
                placeholder="Re-enter new password"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white py-4 rounded-xl font-black text-sm uppercase tracking-widest transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed shadow-md shadow-blue-500/10 mt-4"
            >
              <Save className="w-5 h-5" />
              {loading ? 'Processing...' : 'Save Password'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default Settings;
