import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import Navbar from '../components/Navbar';
import {
  Users, ShieldAlert, CheckCircle, Activity, Shield, Ban, Search,
  UserPlus, Trash2, ArrowUpRight, Zap, X, AlertCircle,
  MicOff, CalendarClock, LineChart, Mail, Mic, ShieldOff,
  ChevronLeft, ChevronRight, ChevronDown, ChevronUp, MessageSquare
} from 'lucide-react';

interface User { telegram_id: number; first_name: string; username: string; email: string; is_verified: boolean; ai_allowed?: boolean; voice_allowed?: boolean; created_at: string; }
interface Admin { id: string; email: string; role: string; }
interface Block { id: string; block_type: string; block_value: string; reason: string; expires_at?: string; }
interface Stats { total_users: number; verified_users: number; blocked_users: number; total_admins: number; total_stt_seconds_used: number; total_scheduled_emails: number; total_conversations: number; }
interface STTUsage { id: string; duration_seconds: number; method: string; created_at: string; }
interface ScheduledEmail { id: string; to_email: string; status: string; scheduled_time: string; }
interface ContactMessage { id: string; sender_email: string; message_text: string; status: string; created_at: string; reviewed_by?: string; }

const backendUrl = import.meta.env.VITE_BACKEND_URL || '';

