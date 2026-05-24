import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import Navbar from '../components/Navbar';
import { 
  Bot, Shield, Zap, Mail, MessageSquare, 
  ChevronRight, Phone, Send, Lock, CheckCircle2 
} from 'lucide-react';

const backendUrl = import.meta.env.VITE_BACKEND_URL || 'https://smart-email-assistant-using-agentic-ai.onrender.com';

const About = () => {
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitStatus, setSubmitStatus] = useState<{type: 'success'|'error', text: string} | null>(null);

  useEffect(() => {
    if (location.hash) {
      const element = document.getElementById(location.hash.substring(1));
      if (element) {
        setTimeout(() => {
          element.scrollIntoView({ behavior: 'smooth' });
        }, 100);
      }
    } else {
      window.scrollTo(0, 0);
    }
  }, [location]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setSubmitStatus(null);

    try {
      const res = await fetch(`${backendUrl}/api/user/public/contact`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, message }),
      });

      if (res.ok) {
        setSubmitStatus({type: 'success', text: 'Message sent successfully! We will get back to you soon.'});
        setEmail('');
        setMessage('');
      } else {
        setSubmitStatus({type: 'error', text: 'Failed to send message. Please try again later.'});
      }
    } catch {
      setSubmitStatus({type: 'error', text: 'Network error. Please check your connection and try again.'});
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-50 via-white to-blue-50 dark:from-slate-950 dark:via-slate-900 dark:to-indigo-950/20 font-sans transition-colors duration-500">
      <Navbar />
      
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-12 space-y-24">
        
        {/* HERO / ABOUT SECTION */}
        <section id="about" className="text-center space-y-6 pt-10 animate-in fade-in slide-in-from-bottom-8 duration-700 scroll-mt-24">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 font-bold text-sm border border-blue-100 dark:border-blue-500/20 mb-4 shadow-sm">
            <Bot className="w-4 h-4" /> Powered by Agentic AI
          </div>
          <h1 className="text-4xl sm:text-6xl font-black text-slate-900 dark:text-white tracking-tight leading-tight">
            Your Smart <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-indigo-600">Email Assistant</span>
          </h1>
          <p className="max-w-2xl mx-auto text-lg text-slate-600 dark:text-slate-400 font-medium">
            Seamlessly manage your professional communications. Draft, schedule, and analyze emails using natural language voice notes or text commands directly from Telegram.
          </p>
          <div className="flex flex-col sm:flex-row justify-center items-center gap-4 pt-6">
            <Link to="/admin/login" className="flex items-center justify-center gap-2 w-full sm:w-auto bg-blue-600 text-white px-8 py-4 rounded-2xl font-bold hover:bg-blue-700 transition-all shadow-lg hover:shadow-blue-500/30">
              Go to Admin Portal <ChevronRight className="w-5 h-5" />
            </Link>
            <a href="#how-it-works" className="flex items-center justify-center gap-2 w-full sm:w-auto bg-white dark:bg-slate-900 text-slate-700 dark:text-white px-8 py-4 rounded-2xl font-bold hover:bg-slate-50 dark:hover:bg-slate-800 transition-all shadow-sm border border-slate-200 dark:border-slate-800">
              Learn More
            </a>
          </div>
        </section>

        {/* HOW IT WORKS */}
        <section id="how-it-works" className="scroll-mt-24">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-black text-slate-900 dark:text-white">How It Works</h2>
            <p className="text-slate-500 dark:text-slate-400 mt-2 font-medium">Three simple steps to automate your workflow.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {[
              { icon: MessageSquare, title: "1. Connect Bot", desc: "Link your Telegram account to our secure system and authorize Gmail access." },
              { icon: Zap, title: "2. Send Commands", desc: "Use voice notes or text to instruct the AI to draft an email on your behalf." },
              { icon: Mail, title: "3. Auto-Dispatch", desc: "The AI structures, schedules, and dispatches the email automatically." }
            ].map((item, i) => (
              <div key={i} className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-md p-8 rounded-3xl border border-slate-200/50 dark:border-slate-800/50 shadow-sm hover:shadow-xl transition-all text-center group">
                <div className="w-16 h-16 mx-auto bg-blue-50 dark:bg-blue-500/10 rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 group-hover:rotate-3 transition-transform duration-300 shadow-inner">
                  <item.icon className="w-8 h-8 text-blue-600 dark:text-blue-400" />
                </div>
                <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-2">{item.title}</h3>
                <p className="text-slate-600 dark:text-slate-400 text-sm font-medium">{item.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* SECURITY & PRIVACY */}
        <section id="security" className="bg-slate-900 dark:bg-slate-950 text-white rounded-[3rem] p-8 sm:p-12 shadow-2xl relative overflow-hidden scroll-mt-24">
          <div className="absolute top-0 right-0 w-64 h-64 bg-blue-500 rounded-full mix-blend-screen filter blur-[100px] opacity-30 animate-pulse"></div>
          <div className="absolute bottom-0 left-0 w-64 h-64 bg-indigo-500 rounded-full mix-blend-screen filter blur-[100px] opacity-30 animate-pulse delay-1000"></div>
          
          <div className="relative z-10 flex flex-col md:flex-row items-center gap-12">
            <div className="flex-1 space-y-6">
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/10 font-bold text-sm backdrop-blur-md border border-white/20">
                <Shield className="w-4 h-4 text-emerald-400" /> Enterprise Grade
              </div>
              <h2 className="text-3xl sm:text-4xl font-black leading-tight">Your Data is Encrypted & Secure.</h2>
              <p className="text-slate-300 text-lg font-medium leading-relaxed">
                We utilize JSON Web Tokens (JWT) for authentication and Supabase Row Level Security (RLS) to ensure your data never falls into the wrong hands. Your credentials and conversations are fully isolated.
              </p>
              <ul className="space-y-4 pt-2">
                <li className="flex items-center gap-3 text-slate-200 font-bold"><CheckCircle2 className="w-6 h-6 text-emerald-400" /> End-to-end credential encryption</li>
                <li className="flex items-center gap-3 text-slate-200 font-bold"><CheckCircle2 className="w-6 h-6 text-emerald-400" /> Granular Admin access controls</li>
                <li className="flex items-center gap-3 text-slate-200 font-bold"><CheckCircle2 className="w-6 h-6 text-emerald-400" /> No unauthorized data sharing</li>
              </ul>
            </div>
            <div className="w-full md:w-1/3 flex justify-center drop-shadow-2xl">
              <Lock className="w-40 h-40 text-slate-700 dark:text-slate-800" />
            </div>
          </div>
        </section>

        {/* HELP & GUIDES (FAQ) */}
        <section id="help" className="scroll-mt-24">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-black text-slate-900 dark:text-white">Help & Guides</h2>
            <p className="text-slate-500 dark:text-slate-400 mt-2 font-medium">Frequently asked questions and troubleshooting.</p>
          </div>
          <div className="max-w-3xl mx-auto space-y-4">
            {[
              { q: "How do I connect my Gmail account?", a: "Start the bot on Telegram with /start. It will show a secure Google OAuth link for authorization." },
              { q: "What is 'Agentic AI'?", a: "Unlike standard chatbots, Agentic AI doesn't just talk; it acts. It can read your command, structure a professional email, identify the recipient, and dispatch it automatically." },
              { q: "Why are my voice notes failing?", a: "Ensure the administrator has not restricted your voice privileges. Also, make sure your voice note is clear and under the maximum duration limit." },
              { q: "What happens if I get blocked?", a: "If an admin blocks your account, the bot will stop responding to your commands immediately. You will need to contact support or your system admin to lift the restriction." }
            ].map((faq, i) => (
              <div key={i} className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-md p-6 rounded-3xl border border-slate-200/50 dark:border-slate-800/50 hover:shadow-md transition-shadow">
                <h4 className="font-bold text-lg text-slate-900 dark:text-white mb-2 flex items-start gap-2">
                  <span className="text-blue-500 mt-1">Q.</span> {faq.q}
                </h4>
                <p className="text-slate-600 dark:text-slate-400 font-medium leading-relaxed pl-6">{faq.a}</p>
              </div>
            ))}
          </div>
        </section>

        {/* CONTACT US */}
        <section id="contact" className="max-w-4xl mx-auto text-center scroll-mt-24 pb-12">
          <div className="bg-blue-50/50 dark:bg-blue-900/10 p-8 sm:p-12 rounded-[3rem] border border-blue-100 dark:border-blue-800/30 shadow-inner">
            <div className="w-20 h-20 mx-auto bg-gradient-to-br from-blue-600 to-indigo-600 text-white rounded-3xl flex items-center justify-center mb-6 shadow-xl shadow-blue-500/30 transform rotate-3 hover:rotate-0 transition-transform">
              <Phone className="w-8 h-8" />
            </div>
            <h2 className="text-3xl font-black text-slate-900 dark:text-white mb-4">Need More Help?</h2>
            <p className="text-slate-600 dark:text-slate-400 mb-10 max-w-xl mx-auto font-medium">
              Our support team is available to assist you with any technical issues, onboarding process, or custom feature requests.
            </p>
            
            {submitStatus && (
              <div className={`max-w-md mx-auto mb-6 p-4 rounded-2xl font-bold text-sm flex items-center gap-2 ${submitStatus.type === 'success' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400' : 'bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400'}`}>
                {submitStatus.type === 'success' ? <CheckCircle2 className="w-5 h-5" /> : <Send className="w-5 h-5" />}
                {submitStatus.text}
              </div>
            )}
            
            <form className="max-w-md mx-auto space-y-4 text-left" onSubmit={handleSubmit}>
              <input 
                type="email" 
                placeholder="Your Email Address" 
                required 
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full p-4 bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-2xl outline-none focus:ring-2 focus:ring-blue-500 transition-all dark:text-white font-medium shadow-sm" 
              />
              <textarea 
                placeholder="How can we help you?" 
                required 
                rows={4}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                className="w-full p-4 bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-2xl outline-none focus:ring-2 focus:ring-blue-500 transition-all dark:text-white font-medium shadow-sm resize-none"
              ></textarea>
              <button 
                type="submit" 
                disabled={submitting}
                className="w-full bg-slate-900 dark:bg-blue-600 text-white py-4 rounded-2xl font-black uppercase tracking-widest text-sm hover:bg-slate-800 dark:hover:bg-blue-700 transition-all flex items-center justify-center gap-2 shadow-lg mt-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Send className="w-4 h-4" /> {submitting ? 'Sending...' : 'Send Message'}
              </button>
            </form>
          </div>
        </section>

      </div>
    </div>
  );
};

export default About;