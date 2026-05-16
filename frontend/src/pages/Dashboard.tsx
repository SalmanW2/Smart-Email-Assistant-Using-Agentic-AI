import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import Navbar from '../components/Navbar';
import { 
  Users, ShieldAlert, CheckCircle, Activity, Shield, Ban, Search, 
  UserPlus, Trash2, ArrowUpRight, Zap, X, AlertCircle, Settings2, 
  MicOff, CalendarClock, LineChart, Mail, Mic, ShieldOff, ChevronLeft, ChevronRight
} from 'lucide-react';

interface User { telegram_id: number; first_name: string; username: string; email: string; is_verified: boolean; ai_allowed?: boolean; voice_allowed?: boolean; created_at: string; }
interface Admin { id: string; email: string; role: string; }
interface Block { id: string; block_type: string; block_value: string; reason: string; expires_at?: string; }
interface Stats { total_users: number; verified_users: number; blocked_users: number; total_admins: number; total_stt_seconds_used: number; total_scheduled_emails: number; total_conversations: number; }
interface STTUsage { id: string; duration_seconds: number; method: string; created_at: string; }
interface ScheduledEmail { id: string; to_email: string; status: string; scheduled_time: string; }

const backendUrl = import.meta.env.VITE_BACKEND_URL || 'https://smart-email-assistant-using-agentic-ai.onrender.com';

// ==========================================
// 1. CONFIRMATION MODAL COMPONENT
// ==========================================
const ConfirmModal = ({ isOpen, title, message, onConfirm, onCancel }: { isOpen: boolean, title: string, message: string, onConfirm: () => void, onCancel: () => void }) => {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/50 backdrop-blur-sm animate-in fade-in duration-200 p-4">
      <div className="bg-white dark:bg-slate-900 p-6 rounded-3xl max-w-sm w-full shadow-2xl border border-slate-200 dark:border-slate-800 animate-in zoom-in-95 duration-200">
        <div className="flex items-center gap-3 mb-4 text-red-600 dark:text-red-500">
          <AlertCircle className="w-6 h-6" />
          <h3 className="text-xl font-bold">{title}</h3>
        </div>
        <p className="text-slate-600 dark:text-slate-400 mb-6 font-medium">{message}</p>
        <div className="flex gap-3">
          <button onClick={onCancel} className="flex-1 px-4 py-3 rounded-xl font-bold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors">Cancel</button>
          <button onClick={onConfirm} className="flex-1 px-4 py-3 rounded-xl font-bold bg-red-600 text-white hover:bg-red-700 shadow-md shadow-red-500/20 transition-all">Yes, Confirm</button>
        </div>
      </div>
    </div>
  );
};

// ==========================================
// 2. LOADING SKELETON COMPONENT
// ==========================================
const SkeletonLoader = () => (
  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-4 animate-pulse">
    {[1, 2, 3, 4, 5, 6].map(i => (
      <div key={i} className="bg-slate-200 dark:bg-slate-800 h-40 rounded-2xl"></div>
    ))}
  </div>
);

