import React from 'react';
import { HelpCircle, BookOpen, MessageSquare } from 'lucide-react';
import { Link } from 'react-router-dom';

const Help = () => {
  return (
    <div className="max-w-3xl mx-auto p-6 space-y-8">
      <div className="text-center mt-10">
        <HelpCircle className="w-16 h-16 text-blue-600 mx-auto mb-4" />
        <h1 className="text-3xl font-bold text-gray-900">How can we help?</h1>
        <p className="text-gray-500 mt-2">Guides and documentation for your Agentic AI Assistant</p>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-4">
        <h2 className="text-xl font-bold text-gray-900 flex items-center"><BookOpen className="w-5 h-5 mr-2 text-blue-500"/> Getting Started</h2>
        <ul className="list-disc pl-5 space-y-2 text-gray-600">
          <li><strong>Login:</strong> Type <code>/login</code> in Telegram to authorize your Gmail account securely.</li>
          <li><strong>Natural Language:</strong> Just type naturally! Try: <em>"Send an email to my boss about the meeting."</em></li>
          <li><strong>Memory:</strong> The bot remembers who you talk to. You don't need to type their email address every time.</li>
        </ul>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-4">
        <h2 className="text-xl font-bold text-gray-900 flex items-center"><MessageSquare className="w-5 h-5 mr-2 text-green-500"/> Advanced Commands</h2>
        <ul className="list-disc pl-5 space-y-2 text-gray-600">
          <li><strong>Voice Summaries:</strong> Send a voice note asking for your unread emails, and the bot will reply with a voice summary!</li>
          <li><strong>Settings:</strong> Type <code>/settings</code> or click the Settings button to access your dashboard.</li>
          <li><strong>Undo Send:</strong> You have a 4-second window to cancel an email after you confirm it.</li>
        </ul>
      </div>

      <div className="text-center pt-8">
        <Link to="/dashboard" className="text-blue-600 hover:text-blue-800 font-medium">← Back to Dashboard</Link>
      </div>
    </div>
  );
};

export default Help;