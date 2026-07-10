import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Map, RefreshCw, Loader2, ChevronRight, AlertCircle } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../store/auth'
import PageTransition from '../components/PageTransition'
import { SkeletonCard } from '../components/Skeleton'

interface RoadmapStep {
  step: number
  title: string
  description: string
  objectives: string[]
  time?: string
  difficulty?: 'Beginner' | 'Intermediate' | 'Advanced'
  activities?: string[]
}

interface RoadmapResponse {
  roadmap: RoadmapStep[] | null
  message?: string
}

const DIFFICULTY_COLORS: Record<string, string> = {
  Beginner:     'bg-success/10 text-success border-success/20',
  Intermediate: 'bg-warning/10 text-warning border-warning/20',
  Advanced:     'bg-danger/10 text-danger border-danger/20',
}

export default function RoadmapPage() {
  const { user } = useAuth()
  const qc = useQueryClient()

  const { data, isLoading, isError } = useQuery<RoadmapResponse>({
    queryKey: ['roadmap'],
    queryFn: () => api.get('/roadmap'),
  })

  const generateMutation = useMutation({
    mutationFn: () => api.post('/generate_roadmap', {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['roadmap'] }),
  })

  const steps = data?.roadmap ?? []

  return (
    <PageTransition>
      <div className="page-content py-8">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-cyan/10 flex items-center justify-center">
              <Map size={18} className="text-cyan" />
            </div>
            <div>
              <h1 className="font-display text-xl font-semibold text-text-base">Learning Roadmap</h1>
              <p className="text-xs text-text-muted capitalize">{user?.current_subject || 'general'} path</p>
            </div>
          </div>
          <button
            onClick={() => generateMutation.mutate()}
            disabled={generateMutation.isPending}
            className="btn-ghost flex items-center gap-1.5 text-sm"
          >
            {generateMutation.isPending
              ? <Loader2 size={14} className="animate-spin" />
              : <RefreshCw size={14} />
            }
            {steps.length > 0 ? 'Regenerate' : 'Generate'}
          </button>
        </div>

        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} lines={4} />)}
          </div>
        ) : isError ? (
          <div className="card flex items-center gap-3 text-danger">
            <AlertCircle size={18} />
            <p className="text-sm">Failed to load roadmap. Try generating one.</p>
          </div>
        ) : steps.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-14 h-14 rounded-2xl bg-cyan/10 flex items-center justify-center mb-5">
              <Map size={24} className="text-cyan" />
            </div>
            <h2 className="font-display text-base font-semibold text-text-base mb-2">No roadmap yet</h2>
            <p className="text-sm text-text-muted max-w-xs mb-6">
              Generate a personalised learning path based on your current progress and weak topics.
            </p>
            <button
              onClick={() => generateMutation.mutate()}
              disabled={generateMutation.isPending}
              className="btn-primary flex items-center gap-2"
            >
              {generateMutation.isPending && <Loader2 size={14} className="animate-spin" />}
              Generate roadmap
            </button>
            {generateMutation.isError && (
              <p className="text-xs text-danger mt-3">
                {(generateMutation.error as Error).message}
              </p>
            )}
          </div>
        ) : (
          <div className="relative">
            {/* Vertical timeline line */}
            <div className="absolute left-4 top-6 bottom-6 w-px bg-white/6" />

            <div className="space-y-4 pl-12">
              {steps.map((step, i) => (
                <motion.div
                  key={step.step}
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.06 }}
                  className="relative"
                >
                  {/* Step dot */}
                  <div className="absolute -left-12 top-5 w-8 h-8 rounded-full glass border border-accent/30 flex items-center justify-center">
                    <span className="text-xs font-display font-semibold text-accent">{step.step}</span>
                  </div>

                  <div className="card glass-hover">
                    <div className="flex items-start justify-between gap-3 mb-3">
                      <h3 className="font-display font-semibold text-sm text-text-base">{step.title}</h3>
                      {step.difficulty && (
                        <span className={`text-[10px] font-medium px-2 py-0.5 rounded-md border uppercase tracking-wider flex-shrink-0 ${DIFFICULTY_COLORS[step.difficulty] || ''}`}>
                          {step.difficulty}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-text-muted mb-3 leading-relaxed">{step.description}</p>
                    {step.time && (
                      <p className="text-[11px] text-text-subtle mb-3">⏱ {step.time}</p>
                    )}

                    {step.objectives?.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mb-3">
                        {step.objectives.map(t => (
                          <span key={t} className="text-[11px] px-2 py-0.5 rounded-md bg-accent/8 text-accent border border-accent/15">
                            {t}
                          </span>
                        ))}
                      </div>
                    )}

                    {(step.activities?.length ?? 0) > 0 && (
                      <div className="space-y-1">
                        {(step.activities ?? []).map((r, ri) => (
                          <div key={ri} className="flex items-center gap-1.5 text-xs text-text-subtle">
                            <ChevronRight size={10} />
                            <span>{r}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        )}
      </div>
    </PageTransition>
  )
}
