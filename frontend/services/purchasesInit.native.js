import Purchases, { LOG_LEVEL } from 'react-native-purchases';
import { REVENUECAT_API_KEY } from '../config/revenuecat';

// Called once at app boot (App.js). Purchases.configure() must only be
// called once per app session -- PremiumCheckout.native.js calls
// Purchases.logIn() later to associate the anonymous session with our own
// user id once the person is actually logged in, rather than reconfiguring.
export function initPurchases() {
  if (!REVENUECAT_API_KEY) return; // not set yet -- PremiumCheckout falls back to its missing_config state
  Purchases.setLogLevel(LOG_LEVEL.VERBOSE);
  Purchases.configure({ apiKey: REVENUECAT_API_KEY });
}
