import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Home, MessageSquare, Brain, Map, BarChart3,
  User, LogOut, ChevronLeft, ChevronRight, BookOpen,
} from 'lucide-react'
import { cn } from '../lib/cn'
import { useAuth } from '../store/auth'

const NAV_ITEMS = [
  { to: '/',         icon: Home,         label: 'Home' },
  { to: '/chat',     icon: MessageSquare, label: 'Chat' },
  { to: '/quiz',     icon: Brain,        label: 'Quiz' },
  { to: '/roadmap',  icon: Map,          label: 'Roadmap' },
  { to: '/analytics',icon: BarChart3,    label: 'Analytics' },
  { to: '/profile',  icon: User,         label: 'Profile' },
]

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false)
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/auth')
  }

  return (
    <motion.aside
      animate={{ width: collapsed ? 64 : 220 }}
      transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
      className="relative flex flex-col h-screen flex-shrink-0 overflow-hidden"
      style={{
        background: 'rgba(255,255,255,0.02)',
        borderRight: '1px solid rgba(255,255,255,0.06)',
      }}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 overflow-hidden">
        <div className="w-8 h-8 rounded-lg bg-accent-gradient flex items-center justify-center flex-shrink-0 shadow-accent-glow">
          <BookOpen size={16} className="text-white" />
        </div>
        <AnimatePresence>
          {!collapsed && (
            <motion.span
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.15 }}
              className="font-display font-semibold text-sm text-text-base whitespace-nowrap"
            >
              Aurora Scholar
            </motion.span>
          )}
        </AnimatePresence>
      </div>

      {/* Nav */}
      <nav className="flex-1 flex flex-col gap-0.5 px-2 py-2">
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              cn(
                'relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 cursor-pointer group overflow-hidden',
                isActive
                  ? 'bg-accent/10 text-accent'
                  : 'text-text-muted hover:bg-white/5 hover:text-text-base'
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon
                  size={18}
                  className={cn(
                    'flex-shrink-0 transition-colors',
                    isActive ? 'text-accent' : 'text-text-subtle group-hover:text-text-muted'
                  )}
                />
                <AnimatePresence>
                  {!collapsed && (
                    <motion.span
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.12 }}
                      className="whitespace-nowrap"
                    >
                      {label}
                    </motion.span>
                  )}
                </AnimatePresence>
                {isActive && (
                  <motion.div
                    layoutId="sidebar-indicator"
                    className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 bg-accent rounded-r-full"
                    transition={{ duration: 0.2, ease: 'easeInOut' }}
                  />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* User + Logout */}
      <div className="px-2 pb-4 flex flex-col gap-0.5">
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-text-subtle hover:bg-danger/10 hover:text-danger transition-all duration-150 cursor-pointer w-full text-left"
        >
          <LogOut size={18} className="flex-shrink-0" />
          <AnimatePresence>
            {!collapsed && (
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.12 }}
                className="whitespace-nowrap"
              >
                Log out
              </motion.span>
            )}
          </AnimatePresence>
        </button>

        {/* User chip */}
        {!collapsed && user && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="mt-2 mx-1 p-2.5 rounded-xl bg-white/3 border border-white/6"
          >
            <p className="text-xs font-medium text-text-base truncate">{user.full_name || user.username}</p>
            <p className="text-[11px] text-text-subtle truncate mt-0.5">{user.email}</p>
          </motion.div>
        )}
      </div>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed(c => !c)}
        className="absolute -right-3 top-6 w-6 h-6 rounded-full glass border border-white/10 flex items-center justify-center cursor-pointer hover:border-accent/40 hover:text-accent transition-all duration-150 z-10"
      >
        {collapsed ? <ChevronRight size={12} /> : <ChevronLeft size={12} />}
      </button>
    </motion.aside>
  )
}
