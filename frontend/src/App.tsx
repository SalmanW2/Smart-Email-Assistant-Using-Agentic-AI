import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Landing from './pages/Landing';
import AdminLogin from './pages/AdminLogin';
import Dashboard from './pages/Dashboard';
import Settings from './pages/Settings';
import About from './pages/About'; // Help renamed to About

const App = () => {
  return (
    <Router>
      <Routes>
        {/* Public Routes */}
        <Route path="/" element={<Landing />} />
        <Route path="/about" element={<About />} />
        
        {/* Admin Auth */}
        <Route path="/admin/login" element={<AdminLogin />} />
        
        {/* Protected Admin Routes */}
        <Route path="/admin/dashboard" element={<Dashboard />} />
        <Route path="/admin/settings" element={<Settings />} />
        
        {/* Strict Fallback: Agar URL ghalat ho toh Landing page par bhej do */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  );
};

export default App;