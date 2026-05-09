import React, { useState } from 'react';
import { Mail, ShieldCheck } from 'lucide-react';
import { authService } from '../services/api';

const Login = () => {
  const [telegramId, setTelegramId] = useState('');

  const handleLogin = () => {
    if (!telegramId) return alert("Please enter your Telegram ID for testing.");
    authService.login(Number(telegramId));
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-md w-full bg-white rounded-xl shadow-lg p-8 space-y-6">
        <div className="text-center">
          <div className="bg-blue-100 w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4">
            <Mail className="h-8 w-8 text-blue-600" />
          </div>
          <h2 className="text-2xl font-bold text-gray-900">Smart Email Assistant</h2>
          <p className="text-gray-500 mt-2">Sign in to connect your Agentic AI</p>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">Telegram ID (For Testing)</label>
            <input 
              type="number" 
              value={telegramId}
              onChange={(e) => setTelegramId(e.target.value)}
              className="mt-1 block w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"
              placeholder="e.g. 123456789"
            />
          </div>
          <button
            onClick={handleLogin}
            className="w-full flex justify-center items-center py-2.5 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors"
          >
            <ShieldCheck className="w-5 h-5 mr-2" />
            Connect with Google
          </button>
        </div>
      </div>
    </div>
  );
};

export default Login;