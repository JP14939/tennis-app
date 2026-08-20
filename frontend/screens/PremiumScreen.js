import { View, Text, SafeAreaView, ScrollView, StyleSheet } from 'react-native';
import { useAuth } from '../context/AuthContext';
import PremiumCheckout from '../components/PremiumCheckout';
import { colors, fonts, spacing } from '../theme';
import CourtBackground from '../components/CourtBackground';
import { PremiumIcon } from '../components/icons';

// Trimmed 2026-08-20: the 2 feature cards that used to live here (1v1
// Comparison, Highlight Archive) now live directly on Home
// (PremiumFeaturesSection.js), locked with a lock badge -- this screen is
// reached only by tapping one of those, or an "Upgrade" CTA elsewhere
// (LessonsSection.js, HistoryScreen.js's free-tier-cap notice,
// ProfileScreen.js). Whoever lands here already saw the pitch and chose
// to act on it, so this is just the checkout itself now, not a repeat of
// the feature marketing.
export default function PremiumScreen() {
  const { isPremium } = useAuth();

  return (
    <SafeAreaView style={s.safe}>
      <CourtBackground />
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        <View style={s.badge}>
          <PremiumIcon size={12} color={colors.limeText} filled />
          <Text style={s.badgeText}>PREMIUM</Text>
        </View>
        <Text style={s.title}>Go deeper on your game</Text>
        <Text style={s.sub}>
          {isPremium
            ? "You're already on Premium — thanks for supporting RallyMax."
            : 'Unlock 1v1 Comparison and the Highlight Archive.'}
        </Text>

        {!isPremium && <PremiumCheckout />}

      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingTop: 20, paddingBottom: 60 },

  badge: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    alignSelf: 'flex-start', backgroundColor: colors.lime,
    borderRadius: 20, paddingHorizontal: 12, paddingVertical: 5, marginBottom: 16,
  },
  badgeText: { color: colors.limeText, fontSize: 11, fontFamily: fonts.extrabold, letterSpacing: 0.5 },

  title: { color: colors.ink, fontSize: 32, fontFamily: fonts.serifItalic, lineHeight: 36, marginBottom: 8 },
  sub: { color: colors.muted, fontSize: 14, marginBottom: spacing.xl, fontFamily: fonts.regular },
});
