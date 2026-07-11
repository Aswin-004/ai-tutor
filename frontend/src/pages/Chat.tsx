import { useState, useRef, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Send, Trash2, ThumbsUp, ThumbsDown, Loader2,
  Mic, MicOff, ExternalLink, ChevronDown, ChevronUp,
} from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../store/auth'
import PageTransition from '../components/PageTransition'
import { Skeleton } from '../components/Skeleton'

interface VideoRec {
  title: string
  url: string
  level: 'beginner' | 'advanced'
}

interface ChatEntry {
  role: 'user' | 'assistant'
  message: string
  created_at: string
  emotion?: string
  videos?: VideoRec[]
}

interface ChatResponse {
  response: string
  emotion?: string
  videos?: VideoRec[]
}

interface HistoryResponse {
  history: { role: 'user' | 'assistant'; message: string; created_at: string }[]
}

interface TranscribeResponse {
  transcript: string
  tone: string
  emotion: string
}

const EMOTION_STYLE: Record<string, { color: string; label: string }> = {
  confident:  { color: 'bg-success',  label: 'Confident' },
  excited:    { color: 'bg-cyan',     label: 'Excited' },
  confused:   { color: 'bg-warning',  label: 'Confused' },
  frustrated: { color: 'bg-danger',   label: 'Frustrated' },
  neutral:    { color: 'bg-text-subtle', label: 'Neutral' },
}

