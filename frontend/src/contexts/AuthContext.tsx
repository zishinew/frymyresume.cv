import { createContext, useContext, useState, useEffect } from 'react'
import type { ReactNode } from 'react'
import { supabase } from '../lib/supabase'
import type { Session } from '@supabase/supabase-js'
import { API_BASE_URL } from '../config'

interface User {
  id: string
  email: string
  username: string
  profile_picture: string | null
  auth_provider: string
  is_verified: boolean
  created_at: string | null
}

interface AuthContextType {
  user: User | null
  session: Session | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, username: string) => Promise<void>
  logout: () => Promise<void>
  loginWithGoogle: () => Promise<void>
  loginWithGitHub: () => Promise<void>
  refreshUser: () => Promise<void>
  getAccessToken: () => Promise<string | null>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [session, setSession] = useState<Session | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let isMounted = true

    // Get initial session with timeout
    const initAuth = async () => {
      try {
        const { data: { session } } = await supabase.auth.getSession()
        if (!isMounted) return

        setSession(session)
        if (session) {
          await fetchUserProfile(session)
        } else {
          setIsLoading(false)
        }
      } catch (error) {
        console.error('Error getting session:', error)
        if (isMounted) {
          setIsLoading(false)
        }
      }
    }

    // Set a timeout to ensure loading state is cleared even if Supabase hangs
    const timeoutId = setTimeout(() => {
      if (isMounted) {
        console.warn('Auth initialization timed out')
        setIsLoading(false)
      }
    }, 5000)

    initAuth().finally(() => clearTimeout(timeoutId))

    // Listen for auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (_event, session) => {
        if (!isMounted) return
        setSession(session)
        if (session) {
          await fetchUserProfile(session)
        } else {
          setUser(null)
          setIsLoading(false)
        }
      }
    )

    return () => {
      isMounted = false
      subscription.unsubscribe()
    }
  }, [])

  const buildUserFromSession = (session: Session): User => {
    const supabaseUser = session.user
    return {
      id: supabaseUser.id,
      email: supabaseUser.email || '',
      username: supabaseUser.user_metadata?.full_name || supabaseUser.user_metadata?.name || supabaseUser.email?.split('@')[0] || '',
      profile_picture: supabaseUser.user_metadata?.avatar_url || null,
      auth_provider: supabaseUser.app_metadata?.provider || 'email',
      is_verified: !!supabaseUser.email_confirmed_at,
      created_at: supabaseUser.created_at,
    }
  }

  const fetchUserProfile = async (session: Session) => {
    try {
      // Build user from session data immediately (no network call needed)
      const userData = buildUserFromSession(session)
      setUser(userData)
      setIsLoading(false)

      // Then try to get enhanced profile from backend (non-blocking, fire and forget)
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 2000) // 2 second timeout

      fetch(`${API_BASE_URL}/api/auth/me`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
        signal: controller.signal,
      })
        .then((response) => {
          clearTimeout(timeoutId)
          if (response.ok) {
            return response.json()
          }
          return null
        })
        .then((backendUserData) => {
          if (backendUserData) {
            setUser(backendUserData)
          }
        })
        .catch(() => {
          // Backend not available - that's fine, we already have Supabase data
        })
    } catch {
      setUser(null)
      setIsLoading(false)
    }
  }

  const refreshUser = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    if (session) {
      await fetchUserProfile(session)
    }
  }

  const login = async (email: string, password: string) => {
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password,
    })

    if (error) {
      throw new Error(error.message)
    }

    // Fetch user profile immediately after login
    if (data.session) {
      await fetchUserProfile(data.session)
    }
  }

  const register = async (email: string, password: string, username: string) => {
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          full_name: username,
        },
      },
    })

    if (error) {
      throw new Error(error.message)
    }
  }

  const logout = async () => {
    await supabase.auth.signOut()
    setUser(null)
    setSession(null)
  }

  const loginWithGoogle = async () => {
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    })

    if (error) {
      throw new Error(error.message)
    }
  }

  const loginWithGitHub = async () => {
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'github',
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    })

    if (error) {
      throw new Error(error.message)
    }
  }

  const getAccessToken = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    return session?.access_token ?? null
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        session,
        isLoading,
        isAuthenticated: !!user,
        login,
        register,
        logout,
        loginWithGoogle,
        loginWithGitHub,
        refreshUser,
        getAccessToken,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