// ── Confirm Modal ──────────────────────────────────────────────────────────────
const ConfirmModal = ({ isOpen, title, message, onConfirm, onCancel }: { isOpen: boolean; title: string; message: string; onConfirm: () => void; onCancel: () => void; }) => {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200 p-4">
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

// ── Skeleton Loader ────────────────────────────────────────────────────────────
const ListSkeletonLoader = () => (
  <div className="space-y-3 p-4 animate-pulse">
    {[1, 2, 3, 4, 5].map(i => (
      <div key={i} className="bg-slate-200 dark:bg-slate-800/50 h-20 rounded-2xl w-full" />
    ))}
  </div>
);

// ── Accordion User Item ────────────────────────────────────────────────────────
const AccordionUserItem = ({ user, blocks, onUpdate, isManaging, setManageUserId, triggerConfirm }: {
  user: User; blocks: Block[]; onUpdate: any; isManaging: boolean; setManageUserId: any; triggerConfirm: any;
}) => {
  const [tmpAi, setTmpAi] = useState(user.ai_allowed !== false);
  const [tmpVoice, setTmpVoice] = useState(user.voice_allowed !== false);
  const [tmpBlockDays, setTmpBlockDays] = useState(0);

  const userBlock = blocks.find(b => b.block_value === String(user.telegram_id));
  const isActuallyVerified = user.is_verified && !userBlock;
  const displayName = user.first_name || user.username || 'Unknown User';

  const handleBlockClick = () => {
    triggerConfirm(
      'Restrict User',
      `Are you sure you want to ${tmpBlockDays > 0 ? `suspend this user for ${tmpBlockDays} days` : 'permanently block this user'}?`,
      () => onUpdate(user.telegram_id, false, tmpAi, tmpVoice, tmpBlockDays)
    );
  };

  return (
    <div className={`bg-white dark:bg-slate-900/40 border transition-all duration-300 overflow-hidden ${isManaging ? 'border-blue-400 dark:border-blue-500/50 shadow-md rounded-3xl my-4' : 'border-slate-200 dark:border-slate-800 rounded-2xl mb-3 hover:border-blue-300 dark:hover:border-slate-700'}`}>
      <div onClick={() => isManaging ? setManageUserId(null) : setManageUserId(user.telegram_id)} className="p-4 sm:p-5 flex items-center justify-between cursor-pointer group">
        <div className="flex items-center gap-3 sm:gap-4 overflow-hidden">
          <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-blue-100 dark:bg-blue-900/50 flex items-center justify-center shrink-0 border border-slate-200 dark:border-slate-700">
            <span className="text-blue-700 dark:text-blue-400 font-black text-sm sm:text-lg uppercase">{displayName.charAt(0)}</span>
          </div>
          <div className="flex flex-col truncate">
            <h3 className="font-bold text-sm sm:text-base text-slate-900 dark:text-white truncate group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">{displayName}</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 truncate">{user.email || `ID: ${user.telegram_id}`}</p>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className={`hidden sm:inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-black uppercase tracking-wider border ${isActuallyVerified ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400' : 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400'}`}>
            {isActuallyVerified ? 'Verified' : 'Restricted'}
          </span>
          <div className={`p-2 rounded-full transition-colors ${isManaging ? 'bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400' : 'text-slate-400 group-hover:bg-slate-50 dark:group-hover:bg-slate-800'}`}>
            {isManaging ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
          </div>
        </div>
      </div>
      
      {isManaging && (
        <div className="p-4 sm:p-5 border-t border-slate-100 dark:border-slate-800/50 bg-slate-50/50 dark:bg-slate-950/30 animate-in slide-in-from-top-2 duration-300">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h4 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-3">User Details</h4>
              <div className="space-y-2 text-sm">
                <p className="flex justify-between border-b border-slate-200 dark:border-slate-800 pb-1"><span className="text-slate-500">Telegram ID:</span><span className="font-bold text-slate-700 dark:text-slate-300">{user.telegram_id}</span></p>
                <p className="flex justify-between border-b border-slate-200 dark:border-slate-800 pb-1"><span className="text-slate-500">Email:</span><span className="font-bold text-slate-700 dark:text-slate-300">{user.email || 'N/A'}</span></p>
                <p className="flex justify-between border-b border-slate-200 dark:border-slate-800 pb-1"><span className="text-slate-500">Joined On:</span><span className="font-bold text-slate-700 dark:text-slate-300">{user.created_at ? new Date(user.created_at).toLocaleDateString() : 'N/A'}</span></p>
                <p className="flex justify-between pb-1 sm:hidden"><span className="text-slate-500">Status:</span><span className={`font-bold ${isActuallyVerified ? 'text-emerald-600' : 'text-amber-600'}`}>{isActuallyVerified ? 'Verified' : 'Restricted'}</span></p>
              </div>
            </div>
            <div>
              <h4 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-3">Granular Controls</h4>
              <div className="space-y-3 mb-5">
                <label className="flex items-center justify-between text-sm font-medium text-slate-700 dark:text-slate-300 p-2 hover:bg-white dark:hover:bg-slate-900 rounded-lg transition-colors cursor-pointer">
                  <span className="flex items-center gap-2"><ShieldOff className="w-4 h-4 text-slate-400" /> Allow AI Engine</span>
                  <input type="checkbox" checked={tmpAi} onChange={(e) => setTmpAi(e.target.checked)} className="w-4 h-4 rounded text-blue-600 border-slate-300" />
                </label>
                <label className="flex items-center justify-between text-sm font-medium text-slate-700 dark:text-slate-300 p-2 hover:bg-white dark:hover:bg-slate-900 rounded-lg transition-colors cursor-pointer">
                  <span className="flex items-center gap-2"><MicOff className="w-4 h-4 text-slate-400" /> Allow Voice Notes</span>
                  <input type="checkbox" checked={tmpVoice} onChange={(e) => setTmpVoice(e.target.checked)} className="w-4 h-4 rounded text-blue-600 border-slate-300" />
                </label>
                <label className="flex items-center justify-between text-sm font-medium text-slate-700 dark:text-slate-300 p-2">
                  <span className="flex items-center gap-2"><CalendarClock className="w-4 h-4 text-slate-400" /> Temp Ban (Days)</span>
                  <input type="number" min="0" max="365" value={tmpBlockDays} onChange={(e) => setTmpBlockDays(Number(e.target.value))} className="w-16 p-1 text-center bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-md outline-none dark:text-white" />
                </label>
              </div>
              <div className="flex flex-col sm:flex-row gap-2">
                <button onClick={() => onUpdate(user.telegram_id, true, tmpAi, tmpVoice, 0)} className="flex-1 bg-emerald-500 text-white py-2.5 rounded-xl text-sm font-bold hover:bg-emerald-600 transition-all shadow-sm">Save / Approve</button>
                <button onClick={handleBlockClick} className="flex-1 bg-red-500 text-white py-2.5 rounded-xl text-sm font-bold hover:bg-red-600 transition-all shadow-sm">{tmpBlockDays > 0 ? 'Suspend User' : 'Block Fully'}</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ── Main Dashboard ─────────────────────────────────────────────────────────────
const Dashboard = () => {
  const [activeTab, setActiveTab] = useState('stats');
  const [users, setUsers] = useState<User[]>([]);
  const [admins, setAdmins] = useState<Admin[]>([]);
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [sttUsage, setSttUsage] = useState<STTUsage[]>([]);
  const [scheduledEmails, setScheduledEmails] = useState<ScheduledEmail[]>([]);
  const [contactMessages, setContactMessages] = useState<ContactMessage[]>([]);
  const [cacheStats, setCacheStats] = useState<{ hits: number; misses: number; user_count: number } | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [role, setRole] = useState<string>('');
  const [manageUserId, setManageUserId] = useState<number | null>(null);
  const [toast, setToast] = useState<{ msg: string; type: 'success' | 'error' } | null>(null);
  const [userPage, setUserPage] = useState(1);
  const [blockPage, setBlockPage] = useState(1);
  const ITEMS_PER_PAGE = 10;
  const [confirmModal, setConfirmModal] = useState<{ isOpen: boolean; title: string; message: string; onConfirm: () => void }>({ isOpen: false, title: '', message: '', onConfirm: () => {} });
  const [showBanner, setShowBanner] = useState(localStorage.getItem('password_setup_dismissed') !== 'true');
  const [adminEmail, setAdminEmail] = useState(localStorage.getItem('admin_email') || '');

  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  useEffect(() => { setUserPage(1); setBlockPage(1); setManageUserId(null); }, [searchQuery, activeTab]);

  // Session timeout — 10 minutes inactivity
  useEffect(() => {
    let timeoutId: ReturnType<typeof setTimeout>;
    const reset = () => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => {
        localStorage.clear();
        window.location.href = '/admin/login?error=Session+expired+due+to+inactivity';
      }, 600000);
    };
    const events = ['mousemove', 'keydown', 'scroll', 'click', 'touchstart'];
    events.forEach(e => window.addEventListener(e, reset));
    reset();
    return () => { clearTimeout(timeoutId); events.forEach(e => window.removeEventListener(e, reset)); };
  }, [navigate]);

  // Handle token + email from URL (Google OAuth redirect)
  useEffect(() => {
    const urlToken = searchParams.get('token');
    const urlEmail = searchParams.get('email');
    if (urlToken && urlEmail) {
      localStorage.setItem('admin_token', urlToken);
      localStorage.setItem('admin_email', urlEmail.toLowerCase().trim());
      try {
        const payload = JSON.parse(atob(urlToken.split('.')[1]));
        localStorage.setItem('admin_role', payload.role || 'admin');
      } catch (_) {}
      setAdminEmail(urlEmail.toLowerCase().trim());
      searchParams.delete('token');
      searchParams.delete('email');
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    if (adminEmail) { fetchRole(); fetchData(); }
  }, [adminEmail]);

  const showNotification = (msg: string, type: 'success' | 'error' = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  const openConfirm = (title: string, message: string, onConfirm: () => void) => {
    setConfirmModal({ isOpen: true, title, message, onConfirm: () => { onConfirm(); setConfirmModal(p => ({ ...p, isOpen: false })); } });
  };

  // Use JWT Bearer token for all requests
  const getHeaders = () => ({
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${localStorage.getItem('admin_token') || ''}`,
  });

  const fetchRole = async () => {
    try {
      const res = await fetch(`${backendUrl}/api/admin/role`, { headers: getHeaders() });
      if (res.ok) {
        const data = await res.json();
        const r = data.role || 'admin';
        setRole(r);
        localStorage.setItem('admin_role', r);
      } else if (res.status === 401) {
        localStorage.removeItem('admin_token');
        localStorage.removeItem('admin_email');
        localStorage.removeItem('admin_role');
        navigate('/admin/login?error=Access+Revoked+or+Session+Expired');
      }
    } catch (err) { console.error('Role fetch error:', err); }
  };

  const fetchData = async () => {
    setIsLoading(true);
    try {
      const [usersRes, adminsRes, blocksRes, statsRes, sttRes, schedRes, contactRes, cacheRes] = await Promise.all([
        fetch(`${backendUrl}/api/admin/users`, { headers: getHeaders() }),
        fetch(`${backendUrl}/api/admin/admins`, { headers: getHeaders() }),
        fetch(`${backendUrl}/api/admin/blocks`, { headers: getHeaders() }),
        fetch(`${backendUrl}/api/admin/stats`, { headers: getHeaders() }),
        fetch(`${backendUrl}/api/admin/stt_usage`, { headers: getHeaders() }),
        fetch(`${backendUrl}/api/admin/scheduled_emails`, { headers: getHeaders() }),
        fetch(`${backendUrl}/api/admin/contact_messages`, { headers: getHeaders() }),
        fetch(`${backendUrl}/api/admin/cache-stats`, { headers: getHeaders() }),
      ]);
      if (usersRes.ok) setUsers(await usersRes.json() || []);
      if (adminsRes.ok) setAdmins(await adminsRes.json() || []);
      if (blocksRes.ok) setBlocks(await blocksRes.json() || []);
      if (statsRes.ok) setStats(await statsRes.json() || null);
      if (sttRes.ok) { const d = await sttRes.json(); setSttUsage(d.stt_usage || []); }
      if (schedRes.ok) { const d = await schedRes.json(); setScheduledEmails(d.scheduled_emails || []); }
      if (contactRes.ok) { setContactMessages(await contactRes.json() || []); }
      if (cacheRes.ok) setCacheStats(await cacheRes.json() || null);
    } catch (err) { console.error('Data fetch failed', err); }
    finally { setIsLoading(false); }
  };

  const filteredUsers = users.filter(u =>
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
      const res = await fetch(`${backendUrl}/api/admin/users/${tgId}/permissions`, {
        method: 'POST', headers: getHeaders(),
        body: JSON.stringify({ is_verified, ai_allowed, voice_allowed, block_days, reason: 'Admin enforced restrictions' }),
      });
      if (res.ok) { showNotification('Permissions updated securely!'); setManageUserId(null); fetchData(); }
      else { const d = await res.json(); showNotification(d.detail || 'Failed to update', 'error'); }
    } catch { showNotification('Network Error', 'error'); }
  };

  const removeBlock = async (id: string) => {
    try {
      const res = await fetch(`${backendUrl}/api/admin/blocks/${id}`, { method: 'DELETE', headers: getHeaders() });
      if (res.ok) { showNotification('Restriction lifted successfully!'); fetchData(); }
      else showNotification('Failed to lift restriction', 'error');
    } catch { showNotification('Network Error', 'error'); }
  };

  const addAdmin = async (email: string) => {
    try {
      const res = await fetch(`${backendUrl}/api/admin/admins`, {
        method: 'POST', headers: getHeaders(), body: JSON.stringify({ email, role: 'admin' }),
      });
      if (res.ok) { showNotification('New Admin added successfully!'); fetchData(); }
      else showNotification('Failed to add admin', 'error');
    } catch { showNotification('Network Error', 'error'); }
  };

  const removeAdmin = async (id: string) => {
    try {
      const res = await fetch(`${backendUrl}/api/admin/admins/${id}`, { method: 'DELETE', headers: getHeaders() });
      if (res.ok) { showNotification('Admin revoked successfully!'); fetchData(); }
      else showNotification('Failed to remove admin', 'error');
    } catch { showNotification('Network Error', 'error'); }
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-slate-50 via-white to-blue-50 dark:from-slate-950 dark:via-slate-900 dark:to-indigo-950/20 font-sans pb-20 transition-colors duration-500 selection:bg-blue-500/30 relative">
      <Navbar />

      <ConfirmModal isOpen={confirmModal.isOpen} title={confirmModal.title} message={confirmModal.message} onConfirm={confirmModal.onConfirm} onCancel={() => setConfirmModal(p => ({ ...p, isOpen: false }))} />

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

      {/* Tab Bar */}
      <div className="bg-white/60 dark:bg-slate-900/60 backdrop-blur-xl border-b border-slate-200/50 dark:border-slate-800/50 sticky top-20 z-40 transition-colors duration-500 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <div className="flex space-x-2 sm:space-x-6 overflow-x-auto py-2">
            {['stats', 'users', 'blocklist', 'admins', 'messages'].map((tab) => (
              (tab !== 'admins' || role === 'super_admin') && (tab !== 'messages' || true) && (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`flex items-center gap-2 px-4 py-3 rounded-xl font-bold text-sm whitespace-nowrap transition-all duration-300 capitalize ${activeTab === tab ? 'bg-slate-900 text-white dark:bg-blue-600 dark:text-white shadow-md' : 'text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white'}`}
                >
                  {tab === 'stats' && <LineChart className="w-4 h-4" />}
                  {tab === 'users' && <Users className="w-4 h-4" />}
                  {tab === 'blocklist' && <Ban className="w-4 h-4" />}
                  {tab === 'admins' && <Shield className="w-4 h-4" />}
                  {tab === 'messages' && <MessageSquare className="w-4 h-4" />}
                  {tab}
                </button>
              )
            ))}
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 animate-in fade-in slide-in-from-bottom-4 duration-500">

        {/* STATS */}
        {activeTab === 'stats' && (
          isLoading ? <ListSkeletonLoader /> : stats ? (
            <div className="space-y-8">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                {[
                  { label: 'Total Users', val: stats.total_users || 0, color: 'from-blue-500 to-indigo-600', icon: Users },
                  { label: 'Verified Accounts', val: stats.verified_users || 0, color: 'from-emerald-500 to-teal-600', icon: CheckCircle },
                  { label: 'Blocked Threats', val: stats.blocked_users || 0, color: 'from-rose-500 to-red-600', icon: ShieldAlert },
                  { label: 'Total Convos', val: stats.total_conversations || 0, color: 'from-purple-500 to-fuchsia-600', icon: Activity },
                ].map((s) => (
                  <div key={s.label} className="group relative bg-white/80 dark:bg-slate-900/80 backdrop-blur-md p-6 rounded-3xl border border-slate-200/50 dark:border-slate-800/50 shadow-sm hover:shadow-xl transition-all duration-300 overflow-hidden cursor-default">
                    <div className={`absolute top-0 right-0 w-32 h-32 bg-gradient-to-br ${s.color} opacity-5 group-hover:opacity-10 rounded-bl-full transition-opacity duration-500`} />
                    <div className="flex justify-between items-start mb-4">
                      <div className={`p-3 rounded-2xl bg-gradient-to-br ${s.color} text-white shadow-md group-hover:scale-110 transition-transform duration-300`}><s.icon className="w-6 h-6" /></div>
                      <ArrowUpRight className="w-5 h-5 text-slate-300 dark:text-slate-600 group-hover:text-slate-400 transition-colors" />
                    </div>
                    <h3 className="font-bold text-slate-500 dark:text-slate-400 text-sm tracking-wide">{s.label}</h3>
                    <p className="text-4xl font-black text-slate-900 dark:text-white mt-1 tracking-tight">{s.val}</p>
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-md p-6 sm:p-8 rounded-3xl border border-slate-200/50 dark:border-slate-800/50 shadow-sm">
                  <div className="flex items-center justify-between mb-6">
                    <div>
                      <h3 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2"><Mic className="w-5 h-5 text-indigo-500" /> STT Audio Processed</h3>
                      <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Total audio transcribed by AI</p>
                    </div>
                    <div className="text-3xl font-black text-indigo-600 dark:text-indigo-400">{stats.total_stt_seconds_used}s</div>
                  </div>
                  <div className="mt-8 space-y-3">
                    <div className="flex justify-between text-xs font-bold text-slate-500 dark:text-slate-400">
                      <span>Server Load (Whisper/Gemini)</span>
                      <span>{sttUsage.length} requests</span>
                    </div>
                    <div className="w-full bg-slate-100 dark:bg-slate-800 rounded-full h-4 overflow-hidden">
                      <div className="bg-indigo-500 h-full rounded-full animate-pulse" style={{ width: `${Math.min((stats.total_stt_seconds_used / 1000) * 100, 100)}%` }} />
                    </div>
                  </div>
                </div>

                <div className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-md p-6 sm:p-8 rounded-3xl border border-slate-200/50 dark:border-slate-800/50 shadow-sm">
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
                        <div style={{ width: `${(sentEmails / stats.total_scheduled_emails) * 100}%` }} className="bg-emerald-500 flex items-center justify-center text-white text-xs font-bold">{sentEmails > 0 && sentEmails}</div>
                        <div style={{ width: `${(pendingEmails / stats.total_scheduled_emails) * 100}%` }} className="bg-amber-400 flex items-center justify-center text-amber-900 text-xs font-bold">{pendingEmails > 0 && pendingEmails}</div>
                        <div style={{ width: `${(failedEmails / stats.total_scheduled_emails) * 100}%` }} className="bg-rose-500 flex items-center justify-center text-white text-xs font-bold">{failedEmails > 0 && failedEmails}</div>
                      </>
                    )}
                  </div>
                  <div className="flex items-center justify-between mt-4 text-xs font-bold text-slate-500 dark:text-slate-400">
                    <span className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-full bg-emerald-500" /> Sent ({sentEmails})</span>
                    <span className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-full bg-amber-400" /> Pending ({pendingEmails})</span>
                    <span className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-full bg-rose-500" /> Failed ({failedEmails})</span>
                  </div>
                </div>

                <div className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-md p-6 sm:p-8 rounded-3xl border border-slate-200/50 dark:border-slate-800/50 shadow-sm flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between mb-4">
                      <div>
                        <h3 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2"><Zap className="w-5 h-5 text-amber-500" /> RAM Cache Telemetry</h3>
                        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Live hit-rates & active token caching</p>
                      </div>
                    </div>
                    {cacheStats ? (
                      <div className="space-y-6">
                        <div className="grid grid-cols-3 gap-2 text-center">
                          <div className="p-3 bg-slate-50 dark:bg-slate-950/40 rounded-2xl border border-slate-100 dark:border-slate-800/50">
                            <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider block mb-1">Users</span>
                            <p className="text-2xl font-black text-slate-800 dark:text-white">{cacheStats.user_count}</p>
                          </div>
                          <div className="p-3 bg-slate-50 dark:bg-slate-950/40 rounded-2xl border border-slate-100 dark:border-slate-800/50">
                            <span className="text-[10px] font-black text-emerald-500 uppercase tracking-wider block mb-1">Hits</span>
                            <p className="text-2xl font-black text-emerald-600 dark:text-emerald-400">{cacheStats.hits}</p>
                          </div>
                          <div className="p-3 bg-slate-50 dark:bg-slate-950/40 rounded-2xl border border-slate-100 dark:border-slate-800/50">
                            <span className="text-[10px] font-black text-rose-500 uppercase tracking-wider block mb-1">Misses</span>
                            <p className="text-2xl font-black text-rose-600 dark:text-rose-400">{cacheStats.misses}</p>
                          </div>
                        </div>
                        
                        {(() => {
                          const total = cacheStats.hits + cacheStats.misses;
                          const ratio = total > 0 ? Math.round((cacheStats.hits / total) * 100) : 0;
                          return (
                            <div className="space-y-3">
                              <div className="flex justify-between text-xs font-bold text-slate-500 dark:text-slate-400">
                                <span>Optimization Hit-Rate</span>
                                <span>{ratio}%</span>
                              </div>
                              <div className="w-full bg-slate-100 dark:bg-slate-800 rounded-full h-4 overflow-hidden border border-slate-200/20">
                                <div className="bg-gradient-to-r from-emerald-400 to-teal-500 h-full rounded-full transition-all duration-500" style={{ width: `${ratio}%` }} />
                              </div>
                            </div>
                          );
                        })()}
                      </div>
                    ) : (
                      <div className="text-center py-8 text-xs text-slate-400 font-bold">No Cache Telemetry Available</div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ) : null
        )}

        {/* USERS */}
        {activeTab === 'users' && (
          <div className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-md rounded-3xl border border-slate-200/50 dark:border-slate-800/50 shadow-sm transition-colors duration-500">
            <div className="p-5 sm:p-6 border-b border-slate-100 dark:border-slate-800/50 flex flex-col sm:flex-row justify-between gap-4 items-center rounded-t-3xl">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2"><Users className="w-5 h-5 text-blue-500" /> User Directory</h2>
              <div className="relative w-full sm:w-80">
                <Search className="absolute left-3 top-3 w-5 h-5 text-slate-400" />
                <input type="text" placeholder="Search by name or email..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="w-full pl-10 pr-4 py-2.5 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl text-sm outline-none focus:ring-2 focus:ring-blue-500/50 dark:text-white transition-all shadow-inner" />
              </div>
            </div>
            {isLoading ? <ListSkeletonLoader /> : (
              <>
                <div className="p-4 sm:p-6">
                  {paginatedUsers.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-12 text-slate-500">
                      <p className="font-medium text-lg">No users found.</p>
                    </div>
                  ) : (
                    <div className="flex flex-col">
                      {paginatedUsers.map((user) => (
                        <AccordionUserItem key={user.telegram_id} user={user} blocks={blocks} onUpdate={updatePermissions} isManaging={manageUserId === user.telegram_id} setManageUserId={setManageUserId} triggerConfirm={openConfirm} />
                      ))}
                    </div>
                  )}
                </div>
                {totalUserPages > 1 && (
                  <div className="p-4 border-t border-slate-100 dark:border-slate-800/50 flex justify-between items-center bg-slate-50/50 dark:bg-slate-950/50 rounded-b-3xl">
                    <button disabled={userPage === 1} onClick={() => setUserPage(p => p - 1)} className="px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 disabled:opacity-30 hover:bg-slate-200 dark:hover:bg-slate-800 flex items-center gap-1 transition-colors font-bold text-sm"><ChevronLeft className="w-4 h-4" /> Prev</button>
                    <span className="text-sm font-bold text-slate-500">Page {userPage} of {totalUserPages}</span>
                    <button disabled={userPage === totalUserPages} onClick={() => setUserPage(p => p + 1)} className="px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 disabled:opacity-30 hover:bg-slate-200 dark:hover:bg-slate-800 flex items-center gap-1 transition-colors font-bold text-sm">Next <ChevronRight className="w-4 h-4" /></button>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* BLOCKLIST */}
        {activeTab === 'blocklist' && (
          <div className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-md rounded-3xl border border-slate-200/50 dark:border-slate-800/50 overflow-hidden shadow-sm transition-colors duration-500">
            <div className="p-6 border-b border-slate-100 dark:border-slate-800/50 flex items-center gap-2">
              <Ban className="w-5 h-5 text-red-500" />
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">Restricted Entities</h2>
            </div>
            {isLoading ? <ListSkeletonLoader /> : (
              <>
                {/* Desktop table */}
                <div className="hidden sm:block overflow-x-auto w-full">
                  <table className="w-full text-left min-w-[700px]">
                    <thead className="bg-slate-50/50 dark:bg-slate-950/50 text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider border-b border-slate-100 dark:border-slate-800">
                      <tr><th className="p-5 pl-8">Target Identity</th><th className="p-5">Block Reason & Expiry</th><th className="p-5 pr-8 text-right">Actions</th></tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50 dark:divide-slate-800/50">
                      {paginatedBlocks.length === 0 ? (
                        <tr><td colSpan={3} className="p-10 text-center text-slate-500 dark:text-slate-400 font-medium">No active restrictions.</td></tr>
                      ) : paginatedBlocks.map((block) => (
                        <tr key={block.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors">
                          <td className="p-5 pl-8 font-bold text-slate-900 dark:text-white">
                            <span className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest mr-3 bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded-md">{block.block_type || 'ID'}</span>
                            {block.block_value}
                          </td>
                          <td className="p-5 text-sm font-medium text-slate-600 dark:text-slate-400">
                            <div>{block.reason || 'Security Policy Violation'}</div>
                            {block.expires_at && <div className="text-xs text-amber-600 dark:text-amber-400 mt-1 font-bold">Unblocks on: {new Date(block.expires_at).toLocaleString()}</div>}
                          </td>
                          <td className="p-5 pr-8 text-right">
                            <button onClick={() => openConfirm('Lift Restriction', 'Are you sure you want to lift this restriction?', () => removeBlock(block.id))} className="text-slate-500 dark:text-slate-400 font-bold text-sm bg-white dark:bg-slate-800 px-4 py-2 rounded-xl hover:bg-slate-900 hover:text-white dark:hover:bg-slate-700 transition-colors border border-slate-200 dark:border-slate-700 shadow-sm">Lift</button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {/* Mobile stacked */}
                <div className="sm:hidden flex flex-col p-4 gap-3">
                  {paginatedBlocks.length === 0 ? (
                    <div className="py-8 text-center text-slate-500 font-medium">No active restrictions.</div>
                  ) : paginatedBlocks.map((block) => (
                    <div key={block.id} className="bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-2xl p-4 flex flex-col gap-3">
                      <div className="flex justify-between items-start">
                        <div>
                          <span className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest bg-white dark:bg-slate-900 px-2 py-0.5 rounded-md border border-slate-100 dark:border-slate-800">{block.block_type || 'ID'}</span>
                          <div className="font-bold text-slate-900 dark:text-white mt-1">{block.block_value}</div>
                        </div>
                        <button onClick={() => openConfirm('Lift Restriction', 'Are you sure you want to lift this restriction?', () => removeBlock(block.id))} className="text-slate-500 dark:text-slate-300 font-bold text-xs bg-white dark:bg-slate-700 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-600 shadow-sm">Lift</button>
                      </div>
                      <div className="text-xs text-slate-600 dark:text-slate-400">
                        <div>Reason: {block.reason || 'Security Policy Violation'}</div>
                        {block.expires_at && <div className="text-amber-600 dark:text-amber-400 mt-0.5 font-bold">Unblocks on: {new Date(block.expires_at).toLocaleString()}</div>}
                      </div>
                    </div>
                  ))}
                </div>
                {totalBlockPages > 1 && (
                  <div className="p-4 border-t border-slate-100 dark:border-slate-800/50 flex justify-between items-center bg-slate-50/50 dark:bg-slate-950/50">
                    <button disabled={blockPage === 1} onClick={() => setBlockPage(p => p - 1)} className="px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 disabled:opacity-30 hover:bg-slate-200 dark:hover:bg-slate-800 flex items-center gap-1 transition-colors font-bold text-sm"><ChevronLeft className="w-4 h-4" /> Prev</button>
                    <span className="text-sm font-bold text-slate-500">Page {blockPage} of {totalBlockPages}</span>
                    <button disabled={blockPage === totalBlockPages} onClick={() => setBlockPage(p => p + 1)} className="px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 disabled:opacity-30 hover:bg-slate-200 dark:hover:bg-slate-800 flex items-center gap-1 transition-colors font-bold text-sm">Next <ChevronRight className="w-4 h-4" /></button>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* ADMINS */}
        {activeTab === 'admins' && role === 'super_admin' && (
          <div className="space-y-6">
            <div className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-md p-6 sm:p-8 rounded-3xl border border-slate-200/50 dark:border-slate-800/50 shadow-sm transition-colors duration-500">
              <div className="flex items-center gap-3 mb-6">
                <div className="bg-indigo-100 dark:bg-indigo-500/20 p-3 rounded-2xl">
                  <UserPlus className="w-6 h-6 text-indigo-700 dark:text-indigo-400" />
                </div>
                <div>
                  <h2 className="text-xl font-bold text-slate-900 dark:text-white tracking-tight">Provision New Admin</h2>
                  <p className="text-sm text-slate-500 dark:text-slate-400 font-medium">Grant dashboard access to trusted personnel.</p>
                </div>
              </div>
              <form onSubmit={(e) => { e.preventDefault(); const em = (e.target as HTMLFormElement).email.value; openConfirm('Add Admin', `Grant admin access to ${em}?`, () => { addAdmin(em); (e.target as HTMLFormElement).reset(); }); }} className="flex flex-col sm:flex-row gap-4 max-w-2xl">
                <input type="email" name="email" required placeholder="admin@company.com" className="flex-1 p-4 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl outline-none text-slate-900 dark:text-white font-medium shadow-inner" />
                <button type="submit" className="bg-indigo-600 text-white px-8 py-4 rounded-xl font-bold hover:bg-indigo-700 transition-all shadow-lg hover:shadow-indigo-500/30">Grant Access</button>
              </form>
            </div>
            <div className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-md rounded-3xl border border-slate-200/50 dark:border-slate-800/50 overflow-hidden shadow-sm transition-colors duration-500">
              <div className="p-6 border-b border-slate-100 dark:border-slate-800/50 bg-slate-50/50 dark:bg-slate-900/50 flex items-center gap-2">
                <Shield className="w-5 h-5 text-purple-500" />
                <h2 className="text-xl font-bold text-slate-900 dark:text-white">Active Administrators</h2>
              </div>
              {isLoading ? <ListSkeletonLoader /> : (
                <div className="overflow-x-auto w-full">
                  <table className="w-full text-left min-w-[700px]">
                    <thead className="bg-slate-50 dark:bg-slate-950/50 text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider border-b border-slate-100 dark:border-slate-800">
                      <tr><th className="p-5 pl-8">Email Address</th><th className="p-5">Clearance Level</th><th className="p-5 pr-8 text-right">Actions</th></tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50 dark:divide-slate-800/50">
                      {admins.map((admin) => (
                        <tr key={admin.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors">
                          <td className="p-5 pl-8 font-bold text-slate-900 dark:text-white">{admin.email}</td>
                          <td className="p-5">
                            <span className={`px-3 py-1.5 rounded-full text-[10px] font-black tracking-widest uppercase border ${(admin.role || '').includes('super') ? 'bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-500/10 dark:text-purple-400' : 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-400'}`}>
                              {(admin.role || 'admin').replace('_', ' ')}
                            </span>
                          </td>
                          <td className="p-5 pr-8 text-right">
                            {admin.role !== 'super_admin' ? (
                              <button onClick={() => openConfirm('Revoke Admin', "Revoke this admin's access?", () => removeAdmin(admin.id))} className="text-slate-400 hover:text-red-600 dark:hover:text-red-400 p-2 rounded-xl hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors inline-flex items-center gap-2 text-sm font-bold border border-transparent dark:hover:border-red-500/30">
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


        {/* CONTACT MESSAGES */}
        {activeTab === 'messages' && (
          <div className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-md rounded-3xl border border-slate-200/50 dark:border-slate-800/50 overflow-hidden shadow-sm transition-colors duration-500">
            <div className="p-6 border-b border-slate-100 dark:border-slate-800/50 flex items-center gap-2">
              <MessageSquare className="w-5 h-5 text-blue-500" />
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">Contact Messages</h2>
              <span className="ml-auto text-xs font-bold px-2 py-1 bg-blue-100 dark:bg-blue-500/20 text-blue-700 dark:text-blue-400 rounded-full">{contactMessages.length} messages</span>
            </div>
            {isLoading ? <ListSkeletonLoader /> : (
              <div className="divide-y divide-slate-100 dark:divide-slate-800/50">
                {contactMessages.length === 0 ? (
                  <div className="p-12 text-center text-slate-400 font-medium">No contact messages yet.</div>
                ) : contactMessages.map((cm) => (
                  <div key={cm.id} className="p-5 hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors">
                    <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-2">
                          <span className="font-bold text-slate-900 dark:text-white text-sm">{cm.sender_email}</span>
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-widest border ${cm.status === "reviewed" ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400" : "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400"}`}>{cm.status}</span>
                          <span className="text-xs text-slate-400">{new Date(cm.created_at).toLocaleDateString()}</span>
                        </div>
                        <p className="text-sm text-slate-600 dark:text-slate-400 font-medium leading-relaxed break-words">{cm.message_text}</p>
                        {cm.reviewed_by && <p className="text-xs text-slate-400 mt-1">Reviewed by: {cm.reviewed_by}</p>}
                      </div>
                      {cm.status === "pending" && (
                        <button
                          onClick={async () => {
                            try {
                              const res = await fetch(`${backendUrl}/api/admin/contact_messages/${cm.id}`, {
                                method: "PATCH", headers: getHeaders()
                              });
                              if (res.ok) fetchData();
                            } catch {}
                          }}
                          className="shrink-0 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-xl transition-all shadow-sm"
                        >
                          Mark Reviewed
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
};

export default Dashboard;
