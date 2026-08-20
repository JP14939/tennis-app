import { Alert, Platform } from 'react-native';
import { useAuth } from '../context/AuthContext';

// Shared by PremiumFeaturesSection.js (Home) and PremiumScreen.js itself --
// extracted from what used to be PremiumScreen.js's own local gated()
// function so both places apply the same rule instead of drifting apart.
//
// Not-premium behavior on web changed 2026-08-20: used to show a confirm
// alert ("This is a Premium feature -- Upgrade?") before navigating to
// checkout. Now navigates straight to the Premium screen's checkout --
// tapping a locked feature IS the "go to payment" action, no extra step,
// per direct user feedback ("press on them and premium payment appears").
export function useGatedNavigate(navigation) {
  const { isAuthenticated, isPremium } = useAuth();

  return (destination, params) => {
    if (isPremium) {
      navigation.navigate(destination, params);
      return;
    }
    if (!isAuthenticated) {
      Alert.alert(
        'Log in required',
        'Log in and upgrade to Premium to unlock this feature.',
        [{ text: 'Log in', onPress: () => navigation.navigate('Login') }, { text: 'Cancel', style: 'cancel' }]
      );
      return;
    }
    // Native has no purchase UI yet (PremiumCheckout.native.js is a stub
    // pending an EAS dev-client build) -- say so honestly rather than
    // navigating somewhere that can't actually complete a purchase.
    if (Platform.OS === 'web') {
      navigation.navigate('Premium');
      return;
    }
    Alert.alert(
      'Premium feature',
      "This is a Premium feature. Purchasing Premium currently requires the web version of RallyMax — open the app in a browser to upgrade.",
      [{ text: 'OK', style: 'cancel' }]
    );
  };
}
