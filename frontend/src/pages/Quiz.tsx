import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Brain, CheckCircle2, XCircle, Loader2, RotateCcw, Trophy } from 'lucide-react'
import { api } from '../lib/api'
import PageTransition from '../components/PageTransition'
import { Skeleton } from '../components/Skeleton'

interface QuizQuestion {
  question: string
  options: string[]
  correct_answer: string
  explanation?: string
}

interface GenerateResponse {
  quiz: QuizQuestion[]
  total_questions: number
}

interface WeakTopics {
  weak_topics: string[]
}

type Phase = 'setup' | 'active' | 'result'

export default function QuizPage() {
  const [topic, setTopic] = useState('')
  const [phase, setPhase] = useState<Phase>('setup')
  const [questions, setQuestions] = useState<QuizQuestion[]>([])
  const [currentIdx, setCurrentIdx] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)
  const [showExplanation, setShowExplanation] = useState(false)
  const [score, setScore] = useState(0)
  const [answers, setAnswers] = useState<{ correct: boolean; selected: string }[]>([])

  const { data: weakTopics, isLoading: loadingWeak } = useQuery<WeakTopics>({
    queryKey: ['weak-topics'],
    queryFn: () => api.get('/quiz/weak_topics'),
  })

  const generateMutation = useMutation({
    mutationFn: (t: string) => api.post<GenerateResponse>('/quiz/generate', { topic: t }),
    onSuccess: (data) => {
      setQuestions(data.quiz)
      setCurrentIdx(0)
      setScore(0)
      setAnswers([])
      setSelected(null)
      setShowExplanation(false)
      setPhase('active')
    },
  })

  const submitMutation = useMutation({
    mutationFn: ({ s, total }: { s: number; total: number }) =>
      api.post('/quiz/submit', { score: s, total_questions: total, topic }),
  })

  const currentQ = questions[currentIdx]
  const isLast = currentIdx === questions.length - 1

  const handleAnswer = (option: string) => {
    if (selected) return
    setSelected(option)
    setShowExplanation(true)
    const correct = option === currentQ.correct_answer
    if (correct) setScore(s => s + 1)
    setAnswers(a => [...a, { correct, selected: option }])
  }

  const handleNext = () => {
    if (isLast) {
      submitMutation.mutate({ s: score, total: questions.length })
      setPhase('result')
    } else {
      setCurrentIdx(i => i + 1)
      setSelected(null)
      setShowExplanation(false)
    }
  }

  const handleRestart = () => {
    setPhase('setup')
    setQuestions([])
    setTopic('')
  }

  const pct = Math.round((score / questions.length) * 100)

  return (
    <PageTransition>
      <div className="page-content py-8">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-9 h-9 rounded-xl bg-violet/10 flex items-center justify-center">
            <Brain size={18} className="text-violet" />
          </div>
          <div>
            <h1 className="font-display text-xl font-semibold text-text-base">Quiz</h1>
            <p className="text-xs text-text-muted">Test your knowledge</p>
          </div>
        </div>

        <AnimatePresence mode="wait">
          {phase === 'setup' && (
            <motion.div
              key="setup"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="max-w-lg"
            >
              <div className="card mb-4">
                <label className="block text-sm text-text-muted mb-3">What topic do you want to be quizzed on?</label>
                <input
                  className="input-base mb-3"
                  placeholder="e.g. Neural networks, Python decorators..."
                  value={topic}
                  onChange={e => setTopic(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && topic.trim() && generateMutation.mutate(topic.trim())}
                />
                <button
                  onClick={() => generateMutation.mutate(topic.trim())}
                  disabled={!topic.trim() || generateMutation.isPending}
                  className="btn-primary flex items-center gap-2"
                >
                  {generateMutation.isPending && <Loader2 size={14} className="animate-spin" />}
                  Generate quiz
                </button>
                {generateMutation.isError && (
                  <p className="text-xs text-danger mt-2">{(generateMutation.error as Error).message}</p>
                )}
              </div>

              {/* Weak topics */}
              {loadingWeak ? (
                <Skeleton className="h-20 w-full rounded-xl" />
              ) : weakTopics?.weak_topics && weakTopics.weak_topics.length > 0 && (
                <div className="card">
                  <p className="text-xs text-text-muted mb-2">Suggested — your weak areas:</p>
                  <div className="flex flex-wrap gap-2">
                    {weakTopics.weak_topics.map(t => (
                      <button
                        key={t}
                        onClick={() => setTopic(t)}
                        className="text-xs px-3 py-1.5 rounded-lg bg-danger/10 text-danger border border-danger/20 hover:bg-danger/20 transition-colors cursor-pointer"
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </motion.div>
          )}

          {phase === 'active' && currentQ && (
            <motion.div
              key={`q-${currentIdx}`}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.25 }}
              className="max-w-2xl"
            >
              {/* Progress */}
              <div className="flex items-center gap-3 mb-6">
                <div className="flex-1 h-1.5 bg-white/6 rounded-full overflow-hidden">
                  <motion.div
                    className="h-full bg-accent-gradient rounded-full"
                    animate={{ width: `${((currentIdx) / questions.length) * 100}%` }}
                    transition={{ duration: 0.3 }}
                  />
                </div>
                <span className="text-xs text-text-muted whitespace-nowrap">
                  {currentIdx + 1} / {questions.length}
                </span>
              </div>

              <div className="card mb-4">
                <p className="font-display text-base font-medium text-text-base leading-relaxed">
                  {currentQ.question}
                </p>
              </div>

              <div className="space-y-2 mb-4">
                {currentQ.options.map(option => {
                  const isCorrect = option === currentQ.correct_answer
                  const isSelected = option === selected
                  let style = 'glass-hover'
                  if (selected) {
                    if (isCorrect) style = 'bg-success/10 border-success/30 text-success'
                    else if (isSelected) style = 'bg-danger/10 border-danger/30 text-danger'
                    else style = 'glass opacity-50'
                  }

                  return (
                    <button
                      key={option}
                      onClick={() => handleAnswer(option)}
                      disabled={!!selected}
                      className={`w-full text-left rounded-xl px-4 py-3 text-sm flex items-center gap-3 transition-all duration-150 cursor-pointer border border-transparent ${style}`}
                    >
                      {selected && isCorrect && <CheckCircle2 size={16} className="flex-shrink-0" />}
                      {selected && isSelected && !isCorrect && <XCircle size={16} className="flex-shrink-0" />}
                      <span>{option}</span>
                    </button>
                  )
                })}
              </div>

              {showExplanation && currentQ.explanation && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  className="card bg-accent/5 border-accent/15 mb-4"
                >
                  <p className="text-xs text-text-muted mb-1">Explanation</p>
                  <p className="text-sm text-text-base">{currentQ.explanation}</p>
                </motion.div>
              )}

              {selected && (
                <motion.button
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  onClick={handleNext}
                  className="btn-primary"
                >
                  {isLast ? 'See results' : 'Next question →'}
                </motion.button>
              )}
            </motion.div>
          )}

          {phase === 'result' && (
            <motion.div
              key="result"
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
              className="max-w-md"
            >
              <div className="card text-center mb-4">
                <div className="w-16 h-16 rounded-2xl bg-accent-gradient mx-auto flex items-center justify-center mb-4 shadow-accent-glow">
                  <Trophy size={28} className="text-white" />
                </div>
                <h2 className="font-display text-2xl font-bold text-text-base mb-1">{pct}%</h2>
                <p className="text-text-muted text-sm">
                  {score} out of {questions.length} correct
                </p>
                <div className="mt-4 h-2 bg-white/6 rounded-full overflow-hidden">
                  <motion.div
                    className="h-full rounded-full"
                    style={{ background: pct >= 70 ? '#34d399' : pct >= 40 ? '#fbbf24' : '#f87171' }}
                    initial={{ width: 0 }}
                    animate={{ width: `${pct}%` }}
                    transition={{ duration: 0.8, ease: 'easeOut' }}
                  />
                </div>
              </div>

              <div className="space-y-1.5 mb-6">
                {answers.map((a, i) => (
                  <div key={i} className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs ${a.correct ? 'bg-success/8 text-success' : 'bg-danger/8 text-danger'}`}>
                    {a.correct ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                    <span>Q{i + 1}: {a.correct ? 'Correct' : `Wrong — you chose "${a.selected}"`}</span>
                  </div>
                ))}
              </div>

              <button onClick={handleRestart} className="btn-primary flex items-center gap-2">
                <RotateCcw size={14} />
                New quiz
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </PageTransition>
  )
}
