import { useState, useRef } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  User, FileText, Trash2, Upload, Loader2,
  Key, Plus, CheckCircle2,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useAuth } from '../store/auth'
import PageTransition from '../components/PageTransition'
import { Skeleton } from '../components/Skeleton'

interface Document {
  id: string
  filename: string
  subject: string
  created_at: string
  chunk_count?: number
}

interface DocsResponse {
  documents: Document[]
}

export default function ProfilePage() {
  const { user, updateUser } = useAuth()
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [saved, setSaved] = useState(false)
  const [newSubject, setNewSubject] = useState('')
  const [showSubjectInput, setShowSubjectInput] = useState(false)
  const [passForm, setPassForm] = useState({ current: '', next: '', confirm: '' })

  // Profile form state
  const [form, setForm] = useState({
    full_name: user?.full_name ?? '',
    level: user?.level ?? '',
    learning_style: user?.learning_style ?? '',
    goals: user?.goals ?? '',
  })

  const { data: docsData, isLoading: loadingDocs } = useQuery<DocsResponse>({
    queryKey: ['documents'],
    queryFn: () => api.get('/documents'),
  })

  const updateProfileMutation = useMutation({
    mutationFn: () => api.put('/auth/profile', form),
    onSuccess: async (data: unknown) => {
      updateUser(data as NonNullable<typeof user>)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  const uploadMutation = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData()
      fd.append('file', file)
      return api.post('/upload_pdf', fd)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/documents/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  })

  const refreshUser = async () => {
    try {
      const fresh = await api.get<typeof user>('/auth/me')
      if (fresh) updateUser(fresh as NonNullable<typeof user>)
    } catch { /* token invalid — auth guard will handle */ }
  }

  const switchSubjectMutation = useMutation({
    mutationFn: (subject: string) => api.patch('/auth/subject', { subject }),
    onSuccess: async (_, subject) => {
      updateUser({ current_subject: subject })
      await refreshUser()   // pulls updated subjects_list from server
      qc.invalidateQueries({ queryKey: ['stats'] })
      qc.invalidateQueries({ queryKey: ['analytics'] })
      qc.invalidateQueries({ queryKey: ['roadmap'] })
      qc.invalidateQueries({ queryKey: ['chat-history'] })
    },
  })

  const changePassMutation = useMutation({
    mutationFn: () =>
      api.post('/auth/change-password', {
        current_password: passForm.current,
        new_password: passForm.next,
      }),
    onSuccess: () => setPassForm({ current: '', next: '', confirm: '' }),
  })

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) uploadMutation.mutate(file)
    e.target.value = ''
  }

  const handleAddSubject = () => {
    const s = newSubject.trim().toLowerCase()
    if (!s) return
    switchSubjectMutation.mutate(s)
    setNewSubject('')
    setShowSubjectInput(false)
  }

  const docs = docsData?.documents ?? []

  return (
    <PageTransition>
      <div className="page-content py-8 space-y-5">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-9 h-9 rounded-xl bg-accent/10 flex items-center justify-center">
            <User size={18} className="text-accent" />
          </div>
          <h1 className="font-display text-xl font-semibold text-text-base">Profile</h1>
        </div>

        {/* Profile info */}
        <div className="card">
          <h2 className="font-display font-semibold text-sm text-text-base mb-4">Account details</h2>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-text-muted mb-1.5">Full name</label>
              <input
                className="input-base"
                value={form.full_name}
                onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))}
                placeholder="Your name"
              />
            </div>
            <div>
              <label className="block text-xs text-text-muted mb-1.5">Username</label>
              <input className="input-base opacity-50" value={user?.username || ''} disabled />
            </div>
            <div>
              <label className="block text-xs text-text-muted mb-1.5">Level</label>
              <select
                className="input-base"
                value={form.level}
                onChange={e => setForm(f => ({ ...f, level: e.target.value }))}
              >
                <option value="">Select level</option>
                {['Beginner', 'Intermediate', 'Advanced', 'Expert'].map(l => (
                  <option key={l} value={l}>{l}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-text-muted mb-1.5">Learning style</label>
              <select
                className="input-base"
                value={form.learning_style}
                onChange={e => setForm(f => ({ ...f, learning_style: e.target.value }))}
              >
                <option value="">Select style</option>
                {['Visual', 'Auditory', 'Reading/Writing', 'Kinesthetic'].map(l => (
                  <option key={l} value={l}>{l}</option>
                ))}
              </select>
            </div>
            <div className="col-span-2">
              <label className="block text-xs text-text-muted mb-1.5">Learning goals</label>
              <textarea
                className="input-base resize-none"
                rows={2}
                value={form.goals}
                onChange={e => setForm(f => ({ ...f, goals: e.target.value }))}
                placeholder="What are you trying to learn?"
              />
            </div>
          </div>
          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={() => updateProfileMutation.mutate()}
              disabled={updateProfileMutation.isPending}
              className="btn-primary flex items-center gap-2"
            >
              {updateProfileMutation.isPending && <Loader2 size={14} className="animate-spin" />}
              Save
            </button>
            {saved && (
              <motion.div
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                className="flex items-center gap-1.5 text-xs text-success"
              >
                <CheckCircle2 size={14} />
                Saved
              </motion.div>
            )}
          </div>
        </div>

        {/* Subject workspaces */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display font-semibold text-sm text-text-base">Subject workspaces</h2>
            <button
              onClick={() => setShowSubjectInput(s => !s)}
              className="btn-ghost text-xs flex items-center gap-1"
            >
              <Plus size={13} /> Add
            </button>
          </div>

          <div className="flex flex-wrap gap-2 mb-3">
            {(user?.subjects_list ?? ['general']).map(s => (
              <button
                key={s}
                onClick={() => switchSubjectMutation.mutate(s)}
                className={`text-xs px-3 py-1.5 rounded-lg border capitalize cursor-pointer transition-all duration-150 ${
                  user?.current_subject === s
                    ? 'bg-accent/15 text-accent border-accent/30'
                    : 'glass text-text-muted border-white/8 hover:border-white/15'
                }`}
              >
                {s}
                {user?.current_subject === s && (
                  <span className="ml-1.5 text-[10px] opacity-70">active</span>
                )}
              </button>
            ))}
          </div>

          {showSubjectInput && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              className="flex gap-2 mt-3"
            >
              <input
                className="input-base flex-1"
                placeholder="New subject name (e.g. Python, History)"
                value={newSubject}
                onChange={e => setNewSubject(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleAddSubject()}
                autoFocus
              />
              <button onClick={handleAddSubject} disabled={switchSubjectMutation.isPending} className="btn-primary px-4">
                {switchSubjectMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : 'Add'}
              </button>
            </motion.div>
          )}

          {switchSubjectMutation.isError && (
            <p className="text-xs text-danger mt-2">{(switchSubjectMutation.error as Error).message}</p>
          )}

          <p className="text-xs text-text-subtle mt-3">
            Each workspace has its own documents, chat, quiz scores and roadmap.
          </p>
        </div>

        {/* Documents */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display font-semibold text-sm text-text-base">Documents</h2>
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploadMutation.isPending}
              className="btn-primary text-xs flex items-center gap-1.5 py-1.5"
            >
              {uploadMutation.isPending ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
              Upload PDF
            </button>
            <input ref={fileRef} type="file" accept=".pdf" className="hidden" onChange={handleFileChange} />
          </div>

          {loadingDocs ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full rounded-lg" />
              ))}
            </div>
          ) : docs.length === 0 ? (
            <div className="py-6 text-center">
              <FileText size={24} className="text-text-subtle mx-auto mb-2" />
              <p className="text-sm text-text-muted">No documents uploaded yet.</p>
              <p className="text-xs text-text-subtle mt-0.5">Upload PDFs to enable context-aware chat.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {docs.map(doc => (
                <div key={doc.id} className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-white/3 border border-white/6">
                  <FileText size={14} className="text-text-subtle flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-text-base truncate">{doc.filename}</p>
                    <p className="text-xs text-text-subtle">
                      {doc.subject} · {doc.chunk_count ?? '?'} chunks
                    </p>
                  </div>
                  <button
                    onClick={() => deleteMutation.mutate(doc.id)}
                    disabled={deleteMutation.isPending}
                    className="text-text-subtle hover:text-danger transition-colors cursor-pointer p-1"
                    title="Delete document"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Change password */}
        <div className="card">
          <div className="flex items-center gap-2 mb-4">
            <Key size={14} className="text-text-subtle" />
            <h2 className="font-display font-semibold text-sm text-text-base">Change password</h2>
          </div>
          <div className="space-y-3 max-w-sm">
            {['current', 'next', 'confirm'].map((field) => (
              <div key={field}>
                <label className="block text-xs text-text-muted mb-1.5 capitalize">
                  {field === 'next' ? 'New password' : field === 'confirm' ? 'Confirm new password' : 'Current password'}
                </label>
                <input
                  className="input-base"
                  type="password"
                  value={passForm[field as keyof typeof passForm]}
                  onChange={e => setPassForm(p => ({ ...p, [field]: e.target.value }))}
                  placeholder="••••••••"
                />
              </div>
            ))}
            {changePassMutation.isError && (
              <p className="text-xs text-danger">{(changePassMutation.error as Error).message}</p>
            )}
            {changePassMutation.isSuccess && (
              <p className="text-xs text-success flex items-center gap-1"><CheckCircle2 size={12} /> Password changed</p>
            )}
            <button
              onClick={() => {
                if (passForm.next !== passForm.confirm) return
                changePassMutation.mutate()
              }}
              disabled={
                changePassMutation.isPending ||
                !passForm.current ||
                !passForm.next ||
                passForm.next !== passForm.confirm
              }
              className="btn-primary flex items-center gap-2"
            >
              {changePassMutation.isPending && <Loader2 size={14} className="animate-spin" />}
              Update password
            </button>
            {passForm.next && passForm.confirm && passForm.next !== passForm.confirm && (
              <p className="text-xs text-danger">Passwords do not match</p>
            )}
          </div>
        </div>
      </div>
    </PageTransition>
  )
}
