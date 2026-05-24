import { Bot, FileText, Edit3, Lock, Zap } from 'lucide-react';
import { Link } from 'react-router-dom';
import Navbar from '../components/Navbar';

const Landing = () => {
  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-50 via-white to-blue-50 dark:from-slate-950 dark:via-slate-900 dark:to-indigo-950/20 font-sans transition-colors duration-500 overflow-x-hidden selection:bg-blue-500/30">
      
      <Navbar />

      {/* Hero Section */}
      <main className="relative max-w-7xl mx-auto px-4 sm:px-6 pt-20 sm:pt-32 pb-20 sm:pb-24 text-center">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[300px] sm:w-[600px] h-[300px] sm:h-[600px] bg-blue-500/20 dark:bg-blue-600/10 blur-[100px] sm:blur-[120px] rounded-full pointer-events-none"></div>
        
        <div className="relative z-10 space-y-6 sm:space-y-8 animate-in fade-in slide-in-from-bottom-10 duration-1000">
          
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-blue-100 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800/50 text-blue-700 dark:text-blue-300 text-xs font-black uppercase tracking-widest shadow-sm">
            <Zap className="w-4 h-4 text-amber-500" /> The Future of Email Management
          </div>
          
          <h1 className="text-4xl sm:text-6xl md:text-8xl font-black tracking-tighter leading-[1.1] text-slate-900 dark:text-white">
            Your Inbox, Mastered by <br className="hidden md:block" />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 via-indigo-500 to-purple-500">Agentic AI.</span>
          </h1>
          
          <p className="max-w-2xl mx-auto text-base sm:text-xl text-slate-600 dark:text-slate-400 leading-relaxed font-medium px-2 sm:px-0">
            Stop drowning in emails. Get instant summaries, draft context-aware replies, and command your professional communication—all through a simple Telegram chat.
          </p>
          
          <div className="pt-6 sm:pt-8 flex flex-col sm:flex-row items-center justify-center gap-4 w-full sm:w-auto px-4 sm:px-0">
            <a href="https://t.me/Private_Mail_Assistent_Bot" target="_blank" rel="noreferrer" className="w-full sm:w-auto group relative inline-flex items-center justify-center gap-3 bg-blue-600 text-white px-8 py-4 sm:py-5 rounded-2xl font-black text-base sm:text-lg overflow-hidden transition-all hover:scale-105 hover:shadow-2xl hover:shadow-blue-500/40">
              <Bot className="w-5 h-5 sm:w-6 sm:h-6 relative z-10 group-hover:animate-bounce" /> 
              <span className="relative z-10">Start on Telegram 🚀</span>
            </a>
            <a href="#features" className="w-full sm:w-auto inline-flex items-center justify-center bg-white/80 dark:bg-slate-900/80 backdrop-blur-md border border-slate-200 dark:border-slate-800 px-8 py-4 sm:py-5 rounded-2xl font-bold text-base sm:text-lg text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all shadow-sm">
              See How It Works
            </a>
          </div>

          <div className="mt-10 sm:mt-12 flex flex-col sm:flex-row items-center justify-center gap-2 sm:gap-3 text-xs sm:text-sm text-slate-500 dark:text-slate-400 bg-white/50 dark:bg-slate-900/50 backdrop-blur-sm px-4 sm:px-6 py-3 rounded-full border border-slate-200 dark:border-slate-800 shadow-sm max-w-fit mx-auto">
            <div className="flex items-center gap-1.5">
              <Lock className="w-4 h-4 text-emerald-500" />
              <b className="text-slate-700 dark:text-slate-300">Bank-Level Security:</b>
            </div>
            <span className="text-center">Secured by Official Google OAuth. We never store your emails.</span>
          </div>

        </div>
      </main>

      {/* Features Section */}
      <section id="features" className="relative bg-white/40 dark:bg-slate-900/40 border-t border-slate-200/50 dark:border-slate-800/50 py-16 sm:py-24 transition-colors duration-500">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <div className="text-center mb-12 sm:mb-20">
            <h2 className="text-3xl sm:text-4xl font-black text-slate-900 dark:text-white tracking-tight">Why Use Smart Email Assistant?</h2>
            <p className="text-slate-500 dark:text-slate-400 mt-3 sm:mt-4 text-lg sm:text-xl font-medium">Experience an inbox that practically manages itself.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 sm:gap-8">
            
            <div className="group bg-white/80 dark:bg-slate-900/80 backdrop-blur-md p-8 sm:p-10 rounded-3xl border border-slate-200 dark:border-slate-800 hover:border-blue-500/50 dark:hover:border-blue-500/50 hover:shadow-xl hover:shadow-blue-500/10 transition-all duration-300 hover:-translate-y-2">
              <div className="w-14 h-14 bg-blue-100 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800/50 rounded-2xl flex items-center justify-center shadow-sm mb-6 group-hover:scale-110 transition-transform duration-300">
                <FileText className="w-6 h-6 text-blue-600 dark:text-blue-400" />
              </div>
              <h3 className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight mb-4">Instant Summaries</h3>
              <p className="text-slate-600 dark:text-slate-400 font-medium leading-relaxed">
                Skip the 20-message threads. Our Agentic AI reads the context and gives you the exact action points in bullet format instantly.
              </p>
            </div>

            <div className="group bg-white/80 dark:bg-slate-900/80 backdrop-blur-md p-8 sm:p-10 rounded-3xl border border-slate-200 dark:border-slate-800 hover:border-purple-500/50 dark:hover:border-purple-500/50 hover:shadow-xl hover:shadow-purple-500/10 transition-all duration-300 hover:-translate-y-2">
              <div className="w-14 h-14 bg-purple-100 dark:bg-purple-900/30 border border-purple-200 dark:border-purple-800/50 rounded-2xl flex items-center justify-center shadow-sm mb-6 group-hover:scale-110 transition-transform duration-300">
                <Edit3 className="w-6 h-6 text-purple-600 dark:text-purple-400" />
              </div>
              <h3 className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight mb-4">Smart Drafting</h3>
              <p className="text-slate-600 dark:text-slate-400 font-medium leading-relaxed">
                Tell the bot "Tell John I'll finish the report by Friday." The AI will instantly generate a highly professional email ready to send.
              </p>
            </div>

            <div className="group bg-white/80 dark:bg-slate-900/80 backdrop-blur-md p-8 sm:p-10 rounded-3xl border border-slate-200 dark:border-slate-800 hover:border-emerald-500/50 dark:hover:border-emerald-500/50 hover:shadow-xl hover:shadow-emerald-500/10 transition-all duration-300 hover:-translate-y-2">
              <div className="w-14 h-14 bg-emerald-100 dark:bg-emerald-900/30 border border-emerald-200 dark:border-emerald-800/50 rounded-2xl flex items-center justify-center shadow-sm mb-6 group-hover:scale-110 transition-transform duration-300">
                <Lock className="w-6 h-6 text-emerald-600 dark:text-emerald-400" />
              </div>
              <h3 className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight mb-4">Absolute Privacy</h3>
              <p className="text-slate-600 dark:text-slate-400 font-medium leading-relaxed">
                Your data remains yours. We use strict Google API standards to ensure your inbox remains completely encrypted and isolated.
              </p>
            </div>

          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-slate-900 dark:bg-slate-950 text-white py-12 border-t border-slate-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            
            <div>
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-blue-600 flex items-center justify-center">
                  <Bot className="w-6 h-6" />
                </div>
                <span className="font-black text-xl">Smart Email Assistant</span>
              </div>
              <p className="text-slate-400 text-sm font-medium leading-relaxed">
                Automate your inbox with the power of Agentic AI. Manage emails smarter, faster, and more efficiently.
              </p>
            </div>

            <div>
              <h3 className="font-bold text-lg mb-4">Quick Links</h3>
              <ul className="space-y-2 text-slate-400">
                <li><Link to="/about" className="hover:text-white transition-colors font-medium">About Us</Link></li>
                <li><Link to="/about#how-it-works" className="hover:text-white transition-colors font-medium">How It Works</Link></li>
                <li><Link to="/about#help" className="hover:text-white transition-colors font-medium">Help & FAQ</Link></li>
                <li><Link to="/admin/login" className="hover:text-white transition-colors font-medium">Admin Portal</Link></li>
              </ul>
            </div>

            <div>
              <h3 className="font-bold text-lg mb-4">Contact & Support</h3>
              <ul className="space-y-2 text-slate-400">
                <li><Link to="/about#contact" className="hover:text-white transition-colors font-medium">Contact Form</Link></li>
                <li><Link to="/about#security" className="hover:text-white transition-colors font-medium">Security & Privacy</Link></li>
                <li><a href="https://t.me/Private_Mail_Assistent_Bot" target="_blank" rel="noreferrer" className="hover:text-white transition-colors font-medium">Telegram Bot</a></li>
              </ul>
            </div>

          </div>

          <div className="mt-12 pt-8 border-t border-slate-800 text-center text-slate-500 text-sm font-medium">
            <p>&copy; {new Date().getFullYear()} Smart Email Assistant. Powered by Agentic AI.</p>
          </div>
        </div>
      </footer>

    </div>
  );
};

export default Landing;