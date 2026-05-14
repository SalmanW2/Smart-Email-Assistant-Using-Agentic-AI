import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import Navbar from '../components/Navbar';
import { Users, ShieldAlert, CheckCircle, Activity, Shield, Ban, Search, UserPlus, Trash2, ArrowUpRight, Clock, Zap, X, AlertCircle, Settings2, MicOff, BotOff, CalendarClock } from 'lucide-react';

interface User { telegram_id: number; first_name: string; username: string; email: string; is_verified: boolean; ai_allowed?: boolean; voice_allowed?: boolean; created_at: string; }
interface Admin { id: string; email: string; role: string; }
interface Block { id: string; block_type: string; block_value: string; reason: string; expires_at?: string; }
interface Stats { total_users: number; verified_users: number; blocked_users: number; total_admins: number; }

const backendUrl = import.meta.env.VITE_BACKEND_URL || 'https://smart-email-assistant-using-agentic-ai.onrender.com';

const Dashboard = () => {
  const [activeTab, setActiveTab] = useState('users');
  const [users, setUsers] = useState<User[]>([]);
  const [admins, setAdmins] = useState<Admin[]>([]);
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [role, setRole] = useState<string>('');
  
  const [manageUserId, setManageUserId] = useState<number | null>(null);
  const [toast, setToast] = useState<{msg: string, type: 'success' | 'error'} | null>(null);
  
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [showBanner, setShowBanner] = useState(localStorage.getItem('password_setup_dismissed') !== 'true');
  const [adminEmail, setAdminEmail] = useState(localStorage.getItem('admin_email') || '');

  // 10-Minute Auto Logout Feature
  useEffect(() => {
    let timeoutId: NodeJS.Timeout;
    const resetTimer = () => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => {
        localStorage.removeItem('admin_email');
        navigate('/admin/login?error=Session+expired+due+to+inactivity');
      }, 600000);
    };
    const events = ['mousemove', 'keydown', 'scroll', 'click', 'touchstart'];
    events.forEach(event => window.addEventListener(event, resetTimer));
    resetTimer();
    return () => { clearTimeout(timeoutId); events.forEach(event => window.removeEventListener(event, resetTimer)); };
  }, [navigate]);

  // FIX: Loop Prevention & Smart URL Parsing
  useEffect(() => {
    const urlEmail = searchParams.get('email');
    if (urlEmail) {
      const cleanEmail = urlEmail.toLowerCase().trim();
      localStorage.setItem('admin_email', cleanEmail);
      setAdminEmail(cleanEmail);
      
      // Remove email from URL without reloading the page to stop loops
      searchParams.delete('email');
      setSearchParams(searchParams, { replace: true });
    } else if (!adminEmail) {
      navigate('/admin/login');
    }
  }, [searchParams, navigate, setSearchParams, adminEmail]);

  useEffect(() => {
    if (adminEmail) {
      fetchRole();
      fetchData();
    }
  }, [adminEmail]);

  const showNotification = (msg: string, type: 'success' | 'error' = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  const getHeaders = () => ({ 'Content-Type': 'application/json', 'x-admin-email': adminEmail });

  const fetchRole = async () => {
    try {
      const response = await fetch(`${backendUrl}/api/admin/role`, { headers: getHeaders() });
      if (response.ok) {
        const data = await response.json();
        setRole(data.role || 'admin');
      } else if (response.status === 401) {
        localStorage.removeItem('admin_email');
        navigate('/admin/login?error=Unauthorized+Access');
      }
    } catch (err) { console.error("Role check delayed or failed", err); }
  };

  const fetchData = async () => {
    try {
      const [usersRes, adminsRes, blocksRes, statsRes] = await Promise.all([
        fetch(`${backendUrl}/api/admin/users`, { headers: getHeaders() }),
        fetch(`${backendUrl}/api/admin/admins`, { headers: getHeaders() }),
        fetch(`${backendUrl}/api/admin/blocks`, { headers: getHeaders() }),
        fetch(`${backendUrl}/api/admin/stats`, { headers: getHeaders() }),
      ]);
      if (usersRes.ok) setUsers(await usersRes.json() || []);
      if (adminsRes.ok) setAdmins(await adminsRes.json() || []);
      if (blocksRes.ok) setBlocks(await blocksRes.json() || []);
      if (statsRes.ok) setStats(await statsRes.json() || null);
    } catch (err) { console.error('Data fetch failed', err); }
  };

  const filteredUsers = users.filter((u) => 
    (u.first_name || '').toLowerCase().includes(searchQuery.toLowerCase()) || 
    (u.username || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
    (u.email || '').toLowerCase().includes(searchQuery.toLowerCase())
  );

  const updatePermissions = async (tgId: number, is_verified: boolean, ai_allowed: boolean, voice_allowed: boolean, block_days: number) => {
    try {
      const payload = { is_verified, ai_allowed, voice_allowed, block_days, reason: "Admin enforced restrictions" };
      const res = await fetch(`${backendUrl}/api/admin/users/${tgId}/permissions`, { 
        method: 'POST', headers: getHeaders(), body: JSON.stringify(payload)
      }); 
      if(res.ok) { 
        showNotification('Permissions updated successfully!', 'success'); 
        setManageUserId(null);
        fetchData(); 
      }
      else { const data = await res.json(); showNotification(data.detail || 'Failed to update', 'error'); }
    } catch (e) { showNotification('Network Error', 'error'); }
  };

  const removeBlock = async (id: string) => { 
    try {
      const res = await fetch(`${backendUrl}/api/admin/blocks/${id}`, { method: 'DELETE', headers: getHeaders() }); 
      if(res.ok) { showNotification('Restriction lifted successfully!'); fetchData(); }
      else showNotification('Failed to lift restriction', 'error');
    } catch (e) { showNotification('Network Error', 'error'); }
  };

  const addAdmin = async (email: string) => { 
    try {
      const res = await fetch(`${backendUrl}/api/admin/admins`, { method: 'POST', headers: getHeaders(), body: JSON.stringify({ email, role: 'admin' }) }); 
      if(res.ok) { showNotification('New Admin added successfully!'); fetchData(); }
      else showNotification('Failed to add admin', 'error');
    } catch (e) { showNotification('Network Error', 'error'); }
  };

  const removeAdmin = async (id: string) => { 
    try {
      const res = await fetch(`${backendUrl}/api/admin/admins/${id}`, { method: 'DELETE', headers: getHeaders() }); 
      if(res.ok) { showNotification('Admin revoked successfully!'); fetchData(); }
      else showNotification('Failed to remove admin', 'error');
    } catch (e) { showNotification('Network Error', 'error'); }
  };

  const dismissBanner = () => {
    localStorage.setItem('password_setup_dismissed', 'true');
    setShowBanner(false);
  };

  if (!adminEmail) return null; // Wait for redirect if no email

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 font-sans pb-20 transition-colors duration-500 selection:bg-blue-500/30">
      <Navbar />

      {toast && (
        <div className={`fixed bottom-8 right-8 z-50 flex items-center gap-3 px-6 py-4 rounded-2xl font-bold text-sm shadow-2xl animate-in fade-in slide-in-from-bottom-5 duration-300 text-white ${toast.type === 'success' ? 'bg-emerald-600' : 'bg-red-600'}`}>
          {toast.type === 'success' ? <CheckCircle className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}
          {toast.msg}
        </div>
      )}

      {showBanner && (
        <div className="bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-md animate-in slide-in-from-top-2 duration-500">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex flex-col sm:flex-row items-center justify-between gap-3">
            <div className="flex items-center gap-3 text-center sm:text-left">
              <Zap className="w-5 h-5 text-amber-300 shrink-0 hidden sm:block" />
              <p className="text-sm font-medium">
                <strong className="font-bold mr-1">Want to login faster next time?</strong>
                Set up a manual password in settings.
              </p>
            </div>
            <div className="flex items-center gap-4 shrink-0 mt-2 sm:mt-0">
              <Link to="/admin/settings" className="bg-white text-indigo-700 px-4 py-1.5 rounded-full text-xs font-black uppercase tracking-wider hover:bg-blue-50 transition-colors shadow-sm">
                Setup Password
              </Link>
              <button onClick={dismissBanner} className="p-1 hover:bg-white/20 rounded-full transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      )}

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
              { label: 'Total Users', val: stats.total_users || 0, color: 'from-blue-500 to-indigo-600', icon: Users },
              { label: 'Verified Accounts', val: stats.verified_users || 0, color: 'from-emerald-500 to-teal-600', icon: CheckCircle },
              { label: 'Blocked Threats', val: stats.blocked_users || 0, color: 'from-rose-500 to-red-600', icon: ShieldAlert },
              { label: 'Active Admins', val: stats.total_admins || 0, color: 'from-purple-500 to-fuchsia-600', icon: Shield },
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

        {/* USERS VIEW (Cards Design for Desktop & Mobile) */}
        {activeTab === 'users' && (
          <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm transition-colors duration-500">
            <div className="p-5 sm:p-6 border-b border-slate-100 dark:border-slate-800/50 flex flex-col sm:flex-row justify-between gap-4 items-center bg-slate-50/50 dark:bg-slate-900/50 rounded-t-3xl">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <Users className="w-5 h-5 text-blue-500" /> User Directory
              </h2>
              <div className="relative w-full sm:w-80 group">
                <Search className="absolute left-3 top-3 w-5 h-5 text-slate-400 transition-colors" />
                <input type="text" placeholder="Search by name or email..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="w-full pl-10 pr-4 py-2.5 bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl text-sm outline-none focus:ring-2 focus:ring-blue-500/50 dark:text-white transition-all shadow-sm" />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-4">
              {filteredUsers.length === 0 ? (
                <div className="col-span-full text-center py-8 text-slate-500 font-medium">No users found.</div>
              ) : (
                filteredUsers.map((user) => {
                  const displayName = user.first_name || user.username || 'Unknown User';
                  const displayChar = displayName.charAt(0).toUpperCase();
                  const userBlock = blocks.find(b => b.block_value === String(user.telegram_id));
                  const isBlocked = !!userBlock;
                  const isActuallyVerified = user.is_verified && !isBlocked;

                  const [tmpAi, setTmpAi] = useState(user.ai_allowed !== false);
                  const [tmpVoice, setTmpVoice] = useState(user.voice_allowed !== false);
                  const [tmpBlockDays, setTmpBlockDays] = useState(0);

                  return (
                    <div key={user.telegram_id} className={`bg-slate-50 dark:bg-slate-800/30 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 flex flex-col hover:shadow-md transition-all ${manageUserId === user.telegram_id ? 'ring-2 ring-blue-500' : ''}`}>
                      <div className="flex items-start justify-between mb-3">
                        <div className="flex items-center gap-3">
                          <div className="w-12 h-12 rounded-full bg-blue-100 dark:bg-blue-900/50 flex items-center justify-center text-blue-700 dark:text-blue-400 font-bold text-lg uppercase shadow-inner shrink-0">
                            {displayChar}
                          </div>
                          <div>
                            <h3 className="font-bold text-slate-900 dark:text-white line-clamp-1">{displayName}</h3>
                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">ID: {user.telegram_id}</p>
                          </div>
                        </div>
                        <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-black uppercase tracking-wider border ${isActuallyVerified ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400' : 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400'}`}>
                          {isActuallyVerified ? 'Verified' : 'Pending/Revoked'}
                        </span>
                      </div>
                      <div className="space-y-1 text-sm mb-4">
                        <p className="flex justify-between"><span className="text-slate-500">Email:</span> <span className="font-medium text-slate-700 dark:text-slate-300 truncate max-w-[150px]">{user.email || 'N/A'}</span></p>
                        <p className="flex justify-between"><span className="text-slate-500">Joined:</span> <span className="font-medium text-slate-700 dark:text-slate-300">{user.created_at ? new Date(user.created_at).toLocaleDateString() : 'N/A'}</span></p>
                      </div>
                      
                      {manageUserId === user.telegram_id ? (
                        <div className="pt-4 border-t border-slate-200 dark:border-slate-800 animate-in slide-in-from-top-2">
                          <h4 className="text-xs font-bold text-slate-500 mb-3 uppercase tracking-wider">Granular Permissions</h4>
                          <div className="space-y-3 mb-4">
                            <label className="flex items-center justify-between text-sm font-medium text-slate-700 dark:text-slate-300">
                              <span className="flex items-center gap-2"><BotOff className="w-4 h-4 text-slate-400"/> Allow AI Engine</span>
                              <input type="checkbox" checked={tmpAi} onChange={(e) => setTmpAi(e.target.checked)} className="w-4 h-4 rounded text-blue-600 border-slate-300" />
                            </label>
                            <label className="flex items-center justify-between text-sm font-medium text-slate-700 dark:text-slate-300">
                              <span className="flex items-center gap-2"><MicOff className="w-4 h-4 text-slate-400"/> Allow Voice Notes</span>
                              <input type="checkbox" checked={tmpVoice} onChange={(e) => setTmpVoice(e.target.checked)} className="w-4 h-4 rounded text-blue-600 border-slate-300" />
                            </label>
                            <label className="flex items-center justify-between text-sm font-medium text-slate-700 dark:text-slate-300">
                              <span className="flex items-center gap-2"><CalendarClock className="w-4 h-4 text-slate-400"/> Temporary Ban (Days)</span>
                              <input type="number" min="0" max="365" value={tmpBlockDays} onChange={(e) => setTmpBlockDays(Number(e.target.value))} className="w-16 p-1 text-center bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-md" />
                            </label>
                          </div>
                          
                          <div className="flex gap-2">
                            <button onClick={() => updatePermissions(user.telegram_id, true, tmpAi, tmpVoice, 0)} className="flex-1 bg-emerald-500 text-white py-2 rounded-xl text-sm font-bold hover:bg-emerald-600 transition-all shadow-sm">Save & Approve</button>
                            <button onClick={() => updatePermissions(user.telegram_id, false, tmpAi, tmpVoice, tmpBlockDays)} className="flex-1 bg-red-500 text-white py-2 rounded-xl text-sm font-bold hover:bg-red-600 transition-all shadow-sm">{tmpBlockDays > 0 ? 'Suspend' : 'Block entirely'}</button>
                            <button onClick={() => setManageUserId(null)} className="px-3 bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-xl hover:bg-slate-300 dark:hover:bg-slate-600"><X className="w-4 h-4"/></button>
                          </div>
                        </div>
                      ) : (
                        <div className="pt-3 border-t border-slate-200 dark:border-slate-800 mt-auto flex gap-2">
                          {!isActuallyVerified ? (
                            <button onClick={() => updatePermissions(user.telegram_id, true, true, true, 0)} className="flex-1 bg-blue-600 text-white py-2.5 rounded-xl font-bold hover:bg-blue-700 transition-all text-sm shadow-sm">Approve Fully</button>
                          ) : (
                            <button onClick={() => setManageUserId(user.telegram_id)} className="flex-1 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 py-2.5 rounded-xl font-bold hover:bg-slate-200 dark:hover:bg-slate-700 transition-all text-sm flex items-center justify-center gap-2"><Settings2 className="w-4 h-4" /> Manage Access</button>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
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
                  <tr><th className="p-5 pl-8">Target Identity</th><th className="p-5">Block Reason & Expiry</th><th className="p-5 pr-8 text-right">Actions</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-50 dark:divide-slate-800/50">
                  {blocks.length === 0 ? (
                     <tr><td colSpan={3} className="p-10 text-center text-slate-500 dark:text-slate-400 font-medium">No active restrictions.</td></tr>
                  ) : (
                    blocks.map((block) => (
                      <tr key={block.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                        <td className="p-5 pl-8 font-bold text-slate-900 dark:text-white">
                          <span className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest mr-3 bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded-md">{block.block_type || 'ID'}</span>
                          {block.block_value}
                        </td>
                        <td className="p-5 text-sm font-medium text-slate-600 dark:text-slate-400">
                          <div>{block.reason || 'Security Policy Violation'}</div>
                          {block.expires_at && <div className="text-xs text-amber-600 dark:text-amber-400 mt-1 font-bold">Unblocks on: {new Date(block.expires_at).toLocaleString()}</div>}
                        </td>
                        <td className="p-5 pr-8 text-right">
                          <button onClick={() => removeBlock(block.id)} className="text-slate-500 dark:text-slate-400 font-bold text-sm bg-slate-100 dark:bg-slate-800 px-4 py-2 rounded-xl hover:bg-slate-900 hover:text-white dark:hover:bg-slate-700 transition-colors border border-slate-200 dark:border-slate-700">Lift Restriction</button>
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
                          <span className={`px-3 py-1.5 rounded-full text-[10px] font-black tracking-widest uppercase border ${(admin.role || '').includes('super') ? 'bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-500/10 dark:text-purple-400 dark:border-purple-500/20' : 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/20'}`}>
                            {(admin.role || 'admin').replace('_', ' ')}
                          </span>
                        </td>
                        <td className="p-5 pr-8 text-right">
                          {admin.role !== 'super_admin' ? (
                            <button onClick={() => removeAdmin(admin.id)} className="text-slate-400 hover:text-red-600 dark:hover:text-red-400 p-2 rounded-xl hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors inline-flex items-center gap-2 text-sm font-bold border border-transparent dark:hover:border-red-500/30">
                              <Trash2 className="w-5 h-5" />
                            </button>
                          ) : (
                            <span className="text-xs text-slate-400 dark:text-slate-500 font-bold uppercase tracking-wider mr-2">Protected</span>
                          )}
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