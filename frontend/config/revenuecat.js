import { Platform } from 'react-native';

// Public SDK keys (safe to expose client-side) for native purchases -- see
// PremiumCheckout.native.js. Web has its own key/flow (config/api.js's
// sibling EXPO_PUBLIC_REVENUECAT_WEB_API_KEY, used by
// components/PremiumCheckout.web.js) since RevenueCat's web SDK is a
// separate package from react-native-purchases.
export const REVENUECAT_API_KEY = Platform.select({
  ios: process.env.EXPO_PUBLIC_REVENUECAT_IOS_API_KEY,
  android: process.env.EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY,
  default: undefined,
});
