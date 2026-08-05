import { View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, Alert } from 'react-native';
import { useAuth } from '../context/AuthContext';
import PremiumCheckout from '../components/PremiumCheckout';
import { colors, fonts, radius, spacing } from '../theme';
import CourtBackground from '../components/CourtBackground';
import { PremiumIcon, SwapIcon, FilmIcon, LockIcon } from '../components/icons';

function FeatureCard({ icon, title, desc, cta, locked, onPress }) {
  return (
    <View style={c.card}>
      <View style={c.iconWrap}>{icon}</View>
      <Text style={c.title}>{title}</Text>
      <Text style={c.desc}>{desc}</Text>
      <TouchableOpacity style={c.btn} onPress={onPress} activeOpacity={0.85}>
        {locked && <LockIcon size={13} color={colors.mutedDark} />}
        <Text style={c.btnText}>{cta}</Text>
      </TouchableOpacity>
    </View>
  );
}
const c = StyleSheet.create({
  card: {
    backgroundColor: colors.surface, borderRadius: radius.xl, padding: 20, marginBottom: 14,
  },
  iconWrap: {
    width: 44, height: 44, borderRadius: 12, backgroundColor: colors.primarySoft,
    alignItems: 'center', justifyContent: 'center', marginBottom: 14,
  },
  title: { color: colors.ink, fontSize: 16.5, fontFamily: fonts.extrabold, marginBottom: 6 },
  desc: { color: colors.muted, fontSize: 13, lineHeight: 19.5, marginBottom: 16, fontFamily: fonts.regular },
  btn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    backgroundColor: colors.border, borderRadius: radius.sm, paddingVertical: 12,
  },
  btnText: { color: colors.mutedDark, fontSize: 13.5, fontFamily: fonts.bold },
});

export default function PremiumScreen({ navigation }) {
  const { isAuthenticated, isPremium } = useAuth();

  const gated = (destination) => {
    if (isPremium) {
      navigation.navigate(destination);
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
    Alert.alert(
      'Premium feature',
      'This is a Premium feature — upgrade your plan to unlock it.',
      [{ text: 'OK', style: 'cancel' }]
    );
  };

  return (
    <SafeAreaView style={s.safe}>
      <CourtBackground />
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        <View style={s.badge}>
          <PremiumIcon size={12} color={colors.limeText} filled />
          <Text style={s.badgeText}>PREMIUM</Text>
        </View>
        <Text style={s.title}>Go deeper on your game</Text>
        <Text style={s.sub}>Two ways to get more out of your footage.</Text>

        {!isPremium && <PremiumCheckout />}

        <FeatureCard
          icon={<SwapIcon size={20} color={colors.primary} />}
          title="1v1 Comparison"
          desc="Upload any video you want to copy — a pro clip, a friend, yourself last year — and compare your swing directly against it, frame for frame."
          cta="Compare videos"
          locked={!isPremium}
          onPress={() => gated('VersusPick')}
        />

        <FeatureCard
          icon={<FilmIcon size={20} color={colors.primary} />}
          title="Highlight Archive"
          desc="Upload a full match and we'll automatically clip every shot into your personal swing archive, ready to tag and analyse."
          cta="Upload a match"
          locked={!isPremium}
          onPress={() => gated('HighlightUpload')}
        />

      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingTop: 20, paddingBottom: 130 },

  badge: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    alignSelf: 'flex-start', backgroundColor: colors.lime,
    borderRadius: 20, paddingHorizontal: 12, paddingVertical: 5, marginBottom: 16,
  },
  badgeText: { color: colors.limeText, fontSize: 11, fontFamily: fonts.extrabold, letterSpacing: 0.5 },

  title: { color: colors.ink, fontSize: 32, fontFamily: fonts.serifItalic, lineHeight: 36, marginBottom: 8 },
  sub: { color: colors.muted, fontSize: 14, marginBottom: spacing.xl, fontFamily: fonts.regular },
});
