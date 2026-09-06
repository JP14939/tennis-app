// Side-effect import (App.js, before any screen) — wraps global.fetch once so
// every request to our own backend carries `ngrok-skip-browser-warning`. When
// EXPO_PUBLIC_API_BASE points at an ngrok *free* tunnel (used for on-phone
// testing), ngrok otherwise serves a browser an HTML interstitial with HTTP 200
// instead of proxying to the backend — which makes res.ok true, res.json()
// throw, and every API call silently return nothing on the web build. The
// header makes ngrok skip that page; it's inert against any non-ngrok host
// (localhost dev, the hosted prod domain), so it's safe to always send.
import { API_BASE } from '../config/api';

if (typeof global.fetch === 'function' && !global.__rallymaxFetchShim) {
  const orig = global.fetch;
  global.fetch = (input, init = {}) => {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    if (url.startsWith(API_BASE)) {
      init = {
        ...init,
        headers: { ...(init.headers || {}), 'ngrok-skip-browser-warning': 'true' },
      };
    }
    return orig(input, init);
  };
  global.__rallymaxFetchShim = true;
}
