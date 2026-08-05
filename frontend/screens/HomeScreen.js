import { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { useAuth } from '../context/AuthContext';
import { fetchHistory } from '../api/history';
import { colors, fonts, radius, spacing, scoreColor } from '../theme';
import CourtBackground from '../components/CourtBackground';
import ScoreRing from '../components/ScoreRing';
import { TennisBallIcon, ChevronRightIcon } from '../components/icons';

const QUICK_SHOTS = [
  { label: 'Forehand', value: 'forehand' },
  { label: 'Backhand', value: 'backhand' },
  { label: 'Serve',    value: 'serve' },
];

function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }

function useCountUp(target, durationMs = 1100) {
  const [value, setValue] = useState(0);
  const frame = useRef(null);
  useEffect(() => {
    const start = performance.now();
    const tick = (now) => {
      const t = Math.min(1, (now - start) / durationMs);
      setValue(Math.round(target * easeOutCubic(t)));
      if (t < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => frame.current && cancelAnimationFrame(frame.current);
  }, [target, durationMs]);
  return value;
}

function formatDate(isoString) {
  if (!isoString) return '';
  const d = new Date(isoString.includes('Z') ? isoString : `${isoString.replace(' ', 'T')}Z`);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function RecentRow({ item }) {
  const score = Math.round(item.similarity ?? 0);
  return (
    <View style={r.row}>
      <ScoreRing score={score} />
      <View style={r.body}>
        <Text style={r.title}>{item.shot_type.charAt(0).toUpperCase() + item.shot_type.slice(1)}</Text>
        <Text style={r.date}>{formatDate(item.created_at)} · {item.pro_id ?? 'Technique'}</Text>
      </View>
      <ChevronRightIcon size={7} color={colors.muted} />
    </View>
  );
}
const r = StyleSheet.create({
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 14,
    backgroundColor: colors.surface, borderRadius: radius.lg,
    padding: 13, marginBottom: 10,
  },
  body: { flex: 1, minWidth: 0 },
  title: { color: colors.ink, fontSize: 14.5, fontFamily: fonts.bold },
  date: { color: colors.muted, fontSize: 12, marginTop: 2, fontFamily: fonts.regular },
});

export default function HomeScreen({ navigation }) {
  const { token, isAuthenticated, user } = useAuth();
  const [analyses, setAnalyses] = useState([]);

  useFocusEffect(useCallback(() => {
    if (!isAuthenticated) {
      setAnalyses([]);
      return;
    }
    fetchHistory(token).then(data => setAnalyses(data.analyses)).catch(() => {});
  }, [token, isAuthenticated]));

  const recents = analyses.slice(0, 2);
  const avg = analyses.length
    ? Math.round(analyses.reduce((sum, a) => sum + a.similarity, 0) / analyses.length)
    : 0;
  const great = analyses.filter(a => a.similarity >= 75).length;

  const analysesCount = useCountUp(analyses.length);
  const avgCount = useCountUp(avg);
  const greatCount = useCountUp(great);

  const playerName = isAuthenticated ? user.name.split(' ')[0] : 'there';
  const playerInitial = isAuthenticated ? user.name.charAt(0).toUpperCase() : '🎾';

  const dayLabel = new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });

  return (
    <SafeAreaView style={s.safe}>
      <CourtBackground />
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        <View style={s.topRow}>
          <View style={{ flex: 1 }}>
            <Text style={s.dayLabel}>{dayLabel}</Text>
            <Text style={s.greeting}>Let's play, {playerName}.</Text>
          </View>
          <View style={s.avatar}>
            <Text style={s.avatarText}>{playerInitial}</Text>
          </View>
        </View>

        {/* Primary CTA */}
        <TouchableOpacity
          style={s.ctaCard}
          activeOpacity={0.9}
          onPress={() => navigation.navigate('Upload')}
        >
          <View style={s.ctaTopRow}>
            <View style={s.ctaBadge}>
              <Text style={s.ctaBadgeText}>NEW ANALYSIS</Text>
            </View>
            <Text style={s.ctaHint}>Perfect your swing in under 60s</Text>
          </View>
          <View style={s.ctaPill}>
            <Text style={s.ctaPillText}>Start analysis</Text>
            <Text style={s.ctaPillArrow}>→</Text>
          </View>
        </TouchableOpacity>

        {/* Quick shot picks */}
        <View style={s.quickRow}>
          {QUICK_SHOTS.map(shot => (
            <TouchableOpacity
              key={shot.value}
              style={s.quickPill}
              onPress={() => navigation.navigate('Upload', { shotType: shot.value })}
              activeOpacity={0.85}
            >
              <TennisBallIcon size={15} color={colors.primary} />
              <Text style={s.quickLabel}>{shot.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Stats */}
        <View style={s.statsRow}>
          <View style={s.stat}>
            <View style={[s.statAccent, { backgroundColor: colors.primary }]} />
            <Text style={s.statNum}>{analysesCount}</Text>
            <Text style={s.statLabel}>Analyses</Text>
          </View>
          <View style={s.stat}>
            <View style={[s.statAccent, { backgroundColor: colors.gold }]} />
            <Text style={s.statNum}>{avgCount}</Text>
            <Text style={s.statLabel}>Avg score</Text>
          </View>
          <View style={s.stat}>
            <View style={[s.statAccent, { backgroundColor: colors.lime }]} />
            <Text style={s.statNum}>{greatCount}</Text>
            <Text style={s.statLabel}>Great swings</Text>
          </View>
        </View>

        {/* Recent activity */}
        <View style={s.sectionHeader}>
          <Text style={s.sectionTitle}>Recent activity</Text>
          <TouchableOpacity onPress={() => navigation.jumpTo('History')}>
            <Text style={s.seeAll}>See all</Text>
          </TouchableOpacity>
        </View>
        {!isAuthenticated && (
          <TouchableOpacity style={s.loginPrompt} onPress={() => navigation.navigate('Login')}>
            <Text style={s.loginPromptText}>Log in to track your analysis history →</Text>
          </TouchableOpacity>
        )}
        {isAuthenticated && recents.length === 0 && (
          <Text style={s.noRecents}>No analyses yet — upload a swing to get started.</Text>
        )}
        {recents.map(item => <RecentRow key={item.id} item={item} />)}

      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingTop: 20, paddingBottom: 130 },

  topRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: spacing.xxl },
  dayLabel: { color: colors.muted, fontSize: 13, fontFamily: fonts.semibold, marginBottom: 4 },
  greeting: { color: colors.ink, fontSize: 32, fontFamily: fonts.serifItalic, lineHeight: 36 },
  avatar: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: colors.primary,
    alignItems: 'center', justifyContent: 'center', marginTop: 4,
    shadowColor: colors.primary, shadowOpacity: 0.3, shadowRadius: 10, shadowOffset: { width: 0, height: 4 },
  },
  avatarText: { color: colors.lime, fontSize: 18, fontFamily: fonts.serif },

  ctaCard: {
    backgroundColor: colors.primary, borderRadius: radius.xl, padding: 18, marginBottom: spacing.xl,
    overflow: 'hidden',
  },
  ctaTopRow: { flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 14 },
  ctaBadge: { backgroundColor: colors.lime, borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 4 },
  ctaBadgeText: { color: colors.primary, fontSize: 10, fontFamily: fonts.extrabold, letterSpacing: 0.6 },
  ctaHint: { color: 'rgba(255,255,255,0.85)', fontSize: 12.5, fontFamily: fonts.semibold, flexShrink: 1 },
  ctaPill: {
    flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: colors.white,
    alignSelf: 'flex-start', paddingVertical: 10, paddingHorizontal: 18, borderRadius: radius.pill,
  },
  ctaPillText: { color: colors.primary, fontSize: 14, fontFamily: fonts.bold },
  ctaPillArrow: { color: colors.primary, fontSize: 14, fontFamily: fonts.bold },

  quickRow: { flexDirection: 'row', gap: 9, marginBottom: spacing.xxl },
  quickPill: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    backgroundColor: colors.surface, borderRadius: radius.pill, paddingVertical: 12,
  },
  quickLabel: { color: colors.ink, fontSize: 12.5, fontFamily: fonts.bold },

  statsRow: {
    flexDirection: 'row', gap: 10, marginBottom: spacing.xxl,
  },
  stat: {
    flex: 1, backgroundColor: colors.surface, borderRadius: radius.lg,
    paddingTop: 16, paddingBottom: 14, paddingHorizontal: 10, alignItems: 'center', overflow: 'hidden',
  },
  statAccent: { position: 'absolute', top: 0, left: 0, right: 0, height: 3 },
  statNum: { color: colors.ink, fontSize: 26, fontFamily: fonts.serif },
  statLabel: { color: colors.muted, fontSize: 10.5, fontFamily: fonts.semibold, marginTop: 3 },

  sectionHeader: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: spacing.md,
  },
  sectionTitle: { color: colors.ink, fontSize: 19, fontFamily: fonts.serif },
  seeAll: { color: colors.primary, fontSize: 13, fontFamily: fonts.semibold },

  loginPrompt: {
    backgroundColor: colors.surface, borderRadius: radius.lg, padding: 16, alignItems: 'center',
  },
  loginPromptText: { color: colors.primary, fontSize: 13, fontFamily: fonts.semibold },
  noRecents: { color: colors.muted, fontSize: 13, textAlign: 'center', paddingVertical: 12, fontFamily: fonts.regular },
});
