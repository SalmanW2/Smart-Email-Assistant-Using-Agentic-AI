import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Settings, LogOut, Sun, Moon, Menu, X, Info, HelpCircle, PhoneCall, LayoutDashboard, LogIn, Bot } from 'lucide-react';
import { useState, useEffect } from 'react';

const ThemeToggle = () => {
  const [theme, setTheme] = useState(localStorage.getItem('theme') || 'dark');
  useEffect(() => {
    if (theme === 'dark') document.documentElement.classList.add('dark');
    else document.documentElement.classList.remove('dark');
    localStorage.setItem('theme', theme);
  }, [theme]);
  return (
    <button
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
      className="p-2.5 rounded-xl bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-blue-600 dark:text-blue-400 shadow-inner hover:scale-105 transition-transform"
      aria-label="Toggle Theme"
    >
      {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
    </button>
  );
};

const Navbar = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  const adminEmail = localStorage.getItem('admin_email');
  const adminToken = localStorage.getItem('admin_token');
  const isLoggedIn = !!(adminEmail && adminToken);

  const isActive = (path: string) => location.pathname === path;

  const handleLogout = () => {
    localStorage.removeItem('admin_token');
    localStorage.removeItem('admin_email');
    localStorage.removeItem('admin_role');
    navigate('/admin/login');
  };

  useEffect(() => {
    setIsSidebarOpen(false);
  }, [location]);

  return (
    <>
      {/* TOP NAV */}
      <nav className="bg-white/90 dark:bg-slate-900/90 backdrop-blur-lg border-b border-slate-200 dark:border-slate-800 sticky top-0 z-50 h-20 transition-colors duration-500 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-full flex items-center justify-between">

          {/* Brand */}
          <Link to="/" className="flex items-center gap-3 sm:gap-4 group">
            <div className="w-12 h-12 sm:w-14 sm:h-14 rounded-2xl bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/30 group-hover:shadow-blue-500/50 transition-all border-2 border-blue-500/20 shrink-0">
              <Bot className="w-6 h-6 sm:w-7 sm:h-7 text-white" />
            </div>
            <div className="flex flex-col">
              <span className="font-black text-lg sm:text-2xl text-slate-900 dark:text-white leading-none tracking-tight group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                Smart Email Assistant
              </span>
              <span className="text-[10px] sm:text-xs font-bold text-blue-600 dark:text-blue-500 tracking-widest uppercase mt-1">
                Agentic AI
              </span>
            </div>
          </Link>

          {/* Desktop Nav */}
          <div className="hidden xl:flex items-center space-x-2">
            <ThemeToggle />

            {isLoggedIn && (
              <Link
                to="/admin/dashboard"
                className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-bold transition-all ${isActive('/admin/dashboard') ? 'bg-blue-50 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400 shadow-sm' : 'text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white'}`}
              >
                <LayoutDashboard className="w-4 h-4" /> Dashboard
              </Link>
            )}

            <Link
              to="/about"
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-bold transition-all ${isActive('/about') ? 'bg-blue-50 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400 shadow-sm' : 'text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white'}`}
            >
              <Info className="w-4 h-4" /> About Us
            </Link>

            {isLoggedIn ? (
              <>
                <Link
                  to="/admin/settings"
                  className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-bold transition-all ${isActive('/admin/settings') ? 'bg-blue-50 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400 shadow-sm' : 'text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white'}`}
                >
                  <Settings className="w-4 h-4" /> Settings
                </Link>
                <button
                  onClick={handleLogout}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-bold text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 hover:text-red-600 transition-all"
                >
                  <LogOut className="w-4 h-4" /> Logout
                </button>
              </>
            ) : (
              <Link
                to="/admin/login"
                className="ml-2 flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-bold text-white bg-blue-600 hover:bg-blue-700 transition-all shadow-lg hover:shadow-blue-500/30 hover:-translate-y-0.5"
              >
                Admin Portal <LogIn className="w-4 h-4" />
              </Link>
            )}
          </div>

          {/* Mobile Hamburger */}
          <div className="flex xl:hidden items-center gap-3">
            <ThemeToggle />
            <button
              onClick={() => setIsSidebarOpen(true)}
              className="p-2.5 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors border border-slate-200 dark:border-slate-700"
            >
              <Menu className="w-6 h-6" />
            </button>
          </div>
        </div>
      </nav>

      {/* MOBILE SIDEBAR OVERLAY */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-[90] xl:hidden animate-in fade-in duration-300"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* MOBILE SIDEBAR PANEL */}
      <div className={`fixed top-0 right-0 h-full w-[280px] sm:w-[320px] bg-white dark:bg-slate-950 shadow-2xl z-[100] transform transition-transform duration-300 ease-out xl:hidden flex flex-col border-l border-slate-200 dark:border-slate-800 ${isSidebarOpen ? 'translate-x-0' : 'translate-x-full'}`}>

        <div className="h-20 px-5 flex items-center justify-between border-b border-slate-100 dark:border-slate-800/50 bg-slate-50/50 dark:bg-slate-900/50">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center">
              <Bot className="w-5 h-5 text-white" />
            </div>
            <span className="font-black text-lg text-slate-900 dark:text-white tracking-tight">Menu</span>
          </div>
          <button
            onClick={() => setIsSidebarOpen(false)}
            className="p-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-500 hover:text-slate-900 dark:hover:text-white transition-colors border border-slate-200 dark:border-slate-700"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 flex flex-col gap-2 flex-1 overflow-y-auto">
          {isLoggedIn && (
            <Link to="/admin/dashboard" className={`flex items-center gap-3 p-4 rounded-2xl font-bold transition-all ${isActive('/admin/dashboard') ? 'bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400' : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/50'}`}>
              <LayoutDashboard className="w-5 h-5" /> Dashboard
            </Link>
          )}
          <Link to="/about" className={`flex items-center gap-3 p-4 rounded-2xl font-bold transition-all ${isActive('/about') ? 'bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400' : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/50'}`}>
            <Info className="w-5 h-5" /> About Us
          </Link>
          <Link to="/about#help" className="flex items-center gap-3 p-4 rounded-2xl font-bold text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-all">
            <HelpCircle className="w-5 h-5" /> Help & Guides
          </Link>
          <Link to="/about#contact" className="flex items-center gap-3 p-4 rounded-2xl font-bold text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-all">
            <PhoneCall className="w-5 h-5" /> Contact Support
          </Link>
        </div>

        <div className="p-4 border-t border-slate-100 dark:border-slate-800/50 flex flex-col gap-2 bg-slate-50/30 dark:bg-slate-900/30">
          {isLoggedIn ? (
            <>
              <Link to="/admin/settings" className={`flex items-center gap-3 p-4 rounded-2xl font-bold transition-all ${isActive('/admin/settings') ? 'bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400' : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/50'}`}>
                <Settings className="w-5 h-5" /> Settings
              </Link>
              <button onClick={handleLogout} className="flex items-center gap-3 p-4 rounded-2xl font-bold text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 transition-all w-full text-left">
                <LogOut className="w-5 h-5" /> Logout
              </button>
            </>
          ) : (
            <Link to="/admin/login" className="flex items-center justify-center gap-3 p-4 rounded-2xl font-bold text-white bg-blue-600 hover:bg-blue-700 transition-all shadow-md">
              <LogIn className="w-5 h-5" /> Admin Login
            </Link>
          )}
        </div>
      </div>
    </>
  );
};

export default Navbar;