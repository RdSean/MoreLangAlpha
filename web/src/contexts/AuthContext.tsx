import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { PROFILE_REQUEST_TIMEOUT_MS } from '@/api/user';
import { queryKeys } from '@/lib/queryKeys';
import { resetNavPanelExpansion } from '@/pages/ChatAgent/components/navExpansionStore';
import { resetStableNavOrder } from '@/pages/ChatAgent/hooks/useNavigationData';
import { resetSharedWorkspaceThreads } from '@/lib/navThreadsStore';
import { runAuthResets } from '@/lib/authResets';
import '@/pages/Education/rewardPurchaseStorage';

export interface AuthMember {
  user_id: string;
  email: string | null;
  name: string;
  role: 'parent' | 'student';
  household_id: string;
}

export interface ParentRegistrationInput {
  email: string;
  password: string;
  name: string;
  householdName: string;
  timezone: string;
}

export interface AuthContextValue {
  userId: string | null;
  member: AuthMember | null;
  isInitialized: boolean;
  isLoggedIn: boolean;
  login: (loginIdentifier: string, password: string) => Promise<void>;
  registerParent: (input: ParentRegistrationInput) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [member, setMember] = useState<AuthMember | null>(null);
  const [isInitialized, setIsInitialized] = useState(false);
  const queryClient = useQueryClient();
  const previousUserId = useRef<string | null>(null);

  const clearUserState = useCallback(() => {
    queryClient.clear();
    resetNavPanelExpansion();
    resetStableNavOrder();
    resetSharedWorkspaceThreads();
    runAuthResets();
  }, [queryClient]);

  const acceptMember = useCallback((nextMember: AuthMember | null) => {
    if (previousUserId.current && nextMember?.user_id !== previousUserId.current) {
      clearUserState();
    }
    previousUserId.current = nextMember?.user_id ?? null;
    setMember(nextMember);
  }, [clearUserState]);

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get<AuthMember>('/api/v1/auth/me', {
        timeout: PROFILE_REQUEST_TIMEOUT_MS,
      });
      acceptMember(data);
    } catch {
      acceptMember(null);
    } finally {
      setIsInitialized(true);
    }
  }, [acceptMember]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (loginIdentifier: string, password: string) => {
    const { data } = await api.post<AuthMember>('/api/v1/auth/login', {
      login_identifier: loginIdentifier,
      password,
    });
    acceptMember(data);
    await queryClient.invalidateQueries({ queryKey: queryKeys.user.all });
  }, [acceptMember, queryClient]);

  const registerParent = useCallback(async (input: ParentRegistrationInput) => {
    const { data } = await api.post<AuthMember>('/api/v1/auth/register-parent', {
      email: input.email,
      password: input.password,
      name: input.name,
      household_name: input.householdName,
      timezone: input.timezone,
    });
    acceptMember(data);
    await queryClient.invalidateQueries({ queryKey: queryKeys.user.all });
  }, [acceptMember, queryClient]);

  const logout = useCallback(async () => {
    try {
      await api.post('/api/v1/auth/logout');
    } finally {
      acceptMember(null);
      clearUserState();
    }
  }, [acceptMember, clearUserState]);

  return (
    <AuthContext.Provider value={{
      userId: member?.user_id ?? null,
      member,
      isInitialized,
      isLoggedIn: member !== null,
      login,
      registerParent,
      logout,
      refresh,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
