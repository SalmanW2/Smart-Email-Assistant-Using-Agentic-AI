import { useState, useEffect } from 'react';
import { Mail, Bot, ShieldCheck, Zap, Key, Lock, ArrowRight, Sun, Moon, Globe, BotMessageSquare } from 'lucide-react';
import { Link } from 'react-router-dom';

const ThemeToggle = () => {
  const [theme, setTheme] = useState(localStorage.getItem('theme') || 'light');

  useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    localStorage.setItem('theme', theme);
  }, [theme]);

  return (
    <button
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
      className="p-2.5 rounded-full bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-blue-600 dark:text-blue-400 hover:border-blue-500 transition-all shadow-inner"
    >
      {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
    </button>
  );
};

const Landing = () => {
  return (
    <div className="min-h-screen bg-white dark:bg-slate-950 font-sans selection:bg-blue-500/30 selection:text-blue-900 dark:selection:text-blue-100 transition-colors duration-300">
      
      {/* SaaS Premium Sticky Navbar */}
      <nav className="fixed top-0 w-full z-50 bg-white/95 dark:bg-slate-950/90 backdrop-blur-xl border-b border-slate-100 dark:border-slate-800/50">
        <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="relative flex items-center justify-center w-10 h-10 bg-gradient-to-br from-blue-500 to-sky-600 rounded-xl shadow-[0_4px_12px_rgba(59,130,246,0.3)] dark:shadow-[0_0_20px_rgba(59,130,246,0.2)]">
              <Mail className="w-5 h-5 text-white" />
            </div>
            <span className="font-extrabold text-2xl tracking-tighter text-slate-950 dark:text-white">EmailAgent<span className="text-blue-600 dark:text-blue-500">.ai</span></span>
          </div>
          <div className="flex items-center gap-5">
            <Link to="/help" className="text-sm font-semibold text-slate-600 dark:text-slate-400 hover:text-blue-600 dark:hover:text-white transition-colors">Documentation</Link>
            <div className="h-5 w-px bg-slate-200 dark:bg-slate-800"></div>
            <ThemeToggle />
            <Link to="/admin/login" className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-full text-sm font-bold shadow-[0_4px_12px_rgba(59,130,246,0.3)] hover:shadow-[0_6px_16px_rgba(59,130,246,0.4)] transition-all">
              Admin Access <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <main className="relative max-w-7xl mx-auto px-6 pt-44 pb-32 text-center">
        {/* Background Radial Gradient Effect (Light/Dark) */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-blue-100/50 dark:bg-blue-600/10 blur-[150px] rounded-full pointer-events-none transition-colors"></div>

        <div className="relative z-10 space-y-10">
          <div className="inline-flex items-center gap-2.5 px-4 py-2 rounded-full bg-blue-50 dark:bg-slate-900 border border-blue-100 dark:border-blue-900/50 text-blue-700 dark:text-blue-400 text-xs font-black uppercase tracking-widest backdrop-blur-sm">
            <Zap className="w-4 h-4 fill-current" /> Next-Gen Gemini-Powered Agent
          </div>
          
          <h1 className="text-7xl md:text-8xl font-black tracking-tighter leading-[0.95] text-slate-950 dark:text-white">
            Command Gmail through <br/>
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 via-sky-500 to-blue-600 animate-gradient-fast">
              AI Agents in Telegram.
            </span>
          </h1>
          
          <p className="max-w-2xl mx-auto text-xl text-slate-600 dark:text-slate-400 font-medium leading-relaxed">
            A zero-trust, enterprise-grade AI companion for workspace automation. Draft, summarize, and manage inbox dynamically via professional Telegram interfaces.
          </p>
          
          <div className="flex flex-col sm:flex-row items-center justify-center gap-6 pt-5">
            <a href="http://t.me/Smart_Emailbot" target="_blank" rel="noreferrer" className="group relative flex items-center justify-center gap-3.5 bg-blue-600 text-white px-10 py-5 rounded-2xl font-black text-xl hover:scale-105 transition-all w-full sm:w-auto overflow-hidden shadow-[0_10px_30px_rgba(59,130,246,0.3)] hover:shadow-[0_15px_40px_rgba(59,130,246,0.4)]">
              <BotMessageSquare className="w-6 h-6 group-hover:rotate-6 transition-transform" /> Deploy AI Agent to Telegram
            </a>
          </div>
        </div>
      </main>

      {/* Modern SaaS Feature Section (Grid + BYOK Highlight) */}
      <section className="relative bg-white dark:bg-slate-900 border-t border-slate-100 dark:border-slate-800 py-32 transition-colors">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8">
            
            {/* Bring Your Own Key (BYOK) - Highlight Feature */}
            <div className="group md:col-span-2 bg-slate-50 dark:bg-slate-950 p-10 rounded-3xl border border-blue-100 dark:border-blue-900/50 hover:border-blue-500 dark:hover:border-blue-500 transition-colors relative overflow-hidden shadow-sm dark:shadow-none">
              <div className="absolute top-0 right-0 w-48 h-48 bg-blue-100/50 dark:bg-blue-500/10 rounded-bl-full -z-10 group-hover:scale-110 transition-transform"></div>
              <div className="w-14 h-14 bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-2xl flex items-center justify-center mb-8 shadow-inner dark:shadow-none">
                <Key className="w-6 h-6 text-blue-600 dark:text-blue-400" />
              </div>
              <h3 className="text-3xl font-extrabold text-slate-950 dark:text-white tracking-tighter mb-4">Bring Your Own Keys (BYOK)</h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed font-medium mb-5 max-w-xl">Ultimate sovereignty over your data and costs. Integrate your personal Google Gemini LLM keys and Google Workspace OAuth credentials for absolute privacy and granular resource management.</p>
              <div className="inline-flex items-center gap-2 text-sm font-bold text-blue-600 dark:text-blue-400">Zero Trust Deployment <ArrowRight className="w-4 h-4" /></div>
            </div>

            <div className="group bg-white dark:bg-slate-950 p-8 rounded-3xl border border-slate-100 dark:border-slate-800 hover:border-blue-500 transition-colors relative shadow-sm dark:shadow-none">
              <div className="w-14 h-14 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-2xl flex items-center justify-center mb-6 shadow-inner dark:shadow-none">
                <Globe className="w-6 h-6 text-blue-600 dark:text-blue-400" />
              </div>
              <h3 className="text-xl font-bold text-slate-950 dark:text-white tracking-tight mb-3">Enterprise Security</h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed font-medium">Official Google OAuth 2.0 integration. Conversations are processed dynamically in isolated RAM slots and never stored.</p>
            </div>

            <div className="group bg-white dark:bg-slate-950 p-8 rounded-3xl border border-slate-100 dark:border-slate-800 hover:border-blue-500 transition-colors relative shadow-sm dark:shadow-none">
              <div className="w-14 h-14 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-2xl flex items-center justify-center mb-6 shadow-inner dark:shadow-none">
                <ShieldCheck className="w-6 h-6 text-blue-600 dark:text-blue-400" />
              </div>
              <h3 className="text-xl font-bold text-slate-950 dark:text-white tracking-tight mb-3">Granular Access Control</h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed font-medium">Administrators verified via PBKDF2 can manage user verification, blocklists, and system resource health from a central dashboard.</p>
            </div>

          </div>
        </div>
      </section>
    </div>
  );
};

export default Landing;