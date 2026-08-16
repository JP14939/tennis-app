import { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { Purchases } from '@revenuecat/purchases-js';
import { useAuth } from '../context/AuthContext';
import { API_BASE } from '../config/api';
import { colors, fonts, radius, spacing } from '../theme';
import { playTapSound } from '../utils/sounds';

const RC_API_KEY = process.env.EXPO_PUBLIC_REVENUECAT_WEB_API_KEY;

async function syncBilling(token) {
  const response = await fetch(`${API_BASE}/api/billing/sync`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error('Could not confirm your purchase — try refreshing in a moment.');
  }
}

// Web-only (see PlatformVideo.web.js/.native.js for the same split pattern
// already used elsewhere) -- RevenueCat's web SDK targets a browser
// environment, and there's no real purchase path on native yet regardless
// (PremiumScreen keeps its existing alert there).
export default function PremiumCheckout() {
  const { user, token, refreshUser } = useAuth();
  const [status, setStatus] = useState('loading'); // loading | ready | purchasing | error | missing_config
  const [pkg, setPkg] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    if (!RC_API_KEY || !user) {
      setStatus('missing_config');
      return;
    }
    (async () => {
      try {
        const purchases = Purchases.configure(RC_API_KEY, String(user.id));
        const offerings = await purchases.getOfferings();
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
      const purchases = Purchases.configure(RC_API_KEY, String(user.id));
      await purchases.purchase({ rcPackage: pkg, customerEmail: user.email });
      await syncBilling(token);
      await refreshUser();
      setStatus('ready');
    } catch (err) {
      // RevenueCat throws a distinct error for a user-cancelled checkout —
      // that's not a failure worth alarming over.
      if (err?.errorCode === 1 /* UserCancelledError */) {
        setStatus('ready');
        return;
      }
      setErrorMsg(err.message || 'Purchase failed — please try again.');
      setStatus('error');
    }
  };

  if (status === 'missing_config') {
    return null; // not configured yet — PremiumScreen's existing cards still work as before
  }

  if (status === 'loading') {
    return <ActivityIndicator color={colors.primary} style={{ marginVertical: 16 }} />;
  }

  const product = pkg?.webBillingProduct;

  return (
    <View style={s.card}>
      <Text style={s.title}>{product?.title || 'RallyMax Premium'}</Text>
      {product?.description && <Text style={s.desc}>{product.description}</Text>}
      {product?.currentPrice?.formattedPrice && (
        <Text style={s.price}>{product.currentPrice.formattedPrice}</Text>
      )}

      {status === 'error' && <Text style={s.error}>{errorMsg}</Text>}

      <TouchableOpacity
        style={[s.btn, status === 'purchasing' && s.btnDisabled]}
        onPress={() => { playTapSound(); purchase(); }}
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
