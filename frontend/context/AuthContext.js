import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import { API_BASE } from '../config/api';

const TOKEN_KEY = 'tennisai_token';

// expo-secure-store's native APIs aren't available on web — fall back to
// localStorage there so the same AuthContext code works in both.
const storage = Platform.OS === 'web'
  ? {
      getItem: async (key) => localStorage.getItem(key),
      setItem: async (key, value) => localStorage.setItem(key, value),
      deleteItem: async (key) => localStorage.removeItem(key),
    }
  : {
      getItem: SecureStore.getItemAsync,
      setItem: SecureStore.setItemAsync,
      deleteItem: SecureStore.deleteItemAsync,
    };

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true); // restoring session from storage on boot

  useEffect(() => {
    (async () => {
      try {
        const savedToken = await storage.getItem(TOKEN_KEY);
        if (savedToken) {
          const res = await fetch(`${API_BASE}/api/auth/me`, {
            headers: { Authorization: `Bearer ${savedToken}` },
          });
          if (res.ok) {
            const data = await res.json();
            setToken(savedToken);
            setUser(data.user);
          } else {
            await storage.deleteItem(TOKEN_KEY); // stale/expired
          }
        }
      } catch {
        // Offline or backend unreachable on boot — treat as logged out
        // rather than blocking app startup.
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleAuthResponse = useCallback(async (res) => {
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || 'Something went wrong');
    }
    await storage.setItem(TOKEN_KEY, data.token);
    setToken(data.token);
    setUser(data.user);
    return data.user;
  }, []);

  const signup = useCallback((email, password, name) =>
    fetch(`${API_BASE}/api/auth/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, name }),
    }).then(handleAuthResponse), [handleAuthResponse]);

  const login = useCallback((email, password) =>
    fetch(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    }).then(handleAuthResponse), [handleAuthResponse]);

  const logout = useCallback(async () => {
    await storage.deleteItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  const value = {
    user,
    token,
    loading,
    isAuthenticated: !!user,
    isPremium: user?.tier === 'premium',
    signup,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
