import React, { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import type { Session, User } from '@supabase/supabase-js';
import { supabase, isSupabaseConfigured } from '../services/supabaseClient';

export interface UserProfile {
  id: string;
  email: string;
  full_name?: string;
  role: 'user' | 'admin';
}

interface AuthContextType {
  user: UserProfile | null;
  supabaseUser: User | null;
  session: Session | null;
  role: 'user' | 'admin';
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<{ error?: string }>;
  register: (email: string, password: string, fullName: string) => Promise<{ error?: string; confirmationRequired?: boolean }>;
  logout: () => Promise<void>;
  resetPassword: (email: string) => Promise<{ error?: string }>;
  updatePassword: (newPassword: string) => Promise<{ error?: string }>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [session, setSession] = useState<Session | null>(null);
  const [supabaseUser, setSupabaseUser] = useState<User | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const fetchProfile = async (sUser: User): Promise<UserProfile> => {
    let role: 'user' | 'admin' = 'user';
    let fullName = sUser.user_metadata?.full_name || '';

    // 1. Try querying public.profiles via Supabase client
    if (supabase) {
      try {
        const { data, error } = await supabase
          .from('profiles')
          .select('full_name, role')
          .eq('id', sUser.id)
          .maybeSingle();

        if (!error && data) {
          if (data.role === 'admin' || data.role === 'user') {
            role = data.role;
          }
          if (data.full_name) {
            fullName = data.full_name;
          }
        }
      } catch {
        // Fall through to metadata fallback
      }
    }

    // 2. Check auth metadata if role not already admin
    if (role !== 'admin') {
      const metaRole = sUser.app_metadata?.role || sUser.user_metadata?.role;
      if (metaRole === 'admin') {
        role = 'admin';
      }
    }

    return {
      id: sUser.id,
      email: sUser.email || '',
      full_name: fullName,
      role,
    };
  };

  const refreshProfile = async () => {
    if (!supabaseUser) return;
    const prof = await fetchProfile(supabaseUser);
    setUser(prof);
  };

  useEffect(() => {
    if (!isSupabaseConfigured || !supabase) {
      // In development mode without Supabase, provide fallback admin user
      setUser({
        id: '00000000-0000-0000-0000-000000000001',
        email: 'dev@company.local',
        full_name: 'Dev Administrator',
        role: 'admin',
      });
      setIsLoading(false);
      return;
    }

    // 1. Check initial session
    supabase.auth.getSession().then(({ data: { session: initSession } }) => {
      setSession(initSession);
      if (initSession?.user) {
        setSupabaseUser(initSession.user);
        fetchProfile(initSession.user).then((p) => {
          setUser(p);
          setIsLoading(false);
        });
      } else {
        setUser(null);
        setIsLoading(false);
      }
    });

    // 2. Listen for auth state changes
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (_event, newSession) => {
      setSession(newSession);
      if (newSession?.user) {
        setSupabaseUser(newSession.user);
        const p = await fetchProfile(newSession.user);
        setUser(p);
      } else {
        setSupabaseUser(null);
        setUser(null);
      }
      setIsLoading(false);
    });

    return () => {
      subscription.unsubscribe();
    };
  }, []);

  const login = async (email: string, password: string) => {
    if (!supabase) {
      return { error: 'Authentication service is not configured.' };
    }
    try {
      const { data, error } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      if (error) {
        if (error.message.toLowerCase().includes('email not confirmed')) {
          return { error: 'Please confirm your email before signing in.' };
        }
        if (error.message.toLowerCase().includes('invalid login credentials')) {
          return { error: 'Email or password is incorrect.' };
        }
        return { error: error.message };
      }
      if (data.user) {
        const p = await fetchProfile(data.user);
        setUser(p);
      }
      return {};
    } catch (err: unknown) {
      return { error: (err as Error).message || 'Service temporarily unavailable.' };
    }
  };

  const register = async (email: string, password: string, fullName: string) => {
    if (!supabase) {
      return { error: 'Authentication service is not configured.' };
    }
    try {
      const { data, error } = await supabase.auth.signUp({
        email: email.trim(),
        password,
        options: {
          data: {
            full_name: fullName.trim(),
          },
        },
      });
      if (error) {
        return { error: error.message };
      }
      // If user is returned without session, confirmation email is required
      const confirmationRequired = !data.session;
      return { confirmationRequired };
    } catch (err: unknown) {
      return { error: (err as Error).message || 'Failed to create account.' };
    }
  };

  const logout = async () => {
    if (supabase) {
      try {
        await supabase.auth.signOut({ scope: 'local' });
      } catch {
        // Safe swallow
      }
    }
    setSession(null);
    setSupabaseUser(null);
    setUser(null);
  };

  const resetPassword = async (email: string) => {
    if (!supabase) {
      return { error: 'Authentication service is not configured.' };
    }
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email.trim(), {
        redirectTo: `${window.location.origin}/reset-password`,
      });
      if (error) return { error: error.message };
      return {};
    } catch (err: unknown) {
      return { error: (err as Error).message || 'Failed to send reset link.' };
    }
  };

  const updatePassword = async (newPassword: string) => {
    if (!supabase) {
      return { error: 'Authentication service is not configured.' };
    }
    try {
      const { error } = await supabase.auth.updateUser({
        password: newPassword,
      });
      if (error) return { error: error.message };
      return {};
    } catch (err: unknown) {
      return { error: (err as Error).message || 'Failed to update password.' };
    }
  };

  const role: 'user' | 'admin' = user?.role || 'user';
  const isAuthenticated = Boolean(user);

  return (
    <AuthContext.Provider
      value={{
        user,
        supabaseUser,
        session,
        role,
        isLoading,
        isAuthenticated,
        login,
        register,
        logout,
        resetPassword,
        updatePassword,
        refreshProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
