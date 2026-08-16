import { View, Text, StyleSheet } from 'react-native';
import { colors, fonts, radius, spacing } from '../theme';
import { DrillsIcon, TennisBallIcon } from './icons';

// Structural stub -- real drill content (a database of drills tied to shot
// types/issues, mirroring data/08_coaching_ai/coaching_tips_database.json's
// pattern) is deliberately deferred, per Jack. This establishes the section
// shell so it exists and looks finished; the categories below are
// placeholders, not real drill data.
const CATEGORIES = [
  { key: 'forehand', label: 'Forehand' },
  { key: 'backhand', label: 'Backhand' },
  { key: 'serve', label: 'Serve' },
  { key: 'footwork', label: 'Footwork & fitness' },
];

function CategoryCard({ label }) {
  return (
    <View style={cc.card}>
      <View style={cc.iconWrap}>
        <TennisBallIcon size={18} color={colors.primary} />
      </View>
      <View style={cc.body}>
        <Text style={cc.title}>{label}</Text>
        <Text style={cc.sub}>Drills coming soon</Text>
      </View>
    </View>
  );
}
const cc = StyleSheet.create({
  card: {
    flexDirection: 'row', alignItems: 'center', gap: 14,
    backgroundColor: colors.surface, borderRadius: radius.lg,
    padding: 16, marginBottom: 12,
  },
  iconWrap: {
    width: 40, height: 40, borderRadius: 20, backgroundColor: colors.primarySoft,
    alignItems: 'center', justifyContent: 'center',
  },
  body: { flex: 1 },
  title: { color: colors.ink, fontSize: 15, fontFamily: fonts.bold },
  sub: { color: colors.muted, fontSize: 12.5, marginTop: 2, fontFamily: fonts.regular },
});

export default function DrillsSection() {
  return (
    <View>
      <View style={s.empty}>
        <View style={s.emptyIconWrap}>
          <DrillsIcon size={26} color={colors.primary} />
        </View>
        <Text style={s.emptyTitle}>Drills & exercises are on the way</Text>
        <Text style={s.emptySub}>
          We're building a library of drills tied to the coaching tips from
          your swing analyses, so you can practise exactly what's holding
          your technique back.
        </Text>
      </View>

      <Text style={s.sectionTitle}>Categories</Text>
      {CATEGORIES.map((cat) => (
        <CategoryCard key={cat.key} label={cat.label} />
      ))}
    </View>
  );
}

const s = StyleSheet.create({
  empty: {
    alignItems: 'center', backgroundColor: colors.surface, borderRadius: radius.lg,
    padding: 24, marginBottom: spacing.xl,
  },
  emptyIconWrap: {
    width: 52, height: 52, borderRadius: 26, backgroundColor: colors.primarySoft,
    alignItems: 'center', justifyContent: 'center', marginBottom: 14,
  },
  emptyTitle: { color: colors.ink, fontSize: 17, fontFamily: fonts.extrabold, marginBottom: 8, textAlign: 'center' },
  emptySub:   { color: colors.muted, fontSize: 13.5, lineHeight: 20, textAlign: 'center', fontFamily: fonts.regular },

  sectionTitle: { color: colors.ink, fontSize: 16, fontFamily: fonts.bold, marginBottom: 12 },
});
