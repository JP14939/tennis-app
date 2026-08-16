// Web uses a separate SDK (@revenuecat/purchases-js, configured directly in
// PremiumCheckout.web.js) since react-native-purchases is native-only and
// has no web implementation -- this no-op keeps App.js's call site the same
// across platforms.
export function initPurchases() {}
