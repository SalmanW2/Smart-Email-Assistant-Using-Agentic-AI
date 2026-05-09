import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';

const AdminLogin = () => {
  const [searchParams] = useSearchParams();
  const error = searchParams.get('error');
  const msg = searchParams.get('msg');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const response = await fetch(`${import.meta.env.VITE_BACKEND_URL}/admin/login_with_password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ email, password }),
        credentials: 'include',
      });
      if (response.ok) {
        window.location.href = '/admin/dashboard';
      } else {
        alert('Invalid email or password');
      }
    } catch (err) {
      alert('Login failed');
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = () => {
    window.location.href = `${import.meta.env.VITE_BACKEND_URL}/admin/auth/google`;
  };

  return (
    <div className="bg-slate-100 flex items-center justify-center min-h-screen font-sans p-4">
      <div className="bg-white p-8 md:p-10 rounded-2xl shadow-2xl w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-slate-800">Admin Portal</h1>
          <p className="text-slate-500 mt-2 text-sm">Secure access for authorized personnel.</p>
        </div>

        {error && <div className="bg-red-100 text-red-700 p-3 rounded-lg mb-4 text-sm font-semibold">{error}</div>}
        {msg && <div className="bg-green-100 text-green-700 p-3 rounded-lg mb-4 text-sm font-semibold">{msg}</div>}

        <div className="text-center mb-6">
          <button onClick={handleGoogleLogin} className="w-full flex items-center justify-center gap-3 bg-white border border-slate-300 p-3 rounded-lg hover:bg-slate-50 transition-all shadow-sm">
            <img src="https://www.google.com/favicon.ico" className="w-5 h-5" alt="Google" />
            <span className="font-semibold text-slate-700">Continue with Google</span>
          </button>
        </div>

        <div className="relative flex py-4 items-center">
          <div className="flex-grow border-t border-slate-200"></div>
          <span className="flex-shrink mx-4 text-slate-400 text-sm font-semibold">OR</span>
          <div className="flex-grow border-t border-slate-200"></div>
        </div>

        <div className="text-center mb-4">
          <p className="text-xs text-slate-500 mb-3 px-2">If you have configured a password, login below:</p>
        </div>
        <form onSubmit={handlePasswordLogin} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1 text-left">Email Address</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full p-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1 text-left">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full p-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-slate-900 text-white p-3 rounded-lg font-bold hover:bg-slate-800 transition-all shadow-md disabled:opacity-50"
          >
            {loading ? 'Logging in...' : 'Login to Dashboard'}
          </button>
        </form>
      </div>
    </div>
  );
};

export default AdminLogin;