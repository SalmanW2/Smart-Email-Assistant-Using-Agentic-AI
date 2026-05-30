import { BrowserRouter as Router, Routes, Route, Navigate, Link } from 'react-router-dom';
import { useEffect, useState } from 'react';
import Landing from './pages/Landing';
import About from './pages/About';
import AdminLogin from './pages/AdminLogin';
import Dashboard from './pages/Dashboard';
import Settings from './pages/Settings';

const App = () => {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/about" element={<About />} />
        <Route path="/admin/login" element={<AdminLogin />} />
        <Route path="/admin/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
        <Route path="/admin/settings" element={<ProtectedRoute><Settings /></ProtectedRoute>} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Router>
  );
};

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const [isValid, setIsValid] = useState<boolean | null>(null);

  useEffect(() => {
    const validateToken = async () => {
      // 1. Intercept URL parameters if redirected from Google Auth
      const urlParams = new URLSearchParams(window.location.search);
      const urlToken = urlParams.get('token');
      const urlEmail = urlParams.get('email');

      if (urlToken && urlEmail) {
        localStorage.setItem('admin_token', urlToken);
        localStorage.setItem('admin_email', urlEmail);
        // ✨ Google login detecter (flag set)
        localStorage.setItem('prompt_easy_password', 'true'); 
        window.history.replaceState({}, document.title, window.location.pathname);
      }

      // 2. Fetch from localStorage
      const token = localStorage.getItem('admin_token');
      const email = localStorage.getItem('admin_email');

      if (!token || !email) {
        setIsValid(false);
        return;
      }

      try {
        // 3. Robust Client-Side Validation First (Prevents blinking checks)
        const payload = JSON.parse(atob(token.split('.')[1]));
        if (payload.exp * 1000 < Date.now()) {
          localStorage.clear();
          setIsValid(false);
          return;
        }

        // Set true immediately on verified token shape to stop flickering/bumping
        setIsValid(true);

        // 4. Background verification with server (Silently signs out ONLY on definite 401)
        const backendUrl = import.meta.env.VITE_BACKEND_URL || import.meta.env.VITE_BACKEND || 'https://smart-email-assistant-using-agentic-ai.onrender.com';
        const res = await fetch(`${backendUrl}/api/admin/get_current_admin`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!res.ok && res.status === 401) {
          localStorage.clear();
          setIsValid(false);
        }
      } catch (err) {
        localStorage.clear();
        setIsValid(false);
      }
    };

    validateToken();
  }, []);

  if (isValid === null) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-slate-400 font-bold">Verifying access...</p>
        </div>
      </div>
    );
  }

  if (!isValid) {
    return <Navigate to="/admin/login" replace />;
  }

  return <>{children}</>;
};

const NotFound = () => {
  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-50 via-white to-blue-50 dark:from-slate-950 dark:via-slate-900 dark:to-indigo-950/20 flex items-center justify-center px-4 font-sans">
      <div className="text-center space-y-6 max-w-lg">
        <div className="text-9xl font-black text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-indigo-600">
          404
        </div>
        <h1 className="text-3xl sm:text-4xl font-black text-slate-900 dark:text-white">
          Page Not Found
        </h1>
        <p className="text-lg text-slate-600 dark:text-slate-400 font-medium">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="pt-4">
          <Link
            to="/"
            className="inline-flex items-center gap-2 bg-blue-600 text-white px-8 py-4 rounded-2xl font-bold hover:bg-blue-700 transition-all shadow-lg hover:shadow-blue-500/30"
          >
            ← Back to Home
          </Link>
        </div>
      </div>
    </div>
  );
};

export default App;