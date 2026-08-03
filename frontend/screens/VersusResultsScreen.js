import { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView,
  ScrollView, ActivityIndicator,
} from 'react-native';

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

// Mock tips so the results UI can be reviewed now — TODO: replace with a real
// POST to /api/compare-videos (backend engine already exists at
// scripts/08_comparison_engine/compare_videos.py, just not wired up yet).
const MOCK_TIPS = {
  forehand: [
    'Your elbow is too far from your body at contact — tuck it closer for more control.',
    "Your wrist isn't crossing your body enough — follow through more to your left shoulder.",
  ],
  backhand: [
    "Your left wrist isn't leading enough — drive through with your non-dominant hand.",
    'Keep your wrists firm at contact — they\'re dropping and causing errors.',
  ],
  serve: [
    'Your contact point is too low — toss the ball higher and reach up more.',
    'Your elbow is dropping before contact — keep your arm up in the trophy position longer.',
  ],
};

function buildMockResult(shotType) {
  const score = 55 + Math.round(Math.random() * 30);
  return {
    shot_type: shotType,
    similarity: score,
    reference_angle_label: 'Diagonal',
    your_angle_label: 'Semi-front',
    angle_mismatch_deg: 12,
    angle_mismatch_warning: false,
    tips: MOCK_TIPS[shotType] ?? [],
  };
}

export default function VersusResultsScreen({ route, navigation }) {
  const { shotType, reference, yours } = route.params ?? {};

  const [status, setStatus] = useState('loading'); // loading | done
  const [result, setResult] = useState(null);

  useEffect(() => {
    // TODO: replace with a real call once /api/compare-videos exists —
    // POST reference.videoUri + yours.videoUri + shotType + both
    // contactTimeSec values, same pattern as ResultsScreen's buildFormData.
    const timer = setTimeout(() => {
      setResult(buildMockResult(shotType));
      setStatus('done');
    }, 1800);
    return () => clearTimeout(timer);
  }, [shotType]);

  if (status === 'loading') {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.centerFill}>
          <ActivityIndicator size="large" color={GREEN} />
          <Text style={s.loadingTitle}>Comparing your swing...</Text>
          <Text style={s.loadingSub}>Analysing both videos frame by frame</Text>
        </View>
      </SafeAreaView>
    );
  }

  const score = result.similarity;

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        <Text style={s.header}>Comparison Results</Text>
        <Text style={s.headerSub}>{shotType?.charAt(0).toUpperCase() + shotType?.slice(1)}</Text>

        <View style={s.scoreCard}>
          <Text style={[s.scoreNum, { color: scoreColor(score) }]}>{score}</Text>
          <Text style={s.scoreOutOf}>/ 100</Text>
          <View style={s.scoreTrack}>
            <View style={[s.scoreFill, { width: `${score}%`, backgroundColor: scoreColor(score) }]} />
          </View>
          <Text style={s.matchedTo}>How closely your swing matches the reference video</Text>
        </View>

        <View style={s.angleRow}>
          <View style={s.angleCard}>
            <Text style={s.angleLabel}>Reference angle</Text>
            <Text style={s.angleValue}>{result.reference_angle_label ?? '—'}</Text>
          </View>
          <View style={s.angleCard}>
            <Text style={s.angleLabel}>Your angle</Text>
            <Text style={s.angleValue}>{result.your_angle_label ?? '—'}</Text>
          </View>
        </View>
        {result.angle_mismatch_warning && (
          <View style={s.warnCard}>
            <Text style={s.warnText}>⚠️ These videos were filmed from noticeably different angles — the score may be less reliable than usual.</Text>
          </View>
        )}

        <Text style={s.sectionTitle}>What's different</Text>
        {result.tips.map((tip, i) => (
          <View key={i} style={s.tipCard}>
            <Text style={s.tipIcon}>💡</Text>
            <Text style={s.tipText}>{tip}</Text>
          </View>
        ))}

        <TouchableOpacity style={s.primaryBtn} onPress={() => navigation.navigate('VersusPick')}>
          <Text style={s.primaryBtnText}>Compare another video</Text>
        </TouchableOpacity>
        <TouchableOpacity style={s.secondaryBtn} onPress={() => navigation.popToTop()}>
          <Text style={s.secondaryBtnText}>Back to home</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: DARK },
  scroll: { padding: 20, paddingTop: 32, paddingBottom: 48 },

  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32 },
  loadingTitle: { color: TEXT, fontSize: 18, fontWeight: '700', marginTop: 20, textAlign: 'center' },
  loadingSub: { color: MUTED, fontSize: 14, marginTop: 8, textAlign: 'center', lineHeight: 20 },

  header: { color: TEXT, fontSize: 26, fontWeight: '800', letterSpacing: -0.5 },
  headerSub: { color: MUTED, fontSize: 14, marginTop: 2, marginBottom: 24 },

  scoreCard: {
    backgroundColor: CARD, borderWidth: 1, borderColor: BORDER, borderRadius: 18,
    padding: 24, alignItems: 'center', marginBottom: 16,
  },
  scoreNum: { fontSize: 56, fontWeight: '800' },
  scoreOutOf: { color: MUTED, fontSize: 14, marginTop: -8 },
  scoreTrack: { width: '100%', height: 8, backgroundColor: '#1a1a1a', borderRadius: 4, marginTop: 16, overflow: 'hidden' },
  scoreFill: { height: 8, borderRadius: 4 },
  matchedTo: { color: MUTED, fontSize: 13, marginTop: 14, textAlign: 'center' },

  angleRow: { flexDirection: 'row', gap: 12, marginBottom: 12 },
  angleCard: {
    flex: 1, backgroundColor: CARD, borderWidth: 1, borderColor: BORDER,
    borderRadius: 14, padding: 16, alignItems: 'center',
  },
  angleLabel: { color: MUTED, fontSize: 12 },
  angleValue: { color: TEXT, fontSize: 17, fontWeight: '700', marginTop: 4 },

  warnCard: {
    backgroundColor: '#241a0d', borderWidth: 1, borderColor: '#4a3a1a',
    borderRadius: 12, padding: 14, marginBottom: 12,
  },
  warnText: { color: '#facc15', fontSize: 12, lineHeight: 18 },

  sectionTitle: { color: TEXT, fontSize: 16, fontWeight: '700', marginBottom: 12, marginTop: 12 },
  tipCard: {
    flexDirection: 'row', gap: 10, backgroundColor: CARD, borderWidth: 1, borderColor: BORDER,
    borderRadius: 14, padding: 14, marginBottom: 10, alignItems: 'flex-start',
  },
  tipIcon: { fontSize: 16 },
  tipText: { color: '#ccc', fontSize: 14, lineHeight: 20, flex: 1 },

  primaryBtn: { backgroundColor: GREEN, borderRadius: 12, paddingVertical: 15, alignItems: 'center', marginTop: 16 },
  primaryBtnText: { color: '#000', fontSize: 15, fontWeight: '700' },
  secondaryBtn: {
    borderWidth: 1, borderColor: BORDER, borderRadius: 12,
    paddingVertical: 14, alignItems: 'center', marginTop: 10,
  },
  secondaryBtnText: { color: '#aaa', fontSize: 15, fontWeight: '600' },
});
