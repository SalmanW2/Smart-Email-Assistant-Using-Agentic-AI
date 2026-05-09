import { useState, useEffect } from 'react';

const Admin = () => {
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);

  useEffect(() => {
    loadStats();
    loadUsers();
  }, []);

  const loadStats = async () => {
    try {
      // const response = await api.getAdminStats();
      setStats({
        total_users: 150,
        total_emails_processed: 1250,
        active_sessions: 45
      });
    } catch (error) {
      console.error('Failed to load stats');
    }
  };

  const loadUsers = async () => {
    try {
      // const response = await api.getUsers();
      setUsers([
        { id: 1, username: 'john_doe', first_name: 'John', role: 'user', ai_mode: true },
        { id: 2, username: 'jane_smith', first_name: 'Jane', role: 'admin', ai_mode: false }
      ]);
    } catch (error) {
      console.error('Failed to load users');
    }
  };

  const toggleBlock = async (userId: number, blocked: boolean) => {
    try {
      if (blocked) {
        // await api.unblockUser(userId);
      } else {
        // await api.blockUser(userId);
      }
      loadUsers();
    } catch (error) {
      console.error('Failed to toggle block');
    }
  };

  if (!stats) return <div>Loading...</div>;

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center">
              <h1 className="text-xl font-semibold">Admin Dashboard</h1>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="px-4 py-6 sm:px-0">
          <h2 className="text-2xl font-bold mb-6">System Statistics</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div className="bg-white overflow-hidden shadow rounded-lg">
              <div className="p-5">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">Total Users</dt>
                  <dd className="text-3xl font-semibold text-gray-900">{stats.total_users}</dd>
                </dl>
              </div>
            </div>
            <div className="bg-white overflow-hidden shadow rounded-lg">
              <div className="p-5">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">Emails Processed</dt>
                  <dd className="text-3xl font-semibold text-gray-900">{stats.total_emails_processed}</dd>
                </dl>
              </div>
            </div>
            <div className="bg-white overflow-hidden shadow rounded-lg">
              <div className="p-5">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">Active Sessions</dt>
                  <dd className="text-3xl font-semibold text-gray-900">{stats.active_sessions}</dd>
                </dl>
              </div>
            </div>
          </div>

          <h2 className="text-2xl font-bold mb-4">User Management</h2>
          <div className="bg-white shadow overflow-hidden sm:rounded-md">
            <ul className="divide-y divide-gray-200">
              {users.map((user) => (
                <li key={user.id} className="px-6 py-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-gray-900">{user.first_name} ({user.username})</p>
                      <p className="text-sm text-gray-500">Role: {user.role} | AI Mode: {user.ai_mode ? 'ON' : 'OFF'}</p>
                    </div>
                    <button
                      onClick={() => toggleBlock(user.id, false)} // Simplified
                      className="bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded text-sm"
                    >
                      Block
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </main>
    </div>
  );
};

export default Admin;