import React, { createContext, useContext, useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch, type AuthSession, type StoreSummary } from '../lib/api';

interface StoreContextValue {
  stores: StoreSummary[];
  activeStoreId: string;
  activeStore: StoreSummary | null;
  setActiveStoreId: (id: string) => void;
  session: AuthSession | null;
  setSession: (session: AuthSession | null) => void;
  isLoadingStores: boolean;
}

const StoreContext = createContext<StoreContextValue | undefined>(undefined);

export const StoreProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [session, setSessionState] = useState<AuthSession | null>(() => {
    try {
      const raw = localStorage.getItem('rc_session');
      return raw ? (JSON.parse(raw) as AuthSession) : null;
    } catch {
      return null;
    }
  });

  const [activeStoreId, setActiveStoreIdState] = useState<string>(() => {
    return localStorage.getItem('rc_active_store_id') || '';
  });

  const { data, isLoading } = useQuery({
    queryKey: ['stores'],
    queryFn: () => apiFetch<{ stores: StoreSummary[] }>('/stores'),
  });

  const stores = data?.stores ?? [];

  useEffect(() => {
    if (stores.length > 0 && !stores.some((s) => s.id === activeStoreId)) {
      const preferred = session?.stores?.[0]?.id || stores[0].id;
      setActiveStoreIdState(preferred);
      localStorage.setItem('rc_active_store_id', preferred);
    }
  }, [stores, activeStoreId, session]);

  const setActiveStoreId = (id: string) => {
    setActiveStoreIdState(id);
    localStorage.setItem('rc_active_store_id', id);
  };

  const setSession = (next: AuthSession | null) => {
    setSessionState(next);
    if (next) {
      localStorage.setItem('rc_token', next.access_token);
      localStorage.setItem('rc_session', JSON.stringify(next));
      if (next.stores[0]?.id) {
        setActiveStoreId(next.stores[0].id);
      }
    } else {
      localStorage.removeItem('rc_token');
      localStorage.removeItem('rc_session');
    }
  };

  const activeStore = stores.find((s) => s.id === activeStoreId) ?? stores[0] ?? null;

  return (
    <StoreContext.Provider
      value={{
        stores,
        activeStoreId: activeStore?.id || activeStoreId,
        activeStore,
        setActiveStoreId,
        session,
        setSession,
        isLoadingStores: isLoading,
      }}
    >
      {children}
    </StoreContext.Provider>
  );
};

export function useStoreContext(): StoreContextValue {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error('useStoreContext must be used inside StoreProvider');
  return ctx;
}
