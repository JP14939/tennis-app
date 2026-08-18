import { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView, ActivityIndicator, Alert } from 'react-native';
import PlatformVideo from '../components/PlatformVideo';
import TipDiagram from '../components/TipDiagram';
import { colors, fonts, radius, spacing } from '../theme';
import { useAuth } from '../context/AuthContext';
import { getDrill } from '../api/drills';
import { playTapSound } from '../utils/sounds';
import { useWindowWidth } from '../utils/responsive';
import { BackChevronIcon, CheckIcon } from '../components/icons';
import { API_BASE } from '../config/api';

export default function LessonDetailScreen({ route, navigation }) {
  const { id } = route.params ?? {};
  const { token } = useAuth();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null); // null | 'not_found' | 'locked' | 'generic'
  const [item, setItem] = useState(null);

  const windowWidth = useWindowWidth();
  const videoWidth = Math.min(windowWidth - 40, 500);
  const videoHeight = Math.round(videoWidth * 0.56);

  const load = () => {
    setLoading(true);
    setLoadError(null);
    getDrill(token, id)
      .then((data) => setItem(data))
      .catch((err) => setLoadError(err.code === 'PREMIUM_REQUIRED' ? 'locked' : err.message === 'Not found' ? 'not_found' : 'generic'))
      .finally(() => setLoading(false));
  };
  useEffect(load, [id, token]);

  const practiceStep = (step) => {
    if (!step.shot_type) return;
    playTapSound();
    if (!token) {
      Alert.alert('Log in to practise', 'Log in or sign up to record and analyze a practice attempt.', [
        { text: 'Log in', onPress: () => navigation.navigate('Login') },
        { text: 'Cancel', style: 'cancel' },
      ]);
      return;
    }
    navigation.navigate('Upload', { shotType: step.shot_type, practiceStepId: step.id });
  };

  if (loading) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.centerFill}><ActivityIndicator size="large" color={colors.primary} /></View>
      </SafeAreaView>
    );
  }

  if (loadError) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.header}>
          <TouchableOpacity onPress={() => navigation.goBack()}><BackChevronIcon size={16} color={colors.ink} /></TouchableOpacity>
        </View>
        <View style={s.centerFill}>
          <Text style={s.errorText}>
            {loadError === 'locked'
              ? 'This lesson is Premium — upgrade to unlock it.'
              : loadError === 'not_found'
                ? "This drill/lesson doesn't exist anymore."
                : "Couldn't load this — check your connection."}
          </Text>
          {loadError === 'locked' ? (
            <TouchableOpacity style={s.retryBtn} onPress={() => navigation.navigate('MainTabs', { screen: 'Premium' })}>
              <Text style={s.retryBtnText}>See Premium</Text>
            </TouchableOpacity>
          ) : loadError === 'generic' ? (
            <TouchableOpacity style={s.retryBtn} onPress={load}>
              <Text style={s.retryBtnText}>Try again</Text>
            </TouchableOpacity>
          ) : null}
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        <View style={s.header}>
          <TouchableOpacity onPress={() => navigation.goBack()}><BackChevronIcon size={16} color={colors.ink} /></TouchableOpacity>
        </View>

        <Text style={s.title}>{item.title}</Text>

        {item.video_url ? (
          <View style={[s.videoWrap, { width: videoWidth, height: videoHeight, alignSelf: 'center' }]}>
            <PlatformVideo uri={`${API_BASE}${item.video_url}`} width={videoWidth} height={videoHeight} />
          </View>
        ) : item.diagram_tip_id ? (
          <View style={s.diagramWrap}><TipDiagram tipId={item.diagram_tip_id} /></View>
        ) : null}

        <Text style={s.sectionLabel}>What to emphasize</Text>
        <Text style={s.body}>{item.explanation}</Text>
        {item.emphasis && (
          <View style={s.emphasisBox}>
            <Text style={s.emphasisText}>{item.emphasis}</Text>
          </View>
        )}

        {item.steps?.length > 0 && (
          <>
            <Text style={s.sectionLabel}>Practice routine</Text>
            {item.steps.map((step, i) => (
              <View key={step.id} style={s.stepCard}>
                <View style={s.stepHeader}>
                  <View style={s.stepNumber}><Text style={s.stepNumberText}>{i + 1}</Text></View>
                  <Text style={s.stepLabel}>{step.label}</Text>
                </View>
                {step.shot_type ? (
                  <>
                    <TouchableOpacity style={s.practiceBtn} onPress={() => practiceStep(step)}>
                      <Text style={s.practiceBtnText}>Practise this →</Text>
                    </TouchableOpacity>
                    {step.attempt_count > 0 && (
                      <View style={s.attemptRow}>
                        <CheckIcon size={11} color={colors.primary} />
                        <Text style={s.attemptText}>
                          {step.attempt_count} attempt{step.attempt_count === 1 ? '' : 's'} so far
                        </Text>
                      </View>
                    )}
                  </>
                ) : null}
              </View>
            ))}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingTop: 12, paddingBottom: 48 },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 24 },
  header: { marginBottom: 10 },

  title: { color: colors.ink, fontSize: 22, fontFamily: fonts.bold, letterSpacing: -0.3, marginBottom: 14 },

  videoWrap: { borderRadius: radius.lg, overflow: 'hidden', backgroundColor: '#000', marginBottom: 18 },
  diagramWrap: { alignItems: 'center', backgroundColor: colors.surface, borderRadius: radius.lg, paddingVertical: 12, marginBottom: 18 },

  sectionLabel: { color: colors.ink, fontSize: 15, fontFamily: fonts.bold, marginBottom: 8, marginTop: 6 },
  body: { color: colors.mutedDark, fontSize: 14, lineHeight: 21, fontFamily: fonts.regular, marginBottom: 10 },
  emphasisBox: { backgroundColor: colors.primarySoft, borderRadius: radius.md, padding: 14, marginBottom: 10 },
  emphasisText: { color: colors.limeText, fontSize: 13.5, lineHeight: 20, fontFamily: fonts.regular },

  stepCard: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: 16, marginBottom: 12 },
  stepHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 10 },
  stepNumber: {
    width: 24, height: 24, borderRadius: 12, backgroundColor: colors.primary,
    alignItems: 'center', justifyContent: 'center',
  },
  stepNumberText: { color: colors.white, fontSize: 12, fontFamily: fonts.bold },
  stepLabel: { color: colors.ink, fontSize: 14.5, fontFamily: fonts.semibold, flex: 1 },

  practiceBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingVertical: 11, alignItems: 'center' },
  practiceBtnText: { color: colors.white, fontSize: 13.5, fontFamily: fonts.bold },
  attemptRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10 },
  attemptText: { color: colors.muted, fontSize: 12, fontFamily: fonts.regular },

  errorText: { color: colors.muted, fontSize: 13.5, textAlign: 'center', marginBottom: 14, lineHeight: 19 },
  retryBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingHorizontal: 20, paddingVertical: 11 },
  retryBtnText: { color: colors.white, fontSize: 13.5, fontFamily: fonts.bold },
});
