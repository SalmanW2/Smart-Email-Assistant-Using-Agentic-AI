import React, { useState, useEffect } from 'react';
import { Settings, BrainCircuit, Mic, Save, ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';
import { userService } from '../services/api';

const Dashboard = () => {
  const [aiEnabled, setAiEnabled] = useState(true);
  const [voicePref, setVoicePref] = useState('text');
  // For testing, hardcode an ID. In production, get this from context/URL.
  const TEST_TELEGRAM_ID = 123456789; 

  const handleSave = async () => {
    try {
      await userService.updatePreferences({
        telegram_id: TEST_TELEGRAM_ID,
        ai_mode_enabled: aiEnabled,
        voice_preference: voicePref
      });
      alert('Preferences saved successfully!');
    } catch (error) {
      console.error(error);
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="flex items-center space-x-4 mb-8">
        <Link to="/login" className="p-2 bg-white rounded-full shadow hover:bg-gray-50"><ArrowLeft className="w-5 h-5 text-gray-600" /></Link>
        <h1 className="text-3xl font-bold text-gray-900">User Dashboard</h1>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-6">
        <div className="flex items-center justify-between border-b pb-6">
          <div className="flex items-center space-x-4">
            <div className={`p-3 rounded-lg ${aiEnabled ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-500'}`}>
              <BrainCircuit className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-lg font-medium text-gray-900">Agentic AI Mode</h3>
              <p className="text-sm text-gray-500">Enable natural language processing for emails.</p>
            </div>
          </div>
          <label className="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" className="sr-only peer" checked={aiEnabled} onChange={() => setAiEnabled(!aiEnabled)} />
            <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-500"></div>
          </label>
        </div>

        <div className="flex flex-col space-y-4 border-b pb-6">
          <div className="flex items-center space-x-4">
            <div className="p-3 bg-blue-100 text-blue-600 rounded-lg">
              <Mic className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-lg font-medium text-gray-900">Voice Output Preference</h3>
              <p className="text-sm text-gray-500">How should the bot respond to summaries?</p>
            </div>
          </div>
          <select 
            value={voicePref} 
            onChange={(e) => setVoicePref(e.target.value)}
            className="mt-2 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md"
          >
            <option value="text">Text Only</option>
            <option value="voice">Voice Notes</option>
            <option value="both">Text & Voice</option>
          </select>
        </div>

        <button onClick={handleSave} className="w-full flex justify-center items-center py-3 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 transition-colors">
          <Save className="w-5 h-5 mr-2" />
          Save Preferences
        </button>
      </div>
    </div>
  );
};

export default Dashboard;