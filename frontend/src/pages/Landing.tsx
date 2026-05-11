import { Mail, Bot, Shield, Zap, Key, Lock, ArrowRight, Server } from 'lucide-react';
import { Link } from 'react-router-dom';

const Landing = () => {
  return (
    <div className="min-h-screen bg-slate-950 font-sans selection:bg-indigo-500/30">
      {/* Premium Glassmorphism Navbar */}
      <nav className="fixed top-0 w-full z-50 bg-slate-950/80 backdrop-blur-xl border-b border-slate-800">
        <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="relative flex items-center justify-center w-10 h-10 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl shadow-[0_0_20px_rgba(99,102,241,0.4)]">
              <Mail className="w-5 h-5 text-white" />
            </div>
            <span className="font-extrabold text-2xl tracking-tighter text-white">EmailAgent<span className="text-indigo-500">.ai</span></span>
          </div>
          <div className="flex items-center gap-6">
            <Link to="/help" className="text-sm font-semibold text-slate-400 hover:text-white transition-colors">Documentation</Link>
            <Link to="/admin/login" className="relative group px-6 py-2.5 rounded-full bg-slate-900 border border-slate-700 text-sm font-bold text-white hover:border-indigo-500 transition-all overflow-hidden">
              <div className="absolute inset-0 bg-indigo-500/10 group-hover:bg-indigo-500/20 transition-all"></div>
              <span className="relative z-10 flex items-center gap-2">Admin Portal <ArrowRight className="w-4 h-4" /></span>
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <main className="relative max-w-7xl mx-auto px-6 pt-40 pb-32 text-center">
        {/* Background Glow */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-indigo-600/20 blur-[120px] rounded-full pointer-events-none"></div>

        <div className="relative z-10">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-slate-900/50 border border-slate-800 text-indigo-400 text-xs font-black uppercase tracking-widest mb-8 backdrop-blur-sm">
            <Zap className="w-4 h-4 fill-current" /> Enterprise Agentic Workflow
          </div>
          
          <h1 className="text-6xl md:text-8xl font-black tracking-tighter mb-8 leading-[1.05] text-white">
            Command your inbox <br/>
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 via-purple-400 to-pink-400">
              with absolute authority.
            </span>
          </h1>
          
          <p className="max-w-2xl mx-auto text-xl text-slate-400 mb-12 font-medium leading-relaxed">
            Draft, summarize, and organize professional communications seamlessly through Telegram. Powered by Google Gemini and built for maximum privacy.
          </p>
          
          <div className="flex flex-col sm:flex-row items-center justify-center gap-6">
            <a href="http://t.me/Smart_Emailbot" target="_blank" rel="noreferrer" className="group relative flex items-center justify-center gap-3 bg-white text-slate-950 px-10 py-5 rounded-2xl font-black text-xl hover:scale-105 transition-all w-full sm:w-auto overflow-hidden shadow-[0_0_40px_rgba(255,255,255,0.2)] hover:shadow-[0_0_60px_rgba(255,255,255,0.4)]">
              <Bot className="w-6 h-6 group-hover:animate-bounce" /> Deploy Bot Now
            </a>
          </div>
        </div>
      </main>

      {/* Feature Grid with BYOK */}
      <section className="relative bg-slate-900 border-t border-slate-800 py-32">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid md:grid-cols-3 gap-8">
            
            {/* BYOK Concept Feature */}
            <div className="group bg-slate-950 p-8 rounded-3xl border border-slate-800 hover:border-indigo-500/50 transition-colors relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500/10 rounded-bl-full -z-10 group-hover:bg-indigo-500/20 transition-colors"></div>
              <div className="w-14 h-14 bg-slate-900 border border-slate-700 rounded-2xl flex items-center justify-center mb-6 shadow-lg shadow-black/50">
                <Key className="w-6 h-6 text-indigo-400" />
              </div>
              <h3 className="text-2xl font-bold text-white tracking-tight mb-3">Bring Your Own Keys (BYOK)</h3>
              <p className="text-slate-400 leading-relaxed font-medium">Plug in your own Gemini LLM and Google OAuth keys. Complete sovereignty over your API usage, token limits, and AI ecosystem.</p>
            </div>

            <div className="group bg-slate-950 p-8 rounded-3xl border border-slate-800 hover:border-purple-500/50 transition-colors relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-purple-500/10 rounded-bl-full -z-10 group-hover:bg-purple-500/20 transition-colors"></div>
              <div className="w-14 h-14 bg-slate-900 border border-slate-700 rounded-2xl flex items-center justify-center mb-6 shadow-lg shadow-black/50">
                <Lock className="w-6 h-6 text-purple-400" />
              </div>
              <h3 className="text-2xl font-bold text-white tracking-tight mb-3">Zero-Trust Architecture</h3>
              <p className="text-slate-400 leading-relaxed font-medium">We don't store your emails. Content is fetched dynamically via Google's official API and wiped from RAM immediately after processing.</p>
            </div>

            <div className="group bg-slate-950 p-8 rounded-3xl border border-slate-800 hover:border-pink-500/50 transition-colors relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-pink-500/10 rounded-bl-full -z-10 group-hover:bg-pink-500/20 transition-colors"></div>
              <div className="w-14 h-14 bg-slate-900 border border-slate-700 rounded-2xl flex items-center justify-center mb-6 shadow-lg shadow-black/50">
                <Server className="w-6 h-6 text-pink-400" />
              </div>
              <h3 className="text-2xl font-bold text-white tracking-tight mb-3">Supabase Edge Memory</h3>
              <p className="text-slate-400 leading-relaxed font-medium">Our optimized PostgreSQL schema summarizes conversations on the fly, drastically reducing context window bloat and API costs.</p>
            </div>

          </div>
        </div>
      </section>
    </div>
  );
};

export default Landing;