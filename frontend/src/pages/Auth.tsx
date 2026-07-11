import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { BookOpen, Eye, EyeOff, Loader2 } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../store/auth'
import type { User } from '../store/auth'

interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}

type Tab = 'login' | 'register'

export default function AuthPage() {
  const [tab, setTab] = useState<Tab>('login')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showPass, setShowPass] = useState(false)

  // Login fields
  const [loginUser, setLoginUser] = useState('')
  const [loginPass, setLoginPass] = useState('')

  // Register fields
  const [regEmail, setRegEmail] = useState('')
  const [regUser, setRegUser] = useState('')
  const [regPass, setRegPass] = useState('')
  const [regName, setRegName] = useState('')

  const { login } = useAuth()
  const navigate = useNavigate()

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await api.post<TokenResponse>('/auth/login', {
        username: loginUser,
        password: loginPass,
      })
      login(data.access_token, data.user)
      navigate('/')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await api.post<TokenResponse>('/auth/register', {
        email: regEmail,
        username: regUser,
        password: regPass,
        full_name: regName || undefined,
      })
      login(data.access_token, data.user)
      navigate('/')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg relative overflow-hidden">
      {/* Aurora background */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse 80% 60% at 20% -5%, rgba(129,140,248,0.22) 0%, transparent 60%),' +
            'radial-gradient(ellipse 60% 50% at 80% 110%, rgba(167,139,250,0.16) 0%, transparent 60%)',
        }}
      />

      {/* Noise texture overlay */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
        }}
      />

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="relative w-full max-w-sm mx-4"
      >
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-2xl bg-accent-gradient flex items-center justify-center shadow-accent-glow mb-4">
            <BookOpen size={22} className="text-white" />
          </div>
          <h1 className="font-display text-2xl font-semibold text-text-base">Aurora Scholar</h1>
          <p className="text-sm text-text-muted mt-1">Your adaptive learning workspace</p>
        </div>

        {/* Card */}
        <div className="glass rounded-2xl p-6 shadow-glass">
          {/* Tab switcher */}
          <div className="flex rounded-xl bg-white/4 p-1 mb-6">
            {(['login', 'register'] as Tab[]).map(t => (
              <button
                key={t}
                onClick={() => { setTab(t); setError('') }}
                className={`flex-1 py-1.5 text-sm font-medium rounded-lg transition-all duration-200 cursor-pointer capitalize ${
                  tab === t
                    ? 'bg-accent/20 text-accent shadow-sm'
                    : 'text-text-subtle hover:text-text-muted'
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          <AnimatePresence mode="wait">
            {tab === 'login' ? (
              <motion.form
                key="login"
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 12 }}
                transition={{ duration: 0.2 }}
                onSubmit={handleLogin}
                className="space-y-4"
              >
                <div>
                  <label className="block text-xs text-text-muted mb-1.5">Username or email</label>
                  <input
                    className="input-base"
                    placeholder="your_username"
                    value={loginUser}
                    onChange={e => setLoginUser(e.target.value)}
                    required
                    autoFocus
                  />
                </div>
                <div>
                  <label className="block text-xs text-text-muted mb-1.5">Password</label>
                  <div className="relative">
                    <input
                      className="input-base pr-10"
                      type={showPass ? 'text' : 'password'}
                      placeholder="••••••••"
                      value={loginPass}
                      onChange={e => setLoginPass(e.target.value)}
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowPass(p => !p)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-text-subtle hover:text-text-muted cursor-pointer transition-colors"
                    >
                      {showPass ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                </div>
                {error && <p className="text-xs text-danger bg-danger/10 rounded-lg px-3 py-2">{error}</p>}
                <button type="submit" disabled={loading} className="btn-primary w-full flex items-center justify-center gap-2">
                  {loading && <Loader2 size={15} className="animate-spin" />}
                  Sign in
                </button>
              </motion.form>
            ) : (
              <motion.form
                key="register"
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -12 }}
                transition={{ duration: 0.2 }}
                onSubmit={handleRegister}
                className="space-y-3"
              >
                <div>
                  <label className="block text-xs text-text-muted mb-1.5">Full name <span className="text-text-subtle">(optional)</span></label>
                  <input
                    className="input-base"
                    placeholder="Jane Doe"
                    value={regName}
                    onChange={e => setRegName(e.target.value)}
                  />
                </div>
                <div>
                  <label className="block text-xs text-text-muted mb-1.5">Email</label>
                  <input
                    className="input-base"
                    type="email"
                    placeholder="jane@example.com"
                    value={regEmail}
                    onChange={e => setRegEmail(e.target.value)}
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs text-text-muted mb-1.5">Username</label>
                  <input
                    className="input-base"
                    placeholder="jane_doe"
                    value={regUser}
                    onChange={e => setRegUser(e.target.value)}
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs text-text-muted mb-1.5">Password</label>
                  <div className="relative">
                    <input
                      className="input-base pr-10"
                      type={showPass ? 'text' : 'password'}
                      placeholder="min. 8 characters"
                      value={regPass}
                      onChange={e => setRegPass(e.target.value)}
                      required
                      minLength={8}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPass(p => !p)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-text-subtle hover:text-text-muted cursor-pointer transition-colors"
                    >
                      {showPass ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                </div>
                {error && <p className="text-xs text-danger bg-danger/10 rounded-lg px-3 py-2">{error}</p>}
                <button type="submit" disabled={loading} className="btn-primary w-full flex items-center justify-center gap-2 mt-1">
                  {loading && <Loader2 size={15} className="animate-spin" />}
                  Create account
                </button>
              </motion.form>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  )
}
