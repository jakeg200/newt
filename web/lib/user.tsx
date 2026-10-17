"use client";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, ApiError, setApiToken, setApiUser, type DevUser } from "./api";

const STORAGE_KEY = "agent-onboarding.dev-user";
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

/** "supabase" when the app is configured for real sign-in; otherwise the development user picker. */
export const AUTH_MODE: "supabase" | "dev" = SUPABASE_URL && SUPABASE_ANON_KEY ? "supabase" : "dev";

interface UserState {
  mode: typeof AUTH_MODE;
  users: DevUser[];
  user: DevUser | null;
  setUser: (id: string) => void;
  signedOut: boolean;
  signIn: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
  error: string | null;
}

const UserContext = createContext<UserState>({
  mode: AUTH_MODE, users: [], user: null, setUser: () => {}, signedOut: false,
  signIn: async () => {}, signOut: async () => {}, error: null,
});

export function UserProvider({ children }: { children: React.ReactNode }) {
  const [users, setUsers] = useState<DevUser[]>([]);
  const [user, setUserState] = useState<DevUser | null>(null);
  const [signedOut, setSignedOut] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const supabase: SupabaseClient | null = useMemo(
    () => (AUTH_MODE === "supabase" ? createClient(SUPABASE_URL!, SUPABASE_ANON_KEY!) : null),
    [],
  );

  // Production: follow the Supabase session; the API decides who that email is.
  useEffect(() => {
    if (!supabase) return;
    const apply = async (token: string | null) => {
      setApiToken(token);
      if (!token) {
        setUserState(null);
        setSignedOut(true);
        return;
      }
      try {
        const me = await api.me();
        setUserState({ id: me.id, name: me.name, role: me.role, email: me.email, org: me.org, synthetic: me.synthetic });
        setSignedOut(false);
        setError(null);
      } catch (e) {
        setUserState(null);
        setSignedOut(true);
        setError(e instanceof ApiError ? e.message : String(e));
      }
    };
    supabase.auth.getSession().then(({ data }) => apply(data.session?.access_token ?? null));
    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => apply(session?.access_token ?? null));
    return () => sub.subscription.unsubscribe();
  }, [supabase]);

  // Development: pick any seeded user.
  useEffect(() => {
    if (supabase) return;
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
  }, [supabase]);

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

  const signIn = useCallback(async (email: string) => {
    if (!supabase) return;
    const { error: err } = await supabase.auth.signInWithOtp({ email, options: { emailRedirectTo: window.location.origin, shouldCreateUser: false } });
    if (err) throw new Error(err.message);
  }, [supabase]);

  const signOut = useCallback(async () => {
    await supabase?.auth.signOut();
  }, [supabase]);

  return (
    <UserContext.Provider value={{ mode: AUTH_MODE, users, user, setUser, signedOut, signIn, signOut, error }}>
      {children}
    </UserContext.Provider>
  );
}

export const useUser = () => useContext(UserContext);
