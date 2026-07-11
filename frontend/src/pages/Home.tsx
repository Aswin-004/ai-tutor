import { useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { MessageSquare, Brain, Map, BarChart3, FileText, TrendingUp } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../store/auth'
import PageTransition from '../components/PageTransition'
import { SkeletonStat } from '../components/Skeleton'

interface Stats {
  documents_count: number
  messages_count: number
  chunks_count: number
}

const ACTION_CARDS = [
  { icon: MessageSquare, label: 'Start chatting',  sub: 'Ask anything about your documents', to: '/chat',      color: 'text-accent' },
  { icon: Brain,         label: 'Take a quiz',     sub: 'Test your knowledge on any topic',  to: '/quiz',      color: 'text-violet' },
  { icon: Map,           label: 'View roadmap',    sub: 'See your personalised learning path', to: '/roadmap', color: 'text-cyan' },
  { icon: BarChart3,     label: 'Analytics',       sub: 'Track your progress over time',      to: '/analytics', color: 'text-success' },
]

function greeting(name: string) {
  const h = new Date().getHours()
  const time = h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
  return `${time}, ${name}`
}

export default function HomePage() {
  const { user } = useAuth()
  const navigate = useNavigate()

  const { data: stats, isLoading } = useQuery<Stats>({
    queryKey: ['stats'],
    queryFn: () => api.get('/stats'),
  })

  // Fire heartbeat on mount — tells backend user is active
  const heartbeat = useMutation({ mutationFn: () => api.post('/heartbeat') })
  useEffect(() => { heartbeat.mutate() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const displayName = user?.full_name?.split(' ')[0] || user?.username || 'there'
  const currentSubject = user?.current_subject || 'general'

  return (
    <PageTransition>
      <div className="page-content py-8">
        {/* Greeting */}
        <div className="mb-8">
          <motion.h1
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="font-display text-3xl font-semibold text-text-base"
          >
            {greeting(displayName)}
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="text-text-muted mt-1 text-sm"
          >
            Currently studying{' '}
            <span className="text-accent font-medium capitalize">{currentSubject}</span>
          </motion.p>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-3 mb-8">
          {isLoading
            ? [0, 1, 2].map(i => <SkeletonStat key={i} />)
            : [
                { label: 'Documents',        value: stats?.documents_count ?? 0,  icon: FileText },
                { label: 'Messages sent',    value: stats?.messages_count ?? 0,   icon: MessageSquare },
                { label: 'Knowledge chunks', value: stats?.chunks_count ?? 0,     icon: TrendingUp },
              ].map(({ label, value, icon: Icon }, i) => (
                <motion.div
                  key={label}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.08 + i * 0.04 }}
                  className="card"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <Icon size={13} className="text-text-subtle" />
                    <span className="text-xs text-text-muted">{label}</span>
                  </div>
                  <p className="font-display text-2xl font-semibold text-text-base">
                    {value.toLocaleString()}
                  </p>
                </motion.div>
              ))
          }
        </div>

        {/* Action cards */}
        <div className="mb-6">
          <h2 className="font-display text-xs font-semibold text-text-subtle uppercase tracking-widest mb-3">
            Quick actions
          </h2>
          <div className="grid grid-cols-2 gap-3">
            {ACTION_CARDS.map(({ icon: Icon, label, sub, to, color }, i) => (
              <motion.button
                key={to}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.12 + i * 0.04 }}
                onClick={() => navigate(to)}
                className="glass-hover rounded-2xl p-4 text-left cursor-pointer group"
              >
                <div className={`w-9 h-9 rounded-xl bg-white/5 flex items-center justify-center mb-3 group-hover:scale-105 transition-transform ${color}`}>
                  <Icon size={17} />
                </div>
                <p className="font-display font-semibold text-sm text-text-base mb-0.5">{label}</p>
                <p className="text-xs text-text-subtle leading-snug">{sub}</p>
              </motion.button>
            ))}
          </div>
        </div>

        {/* Subject workspaces note */}
        {user?.subjects_list && user.subjects_list.length > 1 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3 }}
            className="glass rounded-xl p-3 flex items-center gap-3"
          >
            <div className="w-1 h-8 rounded-full bg-accent-gradient flex-shrink-0" />
            <p className="text-xs text-text-muted">
              You have{' '}
              <span className="text-text-base font-medium">{user.subjects_list.length}</span>{' '}
              subject workspaces. Switch them from the{' '}
              <button onClick={() => navigate('/profile')} className="text-accent hover:underline cursor-pointer">
                Profile
              </button>{' '}
              page.
            </p>
          </motion.div>
        )}
      </div>
    </PageTransition>
  )
}
