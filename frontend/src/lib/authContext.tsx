"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { api } from "./api";

export interface UserState {
  id: number;
  email: string;
  full_name: string;
  phone?: string;
  role: "JOB_SEEKER" | "HR" | "ADMIN";
  avatar_url?: string;
  is_email_verified: boolean;
  is_phone_verified?: boolean;
}

interface AuthContextType {
  user: UserState | null;
  token: string | null;
  isLoading: boolean;
  login: (email: string, pass: string) => Promise<void>;
  loginWithOtp: (email: string, code: string) => Promise<void>;
  logout: () => void;
  switchDemoRole: (role: "JOB_SEEKER" | "HR" | "ADMIN") => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const PUBLIC_PATHS = ["/", "/login", "/register", "/verify-email", "/jobs"];

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserState | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const clearAuthState = () => {
    if (typeof window !== "undefined") {
      localStorage.removeItem("skills2job_token");
    }
    setToken(null);
    setUser(null);
  };

  const initAuth = async () => {
    try {
      const savedToken = localStorage.getItem("skills2job_token");
      if (savedToken) {
        setToken(savedToken);
        const me = await api.getMe();
        setUser(me);
      }
    } catch (err) {
      console.warn("Auth initialization failed, clearing token");
      clearAuthState();
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    initAuth();
  }, []);

  useEffect(() => {
    const onUnauthorized = () => {
      clearAuthState();
      const isPublic = PUBLIC_PATHS.some((p) => pathname === p || (p === "/jobs" && pathname?.startsWith("/jobs")));
      if (!isPublic) {
        router.push("/login");
      }
    };
    window.addEventListener("skills2job:unauthorized", onUnauthorized);
    return () => window.removeEventListener("skills2job:unauthorized", onUnauthorized);
  }, [pathname, router]);

  const login = async (email: string, pass: string) => {
    setIsLoading(true);
    try {
      const res = await api.login({ email, password: pass });
      localStorage.setItem("skills2job_token", res.access_token);
      setToken(res.access_token);
      setUser(res.user);
    } finally {
      setIsLoading(false);
    }
  };

  const loginWithOtp = async (email: string, code: string) => {
    setIsLoading(true);
    try {
      const res = await api.verifyOtpLogin({ email, code });
      localStorage.setItem("skills2job_token", res.access_token);
      setToken(res.access_token);
      setUser(res.user);
    } finally {
      setIsLoading(false);
    }
  };

  const logout = () => {
    clearAuthState();
    router.push("/login");
  };

  const switchDemoRole = async (role: "JOB_SEEKER" | "HR" | "ADMIN") => {
    setIsLoading(true);
    try {
      const res = await api.demoLogin(role.toLowerCase());
      if (!res?.access_token || !res?.user) {
        throw new Error("Invalid demo login response from server");
      }
      localStorage.setItem("skills2job_token", res.access_token);
      setToken(res.access_token);
      setUser(res.user);
    } catch (err) {
      clearAuthState();
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  const refreshUser = async () => {
    try {
      const me = await api.getMe();
      setUser(me);
    } catch (e) {
      // ignore
    }
  };

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, loginWithOtp, logout, switchDemoRole, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
