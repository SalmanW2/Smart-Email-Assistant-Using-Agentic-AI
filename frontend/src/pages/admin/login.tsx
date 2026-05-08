import React, { useState } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Link from 'next/link'
import api from '../../services/api'

const FAVICON_SVG = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">📧</text></svg>'

export default function AdminLoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { msg, error: urlError } = router.query

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      const formData = new FormData()
      formData.append('email', email)
      formData.append('password', password)

      const response = await api.post('/admin/password/verify', formData)

      if (response.data.valid) {
        router.push('/admin/dashboard')
      } else {
        setError('Invalid email or password')
      }
    } catch (err) {
      setError('Login failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleLogin = () => {
    window.location.href = '/admin/auth/google'
  }

  return (
    <>
      <Head>
        <title>Admin Login - Smart Email Assistant</title>
        <link rel="icon" href={`data:image/svg+xml,${FAVICON_SVG}`} />
      </Head>

      <div className="min-h-screen bg-slate-100 flex items-center justify-center p-4">
        <div className="bg-white p-10 rounded-2xl shadow-2xl w-full max-w-md">
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold text-slate-800">Admin Portal</h1>
            <p className="text-slate-500 mt-2 text-sm">
              Secure access for authorized personnel.
            </p>
          </div>

          {error && (
            <div className="bg-red-100 text-red-700 p-3 rounded-lg mb-4 text-sm font-semibold">
              {error}
            </div>
          )}

          {msg && (
            <div className="bg-green-100 text-green-700 p-3 rounded-lg mb-4 text-sm font-semibold">
              {msg}
            </div>
          )}

          <button
            onClick={handleGoogleLogin}
            className="w-full flex items-center justify-center gap-3 bg-white border border-slate-300 p-3 rounded-lg hover:bg-slate-50 transition mb-6"
          >
            <img src="https://www.google.com/favicon.ico" alt="Google" className="w-5 h-5" />
            <span className="font-semibold text-slate-700">Continue with Google</span>
          </button>

          <div className="relative flex py-4 items-center mb-6">
            <div className="flex-grow border-t border-slate-200"></div>
            <span className="flex-shrink mx-4 text-slate-400 text-sm font-semibold">OR</span>
            <div className="flex-grow border-t border-slate-200"></div>
          </div>

          <form onSubmit={handlePasswordLogin} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1 text-left">
                Email Address
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full p-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1 text-left">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full p-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
                required
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-slate-900 text-white p-3 rounded-lg font-bold hover:bg-slate-800 transition disabled:opacity-50"
            >
              {loading ? 'Logging in...' : 'Login to Dashboard'}
            </button>
          </form>
        </div>
      </div>
    </>
  )
}