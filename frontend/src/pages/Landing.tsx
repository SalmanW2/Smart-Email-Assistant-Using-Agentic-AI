import { Link } from 'react-router-dom';

const Landing = () => {
  return (
    <html>
      <head>
        <title>Smart Email Assistant | Agentic AI</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>📧</text></svg>" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap" rel="stylesheet" />
        <style>
          {`
            body { font-family: 'Inter', sans-serif; scroll-behavior: smooth; }
            .bg-grid { background-size: 40px 40px; background-image: linear-gradient(to right, rgba(0, 0, 0, 0.04) 1px, transparent 1px), linear-gradient(to bottom, rgba(0, 0, 0, 0.04) 1px, transparent 1px); }
          `}
        </style>
      </head>
      <body className="bg-slate-50 text-slate-900 bg-grid relative overflow-x-hidden">
        <nav className="p-6 flex justify-between items-center max-w-7xl mx-auto">
          <div className="text-xl md:text-2xl font-extrabold text-blue-600 flex items-center gap-2 tracking-tight">
            <span>📧</span>
            <span>Smart Email Assistant <span className="font-light text-slate-400 hidden md:inline ml-1">| Powered by Agentic AI</span></span>
          </div>
          <Link to="/admin/login" className="text-slate-600 hover:text-blue-600 font-semibold transition-colors bg-white px-5 py-2 rounded-full shadow-sm border border-slate-200 text-sm md:text-base">Admin Login</Link>
        </nav>

        <main className="flex flex-col items-center justify-center min-h-[75vh] text-center px-4 mt-4">
          <div className="inline-block bg-blue-100 text-blue-800 font-bold px-4 py-2 rounded-full mb-6 text-sm shadow-sm border border-blue-200">
            ✨ The Future of Email Management
          </div>
          <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight mb-6 leading-tight text-slate-900">
            Your Inbox, Mastered by <br className="hidden md:block" /><span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-purple-600">Agentic AI</span>
          </h1>
          <p className="text-xl text-slate-600 mb-10 max-w-2xl leading-relaxed">
            Stop drowning in emails. Get instant summaries, draft context-aware replies, and command your professional communication—all through a simple Telegram chat.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 w-full sm:w-auto z-10">
            <a href="https://t.me/Private_Mail_Assistent_Bot" target="_blank" className="bg-blue-600 text-white px-10 py-4 rounded-2xl shadow-xl hover:bg-blue-700 hover:-translate-y-1 transition-all font-bold text-lg w-full sm:w-auto flex justify-center items-center gap-2">
              Start on Telegram 🚀
            </a>
            <a href="#features" className="bg-white border border-slate-200 px-10 py-4 rounded-2xl shadow-sm hover:bg-slate-50 hover:-translate-y-1 transition-all font-bold text-lg text-slate-700 w-full sm:w-auto flex justify-center items-center">
              See How It Works
            </a>
          </div>

          <div className="mt-12 flex flex-col md:flex-row items-center justify-center gap-3 text-sm text-slate-500 bg-white px-6 py-3 rounded-full border border-slate-200 shadow-sm">
            <div className="flex items-center gap-2">
              <svg className="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8V7a4 4 0 00-8 0v4h8z"></path></svg>
              <b>Bank-Level Security:</b>
            </div>
            <span>Secured by Official Google OAuth. We never store your passwords or emails.</span>
          </div>
        </main>

        <section id="features" className="py-24 bg-white border-t border-slate-200 relative">
          <div className="max-w-7xl mx-auto px-6">
            <div className="text-center mb-20">
              <h2 className="text-4xl font-extrabold text-slate-900">Why Use Smart Email Assistant?</h2>
              <p className="text-slate-500 mt-4 text-xl">Experience an inbox that practically manages itself.</p>
            </div>

            <div className="grid md:grid-cols-3 gap-8">
              <div className="p-10 bg-gradient-to-br from-slate-50 to-white rounded-3xl border border-slate-100 shadow-lg hover:shadow-xl transition-all hover:-translate-y-2">
                <div className="w-16 h-16 bg-blue-100 text-blue-600 rounded-2xl flex items-center justify-center text-3xl mb-6 shadow-inner">📝</div>
                <h3 className="text-2xl font-bold text-slate-800 mb-4">Instant Summaries</h3>
                <p className="text-slate-600 leading-relaxed">Skip the 20-message threads. Our Agentic AI reads the context and gives you the exact action points in bullet format.</p>
              </div>
              <div className="p-10 bg-gradient-to-br from-slate-50 to-white rounded-3xl border border-slate-100 shadow-lg hover:shadow-xl transition-all hover:-translate-y-2">
                <div className="w-16 h-16 bg-purple-100 text-purple-600 rounded-2xl flex items-center justify-center text-3xl mb-6 shadow-inner">✍️</div>
                <h3 className="text-2xl font-bold text-slate-800 mb-4">Smart Drafting</h3>
                <p className="text-slate-600 leading-relaxed">Tell the bot "Tell John I'll finish the report by Friday." The AI will instantly generate a highly professional email ready to send.</p>
              </div>
              <div className="p-10 bg-gradient-to-br from-slate-50 to-white rounded-3xl border border-slate-100 shadow-lg hover:shadow-xl transition-all hover:-translate-y-2">
                <div className="w-16 h-16 bg-green-100 text-green-600 rounded-2xl flex items-center justify-center text-3xl mb-6 shadow-inner">🔒</div>
                <h3 className="text-2xl font-bold text-slate-800 mb-4">Absolute Privacy</h3>
                <p className="text-slate-600 leading-relaxed">Your data remains yours. We use strict Google API standards to ensure your inbox remains completely encrypted and isolated.</p>
              </div>
            </div>
          </div>
        </section>

        <footer className="bg-slate-900 text-white py-16 text-center">
          <h2 className="text-3xl font-bold mb-6">Ready to regain your time?</h2>
          <a href="https://t.me/Private_Mail_Assistent_Bot" target="_blank" className="inline-block bg-blue-600 hover:bg-blue-500 text-white px-10 py-4 rounded-full font-bold transition-all shadow-lg hover:shadow-xl hover:-translate-y-1">
            Link Your Inbox Now
          </a>
        </footer>
      </body>
    </html>
  );
};

export default Landing;