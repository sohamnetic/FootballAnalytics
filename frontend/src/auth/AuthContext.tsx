import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { apiFetch, getToken, readError, setToken } from "../api/client";

export interface AuthUser {
  id: string;
  email: string;
  name: string;
}

interface AuthState {
  user: AuthUser | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, name: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setReady(true);
      return;
    }
    apiFetch("/api/auth/me")
      .then(async (res) => {
        if (!res.ok) {
          setToken(null);
          return;
        }
        const data = await res.json();
        setUser(data.user);
      })
      .finally(() => setReady(true));
  }, []);

  async function submit(path: string, email: string, password: string, name = "") {
    const res = await apiFetch(path, {
      method: "POST",
      body: JSON.stringify({ email, password, name }),
    });
    if (!res.ok) throw new Error(await readError(res, "Authentication failed"));
    const data = await res.json();
    setToken(data.token);
    setUser(data.user);
  }

  const value = useMemo<AuthState>(
    () => ({
      user,
      ready,
      login: (email, password) => submit("/api/auth/login", email, password),
      signup: (email, password, name) => submit("/api/auth/signup", email, password, name),
      logout: () => {
        setToken(null);
        setUser(null);
      },
    }),
    [user, ready],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
