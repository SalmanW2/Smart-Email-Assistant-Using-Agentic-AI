import React from 'react'
import Head from 'next/head'
import Link from 'next/link'

const FAVICON_SVG = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">📧</text></svg>'

export default function LandingPage() {
  return (
    <>
      <Head>
        <title>Smart Email Assistant | Agentic AI</title>
        <meta name="description" content="AI-powered email management via Telegram" />
        <link rel="icon" href={`data:image/svg+xml,${FAVICON_SVG}`} />
      </Head>

      <main className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100">
        {/* Navbar */}
        <nav className="flex justify-between items-center max-w-7xl mx-auto px-4 py-6">
          <div className="text-2xl font-bold text-blue-600 flex items-center gap-2">
            <span>📧</span>
            <span>Smart Email Assistant</span>
          </div>
          <Link
            href="/admin/login"
            className="px-6 py-2 bg-white border border-slate-200 rounded-full text-slate-700 font-semibold hover:bg-slate-50 shadow-sm transition"
          >
            Admin Login
          </Link>
        </nav>

        {/* Hero */}
        <section className="flex flex-col items-center justify-center min-h-[75vh] px-4 text-center">
          <div className="inline-block bg-blue-100 text-blue-800 font-bold px-4 py-2 rounded-full mb-6 text-sm border border-blue-200">
            ✨ The Future of Email Management
          </div>

          <h1 className="text-7xl font-extrabold mb-6 text-slate-900">
            Your Inbox, Mastered by{' '}
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-purple-600">
              Agentic AI
            </span>
          </h1>

          <p className="text-xl text-slate-600 mb-10 max-w-2xl">
            Stop drowning in emails. Get instant summaries, draft context-aware replies, and command your professional communication—all through a simple Telegram chat.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 mb-12">
            <a
              href="https://t.me/Private_Mail_Assistent_Bot"
              target="_blank"
              rel="noopener noreferrer"
              className="px-10 py-4 bg-blue-600 text-white rounded-2xl shadow-lg hover:bg-blue-700 font-bold text-lg transition hover:-translate-y-1"
            >
              Start on Telegram 🚀
            </a>
            <a
              href="#features"
              className="px-10 py-4 bg-white border border-slate-200 rounded-2xl shadow-sm hover:bg-slate-50 font-bold text-lg text-slate-700 transition hover:-translate-y-1"
            >
              See How It Works
            </a>
          </div>

          <div className="flex items-center justify-center gap-3 text-sm text-slate-500 bg-white px-6 py-3 rounded-full border border-slate-200 shadow-sm">
            <span>🔒 Bank-Level Security:</span>
            <span>Secured by Official Google OAuth. We never store your passwords.</span>
          </div>
        </section>

        {/* Features */}
        <section id="features" className="py-24 bg-white border-t border-slate-200">
          <div className="max-w-7xl mx-auto px-4">
            <div className="text-center mb-20">
              <h2 className="text-4xl font-extrabold text-slate-900 mb-4">
                Why Use Smart Email Assistant?
              </h2>
              <p className="text-slate-500 text-xl">
                Experience an inbox that practically manages itself.
              </p>
            </div>

            <div className="grid md:grid-cols-3 gap-8">
              {[
                {
                  icon: '📝',
                  title: 'Instant Summaries',
                  desc: 'Skip the 20-message threads. Our AI reads the context and gives you action points.',
                },
                {
                  icon: '✍️',
                  title: 'Smart Drafting',
                  desc: 'Tell the bot what to send. The AI generates a professional email instantly.',
                },
                {
                  icon: '🔒',
                  title: 'Absolute Privacy',
                  desc: 'Your data stays yours. We use strict Google API standards for encryption.',
                },
              ].map((feature, i) => (
                <div
                  key={i}
                  className="p-10 bg-gradient-to-br from-slate-50 to-white rounded-3xl border border-slate-100 shadow-lg hover:shadow-xl transition hover:-translate-y-2"
                >
                  <div className="text-5xl mb-4">{feature.icon}</div>
                  <h3 className="text-2xl font-bold text-slate-800 mb-2">
                    {feature.title}
                  </h3>
                  <p className="text-slate-600">{feature.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Footer */}
        <footer className="bg-slate-900 text-white py-16 text-center">
          <h2 className="text-3xl font-bold mb-6">Ready to regain your time?</h2>
          <a
            href="https://t.me/Private_Mail_Assistent_Bot"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block px-10 py-4 bg-blue-600 hover:bg-blue-500 rounded-full font-bold transition shadow-lg hover:-translate-y-1"
          >
            Link Your Inbox Now
          </a>
        </footer>
      </main>
    </>
  )
}