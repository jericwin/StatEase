import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { Spinner } from '@/components/ui/feedback'
import { api, getToken, setToken } from './api'
import type { User } from './types'

export interface AuthConfig {
  mode: 'local' | 'password'
  allow_registration: boolean
  google: boolean
  python_console: boolean
}

interface AuthState {
  config: AuthConfig | undefined
  user: User | null | undefined
  loading: boolean
  signIn: (token: string) => Promise<void>
  signOut: () => void
}

const Ctx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const config = useQuery({ queryKey: ['auth-config'], queryFn: () => api.get<AuthConfig>('/auth/config'), staleTime: Infinity })
  const local = config.data?.mode === 'local'
  // Token kept in state so that signing in re-enables the "me" query in the same render cycle.
  const [token, setTokenState] = useState(() => getToken())
  const me = useQuery({
    queryKey: ['me', token],
    queryFn: () => api.get<User>('/auth/me'),
    enabled: !!config.data && (local || !!token),
    retry: false,
    staleTime: 60_000,
  })

  const signOut = useCallback(() => {
    setToken(null)
    qc.clear()
    window.location.assign('/')
  }, [qc])

  useEffect(() => {
    const h = () => {
      if (getToken()) {
        setToken(null)
        qc.removeQueries({ queryKey: ['me'] })
        window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
      }
    }
    window.addEventListener('statease:unauthorized', h)
    return () => window.removeEventListener('statease:unauthorized', h)
  }, [qc])

  const signIn = useCallback(
    async (newToken: string) => {
      setToken(newToken)
      const u = await api.get<User>('/auth/me')
      qc.setQueryData(['me', newToken], u)
      setTokenState(newToken)
    },
    [qc],
  )

  const hasSession = local || !!token
  const user = !hasSession ? null : me.isError ? null : me.data
  const loading = config.isPending || (hasSession && me.isPending)
  return <Ctx.Provider value={{ config: config.data, user, loading, signIn, signOut }}>{children}</Ctx.Provider>
}

export function useAuth() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth outside AuthProvider')
  return v
}

/** Protects application routes; unauthenticated visitors go to the login page and come back afterwards. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <Spinner className="p-8" label="Loading" />
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />
  return <>{children}</>
}
