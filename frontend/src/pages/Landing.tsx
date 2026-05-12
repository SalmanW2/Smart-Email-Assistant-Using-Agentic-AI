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
    <button onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} className="p-2.5 rounded-full bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-blue-600 dark:text-blue-400 shadow-inner">
      {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
    </button>
  );
};

const Landing = () => {
  const [activeBox, setActiveBox] = useState<number | null>(null);
  const toggleBox = (index: number) => setActiveBox(activeBox === index ? null : index);

  return (
    <div className="min-h-screen bg-white dark:bg-slate-950 font-sans transition-colors duration-300 overflow-x-hidden">
      <nav className="fixed top-0 w-full z-50 bg-white/95 dark:bg-slate-950/90 backdrop-blur-xl border-b border-slate-100 dark:border-slate-800/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 sm:h-20 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="bg-gradient-to-br from-blue-500 to-sky-600 rounded-lg p-1.5 shadow-md">
              <Mail className="w-5 h-5 text-white" />
            </div>
            <span className="font-extrabold text-lg sm:text-2xl tracking-tighter text-slate-900 dark:text-white">EmailAgent<span className="text-blue-600">.ai</span></span>
          </div>
          <div className="flex items-center gap-3 sm:gap-5">
            <a href="/help" className="text-xs sm:text-sm font-semibold text-slate-600 dark:text-slate-400 hidden xs:block">Knowledge Base</a>
            <ThemeToggle />
            <a href="/admin/login" className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 sm:px-6 sm:py-3 rounded-full text-xs sm:text-sm font-bold shadow-lg transition-all">Admin</a>
          </div>
        </div>
      </nav>

      <main className="relative max-w-7xl mx-auto px-4 sm:px-6 pt-32 sm:pt-44 pb-20 text-center">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-[600px] h-[600px] bg-blue-100/30 dark:bg-blue-600/10 blur-[120px] rounded-full pointer-events-none"></div>
        <div className="relative z-10 space-y-6 sm:space-y-10">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-50 dark:bg-slate-900 border border-blue-100 dark:border-blue-900/50 text-blue-700 dark:text-blue-400 text-[10px] sm:text-xs font-black uppercase tracking-widest">
            <Zap className="w-3 h-3 sm:w-4 sm:h-4 fill-current" /> Next-Gen AI Agent
          </div>
          <h1 className="text-4xl sm:text-6xl md:text-8xl font-black tracking-tighter leading-tight text-slate-900 dark:text-white px-2">
            Command Gmail via <br/>
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-sky-500">AI in Telegram.</span>
          </h1>
          <p className="max-w-2xl mx-auto text-base sm:text-xl text-slate-600 dark:text-slate-400 font-medium px-4">Draft, summarize, and manage inbox via dynamic Telegram interfaces.</p>
          <div className="pt-5">
            <a href="http://t.me/Smart_Emailbot" target="_blank" rel="noreferrer" className="inline-flex items-center gap-3 bg-blue-600 text-white px-8 py-4 sm:px-10 sm:py-5 rounded-2xl font-black text-lg sm:text-xl hover:scale-105 transition-all shadow-xl">
              <Bot className="w-6 h-6" /> Deploy to Telegram
            </a>
          </div>
        </div>
      </main>

      <section className="relative bg-slate-50 dark:bg-slate-900 border-t border-slate-100 dark:border-slate-800 py-16 sm:py-32">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 grid grid-cols-1 md:grid-cols-3 gap-6">
          
          <div onClick={() => toggleBox(1)} className="bg-white dark:bg-slate-950 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 cursor-pointer shadow-sm transition-all">
            <div className="flex justify-between items-center mb-4">
              <div className="w-12 h-12 bg-slate-50 dark:bg-slate-900 rounded-xl flex items-center justify-center">
                <Key className="w-6 h-6 text-blue-600" />
              </div>
              {activeBox === 1 ? <ChevronUp className="text-slate-400" /> : <ChevronDown className="text-slate-400" />}
            </div>
            <h3 className="text-xl font-bold text-slate-900 dark:text-white">Bring Your Own Keys</h3>
            {activeBox === 1 && (
              <p className="mt-4 text-sm text-slate-600 dark:text-slate-400 font-medium transition-all">Ultimate sovereignty over your data and costs. Integrate your personal Google Gemini LLM keys and Google Workspace credentials.</p>
            )}
          </div>

          <div onClick={() => toggleBox(2)} className="bg-white dark:bg-slate-950 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 cursor-pointer shadow-sm transition-all">
            <div className="flex justify-between items-center mb-4">
              <div className="w-12 h-12 bg-slate-50 dark:bg-slate-900 rounded-xl flex items-center justify-center">
                <Globe className="w-6 h-6 text-blue-600" />
              </div>
              {activeBox === 2 ? <ChevronUp className="text-slate-400" /> : <ChevronDown className="text-slate-400" />}
            </div>
            <h3 className="text-xl font-bold text-slate-900 dark:text-white">Enterprise Security</h3>
            {activeBox === 2 && (
              <p className="mt-4 text-sm text-slate-600 dark:text-slate-400 font-medium transition-all">Official Google OAuth 2.0 integration. Conversations are processed dynamically in isolated RAM slots and never stored.</p>
            )}
          </div>

          <div onClick={() => toggleBox(3)} className="bg-white dark:bg-slate-950 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 cursor-pointer shadow-sm transition-all">
            <div className="flex justify-between items-center mb-4">
              <div className="w-12 h-12 bg-slate-50 dark:bg-slate-900 rounded-xl flex items-center justify-center">
                <ShieldCheck className="w-6 h-6 text-blue-600" />
              </div>
              {activeBox === 3 ? <ChevronUp className="text-slate-400" /> : <ChevronDown className="text-slate-400" />}
            </div>
            <h3 className="text-xl font-bold text-slate-900 dark:text-white">Access Control</h3>
            {activeBox === 3 && (
              <p className="mt-4 text-sm text-slate-600 dark:text-slate-400 font-medium transition-all">Verified administrators command the ecosystem. Block rogue requests, audit user tables, and monitor bot usage.</p>
            )}
          </div>

        </div>
      </section>
    </div>
  );
};

export default Landing;