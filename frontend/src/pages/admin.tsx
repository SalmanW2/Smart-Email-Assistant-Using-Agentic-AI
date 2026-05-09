import React, { useState, useEffect } from 'react';
import { Users, Activity, ShieldAlert, BarChart } from 'lucide-react';
import { adminService } from '../services/api';

const Admin = () => {
  const [stats, setStats] = useState({ total_users: 0, total_ai_interactions: 0 });
  const [users, setUsers] = useState([]);
  const adminEmail = "muhammadsalmansarwarwattoo@gmail.com"; // Your Super Admin email

  useEffect(() => {
    const fetchAdminData = async () => {
      try {
        const statsRes = await adminService.getStats(adminEmail);
        const usersRes = await adminService.getUsers(adminEmail);
        setStats(statsRes.data);
        setUsers(usersRes.data);
      } catch (error) {
        console.error("Admin Auth Error", error);
      }
    };
    fetchAdminData();
  }, []);

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Admin Control Panel</h1>
          <p className="text-gray-500 mt-1">System Overview & Monitoring</p>
        </div>
        <span className="px-4 py-2 bg-red-100 text-red-800 rounded-full text-sm font-medium flex items-center">
          <ShieldAlert className="w-4 h-4 mr-2" /> Super Admin Active
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex items-center space-x-4">
          <div className="p-4 bg-blue-50 text-blue-600 rounded-full"><Users className="w-8 h-8" /></div>
          <div>
            <p className="text-sm font-medium text-gray-500">Total Users</p>
            <p className="text-2xl font-bold text-gray-900">{stats.total_users || 0}</p>
          </div>
        </div>
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex items-center space-x-4">
          <div className="p-4 bg-purple-50 text-purple-600 rounded-full"><Activity className="w-8 h-8" /></div>
          <div>
            <p className="text-sm font-medium text-gray-500">AI Interactions</p>
            <p className="text-2xl font-bold text-gray-900">{stats.total_ai_interactions || 0}</p>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden mt-8">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-medium leading-6 text-gray-900">Registered Users</h3>
        </div>
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Telegram ID</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">AI Mode</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {users.length === 0 ? (
              <tr><td colSpan={4} className="px-6 py-4 text-center text-gray-500">No users found.</td></tr>
            ) : (
              users.map((user: any, i) => (
                <tr key={i}>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{user.telegram_id}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{user.first_name}</td>
                  <td className="px-6 py-4 whitespace-nowrap"><span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${user.is_verified ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}`}>{user.is_verified ? 'Verified' : 'Pending'}</span></td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{user.ai_mode_enabled ? 'ON' : 'OFF'}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default Admin;
