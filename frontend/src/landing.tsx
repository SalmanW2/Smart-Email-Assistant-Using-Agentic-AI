import { Mail, Bot, Shield, Zap, BookOpen, Settings, Globe, Lock } from 'lucide-react';
import { Link } from 'react-router-dom';

const Landing = () => {
  return (
    <div className="min-h-screen bg-white">
      <nav className="bg-white/90 backdrop-blur-md sticky top-0 z-50 border-b border-slate-100">
        <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="bg-indigo-600 p-2 rounded-xl">
              <Mail className="w-6 h-6 text-white" />
            </div>
            <span className="font-extrabold text-2xl tracking-tighter text-slate-900">EmailAgent.ai</span>
          </div>
          <div className="flex items-center gap-6">
            <Link to="/help" className="text-sm font-bold text-slate-500 hover:text-indigo-600 transition-colors">Documentation</Link>
            <Link to="/admin/login" className="bg-slate-900 text-white px-5 py-2.5 rounded-full text-sm font-bold hover:bg-slate-800 transition-all">Admin Access</Link>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-6 pt-24 pb-32 text-center">
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-indigo-50 text-indigo-700 text-xs font-black uppercase tracking-widest mb-8 border border-indigo-100">
          <Zap className="w-4 h-4 fill-current" /> Next-Gen Agentic Workflow
        </div>
        
        <h1 className="text-6xl md:text-8xl font-black tracking-tighter mb-10 leading-[0.9] text-slate-950">
          Master your inbox <br/>
          <span className="text-indigo-600">with Intelligence.</span>
        </h1>
        
        <p className="max-w-2xl mx-auto text-xl text-slate-500 mb-12 font-medium leading-relaxed">
          The ultimate AI companion for Gmail. Automate drafts, generate instant summaries, and manage professional communications through a secure Telegram interface.
        </p>
        
        <div className="flex flex-col sm:flex-row items-center justify-center gap-6">
          <a href="http://t.me/Smart_Emailbot" target="_blank" rel="noreferrer" className="flex items-center justify-center gap-3 bg-indigo-600 text-white px-10 py-5 rounded-2xl font-black text-xl hover:bg-indigo-700 hover:-translate-y-1 shadow-2xl shadow-indigo-200 transition-all w-full sm:w-auto">
            <Bot className="w-6 h-6" /> Deploy Bot Now
          </a>
        </div>

        <div className="grid md:grid-cols-3 gap-12 mt-32 text-left">
          <div className="space-y-4">
            <div className="w-12 h-12 bg-slate-100 rounded-xl flex items-center justify-center"><Globe className="w-6 h-6 text-slate-900"/></div>
            <h3 className="text-xl font-bold text-slate-900 tracking-tight">Global Connectivity</h3>
            <p className="text-slate-500 leading-relaxed font-medium">Access your entire Gmail history and draft responses from any device via Telegram's secure cloud.</p>
          </div>
          <div className="space-y-4">
            <div className="w-12 h-12 bg-slate-100 rounded-xl flex items-center justify-center"><Lock className="w-6 h-6 text-slate-900"/></div>
            <h3 className="text-xl font-bold text-slate-900 tracking-tight">Enterprise Security</h3>
            <p className="text-slate-500 leading-relaxed font-medium">Zero-trust architecture with official Google API integration. Your data is never used for training.</p>
          </div>
          <div className="space-y-4">
            <div className="w-12 h-12 bg-slate-100 rounded-xl flex items-center justify-center"><Shield className="w-6 h-6 text-slate-900"/></div>
            <h3 className="text-xl font-bold text-slate-900 tracking-tight">Role-Based Access</h3>
            <p className="text-slate-500 leading-relaxed font-medium">Granular control for administrators to manage user access, verification, and system health.</p>
          </div>
        </div>
      </main>
    </div>
  );
};

export default Landing;