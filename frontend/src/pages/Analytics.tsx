import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  BarChart3, TrendingUp, AlertCircle,
  LineChart as LineChartIcon, Activity,
} from 'lucide-react'
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts'
import { api } from '../lib/api'
import { useAuth } from '../store/auth'
import PageTransition from '../components/PageTransition'
import { SkeletonStat, Skeleton } from '../components/Skeleton'

interface AnalyticsData {
  proficiency_score: number
  engagement_score: number
  weak_topics: string[]
  quizzes_attempted: number
  recent_scores: number[]
  recent_activity: number[]
}

const CHART_STYLE = {
  grid: 'rgba(255,255,255,0.05)',
  line: '#818cf8',
  bar: '#a78bfa',
  text: '#94a3b8',
}

function TooltipContent({ active, payload }: { active?: boolean; payload?: { value: number }[] }) {
  if (!active || !payload?.length) return null
  return (
    <div className="glass rounded-lg px-3 py-2 text-xs">
      <span className="text-text-base font-medium">{payload[0].value}</span>
    </div>
  )
}

export default function AnalyticsPage() {
  const { user } = useAuth()
  const subjects = user?.subjects_list ?? ['general']
  const [activeSubject, setActiveSubject] = useState(user?.current_subject || subjects[0] || 'general')

  const { data, isLoading } = useQuery<AnalyticsData>({
    queryKey: ['analytics', activeSubject],
    queryFn: () => api.get(`/analytics/overview?subject=${encodeURIComponent(activeSubject)}`),
  })

  const scoreData = (data?.recent_scores ?? []).map((v, i) => ({ i: `Q${i + 1}`, score: v }))
  const activityData = (data?.recent_activity ?? []).map((v, i) => ({
    day: ['Day 1', 'Day 2', 'Day 3', 'Day 4', 'Day 5'][i],
    events: v,
  }))

  return (
    <PageTransition>
      <div className="page-content py-8">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <div className="w-9 h-9 rounded-xl bg-success/10 flex items-center justify-center">
            <BarChart3 size={18} className="text-success" />
          </div>
          <div>
            <h1 className="font-display text-xl font-semibold text-text-base">Analytics</h1>
            <p className="text-xs text-text-muted">Track your learning progress</p>
          </div>
        </div>

        {/* Subject tabs — dynamic, no hardcoding */}
        {subjects.length > 1 && (
          <div className="flex gap-1.5 mb-6 flex-wrap">
            {subjects.map(s => (
              <button
                key={s}
                onClick={() => setActiveSubject(s)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150 cursor-pointer capitalize ${
                  activeSubject === s
                    ? 'bg-accent/15 text-accent border border-accent/25'
                    : 'glass text-text-muted hover:text-text-base hover:bg-white/5'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {/* KPI row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          {isLoading
            ? Array.from({ length: 4 }).map((_, i) => <SkeletonStat key={i} />)
            : [
                { label: 'Proficiency', value: `${data?.proficiency_score ?? 0}%`, icon: TrendingUp, color: 'text-accent' },
                { label: 'Engagement', value: data?.engagement_score ?? 0, icon: Activity, color: 'text-violet' },
                { label: 'Quizzes taken', value: data?.quizzes_attempted ?? 0, icon: BarChart3, color: 'text-cyan' },
                { label: 'Weak topics', value: data?.weak_topics?.length ?? 0, icon: AlertCircle, color: 'text-warning' },
              ].map(({ label, value, icon: Icon, color }) => (
                <div key={label} className="card">
                  <div className="flex items-center gap-2 mb-2">
                    <Icon size={13} className={color} />
                    <span className="text-xs text-text-muted">{label}</span>
                  </div>
                  <p className={`font-display text-2xl font-bold ${color}`}>{value}</p>
                </div>
              ))
          }
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          {/* Quiz scores chart */}
          <div className="card">
            <div className="flex items-center gap-2 mb-4">
              <LineChartIcon size={14} className="text-text-subtle" />
              <span className="text-sm font-display font-medium text-text-base">Recent quiz scores</span>
            </div>
            {isLoading ? (
              <Skeleton className="h-40 w-full" />
            ) : scoreData.length === 0 || scoreData.every(d => d.score === 0) ? (
              <div className="h-40 flex items-center justify-center text-sm text-text-subtle">
                No quiz data yet — take your first quiz!
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={140}>
                <LineChart data={scoreData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid stroke={CHART_STYLE.grid} vertical={false} />
                  <XAxis dataKey="i" tick={{ fill: CHART_STYLE.text, fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 100]} tick={{ fill: CHART_STYLE.text, fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip content={<TooltipContent />} />
                  <Line
                    type="monotone"
                    dataKey="score"
                    stroke={CHART_STYLE.line}
                    strokeWidth={2}
                    dot={{ fill: CHART_STYLE.line, r: 4 }}
                    activeDot={{ r: 6, fill: '#a78bfa' }}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Activity chart */}
          <div className="card">
            <div className="flex items-center gap-2 mb-4">
              <Activity size={14} className="text-text-subtle" />
              <span className="text-sm font-display font-medium text-text-base">5-day activity</span>
            </div>
            {isLoading ? (
              <Skeleton className="h-40 w-full" />
            ) : activityData.every(d => d.events === 0) ? (
              <div className="h-40 flex items-center justify-center text-sm text-text-subtle">
                No activity in the past 5 days
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={140}>
                <BarChart data={activityData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid stroke={CHART_STYLE.grid} vertical={false} />
                  <XAxis dataKey="day" tick={{ fill: CHART_STYLE.text, fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: CHART_STYLE.text, fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip content={<TooltipContent />} />
                  <Bar dataKey="events" fill={CHART_STYLE.bar} radius={[4, 4, 0, 0]} maxBarSize={40} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Weak topics */}
        <div className="card">
          <div className="flex items-center gap-2 mb-4">
            <AlertCircle size={14} className="text-warning" />
            <span className="text-sm font-display font-medium text-text-base">Weak topics</span>
          </div>
          {isLoading ? (
            <div className="flex gap-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-7 w-24 rounded-lg" />
              ))}
            </div>
          ) : !data?.weak_topics?.length ? (
            <div className="py-4 text-center">
              <p className="text-sm text-text-subtle">
                {data?.quizzes_attempted === 0
                  ? 'Take a quiz to identify your weak areas'
                  : 'No weak topics detected — great work!'}
              </p>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              {data.weak_topics.map(topic => (
                <motion.span
                  key={topic}
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="text-xs px-3 py-1.5 rounded-lg bg-danger/10 text-danger border border-danger/20"
                >
                  {topic}
                </motion.span>
              ))}
            </div>
          )}
        </div>
      </div>
    </PageTransition>
  )
}
