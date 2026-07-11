import { Routes, Route, useLocation } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import Sidebar from '../components/Sidebar'
import HomePage from '../pages/Home'
import ChatPage from '../pages/Chat'
import QuizPage from '../pages/Quiz'
import RoadmapPage from '../pages/Roadmap'
import AnalyticsPage from '../pages/Analytics'
import ProfilePage from '../pages/Profile'

export default function DashboardLayout() {
  const location = useLocation()

  return (
    <div className="flex h-screen bg-bg overflow-hidden relative">
      {/* Aurora background effect */}
      <div
        className="pointer-events-none fixed inset-0 z-0 animate-aurora-pulse"
        style={{
          background:
            'radial-gradient(ellipse 70% 40% at 15% 0%, rgba(129,140,248,0.14) 0%, transparent 70%), ' +
            'radial-gradient(ellipse 50% 35% at 85% 100%, rgba(167,139,250,0.10) 0%, transparent 70%)',
        }}
      />

      <Sidebar />

      <main className="flex-1 overflow-y-auto relative z-10">
        <AnimatePresence mode="wait" initial={false}>
          <Routes location={location} key={location.pathname}>
            <Route path="/"          element={<HomePage />} />
            <Route path="/chat"      element={<ChatPage />} />
            <Route path="/quiz"      element={<QuizPage />} />
            <Route path="/roadmap"   element={<RoadmapPage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="/profile"   element={<ProfilePage />} />
          </Routes>
        </AnimatePresence>
      </main>
    </div>
  )
}
