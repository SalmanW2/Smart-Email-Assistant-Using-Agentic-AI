import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Bot, Shield, Mic, Search, Send, Sun, Moon } from 'lucide-react';

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

const About = () => {
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 pb-20 transition-colors duration-300">
      
      {/* Premium Sticky Header */}
      <div className="bg-white/90 dark:bg-slate-900/90 backdrop-blur-xl border-b border-slate-200 dark:border-slate-800 sticky top-0 z-10 transition-colors">
        <div className="max-w-4xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link to="/" className="p-2 -ml-2 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-400 transition-colors">
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <h1 className="text-xl font-bold text-slate-900 dark:text-white">Knowledge Base</h1>
          </div>
          <ThemeToggle />
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-6 pt-10 space-y-12">
        
        {/* Section 1: Telegram Bot Guide */}
        <section>
          <div className="flex items-center gap-3 mb-6">
            <div className="bg-blue-100 dark:bg-blue-900/30 p-2 rounded-lg text-blue-700 dark:text-blue-400"><Bot className="w-6 h-6" /></div>
            <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Telegram Agent Guide</h2>
          </div>
          <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-800 overflow-hidden transition-colors">
            <div className="p-6 border-b border-slate-100 dark:border-slate-800/50">
              <h3 className="font-bold text-lg text-slate-800 dark:text-slate-200 mb-2">1. Connect Your Account</h3>
              <p className="text-slate-600 dark:text-slate-400">Open <a href="http://t.me/Smart_Emailbot" className="text-blue-600 dark:text-blue-400 hover:underline">@Smart_Emailbot</a> on Telegram and send <code>/start</code>. Click the generated secure link to connect your Gmail account via Google OAuth.</p>
            </div>
            <div className="p-6 border-b border-slate-100 dark:border-slate-800/50 bg-slate-50 dark:bg-slate-800/20">
              <h3 className="font-bold text-lg text-slate-800 dark:text-slate-200 mb-2 flex items-center gap-2"><Send className="w-5 h-5 text-green-600 dark:text-green-400"/> 2. Send Emails via Chat</h3>
              <p className="text-slate-600 dark:text-slate-400">Simply type naturally. Example: <i className="text-slate-500 dark:text-slate-300">"Send an email to my manager saying the project is complete."</i> The AI will auto-detect the contact, draft the email, and ask for your final confirmation.</p>
            </div>
            <div className="p-6 border-b border-slate-100 dark:border-slate-800/50">
              <h3 className="font-bold text-lg text-slate-800 dark:text-slate-200 mb-2 flex items-center gap-2"><Search className="w-5 h-5 text-purple-600 dark:text-purple-400"/> 3. Search & Summarize</h3>
              <p className="text-slate-600 dark:text-slate-400">Ask the bot to check your inbox: <i className="text-slate-500 dark:text-slate-300">"Read my last 3 unread emails"</i> or <i className="text-slate-500 dark:text-slate-300">"Search for emails from HR."</i> The AI will provide a concise summary to save your time.</p>
            </div>
            <div className="p-6">
              <h3 className="font-bold text-lg text-slate-800 dark:text-slate-200 mb-2 flex items-center gap-2"><Mic className="w-5 h-5 text-red-500 dark:text-red-400"/> 4. Voice Commands</h3>
              <p className="text-slate-600 dark:text-slate-400">Don't want to type? Send a voice note to the bot. It will transcribe your voice, understand your intent, and execute the command flawlessly.</p>
            </div>
          </div>
        </section>

        {/* Section 2: Admin Portal Guide */}
        <section>
          <div className="flex items-center gap-3 mb-6">
            <div className="bg-slate-800 dark:bg-slate-700 p-2 rounded-lg text-white"><Shield className="w-6 h-6" /></div>
            <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Admin Portal Guide</h2>
          </div>
          <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-800 p-6 space-y-6 transition-colors">
            <div>
              <h3 className="font-bold text-lg text-slate-800 dark:text-slate-200">Login Access</h3>
              <p className="text-slate-600 dark:text-slate-400 mt-1">Only authorized Admins can access the dashboard. Use Google Login or the Manual Password option set by a Super Admin.</p>
            </div>
            <hr className="border-slate-100 dark:border-slate-800/50" />
            <div>
              <h3 className="font-bold text-lg text-slate-800 dark:text-slate-200">Managing Users</h3>
              <p className="text-slate-600 dark:text-slate-400 mt-1">The dashboard allows you to view all bot users. If a user is misusing the bot, you can click the <b className="text-slate-900 dark:text-white">Block</b> button to revoke their Telegram access immediately.</p>
            </div>
            <hr className="border-slate-100 dark:border-slate-800/50" />
            <div>
              <h3 className="font-bold text-lg text-slate-800 dark:text-slate-200">Admin Settings</h3>
              <p className="text-slate-600 dark:text-slate-400 mt-1">In the Settings tab, you can set a fallback password for manual login. Super Admins also have the authority to add or remove other administrators from the system.</p>
            </div>
          </div>
        </section>

      </div>
    </div>
  );
};

export default About;