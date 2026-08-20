import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { useAuth } from '../context/AuthContext';
import { useGatedNavigate } from '../utils/premiumGate';
import { colors, fonts, radius } from '../theme';
import { SwapIcon, FilmIcon, LockIcon } from './icons';

// The 2 premium features, shown directly on Home (locked with a lock
// badge when not premium) instead of only living on a separate Premium
// page nobody visits unless they already know it exists -- moved here
// 2026-08-20 per direct user feedback. FeatureCard itself used to live in
// PremiumScreen.js; extracted here since both places render the same
// cards now (PremiumScreen.js keeps just the checkout widget).
export function FeatureCard({ icon, title, desc, cta, locked, onPress }) {
  return (
    <View style={c.card}>
      <View style={c.iconWrap}>{icon}</View>
      <Text style={c.title}>{title}</Text>
      <Text style={c.desc}>{desc}</Text>
      <TouchableOpacity style={[c.btn, !locked && c.btnUnlocked]} onPress={onPress} activeOpacity={0.85}>
        {locked && <LockIcon size={13} color={colors.mutedDark} />}
        <Text style={[c.btnText, !locked && c.btnTextUnlocked]}>{cta}</Text>
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
  btnUnlocked: { backgroundColor: colors.primary },
  btnTextUnlocked: { color: colors.white },
});

export default function PremiumFeaturesSection({ navigation }) {
  const { isPremium } = useAuth();
  const gatedNavigate = useGatedNavigate(navigation);

  return (
    <View style={s.wrap}>
      <FeatureCard
        icon={<SwapIcon size={20} color={colors.primary} />}
        title="1v1 Comparison"
        desc="Upload any video you want to copy — a pro clip, a friend, yourself last year — and compare your swing directly against it, frame for frame."
        cta="Compare videos"
        locked={!isPremium}
        onPress={() => gatedNavigate('VersusPick')}
      />

      <FeatureCard
        icon={<FilmIcon size={20} color={colors.primary} />}
        title="Highlight Archive"
        desc="Upload a full match and we'll automatically clip every shot into your personal swing archive, ready to tag and analyse."
        cta="Upload a match"
        locked={!isPremium}
        onPress={() => gatedNavigate('HighlightArchive')}
      />
    </View>
  );
}
const s = StyleSheet.create({
  wrap: { marginTop: 8 },
});
