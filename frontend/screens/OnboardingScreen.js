import { View, Text, Image, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView } from 'react-native';
import { colors, fonts, radius, spacing } from '../theme';
import { playTapSound } from '../utils/sounds';
import { markOnboardingComplete } from '../utils/onboarding';

// First-run welcome. Deliberately ONE screen, not a slide deck -- states the
// payoff and the three steps, then gets out of the way. Shown only while
// utils/onboarding.js's key is unset (App.js decides the initial route).
const STEPS = [
  { n: '1', title: 'Film a swing', body: 'Prop your phone on the fence or net, or upload a clip you already have. 10–30 seconds is plenty.' },
  { n: '2', title: 'Mark the contact', body: 'Scrub to the frame where your racket meets the ball. Got sound? We find it for you.' },
  { n: '3', title: 'Read your score', body: 'A 0–100 match against tour technique, the closest pro, and the fixes that matter most.' },
];

export default function OnboardingScreen({ navigation }) {
  const finish = async (next) => {
    playTapSound();
    await markOnboardingComplete();
    next();
  };

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        <View style={s.header}>
          <Image source={require('../assets/branding/logo-rallymax.png')} style={s.logo} resizeMode="contain" />
          <Text style={s.title}>Your swing, scored against the pros.</Text>
          <Text style={s.sub}>
            RallyMax compares your technique to 600+ tour swings and tells you exactly what to fix.
          </Text>
        </View>

        {STEPS.map((step) => (
          <View key={step.n} style={s.stepCard}>
            <View style={s.stepNumberWrap}><Text style={s.stepNumber}>{step.n}</Text></View>
            <View style={s.stepTextWrap}>
              <Text style={s.stepTitle}>{step.title}</Text>
              <Text style={s.stepBody}>{step.body}</Text>
            </View>
          </View>
        ))}

        <View style={s.spacer} />

        <TouchableOpacity
          style={s.btnPrimary}
          activeOpacity={0.9}
          onPress={() => finish(() => navigation.reset({
            // Home under Upload, so "back" from the flow lands on the app, not
            // a dead end.
            index: 1,
            routes: [{ name: 'MainTabs' }, { name: 'Upload' }],
          }))}
        >
          <Text style={s.btnPrimaryText}>Analyse my first swing</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={s.btnGhost}
          onPress={() => finish(() => navigation.reset({ index: 0, routes: [{ name: 'MainTabs' }] }))}
        >
          <Text style={s.btnGhostText}>Skip for now</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xxl, paddingTop: 40, paddingBottom: 40, flexGrow: 1 },

  header: { marginBottom: 28 },
  logo: { width: 140, height: 46, marginBottom: 24 },
  title: { color: colors.ink, fontSize: 32, lineHeight: 36, fontFamily: fonts.serifItalic, marginBottom: 12 },
  sub: { color: colors.muted, fontSize: 15, lineHeight: 22, fontFamily: fonts.regular },

  stepCard: {
    flexDirection: 'row', gap: 14, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.lg, padding: 16, marginBottom: 12, alignItems: 'flex-start',
  },
  stepNumberWrap: {
    width: 26, height: 26, borderRadius: 13, backgroundColor: colors.primarySoft,
    borderWidth: 1, borderColor: colors.primary, alignItems: 'center', justifyContent: 'center',
  },
  stepNumber: { color: colors.primary, fontSize: 13, fontFamily: fonts.bold },
  stepTextWrap: { flex: 1 },
  stepTitle: { color: colors.ink, fontSize: 15, fontFamily: fonts.bold, marginBottom: 4 },
  stepBody: { color: colors.mutedDark, fontSize: 13, lineHeight: 19, fontFamily: fonts.regular },

  spacer: { flex: 1, minHeight: 24 },

  btnPrimary: { backgroundColor: colors.primary, borderRadius: radius.sm, paddingVertical: 16, alignItems: 'center' },
  btnPrimaryText: { color: colors.white, fontSize: 16, fontFamily: fonts.bold },
  btnGhost: { paddingVertical: 14, alignItems: 'center', marginTop: 4 },
  btnGhostText: { color: colors.muted, fontSize: 14, fontFamily: fonts.semibold },
});
