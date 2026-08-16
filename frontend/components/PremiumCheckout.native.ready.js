// PARKED — not wired up yet, on purpose.
//
// This is the finished native (iOS/Android) purchase flow via
// react-native-purchases, built while setting up RevenueCat. It's kept
// under a ".native.ready.js" name instead of ".native.js" specifically so
// Metro's platform-extension resolution does NOT pick it up automatically
// -- react-native-purchases is a native module with no Expo Go support, so
// if this were live as PremiumCheckout.native.js, PremiumScreen's always-
// mounted `import PremiumCheckout from '../components/PremiumCheckout'`
// would pull it in on every native build, including Expo Go, and crash on
// load there.
//
// To activate once a custom dev client (EAS build, not Expo Go) is ready:
//   1. Replace the contents of PremiumCheckout.native.js with this file's.
//   2. Delete this file.
//   3. In App.js, restore the `initPurchases()` call (see git history /
//      services/purchasesInit.native.js, which is already written and just
//      not currently invoked).
//
// Mirrors PremiumCheckout.web.js's flow (see that file for the shared
// syncBilling contract with backend/src/routes/billing.js), using
// react-native-purchases instead of the web SDK. Purchases.configure()
// itself runs once in App.js via services/purchasesInit.native.js -- this
// only logs the RevenueCat session in as our own user id so
// routes/webhooks.js's app_user_id lookup resolves correctly.
import { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import Purchases from 'react-native-purchases';
import { useAuth } from '../context/AuthContext';
import { API_BASE } from '../config/api';
import { REVENUECAT_API_KEY } from '../config/revenuecat';
import { colors, fonts, radius, spacing } from '../theme';

async function syncBilling(token) {
  const response = await fetch(`${API_BASE}/api/billing/sync`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error('Could not confirm your purchase — try refreshing in a moment.');
  }
}

export default function PremiumCheckout() {
  const { user, token, refreshUser } = useAuth();
  const [status, setStatus] = useState('loading'); // loading | ready | purchasing | error | missing_config
  const [pkg, setPkg] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    if (!REVENUECAT_API_KEY || !user) {
      setStatus('missing_config');
      return;
    }
    (async () => {
      try {
        await Purchases.logIn(String(user.id));
        const offerings = await Purchases.getOfferings();
        const current = offerings.current?.availablePackages?.[0];
        if (!current) {
          throw new Error('No premium plan is configured yet.');
        }
        setPkg(current);
        setStatus('ready');
      } catch (err) {
        setErrorMsg(err.message || 'Could not load premium plans.');
        setStatus('error');
      }
    })();
  }, [user]);

  const purchase = async () => {
    if (!pkg) return;
    setStatus('purchasing');
    setErrorMsg('');
    try {
      await Purchases.purchasePackage(pkg);
      await syncBilling(token);
      await refreshUser();
      setStatus('ready');
    } catch (err) {
      // RevenueCat flags a user-cancelled checkout distinctly -- not a
      // failure worth alarming over, same as the web flow's UserCancelledError.
      if (err?.userCancelled) {
        setStatus('ready');
        return;
      }
      setErrorMsg(err.message || 'Purchase failed — please try again.');
      setStatus('error');
    }
  };

  if (status === 'missing_config') {
    return null; // not configured yet — PremiumScreen's existing alert-based flow still works
  }

  if (status === 'loading') {
    return <ActivityIndicator color={colors.primary} style={{ marginVertical: 16 }} />;
  }

  const product = pkg?.product;

  return (
    <View style={s.card}>
      <Text style={s.title}>{product?.title || 'RallyMax Premium'}</Text>
      {product?.description && <Text style={s.desc}>{product.description}</Text>}
      {product?.priceString && <Text style={s.price}>{product.priceString}</Text>}

      {status === 'error' && <Text style={s.error}>{errorMsg}</Text>}

      <TouchableOpacity
        style={[s.btn, status === 'purchasing' && s.btnDisabled]}
        onPress={purchase}
        disabled={status === 'purchasing'}
      >
        <Text style={s.btnText}>{status === 'purchasing' ? 'Processing…' : 'Subscribe'}</Text>
      </TouchableOpacity>
    </View>
  );
}

const s = StyleSheet.create({
  card: {
    backgroundColor: colors.primary,
    borderRadius: radius.xxl, padding: 24, marginBottom: spacing.xl, alignItems: 'center',
  },
  title: { color: colors.white, fontSize: 17, fontFamily: fonts.extrabold, marginBottom: 4 },
  desc: { color: 'rgba(255,255,255,0.75)', fontSize: 13, textAlign: 'center', marginBottom: 10, fontFamily: fonts.regular },
  price: { color: colors.white, fontSize: 30, fontFamily: fonts.serif, marginBottom: 14 },
  error: { color: colors.coral, fontSize: 12, marginBottom: 10, textAlign: 'center', fontFamily: fonts.regular },
  btn: { backgroundColor: colors.white, borderRadius: radius.pill, paddingVertical: 13, paddingHorizontal: 32 },
  btnDisabled: { opacity: 0.6 },
  btnText: { color: colors.primary, fontSize: 14, fontFamily: fonts.bold },
});
