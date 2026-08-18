import { useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { isAdmin } from '../utils/isAdmin';

// Wrap every Dev Page screen's render with this -- SettingsScreen.js only
// hides the *entry point* to these screens for a non-admin, which isn't a
// real guard: anyone who reaches one of these routes by any other means
// (e.g. driving navigation directly on web) would otherwise see it render
// normally. This is still just a UI-layer guard, not the real security
// boundary -- GET /dev/ml-status is separately 403'd server-side regardless
// -- but it stops a non-admin from ever seeing dev-only UI at all, and
// bounces them out before anything renders rather than flashing it first.
export default function RequireAdmin({ navigation, children }) {
  const { user } = useAuth();
  const allowed = isAdmin(user);

  useEffect(() => {
    if (!allowed) navigation.goBack();
  }, [allowed, navigation]);

  if (!allowed) return null;
  return children;
}
