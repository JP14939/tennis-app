// No real purchase path on native yet (this project's web/Stripe-via-
// RevenueCat integration is the only one built so far -- see
// PremiumCheckout.web.js). Renders nothing so PremiumScreen's existing
// alert-based "Premium feature" flow is the only thing shown here, same as
// before this feature existed. Native (App Store/Play Store) purchases are
// a separate follow-up once an EAS dev client build exists.
export default function PremiumCheckout() {
  return null;
}
