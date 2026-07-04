import { createContext, useContext, useEffect, useState, ReactNode, useCallback } from "react";
import { api } from "../api";

export interface AuthRole {
  entity_id: number;
  role: "treasurer" | "viewer";
}

export interface AuthUser {
  id: number;
  email: string;
  display_name: string;
  is_admin: number;
  roles: AuthRole[];
  allowed_entity_ids: number[] | null; // null = accès total (admin)
}

interface AuthContextType {
  user: AuthUser | null;
  loading: boolean;
  isAdmin: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  reload: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  isAdmin: false,
  login: async () => {},
  logout: async () => {},
  reload: async () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    try {
      setUser(await api.getMe());
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    reload().finally(() => setLoading(false));
  }, [reload]);

  const login = useCallback(async (email: string, password: string) => {
    await api.login(email, password);
    await reload();
  }, [reload]);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setUser(null);
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, loading, isAdmin: !!user?.is_admin, login, logout, reload }}
    >
      {children}
    </AuthContext.Provider>
  );
}