// ==========================================
// 3. ISOLATED USER CARD COMPONENT
// ==========================================
const UserCard = ({ user, blocks, onUpdate, isManaging, setManageUserId, triggerConfirm }: { user: User, blocks: Block[], onUpdate: any, isManaging: boolean, setManageUserId: any, triggerConfirm: any }) => {
  const [tmpAi, setTmpAi] = useState(user.ai_allowed !== false);
  const [tmpVoice, setTmpVoice] = useState(user.voice_allowed !== false);
  const [tmpBlockDays, setTmpBlockDays] = useState(0);
  
  const userBlock = blocks.find(b => b.block_value === String(user.telegram_id));
  const isActuallyVerified = user.is_verified && !userBlock;
  const displayName = user.first_name || user.username || 'Unknown User';

  const handleBlockClick = () => {
    triggerConfirm(
      "Restrict User", 
      `Are you sure you want to ${tmpBlockDays > 0 ? `suspend this user for ${tmpBlockDays} days` : 'permanently block this user'}?`,
      () => onUpdate(user.telegram_id, false, tmpAi, tmpVoice, tmpBlockDays)
    );
  };

  return (
    <div className={`bg-slate-50 dark:bg-slate-800/30 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 flex flex-col hover:shadow-md transition-all ${isManaging ? 'ring-2 ring-blue-500 shadow-lg' : ''}`}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          {/* USER INSTRUCTION: Placeholder for actual avatar images from /pages/assets/ */}
          <div className="w-12 h-12 rounded-full overflow-hidden bg-blue-100 dark:bg-blue-900/50 flex items-center justify-center shrink-0 border border-slate-200 dark:border-slate-700">
             <img src="./assets/default-avatar.png" alt={displayName} className="w-full h-full object-cover opacity-0 transition-opacity duration-300" onLoad={(e) => (e.currentTarget.style.opacity = '1')} onError={(e) => { e.currentTarget.style.display = 'none'; e.currentTarget.parentElement!.innerHTML = `<span class="text-blue-700 dark:text-blue-400 font-bold text-lg uppercase">${displayName.charAt(0).toUpperCase()}</span>`; }} />
          </div>
          <div>
            <h3 className="font-bold text-slate-900 dark:text-white line-clamp-1">{displayName}</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">ID: {user.telegram_id}</p>
          </div>
        </div>
        <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-black uppercase tracking-wider border ${isActuallyVerified ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400' : 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400'}`}>
          {isActuallyVerified ? 'Verified' : 'Restricted'}
        </span>
      </div>
      <div className="space-y-1 text-sm mb-4">
        <p className="flex justify-between"><span className="text-slate-500">Email:</span> <span className="font-medium text-slate-700 dark:text-slate-300 truncate max-w-[150px]">{user.email || 'N/A'}</span></p>
        <p className="flex justify-between"><span className="text-slate-500">Joined:</span> <span className="font-medium text-slate-700 dark:text-slate-300">{user.created_at ? new Date(user.created_at).toLocaleDateString() : 'N/A'}</span></p>
      </div>
      
      {isManaging ? (
        <div className="pt-4 border-t border-slate-200 dark:border-slate-800 animate-in slide-in-from-top-2">
          <h4 className="text-xs font-bold text-slate-500 mb-3 uppercase tracking-wider">Granular Permissions</h4>
          <div className="space-y-3 mb-4">
            <label className="flex items-center justify-between text-sm font-medium text-slate-700 dark:text-slate-300">
              <span className="flex items-center gap-2"><ShieldOff className="w-4 h-4 text-slate-400"/> Allow AI Engine</span>
              <input type="checkbox" checked={tmpAi} onChange={(e) => setTmpAi(e.target.checked)} className="w-4 h-4 rounded text-blue-600 border-slate-300" />
            </label>
            <label className="flex items-center justify-between text-sm font-medium text-slate-700 dark:text-slate-300">
              <span className="flex items-center gap-2"><MicOff className="w-4 h-4 text-slate-400"/> Allow Voice Notes</span>
              <input type="checkbox" checked={tmpVoice} onChange={(e) => setTmpVoice(e.target.checked)} className="w-4 h-4 rounded text-blue-600 border-slate-300" />
            </label>
            <label className="flex items-center justify-between text-sm font-medium text-slate-700 dark:text-slate-300">
              <span className="flex items-center gap-2"><CalendarClock className="w-4 h-4 text-slate-400"/> Temp Ban (Days)</span>
              <input type="number" min="0" max="365" value={tmpBlockDays} onChange={(e) => setTmpBlockDays(Number(e.target.value))} className="w-16 p-1 text-center bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-md outline-none dark:text-white" />
            </label>
          </div>
          
          <div className="flex gap-2">
            <button onClick={() => onUpdate(user.telegram_id, true, tmpAi, tmpVoice, 0)} className="flex-1 bg-emerald-500 text-white py-2 rounded-xl text-sm font-bold hover:bg-emerald-600 transition-all shadow-sm">Save/Approve</button>
            <button onClick={handleBlockClick} className="flex-1 bg-red-500 text-white py-2 rounded-xl text-sm font-bold hover:bg-red-600 transition-all shadow-sm">Block/Suspend</button>
            <button onClick={() => setManageUserId(null)} className="px-3 bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-xl hover:bg-slate-300 dark:hover:bg-slate-600"><X className="w-4 h-4"/></button>
          </div>
        </div>
      ) : (
        <div className="pt-3 border-t border-slate-200 dark:border-slate-800 mt-auto flex gap-2">
          {!isActuallyVerified ? (
            <button onClick={() => triggerConfirm("Approve User", "Are you sure you want to grant this user access to the AI system?", () => onUpdate(user.telegram_id, true, true, true, 0))} className="flex-1 bg-blue-600 text-white py-2.5 rounded-xl font-bold hover:bg-blue-700 transition-all text-sm shadow-sm">Approve User</button>
          ) : (
            <button onClick={() => setManageUserId(user.telegram_id)} className="flex-1 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 py-2.5 rounded-xl font-bold hover:bg-slate-200 dark:hover:bg-slate-700 transition-all text-sm flex items-center justify-center gap-2"><Settings2 className="w-4 h-4" /> Manage Access</button>
          )}
        </div>
      )}
    </div>
  );
};

// ==========================================
// 4. MAIN DASHBOARD COMPONENT
// ==========================================
const Dashboard = () => {
  const [activeTab, setActiveTab] = useState('stats');
  
  // Data States
  const [users, setUsers] = useState<User[]>([]);
  const [admins, setAdmins] = useState<Admin[]>([]);
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [sttUsage, setSttUsage] = useState<STTUsage[]>([]);
  const [scheduledEmails, setScheduledEmails] = useState<ScheduledEmail[]>([]);
  
  // UI & Loading States
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [role, setRole] = useState<string>('');
  const [manageUserId, setManageUserId] = useState<number | null>(null);
  const [toast, setToast] = useState<{msg: string, type: 'success' | 'error'} | null>(null);
  
  // Pagination States
  const [userPage, setUserPage] = useState(1);
  const [blockPage, setBlockPage] = useState(1);
  const ITEMS_PER_PAGE = 9;

  // Confirmation Modal State
  const [confirmModal, setConfirmModal] = useState<{isOpen: boolean, title: string, message: string, onConfirm: () => void}>({ isOpen: false, title: '', message: '', onConfirm: () => {} });

  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [showBanner, setShowBanner] = useState(localStorage.getItem('password_setup_dismissed') !== 'true');
  const [adminEmail, setAdminEmail] = useState(localStorage.getItem('admin_email') || '');

  // Reset pagination when searching or changing tabs
  useEffect(() => { setUserPage(1); setBlockPage(1); }, [searchQuery, activeTab]);

  useEffect(() => {
    let timeoutId: NodeJS.Timeout;
    const resetTimer = () => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => {
        localStorage.clear();
        navigate('/admin/login?error=Session+expired+due+to+inactivity');
      }, 600000); 
    };
    const events = ['mousemove', 'keydown', 'scroll', 'click', 'touchstart'];
    events.forEach(event => window.addEventListener(event, resetTimer));
    resetTimer();
    return () => { clearTimeout(timeoutId); events.forEach(event => window.removeEventListener(event, resetTimer)); };
  }, [navigate]);

  useEffect(() => {
    const urlEmail = searchParams.get('email');
    if (urlEmail) {
      const cleanEmail = urlEmail.toLowerCase().trim();
      localStorage.setItem('admin_email', cleanEmail);
      setAdminEmail(cleanEmail);
      searchParams.delete('email');
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

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

  const openConfirm = (title: string, message: string, onConfirm: () => void) => {
    setConfirmModal({
      isOpen: true, title, message, 
      onConfirm: () => { onConfirm(); setConfirmModal(prev => ({ ...prev, isOpen: false })); }
    });
  };

  const getHeaders = () => ({ 'Content-Type': 'application/json', 'x-admin-email': adminEmail });

  // 100% Correct Logic: Catch silent fails, 401 kicks out.
  const fetchRole = async () => {
    try {
      const response = await fetch(`${backendUrl}/api/admin/role`, { headers: getHeaders() });
      if (response.ok) {
        const data = await response.json();
        setRole(data.role || 'admin');
      } else if (response.status === 401) {
        localStorage.clear();
        navigate('/admin/login?error=Access+Revoked+or+Session+Expired');
      }
    } catch (err) { 
      console.error("Network delay or server timeout", err); 
    }
  };

  const fetchData = async () => {
    setIsLoading(true);
    try {
      const [usersRes, adminsRes, blocksRes, statsRes, sttRes, schedRes] = await Promise.all([
        fetch(`${backendUrl}/api/admin/users`, { headers: getHeaders() }),
        fetch(`${backendUrl}/api/admin/admins`, { headers: getHeaders() }),
        fetch(`${backendUrl}/api/admin/blocks`, { headers: getHeaders() }),
        fetch(`${backendUrl}/api/admin/stats`, { headers: getHeaders() }),
        fetch(`${backendUrl}/api/admin/stt_usage`, { headers: getHeaders() }),
        fetch(`${backendUrl}/api/admin/scheduled_emails`, { headers: getHeaders() }),
      ]);
      
      if (usersRes.ok) setUsers(await usersRes.json() || []);
      if (adminsRes.ok) setAdmins(await adminsRes.json() || []);
      if (blocksRes.ok) setBlocks(await blocksRes.json() || []);
      if (statsRes.ok) setStats(await statsRes.json() || null);
      if (sttRes.ok) { const d = await sttRes.json(); setSttUsage(d.stt_usage || []); }
      if (schedRes.ok) { const d = await schedRes.json(); setScheduledEmails(d.scheduled_emails || []); }
      
    } catch (err) { console.error('Data fetch failed', err); }
    finally { setIsLoading(false); }
  };

  // Pagination Logic
  const filteredUsers = users.filter((u) => 
    (u.first_name || '').toLowerCase().includes(searchQuery.toLowerCase()) || 
    (u.username || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
    (u.email || '').toLowerCase().includes(searchQuery.toLowerCase())
  );
  const totalUserPages = Math.ceil(filteredUsers.length / ITEMS_PER_PAGE);
  const paginatedUsers = filteredUsers.slice((userPage - 1) * ITEMS_PER_PAGE, userPage * ITEMS_PER_PAGE);

  const totalBlockPages = Math.ceil(blocks.length / ITEMS_PER_PAGE);
  const paginatedBlocks = blocks.slice((blockPage - 1) * ITEMS_PER_PAGE, blockPage * ITEMS_PER_PAGE);

  const sentEmails = scheduledEmails.filter(e => e.status === 'sent').length;
  const pendingEmails = scheduledEmails.filter(e => e.status === 'pending').length;
  const failedEmails = scheduledEmails.filter(e => e.status === 'failed').length;

  const updatePermissions = async (tgId: number, is_verified: boolean, ai_allowed: boolean, voice_allowed: boolean, block_days: number) => {
    try {
      const payload = { is_verified, ai_allowed, voice_allowed, block_days, reason: "Admin enforced restrictions" };
      const res = await fetch(`${backendUrl}/api/admin/users/${tgId}/permissions`, { 
        method: 'POST', headers: getHeaders(), body: JSON.stringify(payload)
      }); 
      if(res.ok) { 
        showNotification('Permissions updated securely!', 'success'); 
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

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 font-sans pb-20 transition-colors duration-500 selection:bg-blue-500/30 relative">
      <Navbar />

      <ConfirmModal 
        isOpen={confirmModal.isOpen} 
        title={confirmModal.title} 
        message={confirmModal.message} 
        onConfirm={confirmModal.onConfirm} 
        onCancel={() => setConfirmModal(prev => ({ ...prev, isOpen: false }))} 
      />

      {toast && (
        <div className={`fixed bottom-8 right-8 z-[90] flex items-center gap-3 px-6 py-4 rounded-2xl font-bold text-sm shadow-2xl animate-in fade-in slide-in-from-bottom-5 duration-300 text-white ${toast.type === 'success' ? 'bg-emerald-600' : 'bg-red-600'}`}>
          {toast.type === 'success' ? <CheckCircle className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}
          {toast.msg}
        </div>
      )}

      {showBanner && (
        <div className="bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-md animate-in slide-in-from-top-2 duration-500">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex flex-col sm:flex-row items-center justify-between gap-3">
            <div className="flex items-center gap-3 text-center sm:text-left">
              <Zap className="w-5 h-5 text-amber-300 shrink-0 hidden sm:block" />
              <p className="text-sm font-medium"><strong className="font-bold mr-1">Want to login faster next time?</strong> Set up a manual password.</p>
            </div>
            <div className="flex items-center gap-4 shrink-0 mt-2 sm:mt-0">
              <Link to="/admin/settings" className="bg-white text-indigo-700 px-4 py-1.5 rounded-full text-xs font-black uppercase tracking-wider hover:bg-blue-50 transition-colors shadow-sm">Setup</Link>
              <button onClick={() => { localStorage.setItem('password_setup_dismissed', 'true'); setShowBanner(false); }} className="p-1 hover:bg-white/20 rounded-full transition-colors"><X className="w-5 h-5" /></button>
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
                  {tab === 'stats' && <LineChart className="w-4 h-4" />}
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
        
        {/* ======================= STATS VIEW ======================= */}
        {activeTab === 'stats' && (
          isLoading ? <SkeletonLoader /> : stats ? (
            <div className="space-y-8">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                {[
                  { label: 'Total Users', val: stats.total_users || 0, color: 'from-blue-500 to-indigo-600', icon: Users },
                  { label: 'Verified Accounts', val: stats.verified_users || 0, color: 'from-emerald-500 to-teal-600', icon: CheckCircle },
                  { label: 'Blocked Threats', val: stats.blocked_users || 0, color: 'from-rose-500 to-red-600', icon: ShieldAlert },
                  { label: 'Total Convos', val: stats.total_conversations || 0, color: 'from-purple-500 to-fuchsia-600', icon: Activity },
                ].map((s) => (
                  <div key={s.label} className="group relative bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm hover:shadow-xl transition-all duration-300 overflow-hidden cursor-default">
                    <div className={`absolute top-0 right-0 w-32 h-32 bg-gradient-to-br ${s.color} opacity-5 group-hover:opacity-10 rounded-bl-full transition-opacity duration-500`}></div>
                    <div className="flex justify-between items-start mb-4">
                      <div className={`p-3 rounded-2xl bg-gradient-to-br ${s.color} text-white shadow-md group-hover:scale-110 transition-transform duration-300`}><s.icon className="w-6 h-6" /></div>
                      <ArrowUpRight className="w-5 h-5 text-slate-300 dark:text-slate-600 group-hover:text-slate-400 transition-colors" />
                    </div>
                    <h3 className="font-bold text-slate-500 dark:text-slate-400 text-sm tracking-wide">{s.label}</h3>
                    <p className="text-4xl font-black text-slate-900 dark:text-white mt-1 tracking-tight">{s.val}</p>
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="bg-white dark:bg-slate-900 p-6 sm:p-8 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm">
                  <div className="flex items-center justify-between mb-6">
                    <div>
                      <h3 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2"><Mic className="w-5 h-5 text-indigo-500" /> STT Audio Processed</h3>
                      <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Total audio transcribed by AI (in seconds)</p>
                    </div>
                    <div className="text-3xl font-black text-indigo-600 dark:text-indigo-400">{stats.total_stt_seconds_used}s</div>
                  </div>
                  <div className="mt-8 space-y-3">
                    <div className="flex justify-between text-xs font-bold text-slate-500 dark:text-slate-400">
                      <span>Server Load (Whisper/Gemini)</span>
                      <span>{sttUsage.length} requests</span>
                    </div>
                    <div className="w-full bg-slate-100 dark:bg-slate-800 rounded-full h-4 overflow-hidden flex">
                      <div className="bg-indigo-500 h-full rounded-full animate-[pulse_2s_ease-in-out_infinite]" style={{ width: `${Math.min((stats.total_stt_seconds_used / 1000) * 100, 100)}%` }}></div>
                    </div>
                  </div>
                </div>

                <div className="bg-white dark:bg-slate-900 p-6 sm:p-8 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm">
                  <div className="flex items-center justify-between mb-6">
                    <div>
                      <h3 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2"><Mail className="w-5 h-5 text-blue-500" /> Scheduled Emails</h3>
                      <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Queue & Dispatch Status</p>
                    </div>
                    <div className="text-3xl font-black text-blue-600 dark:text-blue-400">{stats.total_scheduled_emails}</div>
                  </div>
                  <div className="mt-6 flex h-12 rounded-xl overflow-hidden shadow-inner">
                    {stats.total_scheduled_emails === 0 ? (
                      <div className="w-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-xs text-slate-400 font-bold">No Emails Scheduled</div>
                    ) : (
                      <>
                        <div style={{width: `${(sentEmails/stats.total_scheduled_emails)*100}%`}} className="bg-emerald-500 hover:opacity-90 flex items-center justify-center text-white text-xs font-bold">{sentEmails > 0 && sentEmails}</div>
                        <div style={{width: `${(pendingEmails/stats.total_scheduled_emails)*100}%`}} className="bg-amber-400 hover:opacity-90 flex items-center justify-center text-amber-900 text-xs font-bold">{pendingEmails > 0 && pendingEmails}</div>
                        <div style={{width: `${(failedEmails/stats.total_scheduled_emails)*100}%`}} className="bg-rose-500 hover:opacity-90 flex items-center justify-center text-white text-xs font-bold">{failedEmails > 0 && failedEmails}</div>
                      </>
                    )}
                  </div>
                  <div className="flex items-center justify-between mt-4 text-xs font-bold text-slate-500 dark:text-slate-400">
                    <span className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-full bg-emerald-500"></div> Sent ({sentEmails})</span>
                    <span className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-full bg-amber-400"></div> Pending ({pendingEmails})</span>
                    <span className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-full bg-rose-500"></div> Failed ({failedEmails})</span>
                  </div>
                </div>
              </div>
            </div>
          ) : null
        )}

        {/* ======================= USERS VIEW (WITH PAGINATION) ======================= */}
        {activeTab === 'users' && (
          <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm transition-colors duration-500">
            <div className="p-5 sm:p-6 border-b border-slate-100 dark:border-slate-800/50 flex flex-col sm:flex-row justify-between gap-4 items-center bg-slate-50/50 dark:bg-slate-900/50 rounded-t-3xl">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2"><Users className="w-5 h-5 text-blue-500" /> User Directory</h2>
              <div className="relative w-full sm:w-80 group">
                <Search className="absolute left-3 top-3 w-5 h-5 text-slate-400 transition-colors" />
                <input type="text" placeholder="Search by name or email..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="w-full pl-10 pr-4 py-2.5 bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl text-sm outline-none focus:ring-2 focus:ring-blue-500/50 dark:text-white transition-all shadow-sm" />
              </div>
            </div>

            {isLoading ? <SkeletonLoader /> : (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-4">
                  {paginatedUsers.length === 0 ? (
                    <div className="col-span-full flex flex-col items-center justify-center py-12 text-slate-500">
                      {/* USER INSTRUCTION: Placeholder for empty state image */}
                      <img src="./assets/empty-state.png" alt="No data" className="w-32 h-32 mb-4 opacity-50" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                      <p className="font-medium">No users found.</p>
                    </div>
                  ) : (
                    paginatedUsers.map((user) => (
                      <UserCard key={user.telegram_id} user={user} blocks={blocks} onUpdate={updatePermissions} isManaging={manageUserId === user.telegram_id} setManageUserId={setManageUserId} triggerConfirm={openConfirm} />
                    ))
                  )}
                </div>
                
                {/* Pagination Controls */}
                {totalUserPages > 1 && (
                  <div className="p-4 border-t border-slate-100 dark:border-slate-800/50 flex justify-between items-center bg-slate-50/50 dark:bg-slate-950/50">
                    <button disabled={userPage === 1} onClick={() => setUserPage(p => p - 1)} className="p-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 disabled:opacity-30 hover:bg-slate-200 dark:hover:bg-slate-800 flex items-center gap-1"><ChevronLeft className="w-4 h-4"/> Prev</button>
                    <span className="text-sm font-bold text-slate-500">Page {userPage} of {totalUserPages}</span>
                    <button disabled={userPage === totalUserPages} onClick={() => setUserPage(p => p + 1)} className="p-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 disabled:opacity-30 hover:bg-slate-200 dark:hover:bg-slate-800 flex items-center gap-1">Next <ChevronRight className="w-4 h-4"/></button>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* ======================= BLOCKLIST VIEW (WITH PAGINATION) ======================= */}
        {activeTab === 'blocklist' && (
          <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm transition-colors duration-500">
            <div className="p-6 border-b border-slate-100 dark:border-slate-800/50 bg-slate-50/50 dark:bg-slate-900/50">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2"><Ban className="w-5 h-5 text-red-500" /> Restricted Entities</h2>
            </div>
            
            {isLoading ? <div className="p-8 text-center text-slate-400 font-bold animate-pulse">Loading blocklist data...</div> : (
              <div className="overflow-x-auto w-full">
                <table className="w-full text-left min-w-[700px]">
                  <thead className="bg-slate-50 dark:bg-slate-950/50 text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider border-b border-slate-100 dark:border-slate-800">
                    <tr><th className="p-5 pl-8">Target Identity</th><th className="p-5">Block Reason & Expiry</th><th className="p-5 pr-8 text-right">Actions</th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50 dark:divide-slate-800/50">
                    {paginatedBlocks.length === 0 ? (
                       <tr><td colSpan={3} className="p-10 text-center text-slate-500 dark:text-slate-400 font-medium">No active restrictions.</td></tr>
                    ) : (
                      paginatedBlocks.map((block) => (
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
                            <button onClick={() => openConfirm("Lift Restriction", "Are you sure you want to lift this restriction?", () => removeBlock(block.id))} className="text-slate-500 dark:text-slate-400 font-bold text-sm bg-slate-100 dark:bg-slate-800 px-4 py-2 rounded-xl hover:bg-slate-900 hover:text-white dark:hover:bg-slate-700 transition-colors border border-slate-200 dark:border-slate-700">Lift</button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
                
                {/* Blocklist Pagination */}
                {totalBlockPages > 1 && (
                  <div className="p-4 border-t border-slate-100 dark:border-slate-800/50 flex justify-between items-center bg-slate-50/50 dark:bg-slate-950/50">
                    <button disabled={blockPage === 1} onClick={() => setBlockPage(p => p - 1)} className="p-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-600 disabled:opacity-30 flex items-center gap-1"><ChevronLeft className="w-4 h-4"/> Prev</button>
                    <span className="text-sm font-bold text-slate-500">Page {blockPage} of {totalBlockPages}</span>
                    <button disabled={blockPage === totalBlockPages} onClick={() => setBlockPage(p => p + 1)} className="p-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-600 disabled:opacity-30 flex items-center gap-1">Next <ChevronRight className="w-4 h-4"/></button>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ======================= ADMINS VIEW ======================= */}
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
              <form onSubmit={(e) => { e.preventDefault(); openConfirm("Add Admin", `Are you sure you want to grant admin access to ${(e.target as HTMLFormElement).email.value}?`, () => { addAdmin((e.target as HTMLFormElement).email.value); (e.target as HTMLFormElement).reset(); }); }} className="flex flex-col sm:flex-row gap-4 max-w-2xl">
                <input type="email" name="email" required placeholder="admin@company.com" className="flex-1 p-4 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl outline-none text-slate-900 dark:text-white font-medium" />
                <button type="submit" className="bg-indigo-600 text-white px-8 py-4 rounded-xl font-bold hover:bg-indigo-700 transition-all shadow-lg">Grant Access</button>
              </form>
            </div>
            
            <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm transition-colors duration-500">
              <div className="p-6 border-b border-slate-100 dark:border-slate-800/50 bg-slate-50/50 dark:bg-slate-900/50">
                <h2 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2"><Shield className="w-5 h-5 text-purple-500" /> Active Administrators</h2>
              </div>
              
              {isLoading ? <div className="p-8 text-center text-slate-400 font-bold animate-pulse">Loading admins...</div> : (
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
                            <span className={`px-3 py-1.5 rounded-full text-[10px] font-black tracking-widest uppercase border ${(admin.role || '').includes('super') ? 'bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-500/10 dark:text-purple-400' : 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-400'}`}>
                              {(admin.role || 'admin').replace('_', ' ')}
                            </span>
                          </td>
                          <td className="p-5 pr-8 text-right">
                            {admin.role !== 'super_admin' ? (
                              <button onClick={() => openConfirm("Revoke Admin", "Are you sure you want to revoke this admin's access?", () => removeAdmin(admin.id))} className="text-slate-400 hover:text-red-600 dark:hover:text-red-400 p-2 rounded-xl hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors inline-flex items-center gap-2 text-sm font-bold border border-transparent dark:hover:border-red-500/30">
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
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;