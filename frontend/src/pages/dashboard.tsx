import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Navbar from '../components/Navbar';
import { Users, ShieldAlert, CheckCircle, Activity, Shield, Ban, Search, UserPlus, Trash2 } from 'lucide-react';

interface User {
  telegram_id: number;
  first_name: string;
  username: string;
  email: string;
  is_verified: boolean;
  created_at: string;
}

interface Admin {
  id: string;
  email: string;
  role: string;
}

interface Block {
  id: string;
  block_type: string;
  block_value: string;
  reason: string;
}

interface Stats {
  total_users: number;
  verified_users: number;
  blocked_users: number;
  total_admins: number;
}

const Dashboard = () => {
  const [activeTab, setActiveTab] = useState('stats');
  const [users, setUsers] = useState<User[]>([]);
  const [admins, setAdmins] = useState<Admin[]>([]);
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [role, setRole] = useState<string>('');
  const navigate = useNavigate();
  
  const adminEmail = localStorage.getItem('admin_email');

  useEffect(() => {
    if (!adminEmail) {
      navigate('/admin/login');
      return;
    }
    fetchRole();
    fetchData();
  }, [adminEmail, navigate]);

  const getHeaders = () => ({
    'Content-Type': 'application/json',
    'x-admin-email': adminEmail || ''
  });

  const fetchRole = async () => {
    try {
      const response = await fetch(`${import.meta.env.VITE_BACKEND_URL}/api/admin/role`, {
        headers: getHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setRole(data.role);
      } else {
        navigate('/admin/login');
      }
    } catch (err) {
      console.error('Failed to fetch role:', err);
      navigate('/admin/login');
    }
  };

  const fetchData = async () => {
    try {
      const [usersRes, adminsRes, blocksRes, statsRes] = await Promise.all([
        fetch(`${import.meta.env.VITE_BACKEND_URL}/api/admin/users`, { headers: getHeaders() }),
        fetch(`${import.meta.env.VITE_BACKEND_URL}/api/admin/admins`, { headers: getHeaders() }),
        fetch(`${import.meta.env.VITE_BACKEND_URL}/api/admin/blocks`, { headers: getHeaders() }),
        fetch(`${import.meta.env.VITE_BACKEND_URL}/api/admin/stats`, { headers: getHeaders() }),
      ]);

      if (usersRes.ok) setUsers(await usersRes.json());
      if (adminsRes.ok) setAdmins(await adminsRes.json());
      if (blocksRes.ok) setBlocks(await blocksRes.json());
      if (statsRes.ok) setStats(await statsRes.json());
    } catch (err) {
      console.error('Failed to fetch dashboard data:', err);
    }
  };

  const filteredUsers = users.filter(
    (user) =>
      user.first_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      user.username?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      user.email?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const approveUser = async (tgId: number) => {
    try {
      await fetch(`${import.meta.env.VITE_BACKEND_URL}/api/admin/users/${tgId}/approve`, { 
        method: 'POST', 
        headers: getHeaders() 
      });
      fetchData();
    } catch (err) {
      console.error('Failed to approve user:', err);
    }
  };

  const blockUser = async (tgId: number, reason: string) => {
    try {
      await fetch(`${import.meta.env.VITE_BACKEND_URL}/api/admin/users/${tgId}/block?reason=${encodeURIComponent(reason)}`, { 
        method: 'POST', 
        headers: getHeaders() 
      });
      fetchData();
    } catch (err) {
      console.error('Failed to block user:', err);
    }
  };

  const removeBlock = async (id: string) => {
    try {
      await fetch(`${import.meta.env.VITE_BACKEND_URL}/api/admin/blocks/${id}`, { 
        method: 'DELETE', 
        headers: getHeaders() 
      });
      fetchData();
    } catch (err) {
      console.error('Failed to remove block:', err);
    }
  };

  const addAdmin = async (email: string) => {
    try {
      await fetch(`${import.meta.env.VITE_BACKEND_URL}/api/admin/admins`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ email, role: 'admin' }),
      });
      fetchData();
    } catch (err) {
      console.error('Failed to add admin:', err);
    }
  };

  const removeAdmin = async (id: string) => {
    try {
      await fetch(`${import.meta.env.VITE_BACKEND_URL}/api/admin/admins/${id}`, { 
        method: 'DELETE', 
        headers: getHeaders() 
      });
      fetchData();
    } catch (err) {
      console.error('Failed to remove admin:', err);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 font-sans pb-20">
      <Navbar />

      {/* Modern Tab Navigation */}
      <div className="bg-white border-b border-slate-200 sticky top-16 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex space-x-8 overflow-x-auto hide-scrollbar">
            <button
              onClick={() => setActiveTab('stats')}
              className={`flex items-center gap-2 py-4 border-b-2 font-bold text-sm whitespace-nowrap transition-colors ${activeTab === 'stats' ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-slate-500 hover:text-slate-700'}`}
            >
              <Activity className="w-4 h-4" /> Overview
            </button>
            <button
              onClick={() => setActiveTab('users')}
              className={`flex items-center gap-2 py-4 border-b-2 font-bold text-sm whitespace-nowrap transition-colors ${activeTab === 'users' ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-slate-500 hover:text-slate-700'}`}
            >
              <Users className="w-4 h-4" /> Users
            </button>
            <button
              onClick={() => setActiveTab('blocklist')}
              className={`flex items-center gap-2 py-4 border-b-2 font-bold text-sm whitespace-nowrap transition-colors ${activeTab === 'blocklist' ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-slate-500 hover:text-slate-700'}`}
            >
              <Ban className="w-4 h-4" /> Blocklist
            </button>
            {role === 'super_admin' && (
              <button
                onClick={() => setActiveTab('admins')}
                className={`flex items-center gap-2 py-4 border-b-2 font-bold text-sm whitespace-nowrap transition-colors ${activeTab === 'admins' ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-slate-500 hover:text-slate-700'}`}
              >
                <Shield className="w-4 h-4" /> Administrators
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        
        {/* Stats Tab */}
        {activeTab === 'stats' && stats && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
              <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <div className="flex items-center gap-3 mb-2 text-blue-600">
                  <Users className="w-5 h-5" />
                  <h3 className="font-bold text-slate-500 text-sm uppercase tracking-wider">Total Users</h3>
                </div>
                <p className="text-4xl font-black text-slate-900">{stats.total_users}</p>
              </div>
              <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <div className="flex items-center gap-3 mb-2 text-green-600">
                  <CheckCircle className="w-5 h-5" />
                  <h3 className="font-bold text-slate-500 text-sm uppercase tracking-wider">Verified</h3>
                </div>
                <p className="text-4xl font-black text-slate-900">{stats.verified_users}</p>
              </div>
              <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <div className="flex items-center gap-3 mb-2 text-red-600">
                  <ShieldAlert className="w-5 h-5" />
                  <h3 className="font-bold text-slate-500 text-sm uppercase tracking-wider">Blocked</h3>
                </div>
                <p className="text-4xl font-black text-slate-900">{stats.blocked_users}</p>
              </div>
              <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <div className="flex items-center gap-3 mb-2 text-indigo-600">
                  <Shield className="w-5 h-5" />
                  <h3 className="font-bold text-slate-500 text-sm uppercase tracking-wider">Admins</h3>
                </div>
                <p className="text-4xl font-black text-slate-900">{stats.total_admins}</p>
              </div>
            </div>
          </div>
        )}

        {/* Users Tab */}
        {activeTab === 'users' && (
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
            <div className="p-6 border-b border-slate-200 flex flex-col sm:flex-row justify-between sm:items-center gap-4">
              <h2 className="text-xl font-bold text-slate-900">User Management</h2>
              <div className="relative w-full sm:w-80">
                <Search className="absolute left-3 top-3 w-5 h-5 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search by name, ID, or email..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:ring-2 focus:ring-indigo-600 outline-none transition-all font-medium text-sm"
                />
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase font-bold text-slate-500 tracking-wider">
                  <tr>
                    <th className="p-4 pl-6">Telegram User</th>
                    <th className="p-4">Status</th>
                    <th className="p-4">Joined Date</th>
                    <th className="p-4 pr-6 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredUsers.length === 0 ? (
                    <tr><td colSpan={4} className="p-8 text-center text-slate-500 font-medium">No users found.</td></tr>
                  ) : (
                    filteredUsers.map((user) => (
                      <tr key={user.telegram_id} className="hover:bg-slate-50 transition-colors">
                        <td className="p-4 pl-6">
                          <div className="font-bold text-slate-900">{user.first_name || 'Unknown'}</div>
                          <div className="text-xs text-slate-500 mt-0.5">ID: {user.telegram_id} • @{user.username || 'none'}</div>
                          <div className="text-sm text-indigo-600 font-medium mt-1">{user.email || 'No email linked'}</div>
                        </td>
                        <td className="p-4">
                          <span className={`px-3 py-1 rounded-full text-xs font-black tracking-wide ${user.is_verified ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>
                            {user.is_verified ? 'APPROVED' : 'PENDING'}
                          </span>
                        </td>
                        <td className="p-4 text-sm font-medium text-slate-600">
                          {new Date(user.created_at).toLocaleDateString()}
                        </td>
                        <td className="p-4 pr-6 text-right space-x-2">
                          {!user.is_verified ? (
                            <button onClick={() => approveUser(user.telegram_id)} className="bg-indigo-50 text-indigo-700 px-4 py-2 rounded-lg font-bold hover:bg-indigo-600 hover:text-white transition-all text-sm">
                              Approve
                            </button>
                          ) : (
                            <button onClick={() => blockUser(user.telegram_id, 'Blocked by admin')} className="bg-red-50 text-red-600 px-4 py-2 rounded-lg font-bold hover:bg-red-600 hover:text-white transition-all text-sm">
                              Block
                            </button>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Blocklist Tab */}
        {activeTab === 'blocklist' && (
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
            <div className="p-6 border-b border-slate-200">
              <h2 className="text-xl font-bold text-slate-900">System Blocklist</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase font-bold text-slate-500 tracking-wider">
                  <tr>
                    <th className="p-4 pl-6">Target</th>
                    <th className="p-4">Reason</th>
                    <th className="p-4 pr-6 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {blocks.length === 0 ? (
                    <tr><td colSpan={3} className="p-8 text-center text-slate-500 font-medium">No blocked records found.</td></tr>
                  ) : (
                    blocks.map((block) => (
                      <tr key={block.id} className="hover:bg-slate-50 transition-colors">
                        <td className="p-4 pl-6 font-bold text-slate-900">
                          <span className="text-xs font-black text-slate-400 uppercase mr-2">{block.block_type}:</span> 
                          {block.block_value}
                        </td>
                        <td className="p-4 text-sm font-medium text-slate-600">{block.reason || 'No reason provided'}</td>
                        <td className="p-4 pr-6 text-right">
                          <button onClick={() => removeBlock(block.id)} className="text-indigo-600 hover:text-indigo-800 font-bold text-sm bg-indigo-50 hover:bg-indigo-100 px-4 py-2 rounded-lg transition-colors">
                            Lift Block
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Admins Tab */}
        {activeTab === 'admins' && role === 'super_admin' && (
          <div className="space-y-6">
            <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
              <div className="flex items-center gap-3 mb-4">
                <div className="bg-indigo-100 p-2 rounded-lg"><UserPlus className="w-5 h-5 text-indigo-700" /></div>
                <h2 className="text-lg font-bold text-slate-900">Provision New Admin</h2>
              </div>
              <form onSubmit={(e) => {
                e.preventDefault();
                const email = (e.target as HTMLFormElement).email.value;
                addAdmin(email);
                (e.target as HTMLFormElement).reset();
              }} className="flex flex-col sm:flex-row gap-4">
                <input type="email" name="email" required placeholder="admin@company.com" className="flex-1 p-3 bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:ring-2 focus:ring-indigo-600 outline-none transition-all font-medium" />
                <button type="submit" className="bg-slate-900 text-white px-8 py-3 rounded-xl font-bold hover:bg-slate-800 transition-all shadow-md">
                  Grant Access
                </button>
              </form>
            </div>

            <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
              <div className="p-6 border-b border-slate-200">
                <h2 className="text-xl font-bold text-slate-900">Active Administrators</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase font-bold text-slate-500 tracking-wider">
                    <tr>
                      <th className="p-4 pl-6">Email Address</th>
                      <th className="p-4">Access Level</th>
                      <th className="p-4 pr-6 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {admins.map((admin) => (
                      <tr key={admin.id} className="hover:bg-slate-50 transition-colors">
                        <td className="p-4 pl-6 font-bold text-slate-900">{admin.email}</td>
                        <td className="p-4">
                          <span className={`px-3 py-1 rounded-full text-xs font-black tracking-wide uppercase ${admin.role === 'super_admin' ? 'bg-purple-100 text-purple-700' : 'bg-blue-100 text-blue-700'}`}>
                            {admin.role.replace('_', ' ')}
                          </span>
                        </td>
                        <td className="p-4 pr-6 text-right">
                          <button onClick={() => removeAdmin(admin.id)} className="text-red-500 hover:text-red-700 p-2 rounded-lg hover:bg-red-50 transition-colors inline-flex items-center gap-2 text-sm font-bold">
                            <Trash2 className="w-4 h-4" /> Revoke
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;