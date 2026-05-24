import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
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
      const token = localStorage.getItem('admin_token');
      const email = localStorage.getItem('admin_email');

      if (!token || !email) {
        setIsValid(false);
        return;
      }

      try {
        const payload = JSON.parse(atob(token.split('.')[1]));
        const exp = payload.exp * 1000;
        
        if (Date.now() >= exp) {
          localStorage.removeItem('admin_token');
          localStorage.removeItem('admin_email');
          localStorage.removeItem('admin_role');
          setIsValid(false);
          return;
        }

        setIsValid(true);
      } catch {
        localStorage.removeItem('admin_token');
        localStorage.removeItem('admin_email');
        localStorage.removeItem('admin_role');
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
          <a
            href="/"
            className="inline-flex items-center gap-2 bg-blue-600 text-white px-8 py-4 rounded-2xl font-bold hover:bg-blue-700 transition-all shadow-lg hover:shadow-blue-500/30"
          >
            ← Back to Home
          </a>
        </div>
      </div>
    </div>
  );
};

export default App;