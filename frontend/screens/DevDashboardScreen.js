import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView } from 'react-native';
import { colors, fonts, radius, spacing } from '../theme';
import { playTapSound } from '../utils/sounds';
import RequireAdmin from '../components/RequireAdmin';

// Hidden hub (Profile -> Settings -> Dev Page, admin-only -- see
// frontend/utils/isAdmin.js and SettingsScreen.js's conditional row).
// Real access control is server-side (every /api/dev/* route requires
// requireAuth + requireAdmin); this and its children are just kept out of
// normal navigation, not a security boundary on their own.
const TOOLS = [
  {
    key: 'ml-status',
    label: 'ML Reliability',
    sub: 'Live agreement rates and trust status for the shot-contact verifier, shot classifier, and tip selector',
    screen: 'DevMLStatus',
  },
  {
    key: 'swing-review',
    label: 'Swing Review (free, manual)',
    sub: 'Watch each raw swing candidate yourself and tap real-shot + shot-type -- zero API cost, logs exactly like a Claude-verified example',
    screen: 'DevRallyJobs',
    params: {
      targetScreen: 'DevSwingReview',
      title: 'Swing Review',
      subtitle: 'Pick a match to manually review its raw swing candidates -- free, no Claude calls.',
    },
  },
  {
    key: 'rally-boundary',
    label: 'Rally Boundary Review',
    sub: "Tag whether detected rally clips' start/end points are right -- training data for detect_rallies.py, not a user-facing question",
    screen: 'DevRallyJobs',
    params: {
      targetScreen: 'DevRallyBoundaryReview',
      title: 'Rally Boundary Review',
      subtitle: 'Pick a match to review its detected rally boundaries against.',
    },
  },
  {
    key: 'drills-editor',
    label: 'Drills & Lessons Editor',
    sub: 'Create/edit the free Drills library and paid Lessons routines shown on the History screen',
    screen: 'DevDrillsEditor',
  },
];

export default function DevDashboardScreen({ navigation }) {
  return (
    <RequireAdmin navigation={navigation}>
      <SafeAreaView style={s.safe}>
        <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
          <Text style={s.h1}>Dev Page</Text>
          <Text style={s.sub}>Training and review tools -- not visible to real users.</Text>

          {TOOLS.map((tool) => (
            <TouchableOpacity
              key={tool.key}
              style={s.card}
              activeOpacity={0.8}
              onPress={() => { playTapSound(); navigation.navigate(tool.screen, tool.params); }}
            >
              <Text style={s.cardLabel}>{tool.label}</Text>
              <Text style={s.cardSub}>{tool.sub}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </SafeAreaView>
    </RequireAdmin>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingTop: 24, paddingBottom: 48 },

  h1:  { color: colors.ink, fontSize: 24, fontFamily: fonts.bold, letterSpacing: -0.5, marginBottom: 6 },
  sub: { color: colors.muted, fontSize: 13, lineHeight: 19, marginBottom: 24, fontFamily: fonts.regular },

  card: {
    backgroundColor: colors.surface, borderRadius: radius.lg,
    padding: 18, marginBottom: 14,
  },
  cardLabel: { color: colors.ink, fontSize: 15.5, fontFamily: fonts.bold, marginBottom: 6 },
  cardSub: { color: colors.muted, fontSize: 12.5, lineHeight: 18, fontFamily: fonts.regular },
});
