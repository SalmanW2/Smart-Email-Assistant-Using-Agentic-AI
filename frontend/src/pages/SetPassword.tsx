import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

const SetPassword = () => {
  const [step, setStep] = useState(1);
  const [newPass, setNewPass] = useState('');
  const [confPass, setConfPass] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (step === 1) {
      if (newPass.length < 6 || newPass.length > 10) {
        setError('Password must be between 6 and 10 characters long.');
        return;
      }
      setStep(2);
    } else {
      if (newPass !== confPass) {
        setError('Passwords do not match!');
        return;
      }
      setLoading(true);
      try {
        const response = await fetch(`${import.meta.env.VITE_BACKEND_URL}/admin/set_password`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({ password: newPass }),
          credentials: 'include',
        });
        const data = await response.json();
        if (data.status === 'ok') {
          alert('Password saved successfully!');
          navigate('/admin/dashboard');
        } else {
          setError(data.message || 'Failed to save password.');
        }
      } catch (err) {
        setError('Network error occurred.');
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <div className="bg-slate-50 min-h-screen font-sans flex items-center justify-center p-4">
      <div className="bg-white p-6 md:p-8 rounded-2xl shadow-sm border border-slate-200 max-w-lg w-full">
        <h1 className="text-2xl md:text-3xl font-bold text-slate-800 mb-6">Set Admin Password</h1>
        <p className="text-slate-500 mb-6 text-sm md:text-base">Create a password to login directly without using Google SSO.</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">New Password</label>
            <input
              type="password"
              value={newPass}
              onChange={(e) => setNewPass(e.target.value)}
              required
              placeholder="6 to 10 characters"
              className="w-full p-3 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {error && <div className="text-red-500 text-sm font-semibold">{error}</div>}

          {step === 2 && (
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1 mt-2">Confirm Password</label>
              <input
                type="password"
                value={confPass}
                onChange={(e) => setConfPass(e.target.value)}
                required
                placeholder="Retype your password"
                className="w-full p-3 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="bg-slate-800 text-white px-6 py-3 rounded-lg font-bold hover:bg-slate-900 shadow-md w-full transition-all disabled:opacity-50"
          >
            {loading ? 'Saving...' : step === 1 ? 'Next' : 'Save Password'}
          </button>
        </form>
      </div>
    </div>
  );
};

export default SetPassword;