function VideoCard({ video }: { video: VideoRec }) {
  return (
    <a
      href={video.url}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/4 border border-white/8 hover:border-accent/30 hover:bg-accent/5 transition-all duration-150 group"
    >
      <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${video.level === 'beginner' ? 'bg-success' : 'bg-violet'}`} />
      <span className="text-xs text-text-muted group-hover:text-text-base transition-colors flex-1 truncate">{video.title}</span>
      <ExternalLink size={10} className="text-text-subtle group-hover:text-accent transition-colors flex-shrink-0" />
    </a>
  )
}

function MessageBubble({ msg, onFeedback }: { msg: ChatEntry; onFeedback: (t: 'up' | 'down') => void }) {
  const [showVideos, setShowVideos] = useState(false)
  const isAI = msg.role === 'assistant'
  const emotion = msg.emotion ? EMOTION_STYLE[msg.emotion] : null
  const hasVideos = (msg.videos?.length ?? 0) > 0

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={`flex ${isAI ? 'justify-start' : 'justify-end'}`}
    >
      <div className={`max-w-[78%] ${isAI ? '' : ''}`}>
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
            isAI
              ? 'glass rounded-bl-md'
              : 'bg-accent/20 text-text-base rounded-br-md'
          }`}
        >
          <p className="whitespace-pre-wrap text-text-base">{msg.message}</p>

          {isAI && (
            <div className="flex items-center gap-2 mt-2 pt-2 border-t border-white/6">
              {/* Emotion pill */}
              {emotion && (
                <span className="flex items-center gap-1 text-[10px] text-text-subtle">
                  <span className={`w-1.5 h-1.5 rounded-full ${emotion.color}`} />
                  {emotion.label}
                </span>
              )}
              <div className="flex-1" />
              <button
                onClick={() => onFeedback('up')}
                className="text-text-subtle hover:text-success transition-colors cursor-pointer p-0.5"
                title="Helpful"
              >
                <ThumbsUp size={11} />
              </button>
              <button
                onClick={() => onFeedback('down')}
                className="text-text-subtle hover:text-danger transition-colors cursor-pointer p-0.5"
                title="Not helpful"
              >
                <ThumbsDown size={11} />
              </button>
            </div>
          )}
        </div>

        {/* Video recommendations */}
        {isAI && hasVideos && (
          <div className="mt-1.5">
            <button
              onClick={() => setShowVideos(v => !v)}
              className="flex items-center gap-1.5 text-[11px] text-accent hover:text-accent/80 transition-colors cursor-pointer px-1"
            >
              {showVideos ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
              {msg.videos!.length} recommended resource{msg.videos!.length > 1 ? 's' : ''}
            </button>
            <AnimatePresence>
              {showVideos && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="mt-1.5 space-y-1.5 overflow-hidden"
                >
                  {msg.videos!.map((v, i) => <VideoCard key={i} video={v} />)}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>
    </motion.div>
  )
}

export default function ChatPage() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const [input, setInput] = useState('')
  const [localMsgs, setLocalMsgs] = useState<ChatEntry[]>([])
  const [isRecording, setIsRecording] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])

  const { data, isLoading } = useQuery<HistoryResponse>({
    queryKey: ['chat-history'],
    queryFn: () => api.get('/chat/history'),
  })

  // Clear optimistic messages whenever persisted history reloads
  useEffect(() => {
    if (data) setLocalMsgs([])
  }, [data])

  // Merge persisted history with in-flight optimistic messages
  const history: ChatEntry[] = [
    ...(data?.history ?? []),
    ...localMsgs,
  ]

  const sendMutation = useMutation({
    mutationFn: (message: string) => api.post<ChatResponse>('/chat', { message }),
    onMutate: (message) => {
      setLocalMsgs(prev => [...prev, {
        role: 'user', message, created_at: new Date().toISOString(),
      }])
    },
    onSuccess: (res) => {
      setLocalMsgs(prev => [...prev, {
        role: 'assistant',
        message: res.response,
        created_at: new Date().toISOString(),
        emotion: res.emotion,
        videos: res.videos,
      }])
      qc.invalidateQueries({ queryKey: ['chat-history'] })
    },
    onError: () => {
      // remove the optimistic user message on failure
      setLocalMsgs(prev => prev.slice(0, -1))
    },
  })

  const clearMutation = useMutation({
    mutationFn: () => api.delete('/chat/history'),
    onSuccess: () => {
      setLocalMsgs([])
      qc.invalidateQueries({ queryKey: ['chat-history'] })
    },
  })

  const feedbackMutation = useMutation({
    mutationFn: (type: 'up' | 'down') =>
      api.post('/feedback', { message: '', feedback_type: type }),
  })

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => { scrollToBottom() }, [history.length, scrollToBottom])

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 120) + 'px'
  }, [input])

  const handleSend = () => {
    const msg = input.trim()
    if (!msg || sendMutation.isPending) return
    setInput('')
    sendMutation.mutate(msg)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // ── Voice recording ────────────────────────────────────────
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/ogg'
      const recorder = new MediaRecorder(stream, { mimeType })
      audioChunksRef.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data)
      }

      recorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop())
        const blob = new Blob(audioChunksRef.current, { type: mimeType })
        setIsTranscribing(true)
        try {
          const fd = new FormData()
          fd.append('file', blob, `recording.${mimeType.split('/')[1]}`)
          const res = await api.post<TranscribeResponse>('/voice/transcribe', fd)
          setInput(res.transcript)
          // Focus textarea after transcription
          setTimeout(() => textareaRef.current?.focus(), 50)
        } catch {
          // silently fail — user still has the input box
        } finally {
          setIsTranscribing(false)
        }
      }

      mediaRecorderRef.current = recorder
      recorder.start()
      setIsRecording(true)
    } catch {
      // Microphone access denied or not available
    }
  }

  const stopRecording = () => {
    mediaRecorderRef.current?.stop()
    setIsRecording(false)
  }

  const toggleRecording = () => {
    if (isRecording) stopRecording()
    else startRecording()
  }

  return (
    <PageTransition>
      <div className="flex flex-col h-full">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/6 flex-shrink-0">
          <div>
            <h1 className="font-display text-lg font-semibold text-text-base">Chat</h1>
            <p className="text-xs text-text-muted mt-0.5 capitalize">
              {user?.current_subject || 'general'} workspace
            </p>
          </div>
          <button
            onClick={() => clearMutation.mutate()}
            disabled={clearMutation.isPending || history.length === 0}
            className="btn-ghost flex items-center gap-1.5 text-xs"
          >
            <Trash2 size={13} />
            Clear
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {isLoading ? (
            <div className="space-y-4">
              {[0, 1, 2].map(i => (
                <div key={i} className={`flex ${i % 2 === 0 ? 'justify-end' : 'justify-start'}`}>
                  <Skeleton className={`h-12 ${i % 2 === 0 ? 'w-2/3' : 'w-3/4'} rounded-2xl`} />
                </div>
              ))}
            </div>
          ) : history.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center py-16">
              <div className="w-12 h-12 rounded-2xl bg-accent/10 flex items-center justify-center mb-4">
                <Send size={20} className="text-accent" />
              </div>
              <p className="font-display text-base font-medium text-text-base mb-1">Start a conversation</p>
              <p className="text-sm text-text-muted max-w-xs">
                Ask anything about your uploaded documents, or explore any topic.
              </p>
              <p className="text-xs text-text-subtle mt-3">
                Use the <span className="text-accent">mic button</span> to speak instead of type.
              </p>
            </div>
          ) : (
            <>
              <AnimatePresence initial={false}>
                {history.map((msg, i) => (
                  <MessageBubble
                    key={i}
                    msg={msg}
                    onFeedback={feedbackMutation.mutate}
                  />
                ))}
              </AnimatePresence>
              {sendMutation.isPending && (
                <div className="flex justify-start">
                  <div className="glass rounded-2xl rounded-bl-md px-4 py-3">
                    <div className="flex gap-1.5">
                      {[0, 1, 2].map(i => (
                        <motion.span
                          key={i}
                          className="w-1.5 h-1.5 rounded-full bg-text-subtle"
                          animate={{ y: [0, -4, 0] }}
                          transition={{ duration: 0.6, repeat: Infinity, delay: i * 0.15 }}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input bar */}
        <div className="px-6 py-4 border-t border-white/6 flex-shrink-0">
          {/* Transcribing indicator */}
          <AnimatePresence>
            {isTranscribing && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="flex items-center gap-2 text-xs text-accent mb-2 px-1"
              >
                <Loader2 size={12} className="animate-spin" />
                Transcribing audio…
              </motion.div>
            )}
          </AnimatePresence>

          <div className={`glass rounded-2xl flex items-end gap-2 px-4 py-3 transition-all duration-200 ${isRecording ? 'border-danger/40 shadow-[0_0_0_2px_rgba(248,113,113,0.15)]' : ''}`}>
            {/* Voice button */}
            <button
              type="button"
              onClick={toggleRecording}
              disabled={isTranscribing}
              className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 cursor-pointer transition-all duration-200 ${
                isRecording
                  ? 'bg-danger text-white shadow-[0_0_12px_rgba(248,113,113,0.5)]'
                  : 'text-text-subtle hover:text-accent hover:bg-white/5'
              }`}
              title={isRecording ? 'Stop recording' : 'Start voice input'}
            >
              {isRecording ? (
                <motion.div
                  animate={{ scale: [1, 1.15, 1] }}
                  transition={{ duration: 1, repeat: Infinity }}
                >
                  <MicOff size={15} />
                </motion.div>
              ) : (
                <Mic size={15} />
              )}
            </button>

            <textarea
              ref={textareaRef}
              rows={1}
              className="flex-1 bg-transparent text-sm text-text-base placeholder:text-text-subtle outline-none resize-none py-0.5"
              placeholder={isRecording ? 'Recording… click mic to stop' : 'Ask a question…'}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isRecording}
            />

            {/* Send button */}
            <button
              onClick={handleSend}
              disabled={!input.trim() || sendMutation.isPending || isRecording}
              className="w-8 h-8 rounded-xl bg-accent flex items-center justify-center flex-shrink-0 cursor-pointer hover:bg-[#9aa3fb] transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {sendMutation.isPending
                ? <Loader2 size={13} className="animate-spin text-white" />
                : <Send size={13} className="text-white" />
              }
            </button>
          </div>

          <p className="text-[11px] text-text-subtle mt-1.5 text-center">
            Shift+Enter for new line · Enter to send · Mic for voice
          </p>
        </div>
      </div>
    </PageTransition>
  )
}
