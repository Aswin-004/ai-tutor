import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './store/auth'
import { api } from './lib/api'
import AuthPage from './pages/Auth'
import DashboardLayout from './layouts/DashboardLayout'
import type { User } from './store/auth'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { token } = useAuth()
  return token ? <>{children}</> : <Navigate to="/auth" replace />
}

function TokenValidator({ children }: { children: React.ReactNode }) {
  const { token, updateUser, logout } = useAuth()

  useEffect(() => {
    if (!token) return
    api.get<User>('/auth/me')
      .then(user => updateUser(user))
      .catch(() => logout())   // expired / invalid token → force re-login
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return <>{children}</>
}

export default function App() {
  return (
    <TokenValidator>
      <Routes>
        <Route path="/auth" element={<AuthPage />} />
        <Route
          path="/*"
          element={
            <PrivateRoute>
              <DashboardLayout />
            </PrivateRoute>
          }
        />
      </Routes>
    </TokenValidator>
  )
}
