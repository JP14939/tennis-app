import { useCallback, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { SHOT_ICONS } from '../data/mockAnalyses';
import { useAuth } from '../context/AuthContext';
import { fetchHistory } from '../api/history';

const GREEN  = '#4ade80';
const YELLOW = '#facc15';
const RED    = '#f87171';
const DARK   = '#0d0d0d';
const CARD   = '#141414';
const BORDER = '#222';
const TEXT   = '#fff';
const MUTED  = '#888';

function scoreColor(score) {
  if (score >= 75) return GREEN;
  if (score >= 55) return YELLOW;
  return RED;
}

const QUICK_SHOTS = [
  { label: 'Forehand', value: 'forehand' },
  { label: 'Backhand', value: 'backhand' },
  { label: 'Serve',    value: 'serve' },
];

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
      <Text style={r.icon}>{SHOT_ICONS[item.shot_type]}</Text>
      <View style={r.body}>
        <Text style={r.title}>{item.shot_type.charAt(0).toUpperCase() + item.shot_type.slice(1)}</Text>
        <Text style={r.date}>{formatDate(item.created_at)}</Text>
      </View>
      <Text style={[r.score, { color: scoreColor(score) }]}>{score}</Text>
    </View>
  );
}
const r = StyleSheet.create({
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: CARD, borderWidth: 1, borderColor: BORDER,
    borderRadius: 14, padding: 14, marginBottom: 10,
  },
  icon: { fontSize: 22 },
  body: { flex: 1 },
  title: { color: TEXT, fontSize: 14, fontWeight: '700' },
  date: { color: MUTED, fontSize: 12, marginTop: 2 },
  score: { fontSize: 18, fontWeight: '800' },
});

export default function HomeScreen({ navigation }) {
  const { token, isAuthenticated } = useAuth();
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

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        <View style={s.topRow}>
          <Text style={s.greeting}>Welcome back</Text>
          <Text style={s.title}>Ready to train? 🎾</Text>
        </View>

        {/* Primary CTA */}
        <TouchableOpacity
          style={s.ctaCard}
          activeOpacity={0.85}
          onPress={() => navigation.navigate('Upload')}
        >
          <View style={s.ctaText}>
            <Text style={s.ctaTitle}>Analyse your swing</Text>
            <Text style={s.ctaSub}>Get matched to a pro in under 60s</Text>
          </View>
          <View style={s.ctaArrowWrap}>
            <Text style={s.ctaArrow}>→</Text>
          </View>
        </TouchableOpacity>

        {/* Quick shot picks */}
        <View style={s.quickRow}>
          {QUICK_SHOTS.map(shot => (
            <TouchableOpacity
              key={shot.value}
              style={s.quickPill}
              onPress={() => navigation.navigate('Upload', { shotType: shot.value })}
            >
              <Text style={s.quickIcon}>{SHOT_ICONS[shot.value]}</Text>
              <Text style={s.quickLabel}>{shot.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Stats */}
        <View style={s.statsRow}>
          <View style={s.stat}>
            <Text style={s.statNum}>{analyses.length}</Text>
            <Text style={s.statLabel}>Analyses</Text>
          </View>
          <View style={s.statDivider} />
          <View style={s.stat}>
            <Text style={s.statNum}>{avg}</Text>
            <Text style={s.statLabel}>Avg score</Text>
          </View>
          <View style={s.statDivider} />
          <View style={s.stat}>
            <Text style={s.statNum}>{great}</Text>
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
  safe: { flex: 1, backgroundColor: DARK },
  scroll: { padding: 20, paddingTop: 12, paddingBottom: 40 },

  topRow: { marginBottom: 22 },
  greeting: { color: MUTED, fontSize: 14, marginBottom: 2 },
  title: { color: TEXT, fontSize: 26, fontWeight: '800', letterSpacing: -0.5 },

  ctaCard: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: '#0d1f0d', borderWidth: 1, borderColor: '#1a3a1a',
    borderRadius: 18, padding: 20, marginBottom: 18,
  },
  ctaText: { flex: 1 },
  ctaTitle: { color: TEXT, fontSize: 18, fontWeight: '800', marginBottom: 4 },
  ctaSub: { color: '#8fbf9a', fontSize: 13 },
  ctaArrowWrap: {
    width: 40, height: 40, borderRadius: 20, backgroundColor: GREEN,
    alignItems: 'center', justifyContent: 'center', marginLeft: 12,
  },
  ctaArrow: { color: '#000', fontSize: 18, fontWeight: '800' },

  quickRow: { flexDirection: 'row', gap: 10, marginBottom: 20 },
  quickPill: {
    flex: 1, backgroundColor: CARD, borderWidth: 1, borderColor: BORDER,
    borderRadius: 14, paddingVertical: 14, alignItems: 'center', gap: 4,
  },
  quickIcon: { fontSize: 20 },
  quickLabel: { color: '#ccc', fontSize: 12, fontWeight: '600' },

  statsRow: {
    flexDirection: 'row', backgroundColor: CARD,
    borderWidth: 1, borderColor: BORDER, borderRadius: 14,
    padding: 16, marginBottom: 24, alignItems: 'center',
  },
  stat:        { flex: 1, alignItems: 'center' },
  statNum:     { color: TEXT, fontSize: 22, fontWeight: '800' },
  statLabel:   { color: MUTED, fontSize: 11, marginTop: 2 },
  statDivider: { width: 1, height: 32, backgroundColor: BORDER },

  sectionHeader: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    marginBottom: 12,
  },
  sectionTitle: { color: TEXT, fontSize: 16, fontWeight: '700' },
  seeAll: { color: GREEN, fontSize: 13, fontWeight: '600' },

  loginPrompt: {
    backgroundColor: CARD, borderWidth: 1, borderColor: BORDER,
    borderRadius: 14, padding: 16, alignItems: 'center',
  },
  loginPromptText: { color: GREEN, fontSize: 13, fontWeight: '600' },
  noRecents: { color: MUTED, fontSize: 13, textAlign: 'center', paddingVertical: 12 },
});
