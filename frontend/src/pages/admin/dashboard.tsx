import React, { useState, useEffect } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Cookies from 'js-cookie'
import api from '../../services/api'

const FAVICON_SVG = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">📧</text></svg>'

interface User {
  telegram_id: number
  first_name: string
  username: string
  email: string
  is_verified: boolean
  created_at: string
}

interface Stats {
  total_users: number
  approved_users: number
  pending_users: number
  blocked_records: number
  total_admins: number
}

export default function AdminDashboard() {
  const router = useRouter()
  const [activeTab, setActiveTab] = useState('users')
  const [users, setUsers] = useState<User[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    const adminEmail = Cookies.get('admin_session')
    if (!adminEmail) {
      router.push('/admin/login')
      return
    }

    fetchData()
  }, [router])

  const fetchData = async () => {
    try {
      setLoading(true)
      const [usersRes, statsRes] = await Promise.all([
        api.get('/api/admin/users'),
        api.get('/api/admin/stats'),
      ])

      setUsers(usersRes.data.data || [])
      setStats(statsRes.data.stats)
    } catch (error) {
      console.error('Fetch error:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = () => {
    Cookies.remove('admin_session')
    router.push('/admin/login')
  }

  const filteredUsers = users.filter(
    (u) =>
      u.first_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      u.email?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  if (loading) {
    return <div className="flex items-center justify-center min-h-screen">Loading...</div>
  }

  return (
    <>
      <Head>
        <title>Admin Dashboard - Smart Email Assistant</title>
        <link rel="icon" href={`data:image/svg+xml,${FAVICON_SVG}`} />
      </Head>

      <div className="min-h-screen bg-slate-50">
        {/* Top Bar */}
        <div className="bg-slate-900 text-white p-4 flex justify-between items-center">
          <div className="text-xl font-bold flex items-center gap-2">
            <span>📧</span> Smart Email Assistant
          </div>
          <button
            onClick={handleLogout}
            className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg transition"
          >
            Logout
          </button>
        </div>

        {/* Main Content */}
        <div className="max-w-7xl mx-auto p-6">
          {/* Stats */}
          {stats && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
              {[
                { label: 'Total Users', value: stats.total_users, color: 'bg-blue-100 text-blue-700' },
                { label: 'Approved', value: stats.approved_users, color: 'bg-green-100 text-green-700' },
                { label: 'Pending', value: stats.pending_users, color: 'bg-yellow-100 text-yellow-700' },
                { label: 'Blocked', value: stats.blocked_records, color: 'bg-red-100 text-red-700' },
                { label: 'Admins', value: stats.total_admins, color: 'bg-purple-100 text-purple-700' },
              ].map((stat, i) => (
                <div key={i} className={`p-4 rounded-lg ${stat.color}`}>
                  <div className="text-sm font-semibold">{stat.label}</div>
                  <div className="text-3xl font-bold">{stat.value}</div>
                </div>
              ))}
            </div>
          )}

          {/* Tabs */}
          <div className="bg-white rounded-lg shadow">
            <div className="flex border-b">
              <button
                onClick={() => setActiveTab('users')}
                className={`flex-1 p-4 font-semibold ${
                  activeTab === 'users'
                    ? 'border-b-2 border-blue-600 text-blue-600'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Users ({users.length})
              </button>
            </div>

            {/* Users Tab */}
            {activeTab === 'users' && (
              <div className="p-6">
                <input
                  type="text"
                  placeholder="Search users..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full p-3 border border-slate-300 rounded-lg mb-4 focus:ring-2 focus:ring-blue-500 outline-none"
                />

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-slate-50 border-b">
                      <tr>
                        <th className="p-4 font-semibold">Name</th>
                        <th className="p-4 font-semibold">Email</th>
                        <th className="p-4 font-semibold">Status</th>
                        <th className="p-4 font-semibold">Created</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredUsers.map((user) => (
                        <tr key={user.telegram_id} className="border-b hover:bg-slate-50">
                          <td className="p-4">
                            <div className="font-semibold">{user.first_name}</div>
                            <div className="text-xs text-slate-500">@{user.username}</div>
                          </td>
                          <td className="p-4 text-blue-600">{user.email || 'Not linked'}</td>
                          <td className="p-4">
                            <span
                              className={`px-3 py-1 rounded-full text-xs font-bold ${
                                user.is_verified
                                  ? 'bg-green-100 text-green-700'
                                  : 'bg-yellow-100 text-yellow-700'
                              }`}
                            >
                              {user.is_verified ? 'Approved' : 'Pending'}
                            </span>
                          </td>
                          <td className="p-4 text-slate-500">
                            {new Date(user.created_at).toLocaleDateString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}