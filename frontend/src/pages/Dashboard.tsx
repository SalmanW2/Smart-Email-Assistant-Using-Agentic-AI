import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import Navbar from '../components/Navbar';
import { Users, ShieldAlert, CheckCircle, Activity, Shield, Ban, Search, UserPlus, Trash2, ArrowUpRight, Clock } from 'lucide-react';

interface User { telegram_id: number; first_name: string; username: string; email: string; is_verified: boolean; created_at: string; }
interface Admin { id: string; email: string; role: string; }
interface Block { id: string; block_type: string; block_value: string; reason: string; }
interface Stats { total_users: number; verified_users: number; blocked_users: number; total_admins: number; }

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
      } else navigate('/admin/login');
    } catch (err) { navigate('/admin/login'); }
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
    } catch (err) { console.error('Data fetch failed'); }
  };

  const filteredUsers = users.filter((u) => u.first_name?.toLowerCase().includes(searchQuery.toLowerCase()) || u.email?.toLowerCase().includes(searchQuery.toLowerCase()));

  const approveUser = async (tgId: number) => { await fetch(`${backendUrl}/api/admin/users/${tgId}/approve`, { method: 'POST', headers: getHeaders() }); fetchData(); };
  const blockUser = async (tgId: number, reason: string) => { await fetch(`${backendUrl}/api/admin/users/${tgId}/block?reason=${encodeURIComponent(reason)}`, { method: 'POST', headers: getHeaders() }); fetchData(); };
  const removeBlock = async (id: string) => { await fetch(`${backendUrl}/api/admin/blocks/${id}`, { method: 'DELETE', headers: getHeaders() }); fetchData(); };
  const addAdmin = async (email: string) => { await fetch(`${backendUrl}/api/admin/admins`, { method: 'POST', headers: getHeaders(), body: JSON.stringify({ email, role: 'admin' }) }); fetchData(); };
  const removeAdmin = async (id: string) => { await fetch(`${backendUrl}/api/admin/admins/${id}`, { method: 'DELETE', headers: getHeaders() }); fetchData(); };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 font-sans pb-20 transition-colors duration-500 selection:bg-blue-500/30">
      <Navbar />

      {/* Premium Tab Navigation */}
      <div className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl border-b border-slate-200/50 dark:border-slate-800/50 sticky top-16 z-40 transition-colors duration-500 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <div className="flex space-x-2 sm:space-x-6 overflow-x-auto hide-scrollbar py-2">
            {['stats', 'users', 'blocklist', 'admins'].map((tab) => (
              (tab !== 'admins' || role === 'super_admin') && (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`flex items-center gap-2 px-4 py-3 rounded-xl font-bold text-sm whitespace-nowrap transition-all duration-300 capitalize ${activeTab === tab ? 'bg-slate-900 text-white dark:bg-blue-600 dark:text-white shadow-md' : 'text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white'}`}
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

      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
        
        {/* STATS VIEW */}
        {activeTab === 'stats' && stats && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {[
              { label: 'Total Users', val: stats.total_users, color: 'from-blue-500 to-indigo-600', icon: Users },
              { label: 'Verified Accounts', val: stats.verified_users, color: 'from-emerald-500 to-teal-600', icon: CheckCircle },
              { label: 'Blocked Threats', val: stats.blocked_users, color: 'from-rose-500 to-red-600', icon: ShieldAlert },
              { label: 'Active Admins', val: stats.total_admins, color: 'from-purple-500 to-fuchsia-600', icon: Shield },
            ].map((s) => (
              <div key={s.label} className="group relative bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm hover:shadow-xl transition-all duration-300 overflow-hidden cursor-default">
                <div className={`absolute top-0 right-0 w-32 h-32 bg-gradient-to-br ${s.color} opacity-5 group-hover:opacity-10 rounded-bl-full transition-opacity duration-500`}></div>
                <div className="flex justify-between items-start mb-4">
                  <div className={`p-3 rounded-2xl bg-gradient-to-br ${s.color} text-white shadow-md group-hover:scale-110 transition-transform duration-300`}>
                    <s.icon className="w-6 h-6" />
                  </div>
                  <ArrowUpRight className="w-5 h-5 text-slate-300 dark:text-slate-600 group-hover:text-slate-400 transition-colors" />
                </div>
                <h3 className="font-bold text-slate-500 dark:text-slate-400 text-sm tracking-wide">{s.label}</h3>
                <p className="text-4xl font-black text-slate-900 dark:text-white mt-1 tracking-tight">{s.val}</p>
              </div>
            ))}
          </div>
        )}

        {/* USERS VIEW */}
        {activeTab === 'users' && (
          <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm transition-colors duration-500">
            <div className="p-6 border-b border-slate-100 dark:border-slate-800/50 flex flex-col sm:flex-row justify-between gap-4 items-center bg-slate-50/50 dark:bg-slate-900/50">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <Users className="w-5 h-5 text-blue-500" /> User Directory
              </h2>
              <div className="relative w-full sm:w-80 group">
                <Search className="absolute left-3 top-3 w-5 h-5 text-slate-400 group-focus-within:text-blue-500 transition-colors" />
                <input type="text" placeholder="Search users by name or email..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="w-full pl-10 pr-4 py-2.5 bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl text-sm outline-none focus:ring-2 focus:ring-blue-500/50 dark:text-white transition-all shadow-sm" />
              </div>
            </div>
            <div className="overflow-x-auto w-full">
              <table className="w-full text-left min-w-[800px]">
                <thead className="bg-slate-50 dark:bg-slate-950/50 text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider border-b border-slate-100 dark:border-slate-800">
                  <tr><th className="p-5 pl-8">User Profile</th><th className="p-5">Security Status</th><th className="p-5">Joined Date</th><th className="p-5 pr-8 text-right">Actions</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-50 dark:divide-slate-800/50">
                  {filteredUsers.length === 0 ? (
                    <tr><td colSpan={4} className="p-10 text-center text-slate-500 dark:text-slate-400 font-medium">No users found.</td></tr>
                  ) : (
                    filteredUsers.map((user) => (
                      <tr key={user.telegram_id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors group">
                        <td className="p-5 pl-8 flex items-center gap-4">
                          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-100 to-indigo-100 dark:from-blue-900/50 dark:to-indigo-900/50 flex items-center justify-center text-blue-700 dark:text-blue-400 font-bold uppercase shadow-inner">
                            {user.first_name ? user.first_name[0] : 'U'}
                          </div>
                          <div>
                            <div className="font-bold text-slate-900 dark:text-white">{user.first_name || 'Unknown'}</div>
                            <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">ID: {user.telegram_id}</div>
                            <div className="text-sm font-medium text-blue-600 dark:text-blue-400 mt-1">{user.email || 'No connected email'}</div>
                          </div>
                        </td>
                        <td className="p-5">
                          <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold border ${user.is_verified ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20' : 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20'}`}>
                            {user.is_verified ? <><CheckCircle className="w-3 h-3"/> Verified</> : <><Clock className="w-3 h-3"/> Pending</>}
                          </span>
                        </td>
                        <td className="p-5 text-sm font-medium text-slate-600 dark:text-slate-400">
                          {new Date(user.created_at).toLocaleDateString()}
                        </td>
                        <td className="p-5 pr-8 text-right">
                          {!user.is_verified ? (
                            <button onClick={() => approveUser(user.telegram_id)} className="bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400 px-5 py-2.5 rounded-xl font-bold hover:bg-blue-600 hover:text-white dark:hover:bg-blue-600 transition-all text-sm">Authorize</button>
                          ) : (
                            <button onClick={() => blockUser(user.telegram_id, 'Blocked by admin')} className="bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 px-5 py-2.5 rounded-xl font-bold hover:bg-red-600 hover:text-white dark:hover:bg-red-600 transition-all text-sm opacity-0 group-hover:opacity-100 focus:opacity-100">Revoke Access</button>
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

        {/* BLOCKLIST VIEW */}
        {activeTab === 'blocklist' && (
          <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm transition-colors duration-500">
            <div className="p-6 border-b border-slate-100 dark:border-slate-800/50 bg-slate-50/50 dark:bg-slate-900/50">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2"><Ban className="w-5 h-5 text-red-500" /> Restricted Entities</h2>
            </div>
            <div className="overflow-x-auto w-full">
              <table className="w-full text-left min-w-[700px]">
                <thead className="bg-slate-50 dark:bg-slate-950/50 text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider border-b border-slate-100 dark:border-slate-800">
                  <tr><th className="p-5 pl-8">Target Identity</th><th className="p-5">Block Reason</th><th className="p-5 pr-8 text-right">Actions</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-50 dark:divide-slate-800/50">
                  {blocks.length === 0 ? (
                     <tr><td colSpan={3} className="p-10 text-center text-slate-500 dark:text-slate-400 font-medium">No active restrictions.</td></tr>
                  ) : (
                    blocks.map((block) => (
                      <tr key={block.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                        <td className="p-5 pl-8 font-bold text-slate-900 dark:text-white">
                          <span className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest mr-3 bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded-md">{block.block_type}</span>
                          {block.block_value}
                        </td>
                        <td className="p-5 text-sm font-medium text-slate-600 dark:text-slate-400">{block.reason || 'Security Policy Violation'}</td>
                        <td className="p-5 pr-8 text-right">
                          <button onClick={() => removeBlock(block.id)} className="text-slate-500 dark:text-slate-400 font-bold text-sm bg-slate-100 dark:bg-slate-800 px-4 py-2 rounded-xl hover:bg-slate-900 hover:text-white dark:hover:bg-slate-700 transition-colors">Lift Restriction</button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ADMINS VIEW */}
        {activeTab === 'admins' && role === 'super_admin' && (
          <div className="space-y-6">
            <div className="bg-white dark:bg-slate-900 p-6 sm:p-8 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm transition-colors duration-500">
              <div className="flex items-center gap-3 mb-6">
                <div className="bg-indigo-100 dark:bg-indigo-500/20 p-3 rounded-2xl">
                  <UserPlus className="w-6 h-6 text-indigo-700 dark:text-indigo-400" />
                </div>
                <div>
                  <h2 className="text-xl font-bold text-slate-900 dark:text-white tracking-tight">Provision New Admin</h2>
                  <p className="text-sm text-slate-500 dark:text-slate-400 font-medium">Grant dashboard access to trusted personnel.</p>
                </div>
              </div>
              <form onSubmit={(e) => { e.preventDefault(); addAdmin((e.target as HTMLFormElement).email.value); (e.target as HTMLFormElement).reset(); }} className="flex flex-col sm:flex-row gap-4 max-w-2xl">
                <input type="email" name="email" required placeholder="admin@company.com" className="flex-1 p-4 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-indigo-500 outline-none text-slate-900 dark:text-white font-medium shadow-inner" />
                <button type="submit" className="bg-indigo-600 text-white px-8 py-4 rounded-xl font-bold hover:bg-indigo-700 transition-all shadow-lg hover:shadow-indigo-500/30">Grant Access</button>
              </form>
            </div>
            
            <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm transition-colors duration-500">
              <div className="p-6 border-b border-slate-100 dark:border-slate-800/50 bg-slate-50/50 dark:bg-slate-900/50">
                <h2 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2"><Shield className="w-5 h-5 text-purple-500" /> Active Administrators</h2>
              </div>
              <div className="overflow-x-auto w-full">
                <table className="w-full text-left min-w-[700px]">
                  <thead className="bg-slate-50 dark:bg-slate-950/50 text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider border-b border-slate-100 dark:border-slate-800">
                    <tr><th className="p-5 pl-8">Email Address</th><th className="p-5">Clearance Level</th><th className="p-5 pr-8 text-right">Actions</th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50 dark:divide-slate-800/50">
                    {admins.map((admin) => (
                      <tr key={admin.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                        <td className="p-5 pl-8 font-bold text-slate-900 dark:text-white">{admin.email}</td>
                        <td className="p-5">
                          <span className={`px-3 py-1.5 rounded-full text-[10px] font-black tracking-widest uppercase border ${admin.role === 'super_admin' ? 'bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-500/10 dark:text-purple-400 dark:border-purple-500/20' : 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/20'}`}>
                            {admin.role.replace('_', ' ')}
                          </span>
                        </td>
                        <td className="p-5 pr-8 text-right">
                          <button onClick={() => removeAdmin(admin.id)} className="text-slate-400 hover:text-red-600 dark:hover:text-red-400 p-2 rounded-xl hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors inline-flex items-center gap-2 text-sm font-bold">
                            <Trash2 className="w-5 h-5" />
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