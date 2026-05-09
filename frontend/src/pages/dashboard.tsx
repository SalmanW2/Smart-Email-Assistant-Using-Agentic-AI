import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

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
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [role, setRole] = useState<string>('');
  const navigate = useNavigate();

  useEffect(() => {
    fetchRole();
    fetchData();
  }, []);

  const fetchRole = async () => {
    try {
      const response = await fetch(
        `${import.meta.env.VITE_BACKEND_URL}/api/admin/role`,
        { credentials: 'include' }
      );
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
        fetch(`${import.meta.env.VITE_BACKEND_URL}/api/admin/users`, {
          credentials: 'include',
        }),
        fetch(`${import.meta.env.VITE_BACKEND_URL}/api/admin/admins`, {
          credentials: 'include',
        }),
        fetch(`${import.meta.env.VITE_BACKEND_URL}/api/admin/blocks`, {
          credentials: 'include',
        }),
        fetch(`${import.meta.env.VITE_BACKEND_URL}/api/admin/stats`, {
          credentials: 'include',
        }),
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
      await fetch(
        `${import.meta.env.VITE_BACKEND_URL}/api/admin/users/${tgId}/approve`,
        { method: 'POST', credentials: 'include' }
      );
      fetchData();
    } catch (err) {
      console.error('Failed to approve user:', err);
    }
  };

  const blockUser = async (tgId: number, reason: string) => {
    try {
      await fetch(
        `${import.meta.env.VITE_BACKEND_URL}/api/admin/users/${tgId}/block?reason=${encodeURIComponent(reason)}`,
        { method: 'POST', credentials: 'include' }
      );
      fetchData();
    } catch (err) {
      console.error('Failed to block user:', err);
    }
  };

  const removeBlock = async (id: string) => {
    try {
      await fetch(
        `${import.meta.env.VITE_BACKEND_URL}/api/admin/blocks/${id}`,
        { method: 'DELETE', credentials: 'include' }
      );
      fetchData();
    } catch (err) {
      console.error('Failed to remove block:', err);
    }
  };

  const addAdmin = async (email: string) => {
    try {
      await fetch(`${import.meta.env.VITE_BACKEND_URL}/api/admin/admins`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, role: 'admin' }),
        credentials: 'include',
      });
      fetchData();
    } catch (err) {
      console.error('Failed to add admin:', err);
    }
  };

  const removeAdmin = async (id: string) => {
    try {
      await fetch(
        `${import.meta.env.VITE_BACKEND_URL}/api/admin/admins/${id}`,
        { method: 'DELETE', credentials: 'include' }
      );
      fetchData();
    } catch (err) {
      console.error('Failed to remove admin:', err);
    }
  };

  const logout = async () => {
    try {
      await fetch(`${import.meta.env.VITE_BACKEND_URL}/admin/logout`, {
        credentials: 'include',
      });
      navigate('/admin/login');
    } catch (err) {
      console.error('Logout error:', err);
      navigate('/admin/login');
    }
  };

  return (
    <div className="bg-slate-50 min-h-screen font-sans">
      {/* Mobile Header */}
      <div className="lg:hidden bg-slate-900 text-white p-4 flex items-center justify-between sticky top-0 z-40 shadow-md">
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="p-2 bg-slate-800 rounded-lg focus:outline-none"
        >
          <svg
            className="w-6 h-6"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M4 6h16M4 12h16M4 18h16"
            ></path>
          </svg>
        </button>
        <div className="text-lg font-bold flex items-center gap-2">
          <span>📧</span> Smart Email Assistant
        </div>
        <div className="w-10"></div>
      </div>

      {/* Mobile Overlay */}
      {mobileMenuOpen && (
        <div
          onClick={() => setMobileMenuOpen(false)}
          className="fixed inset-0 bg-black bg-opacity-50 z-40 lg:hidden"
        ></div>
      )}

      <div className="flex">
        {/* Sidebar */}
        <div
          className={`fixed inset-y-0 left-0 transform ${
            mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
          } lg:relative lg:translate-x-0 transition duration-200 ease-in-out z-50 w-64 bg-slate-900 text-white min-h-screen p-6 overflow-y-auto shadow-2xl lg:shadow-none`}
        >
          <div className="text-xl font-bold mb-10 hidden lg:flex items-center gap-2">
            <span>📧</span> Smart Email Assistant
          </div>
          <div className="flex justify-between items-center lg:hidden mb-8">
            <span className="text-xl font-bold text-slate-400">Admin Menu</span>
            <button
              onClick={() => setMobileMenuOpen(false)}
              className="text-slate-400 hover:text-white text-2xl font-bold"
            >
              &times;
            </button>
          </div>

          <nav className="space-y-2">
            <button
              onClick={() => {
                setActiveTab('stats');
                setMobileMenuOpen(false);
              }}
              className={`block p-3 ${
                activeTab === 'stats'
                  ? 'bg-blue-600 text-white font-semibold'
                  : 'hover:bg-slate-800 text-slate-400'
              } rounded-lg transition-all w-full text-left`}
            >
              Stats
            </button>
            <button
              onClick={() => {
                setActiveTab('users');
                setMobileMenuOpen(false);
              }}
              className={`block p-3 ${
                activeTab === 'users'
                  ? 'bg-blue-600 text-white font-semibold'
                  : 'hover:bg-slate-800 text-slate-400'
              } rounded-lg transition-all w-full text-left`}
            >
              User Management
            </button>
            <button
              onClick={() => {
                setActiveTab('blocklist');
                setMobileMenuOpen(false);
              }}
              className={`block p-3 ${
                activeTab === 'blocklist'
                  ? 'bg-blue-600 text-white font-semibold'
                  : 'hover:bg-slate-800 text-slate-400'
              } rounded-lg transition-all w-full text-left`}
            >
              Blocklist
            </button>
            {role === 'super_admin' && (
              <button
                onClick={() => {
                  setActiveTab('admins');
                  setMobileMenuOpen(false);
                }}
                className={`block p-3 ${
                  activeTab === 'admins'
                    ? 'bg-blue-600 text-white font-semibold'
                    : 'hover:bg-slate-800 text-slate-400'
                } rounded-lg transition-all w-full text-left`}
              >
                Manage Admins
              </button>
            )}
            <button
              onClick={() => {
                setActiveTab('password');
                setMobileMenuOpen(false);
              }}
              className={`block p-3 ${
                activeTab === 'password'
                  ? 'bg-blue-600 text-white font-semibold'
                  : 'hover:bg-slate-800 text-slate-400'
              } rounded-lg transition-all w-full text-left`}
            >
              Set Password
            </button>
            <div className="pt-8 border-t border-slate-800 mt-8">
              <button
                onClick={logout}
                className="block p-3 text-red-400 hover:text-red-300 hover:bg-slate-800 rounded-lg transition-all w-full text-left"
              >
                Logout
              </button>
            </div>
          </nav>
        </div>

        {/* Main Content */}
        <div className="flex-1 p-4 md:p-10 w-full overflow-hidden bg-slate-50 min-h-screen">
          {/* Stats Tab */}
          {activeTab === 'stats' && stats && (
            <div>
              <h1 className="text-2xl md:text-3xl font-bold text-slate-800 mb-6">
                Dashboard Stats
              </h1>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                  <h3 className="text-lg font-semibold text-slate-700">
                    Total Users
                  </h3>
                  <p className="text-3xl font-bold text-blue-600">
                    {stats.total_users}
                  </p>
                </div>
                <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                  <h3 className="text-lg font-semibold text-slate-700">
                    Verified Users
                  </h3>
                  <p className="text-3xl font-bold text-green-600">
                    {stats.verified_users}
                  </p>
                </div>
                <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                  <h3 className="text-lg font-semibold text-slate-700">
                    Blocked Users
                  </h3>
                  <p className="text-3xl font-bold text-red-600">
                    {stats.blocked_users}
                  </p>
                </div>
                <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                  <h3 className="text-lg font-semibold text-slate-700">
                    Total Admins
                  </h3>
                  <p className="text-3xl font-bold text-purple-600">
                    {stats.total_admins}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Users Tab */}
          {activeTab === 'users' && (
            <div>
              <div className="flex flex-col md:flex-row justify-between md:items-center mb-8 gap-4">
                <h1 className="text-2xl md:text-3xl font-bold text-slate-800">
                  User Management
                </h1>
                <input
                  type="text"
                  placeholder="Search Users..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="p-3 border border-slate-300 rounded-xl w-full md:w-80 shadow-sm focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </div>

              <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-x-auto">
                <table className="w-full text-left min-w-[600px]">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr>
                      <th className="p-4 text-sm font-semibold text-slate-600">
                        Telegram User
                      </th>
                      <th className="p-4 text-sm font-semibold text-slate-600">
                        Status
                      </th>
                      <th className="p-4 text-sm font-semibold text-slate-600">
                        Registration Date
                      </th>
                      <th className="p-4 text-sm font-semibold text-slate-600">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredUsers.map((user) => (
                      <tr
                        key={user.telegram_id}
                        className="border-b border-slate-100 hover:bg-slate-50 transition-all"
                      >
                        <td className="p-4 min-w-[200px]">
                          <div className="font-bold text-slate-800">
                            {user.first_name || 'N/A'}
                          </div>
                          <div className="text-xs text-slate-400">
                            ID: {user.telegram_id} | @{user.username || 'none'}
                          </div>
                          <div className="text-sm text-blue-600 mt-1">
                            {user.email || 'Email Not Linked'}
                          </div>
                        </td>
                        <td className="p-4">
                          {user.is_verified ? (
                            <span className="px-3 py-1 rounded-full text-xs font-bold bg-green-100 text-green-700">
                              APPROVED
                            </span>
                          ) : (
                            <span className="px-3 py-1 rounded-full text-xs font-bold bg-yellow-100 text-yellow-700">
                              PENDING
                            </span>
                          )}
                        </td>
                        <td className="p-4 text-sm text-slate-500 whitespace-nowrap">
                          {new Date(user.created_at).toLocaleDateString()}
                        </td>
                        <td className="p-4 space-x-2 flex items-center">
                          {!user.is_verified ? (
                            <button
                              onClick={() => approveUser(user.telegram_id)}
                              className="bg-blue-50 text-blue-600 px-4 py-2 rounded-lg font-bold hover:bg-blue-600 hover:text-white transition-all text-sm whitespace-nowrap"
                            >
                              Approve
                            </button>
                          ) : (
                            <button
                              onClick={() =>
                                blockUser(user.telegram_id, 'Blocked by admin')
                              }
                              className="bg-red-50 text-red-600 px-4 py-2 rounded-lg font-bold hover:bg-red-600 hover:text-white transition-all text-sm whitespace-nowrap"
                            >
                              Block
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Blocklist Tab */}
          {activeTab === 'blocklist' && (
            <div>
              <h1 className="text-2xl md:text-3xl font-bold text-slate-800 mb-6">
                System Blocklist
              </h1>
              <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-x-auto">
                <table className="w-full text-left min-w-[500px]">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr>
                      <th className="p-4 text-sm font-semibold text-slate-600">
                        Target
                      </th>
                      <th className="p-4 text-sm font-semibold text-slate-600">
                        Reason
                      </th>
                      <th className="p-4 text-sm font-semibold text-slate-600">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {blocks.map((block) => (
                      <tr key={block.id} className="border-b border-slate-100">
                        <td className="p-4 font-semibold text-slate-800 whitespace-nowrap">
                          {block.block_type.toUpperCase()}: {block.block_value}
                        </td>
                        <td className="p-4 text-slate-600 min-w-[150px]">
                          {block.reason || 'No reason provided'}
                        </td>
                        <td className="p-4">
                          <button
                            onClick={() => removeBlock(block.id)}
                            className="text-blue-600 hover:underline font-semibold text-sm whitespace-nowrap"
                          >
                            Remove Block
                          </button>
                        </td>
                      </tr>
                    ))}
                    {blocks.length === 0 && (
                      <tr>
                        <td
                          colSpan={3}
                          className="p-4 text-slate-500 text-center"
                        >
                          No blocked records found.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Admins Tab */}
          {activeTab === 'admins' && role === 'super_admin' && (
            <div>
              <h1 className="text-2xl md:text-3xl font-bold text-slate-800 mb-6">
                Manage Administrators
              </h1>

              <div className="bg-white p-4 md:p-6 rounded-2xl shadow-sm border border-slate-200 mb-8">
                <h2 className="text-lg font-bold text-slate-800 mb-4">
                  Add New Admin
                </h2>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    const email = (e.target as HTMLFormElement).email
                      .value as string;
                    addAdmin(email);
                    (e.target as HTMLFormElement).reset();
                  }}
                  className="flex flex-col sm:flex-row gap-4 sm:items-end"
                >
                  <div className="flex-1">
                    <label className="block text-sm font-medium text-slate-700 mb-1">
                      Email Address
                    </label>
                    <input
                      type="email"
                      name="email"
                      required
                      placeholder="newadmin@example.com"
                      className="w-full p-3 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                  <button
                    type="submit"
                    className="bg-blue-600 text-white px-8 py-3 rounded-lg font-bold hover:bg-blue-700 h-[50px] shadow-sm w-full sm:w-auto transition-all"
                  >
                    Add Admin
                  </button>
                </form>
              </div>

              <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-x-auto">
                <table className="w-full text-left min-w-[400px]">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr>
                      <th className="p-4 text-sm font-semibold text-slate-600">
                        Email Address
                      </th>
                      <th className="p-4 text-sm font-semibold text-slate-600">
                        Role
                      </th>
                      <th className="p-4 text-sm font-semibold text-slate-600">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {admins.map((admin) => (
                      <tr key={admin.id} className="border-b border-slate-100">
                        <td className="p-4 font-semibold text-slate-800">
                          {admin.email}
                        </td>
                        <td className="p-4 text-slate-600 capitalize">
                          {admin.role.replace('_', ' ')}
                        </td>
                        <td className="p-4">
                          <button
                            onClick={() => removeAdmin(admin.id)}
                            className="text-red-600 hover:underline font-semibold text-sm whitespace-nowrap"
                          >
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Password Tab */}
          {activeTab === 'password' && (
            <div>
              <h1 className="text-2xl md:text-3xl font-bold text-slate-800 mb-6">
                Set Admin Password
              </h1>
              <div className="bg-white p-6 md:p-8 rounded-2xl shadow-sm border border-slate-200 max-w-lg">
                <p className="text-slate-500 mb-6 text-sm md:text-base">
                  Create a password to login directly without using Google SSO.
                </p>
                <button
                  onClick={() => navigate('/admin/set-password')}
                  className="bg-slate-800 text-white px-6 py-3 rounded-lg font-bold hover:bg-slate-900 shadow-md w-full transition-all"
                >
                  Go to Set Password
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
