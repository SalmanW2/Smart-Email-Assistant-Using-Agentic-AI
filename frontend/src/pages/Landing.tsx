import { useState, useEffect } from 'react';
import { Mail, ShieldCheck, Zap, Key, ArrowRight, Sun, Moon, Globe, Bot, ChevronDown, ChevronUp } from 'lucide-react';

const ThemeToggle = () => {
  const [theme, setTheme] = useState(localStorage.getItem('theme') || 'light');
  useEffect(() => {
    if (theme === 'dark') document.documentElement.classList.add('dark');
    else document.documentElement.classList.remove('dark');
    localStorage.setItem('theme', theme);
  }, [theme]);
  return (
    <button onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} className="p-2.5 rounded-full bg-slate-100 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 text-blue-600 dark:text-blue-400 hover:bg-white dark:hover:bg-slate-800 hover:scale-110 transition-all duration-300 shadow-sm">
      {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
    </button>
  );
};

const Landing = () => {
  const [activeBox, setActiveBox] = useState<number | null>(null);
  const toggleBox = (index: number) => setActiveBox(activeBox === index ? null : index);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 font-sans transition-colors duration-500 overflow-x-hidden selection:bg-blue-500/30">
      {/* Premium Navbar */}
      <nav className="fixed top-0 w-full z-50 bg-white/80 dark:bg-slate-950/80 backdrop-blur-xl border-b border-slate-200/50 dark:border-slate-800/50 transition-colors duration-500">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-20 flex items-center justify-between">
          <div className="flex items-center gap-3 cursor-pointer group">
            <div className="bg-gradient-to-br from-blue-600 to-indigo-600 rounded-xl p-2.5 shadow-lg shadow-blue-500/30 group-hover:scale-110 transition-transform duration-300">
              <Mail className="w-6 h-6 text-white" />
            </div>
            <span className="font-extrabold text-2xl tracking-tighter text-slate-900 dark:text-white">EmailAgent<span className="text-blue-600 dark:text-blue-500">.ai</span></span>
          </div>
          <div className="flex items-center gap-6">
            <a href="/help" className="text-sm font-bold text-slate-500 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors hidden sm:block">Knowledge Base</a>
            <ThemeToggle />
            <a href="/admin/login" className="bg-slate-900 dark:bg-white text-white dark:text-slate-900 px-6 py-2.5 rounded-full text-sm font-bold shadow-lg hover:shadow-xl hover:-translate-y-0.5 transition-all duration-300 flex items-center gap-2">
              Admin Access <ArrowRight className="w-4 h-4" />
            </a>
          </div>
        </div>
      </nav>

      {/* Hero Section with Glowing Effects */}
      <main className="relative max-w-7xl mx-auto px-4 sm:px-6 pt-40 pb-24 text-center">
        {/* Background Glow */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[300px] sm:w-[600px] h-[300px] sm:h-[600px] bg-blue-500/20 dark:bg-blue-600/10 blur-[100px] sm:blur-[120px] rounded-full pointer-events-none"></div>
        
        <div className="relative z-10 space-y-8 animate-in fade-in slide-in-from-bottom-10 duration-1000">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 text-blue-600 dark:text-blue-400 text-xs font-black uppercase tracking-widest shadow-sm">
            <Zap className="w-4 h-4 fill-current text-amber-500" /> Next-Gen Workspace Intelligence
          </div>
          
          <h1 className="text-5xl sm:text-7xl md:text-8xl font-black tracking-tighter leading-[1.1] text-slate-900 dark:text-white">
            Command Gmail via <br className="hidden sm:block" />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 via-indigo-500 to-purple-500">AI Agents in Telegram.</span>
          </h1>
          
          <p className="max-w-2xl mx-auto text-lg sm:text-xl text-slate-600 dark:text-slate-400 leading-relaxed font-medium">
            Draft, summarize, and manage your inbox dynamically. A zero-trust, enterprise-grade AI companion built for professionals.
          </p>
          
          <div className="pt-8">
            <a href="https://t.me/Smart_Emailbot" target="_blank" rel="noreferrer" className="group relative inline-flex items-center justify-center gap-3 bg-blue-600 text-white px-8 sm:px-12 py-5 rounded-2xl font-black text-lg overflow-hidden transition-all hover:scale-105 hover:shadow-2xl hover:shadow-blue-500/40 w-full sm:w-auto">
              <div className="absolute inset-0 bg-gradient-to-r from-blue-600 to-indigo-600 opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
              <Bot className="w-6 h-6 relative z-10 group-hover:animate-bounce" /> 
              <span className="relative z-10">Deploy to Telegram</span>
            </a>
          </div>
        </div>
      </main>

      {/* Premium Interactive Feature Boxes */}
      <section className="relative bg-white dark:bg-slate-900/50 border-t border-slate-200/50 dark:border-slate-800/50 py-24 transition-colors duration-500">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 grid grid-cols-1 md:grid-cols-3 gap-6 sm:gap-8">
          
          {/* Box 1 */}
          <div onClick={() => toggleBox(1)} className="group bg-slate-50 dark:bg-slate-900 p-8 rounded-3xl border border-slate-200 dark:border-slate-800 cursor-pointer hover:border-blue-500/50 dark:hover:border-blue-500/50 hover:shadow-xl hover:shadow-blue-500/5 transition-all duration-300">
            <div className="flex justify-between items-start mb-6">
              <div className="w-14 h-14 bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-2xl flex items-center justify-center shadow-sm group-hover:scale-110 group-hover:rotate-3 transition-transform duration-300">
                <Key className="w-6 h-6 text-blue-600 dark:text-blue-400" />
              </div>
              <div className="bg-slate-200/50 dark:bg-slate-800/50 p-2 rounded-full text-slate-500 dark:text-slate-400 group-hover:text-blue-500 transition-colors">
                {activeBox === 1 ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
              </div>
            </div>
            <h3 className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight">Bring Your Own Keys</h3>
            <div className={`grid transition-all duration-500 ease-in-out ${activeBox === 1 ? 'grid-rows-[1fr] opacity-100 mt-4' : 'grid-rows-[0fr] opacity-0'}`}>
              <div className="overflow-hidden">
                <p className="text-slate-600 dark:text-slate-400 font-medium leading-relaxed">
                  Ultimate sovereignty over your data. Integrate your personal Google Gemini LLM keys and Workspace credentials. Zero intermediary data processing.
                </p>
              </div>
            </div>
          </div>

          {/* Box 2 */}
          <div onClick={() => toggleBox(2)} className="group bg-slate-50 dark:bg-slate-900 p-8 rounded-3xl border border-slate-200 dark:border-slate-800 cursor-pointer hover:border-indigo-500/50 dark:hover:border-indigo-500/50 hover:shadow-xl hover:shadow-indigo-500/5 transition-all duration-300">
            <div className="flex justify-between items-start mb-6">
              <div className="w-14 h-14 bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-2xl flex items-center justify-center shadow-sm group-hover:scale-110 group-hover:-rotate-3 transition-transform duration-300">
                <Globe className="w-6 h-6 text-indigo-600 dark:text-indigo-400" />
              </div>
              <div className="bg-slate-200/50 dark:bg-slate-800/50 p-2 rounded-full text-slate-500 dark:text-slate-400 group-hover:text-indigo-500 transition-colors">
                {activeBox === 2 ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
              </div>
            </div>
            <h3 className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight">Enterprise Security</h3>
            <div className={`grid transition-all duration-500 ease-in-out ${activeBox === 2 ? 'grid-rows-[1fr] opacity-100 mt-4' : 'grid-rows-[0fr] opacity-0'}`}>
              <div className="overflow-hidden">
                <p className="text-slate-600 dark:text-slate-400 font-medium leading-relaxed">
                  Official Google OAuth 2.0 integration. Conversations are processed dynamically in isolated RAM slots and never permanently stored on our servers.
                </p>
              </div>
            </div>
          </div>

          {/* Box 3 */}
          <div onClick={() => toggleBox(3)} className="group bg-slate-50 dark:bg-slate-900 p-8 rounded-3xl border border-slate-200 dark:border-slate-800 cursor-pointer hover:border-purple-500/50 dark:hover:border-purple-500/50 hover:shadow-xl hover:shadow-purple-500/5 transition-all duration-300">
            <div className="flex justify-between items-start mb-6">
              <div className="w-14 h-14 bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-2xl flex items-center justify-center shadow-sm group-hover:scale-110 group-hover:rotate-3 transition-transform duration-300">
                <ShieldCheck className="w-6 h-6 text-purple-600 dark:text-purple-400" />
              </div>
              <div className="bg-slate-200/50 dark:bg-slate-800/50 p-2 rounded-full text-slate-500 dark:text-slate-400 group-hover:text-purple-500 transition-colors">
                {activeBox === 3 ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
              </div>
            </div>
            <h3 className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight">Granular Control</h3>
            <div className={`grid transition-all duration-500 ease-in-out ${activeBox === 3 ? 'grid-rows-[1fr] opacity-100 mt-4' : 'grid-rows-[0fr] opacity-0'}`}>
              <div className="overflow-hidden">
                <p className="text-slate-600 dark:text-slate-400 font-medium leading-relaxed">
                  Verified administrators command the ecosystem. Monitor user analytics, audit interactions, and block rogue requests instantly from the dashboard.
                </p>
              </div>
            </div>
          </div>

        </div>
      </section>
    </div>
  );
};

export default Landing;