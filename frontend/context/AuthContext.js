import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { API_BASE } from '../config/api';
import { storage } from '../utils/storage';
import { registerForPushNotifications } from '../utils/pushNotifications';
import { updateProfile, deleteAccount as deleteAccountApi } from '../api/account';

const TOKEN_KEY = 'tennisai_token';

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

  // Always resolves (even for an unknown email) -- the backend responds 204
  // either way so this never leaks whether an account exists, see
  // auth.js's /auth/forgot-password comment. Doesn't touch the session.
  const forgotPassword = useCallback((email) =>
    fetch(`${API_BASE}/api/auth/forgot-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    }).then(async (res) => {
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || 'Something went wrong');
      }
    }), []);

  const logout = useCallback(async () => {
    await storage.deleteItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  // Re-fetches the current user (tier included) without a full re-login --
  // used right after a purchase completes so isPremium flips immediately
  // app-wide instead of waiting for the next natural refetch.
  const refreshUser = useCallback(async () => {
    if (!token) return;
    const res = await fetch(`${API_BASE}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const data = await res.json();
      setUser(data.user);
    }
  }, [token]);

  // Used by SettingsScreen for name / notifications_enabled edits -- returns
  // the updated user so callers can show a saved confirmation if they want.
  const updateUser = useCallback(async (patch) => {
    const data = await updateProfile(token, patch);
    setUser(data.user);
    return data.user;
  }, [token]);

  // Same session-clearing shape as logout() -- deleteAccountApi throws (and
  // leaves the session untouched) if the password confirmation is wrong.
  const deleteAccount = useCallback(async (password) => {
    await deleteAccountApi(token, password);
    await storage.deleteItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, [token]);

  // Covers login, signup, and session-restore-on-boot in one place -- push
  // registration only makes sense once we have an authenticated user to
  // associate the device token with.
  useEffect(() => {
    if (token) registerForPushNotifications(token);
  }, [token]);

  const value = {
    user,
    token,
    loading,
    isAuthenticated: !!user,
    isPremium: user?.tier === 'premium',
    signup,
    login,
    forgotPassword,
    logout,
    refreshUser,
    updateUser,
    deleteAccount,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
