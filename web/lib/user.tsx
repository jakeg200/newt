"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, ApiError, setApiUser, type DevUser } from "./api";

const STORAGE_KEY = "agent-onboarding.dev-user";

interface UserState {
  users: DevUser[];
  user: DevUser | null;
  setUser: (id: string) => void;
  error: string | null;
}

const UserContext = createContext<UserState>({ users: [], user: null, setUser: () => {}, error: null });

export function UserProvider({ children }: { children: React.ReactNode }) {
  const [users, setUsers] = useState<DevUser[]>([]);
  const [user, setUserState] = useState<DevUser | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .devUsers()
      .then((list) => {
        setUsers(list);
        let saved: string | null = null;
        try {
          saved = localStorage.getItem(STORAGE_KEY);
        } catch {}
        const initial = list.find((u) => u.id === saved) ?? list.find((u) => u.role === "mentor") ?? list[0] ?? null;
        setApiUser(initial?.id ?? null);
        setUserState(initial);
      })
      .catch((e: ApiError) => setError(e.message));
  }, []);

  const setUser = useCallback(
    (id: string) => {
      const next = users.find((u) => u.id === id) ?? null;
      setApiUser(next?.id ?? null);
      setUserState(next);
      try {
        if (next) localStorage.setItem(STORAGE_KEY, next.id);
      } catch {}
    },
    [users],
  );

  return <UserContext.Provider value={{ users, user, setUser, error }}>{children}</UserContext.Provider>;
}

export const useUser = () => useContext(UserContext);
