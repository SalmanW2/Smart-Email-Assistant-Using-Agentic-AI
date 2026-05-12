import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
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

const backendUrl = import.meta.env.VITE_BACKEND_URL || 'https://smart-email-assistant-using-agentic-ai.onrender.com';

const Dashboard = () => {
  const [activeTab, setActiveTab] = useState('stats');
  const [users, setUsers] = useState<User[]>([]);
  const [admins, setAdmins] = useState<Admin[]>([]);
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [role, setRole] = useState<string>('');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const urlEmail = searchParams.get('email');
  if (urlEmail) {
    localStorage.setItem('admin_email', urlEmail);
    window.history.replaceState(null, '', '/admin/dashboard'); 
  }

  const adminEmail = localStorage.getItem('admin_email');

  useEffect(() => {
    if (!adminEmail) { navigate('/admin/login'); return; }
    fetchRole();
    fetchData();
  }, [adminEmail, navigate]);

  const getHeaders = () => ({ 'Content-Type': 'application/json', 'x-admin-email': adminEmail || '' });

  const fetchRole = async () => {
    try {
      const response = await fetch(`${backendUrl}/api/admin/role`, { headers: getHeaders() });
      if (response.ok) {
        const data = await response.json();
        setRole(data.role);
      } else {
        navigate('/admin/login');
      }
    } catch (err) { 
      navigate('/admin/login'); 
    }
  };

  const fetchData = async () => {
    try {
      const [usersRes, adminsRes, blocksRes, statsRes] = await Promise.all([
        fetch(`${backendUrl}/api/admin/users`, { headers: getHeaders() }),
        fetch(`${backendUrl}/api/admin/admins`, { headers: getHeaders() }),
        fetch(`${backendUrl}/api/admin/blocks`, { headers: getHeaders() }),
        fetch(`${backendUrl}/api/admin/stats`, { headers: getHeaders() }),
      ]);
      if (usersRes.ok) setUsers(await usersRes.json());
      if (adminsRes.ok) setAdmins(await adminsRes.json());
      if (blocksRes.ok) setBlocks(await blocksRes.json());
      if (statsRes.ok) setStats(await statsRes.json());
    } catch (err) { 
      console.error('Data fetch failed', err); 
    }
  };

  const filteredUsers = users.filter((u) => 
    u.first_name?.toLowerCase().includes(searchQuery.toLowerCase()) || 
    u.email?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const approveUser = async (tgId: number) => { 
    await fetch(`${backendUrl}/api/admin/users/${tgId}/approve`, { method: 'POST', headers: getHeaders() }); 
    fetchData(); 
  };
  
  const blockUser = async (tgId: number, reason: string) => { 
    await fetch(`${backendUrl}/api/admin/users/${tgId}/block?reason=${encodeURIComponent(reason)}`, { method: 'POST', headers: getHeaders() }); 
    fetchData(); 
  };
  
  const removeBlock = async (id: string) => { 
    await fetch(`${backendUrl}/api/admin/blocks/${id}`, { method: 'DELETE', headers: getHeaders() }); 
    fetchData(); 
  };
  
  const addAdmin = async (email: string) => { 
    await fetch(`${backendUrl}/api/admin/admins`, { method: 'POST', headers: getHeaders(), body: JSON.stringify({ email, role: 'admin' }) }); 
    fetchData(); 
  };
  
  const removeAdmin = async (id: string) => { 
    await fetch(`${backendUrl}/api/admin/admins/${id}`, { method: 'DELETE', headers: getHeaders() }); 
    fetchData(); 
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 font-sans pb-20 transition-colors duration-300">
      <Navbar />

      <div className="bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 sticky top-16 z-40 transition-colors">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex space-x-6 overflow-x-auto hide-scrollbar">
            {['stats', 'users', 'blocklist', 'admins'].map((tab) => (
              (tab !== 'admins' || role === 'super_admin') && (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`flex items-center gap-2 py-4 border-b-2 font-bold text-sm whitespace-nowrap transition-colors uppercase ${activeTab === tab ? 'border-blue-600 dark:border-blue-400 text-blue-600 dark:text-blue-400' : 'border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'}`}
                >
                  {tab === 'stats' && <Activity className="w-4 h-4" />}
                  {tab === 'users' && <Users className="w-4 h-4" />}
                  {tab === 'blocklist' && <Ban className="w-4 h-4" />}
                  {tab === 'admins' && <Shield className="w-4 h-4" />}
                  {tab}
                </button>
              )
            ))}
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 py-8">
        {activeTab === 'stats' && stats && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { label: 'Total', val: stats.total_users, color: 'blue', icon: Users },
              { label: 'Verified', val: stats.verified_users, color: 'green', icon: CheckCircle },
              { label: 'Blocked', val: stats.blocked_users, color: 'red', icon: ShieldAlert },
              { label: 'Admins', val: stats.total_admins, color: 'purple', icon: Shield },
            ].map((s) => (
              <div key={s.label} className="bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm transition-colors">
                <s.icon className={`w-6 h-6 text-${s.color}-600 dark:text-${s.color}-400 mb-3`} />
                <h3 className="font-bold text-slate-500 dark:text-slate-400 text-xs uppercase">{s.label}</h3>
                <p className="text-2xl sm:text-4xl font-black text-slate-900 dark:text-white">{s.val}</p>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'users' && (
          <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm transition-colors">
            <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex flex-col sm:flex-row justify-between gap-4">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">User Base</h2>
              <div className="relative w-full sm:w-64">
                <Search className="absolute left-3 top-3 w-4 h-4 text-slate-400" />
                <input type="text" placeholder="Search..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="w-full pl-9 pr-4 py-2 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl text-sm outline-none focus:ring-1 focus:ring-blue-600 dark:text-white transition-colors" />
              </div>
            </div>
            <div className="overflow-x-auto w-full">
              <table className="w-full text-left min-w-[700px]">
                <thead className="bg-slate-50 dark:bg-slate-950/50 text-xs uppercase font-bold text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800">
                  <tr><th className="p-4 pl-6">User</th><th className="p-4">Status</th><th className="p-4 pr-6 text-right">Actions</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800/50">
                  {filteredUsers.length === 0 ? (
                    <tr><td colSpan={3} className="p-8 text-center text-slate-500 dark:text-slate-400 font-medium">No users found.</td></tr>
                  ) : (
                    filteredUsers.map((user) => (
                      <tr key={user.telegram_id} className="hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors">
                        <td className="p-4 pl-6">
                          <div className="font-bold text-slate-900 dark:text-white">{user.first_name || 'Unknown'}</div>
                          <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">ID: {user.telegram_id}</div>
                          <div className="text-sm text-blue-600 dark:text-blue-400 mt-1">{user.email || 'No email'}</div>
                        </td>
                        <td className="p-4"><span className={`px-2 py-1 rounded-md text-[10px] font-black ${user.is_verified ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400' : 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400'}`}>{user.is_verified ? 'VERIFIED' : 'PENDING'}</span></td>
                        <td className="p-4 pr-6 text-right">
                          {!user.is_verified ? (
                            <button onClick={() => approveUser(user.telegram_id)} className="bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 px-4 py-2 rounded-lg font-bold hover:bg-blue-600 hover:text-white text-sm transition-all">Approve</button>
                          ) : (
                            <button onClick={() => blockUser(user.telegram_id, 'Blocked by admin')} className="bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 px-4 py-2 rounded-lg font-bold hover:bg-red-600 hover:text-white text-sm transition-all">Block</button>
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

        {activeTab === 'blocklist' && (
          <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm transition-colors">
            <div className="p-4 border-b border-slate-200 dark:border-slate-800"><h2 className="text-xl font-bold text-slate-900 dark:text-white">System Blocklist</h2></div>
            <div className="overflow-x-auto w-full">
              <table className="w-full text-left min-w-[600px]">
                <thead className="bg-slate-50 dark:bg-slate-950/50 text-xs uppercase font-bold text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800">
                  <tr><th className="p-4 pl-6">Target</th><th className="p-4">Reason</th><th className="p-4 pr-6 text-right">Actions</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800/50">
                  {blocks.length === 0 ? (
                     <tr><td colSpan={3} className="p-8 text-center text-slate-500 dark:text-slate-400 font-medium">No blocks found.</td></tr>
                  ) : (
                    blocks.map((block) => (
                      <tr key={block.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors">
                        <td className="p-4 pl-6 font-bold text-slate-900 dark:text-white"><span className="text-[10px] font-black text-slate-500 uppercase mr-2">{block.block_type}:</span>{block.block_value}</td>
                        <td className="p-4 text-sm font-medium text-slate-600 dark:text-slate-400">{block.reason || 'No reason'}</td>
                        <td className="p-4 pr-6 text-right"><button onClick={() => removeBlock(block.id)} className="text-blue-600 dark:text-blue-400 font-bold text-sm bg-blue-50 dark:bg-blue-900/30 px-4 py-2 rounded-lg hover:bg-blue-600 hover:text-white transition-colors">Lift Block</button></td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'admins' && role === 'super_admin' && (
          <div className="space-y-6">
            <div className="bg-white dark:bg-slate-900 p-4 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm transition-colors">
              <div className="flex items-center gap-3 mb-4"><div className="bg-blue-100 dark:bg-blue-900/30 p-2 rounded-lg"><UserPlus className="w-5 h-5 text-blue-700 dark:text-blue-400" /></div><h2 className="text-lg font-bold text-slate-900 dark:text-white">Add Admin</h2></div>
              <form onSubmit={(e) => { e.preventDefault(); addAdmin((e.target as HTMLFormElement).email.value); (e.target as HTMLFormElement).reset(); }} className="flex flex-col sm:flex-row gap-4">
                <input type="email" name="email" required placeholder="admin@company.com" className="flex-1 p-3 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl focus:ring-1 focus:ring-blue-600 outline-none text-slate-900 dark:text-white text-sm" />
                <button type="submit" className="bg-blue-600 text-white px-8 py-3 rounded-xl font-bold hover:bg-blue-700 transition-all text-sm">Grant Access</button>
              </form>
            </div>
            <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm transition-colors">
              <div className="p-4 border-b border-slate-200 dark:border-slate-800"><h2 className="text-xl font-bold text-slate-900 dark:text-white">Active Administrators</h2></div>
              <div className="overflow-x-auto w-full">
                <table className="w-full text-left min-w-[600px]">
                  <thead className="bg-slate-50 dark:bg-slate-950/50 text-xs uppercase font-bold text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800">
                    <tr><th className="p-4 pl-6">Email Address</th><th className="p-4">Access Level</th><th className="p-4 pr-6 text-right">Actions</th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800/50">
                    {admins.map((admin) => (
                      <tr key={admin.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors">
                        <td className="p-4 pl-6 font-bold text-slate-900 dark:text-white">{admin.email}</td>
                        <td className="p-4"><span className={`px-2 py-1 rounded-md text-[10px] font-black uppercase ${admin.role === 'super_admin' ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-400' : 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400'}`}>{admin.role.replace('_', ' ')}</span></td>
                        <td className="p-4 pr-6 text-right"><button onClick={() => removeAdmin(admin.id)} className="text-red-500 dark:text-red-400 hover:text-white p-2 rounded-lg hover:bg-red-600 transition-colors inline-flex items-center gap-2 text-xs font-bold"><Trash2 className="w-4 h-4" /> Revoke</button></td>
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