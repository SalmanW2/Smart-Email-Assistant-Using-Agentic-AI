import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Landing from './pages/Landing';
import AdminLogin from './pages/AdminLogin';
import Dashboard from './pages/Dashboard';
import Settings from './pages/Settings';
import About from './pages/About';

// ==========================================
// CENTRALIZED PROTECTED ROUTE WRAPPER
// ==========================================
const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const adminEmail = localStorage.getItem('admin_email');
  
  if (!adminEmail) {
    // Agar session nahi hai to security warning ke sath login par bhej do
    return <Navigate to="/admin/login?error=Authentication+Required" replace />;
  }
  
  return <>{children}</>;
};

const App = () => {
  return (
    <Router>
      <Routes>
        {/* Public Routes */}
        <Route path="/" element={<Landing />} />
        <Route path="/about" element={<About />} />
        
        {/* Admin Authentication */}
        <Route path="/admin/login" element={<AdminLogin />} />
        
        {/* Protected Admin Routes (Automatic Security Guard) */}
        <Route 
          path="/admin/dashboard" 
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          } 
        />
        <Route 
          path="/admin/settings" 
          element={
            <ProtectedRoute>
              <Settings />
            </ProtectedRoute>
          } 
        />
        
        {/* Strict Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  );
};

export default App;