import { useEffect, useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView,
  ScrollView, ActivityIndicator, Platform,
} from 'react-native';
import { API_BASE } from '../config/api';
import ResultShareCard from '../components/ResultShareCard';
import { captureAndShare } from '../utils/shareCard';
import { ShareIcon } from '../components/icons';

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

async function appendVideo(formData, field, videoUri) {
  if (Platform.OS === 'web') {
    const response = await fetch(videoUri);
    const blob = await response.blob();
    formData.append(field, blob, `${field}.mp4`);
  } else {
    formData.append(field, { uri: videoUri, name: `${field}.mp4`, type: 'video/mp4' });
  }
}

async function buildCompareFormData(reference, yours, shotType) {
  const formData = new FormData();
  await appendVideo(formData, 'reference', reference.videoUri);
  await appendVideo(formData, 'yours', yours.videoUri);
  formData.append('shotType', shotType);
  if (reference.contactTimeSec !== undefined && reference.contactTimeSec !== null) {
    formData.append('contactTimeA', String(reference.contactTimeSec));
  }
  if (yours.contactTimeSec !== undefined && yours.contactTimeSec !== null) {
    formData.append('contactTimeB', String(yours.contactTimeSec));
  }
  return formData;
}

export default function VersusResultsScreen({ route, navigation }) {
  const { shotType, reference, yours } = route.params ?? {};

  const [status, setStatus] = useState('loading'); // loading | error | done
  const [errorMsg, setErrorMsg] = useState('');
  const [result, setResult] = useState(null);
  const shareCardRef = useRef(null);

  const runComparison = async () => {
    setStatus('loading');
    setErrorMsg('');
    try {
      const formData = await buildCompareFormData(reference, yours, shotType);
      const response = await fetch(`${API_BASE}/api/compare-videos`, {
        method: 'POST',
        body: formData,
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Comparison failed');
      }
      setResult(data);
      setStatus('done');
    } catch (err) {
      setErrorMsg(err.message || 'Something went wrong');
      setStatus('error');
    }
  };

  useEffect(() => {
    if (reference?.videoUri && yours?.videoUri && shotType) {
      runComparison();
    } else {
      setErrorMsg('Missing video or shot type — go back and try again.');
      setStatus('error');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  if (status === 'error') {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.centerFill}>
          <Text style={s.errorIcon}>⚠️</Text>
          <Text style={s.loadingTitle}>Comparison failed</Text>
          <Text style={s.loadingSub}>{errorMsg}</Text>
          <TouchableOpacity style={s.retryBtn} onPress={runComparison}>
            <Text style={s.retryBtnText}>Try again</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.secondaryBtn} onPress={() => navigation.navigate('VersusPick')}>
            <Text style={s.secondaryBtnText}>Pick different videos</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const score = result.similarity;

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        <View style={s.headerRow}>
          <View>
            <Text style={s.header}>Comparison Results</Text>
            <Text style={s.headerSub}>{shotType?.charAt(0).toUpperCase() + shotType?.slice(1)}</Text>
          </View>
          {Platform.OS !== 'web' && (
            <TouchableOpacity
              style={s.shareBtn}
              onPress={() => captureAndShare(shareCardRef, 'Share your TennisAI comparison')}
            >
              <ShareIcon size={17} color={TEXT} />
            </TouchableOpacity>
          )}
        </View>

        <View style={s.scoreCard}>
          <Text style={[s.scoreNum, { color: scoreColor(score) }]}>{score}</Text>
          <Text style={s.scoreOutOf}>/ 100</Text>
          <View style={s.scoreTrack}>
            <View style={[s.scoreFill, { width: `${score}%`, backgroundColor: scoreColor(score) }]} />
          </View>
          <Text style={s.matchedTo}>How closely your swing matches the reference video</Text>
        </View>

        {result.reference_clip_url && result.your_clip_url && (
          <TouchableOpacity
            style={s.compareBtn}
            onPress={() => navigation.navigate('SyncCompare', {
              videoAUrl: `${API_BASE}${result.reference_clip_url}`,
              videoBUrl: `${API_BASE}${result.your_clip_url}`,
              croppedAUrl: result.reference_clip_cropped_url ? `${API_BASE}${result.reference_clip_cropped_url}` : null,
              croppedBUrl: result.your_clip_cropped_url ? `${API_BASE}${result.your_clip_cropped_url}` : null,
              contactASec: result.reference_contact_time_sec ?? 0,
              contactBSec: result.your_contact_time_sec ?? 0,
              overlayA: result.reference_overlay_trajectory ?? null,
              overlayB: result.your_overlay_trajectory ?? null,
              labelA: 'Reference',
              labelB: 'You',
            })}
          >
            <Text style={s.compareBtnText}>Compare side-by-side →</Text>
          </TouchableOpacity>
        )}

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

      <View style={s.offscreen}>
        <ResultShareCard
          ref={shareCardRef}
          score={score}
          shotType={shotType}
          caption="Compared to your reference video"
        />
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: DARK },
  scroll: { padding: 20, paddingTop: 32, paddingBottom: 48 },

  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32 },
  loadingTitle: { color: TEXT, fontSize: 18, fontWeight: '700', marginTop: 20, textAlign: 'center' },
  loadingSub: { color: MUTED, fontSize: 14, marginTop: 8, textAlign: 'center', lineHeight: 20 },
  errorIcon: { fontSize: 40 },
  retryBtn: { backgroundColor: GREEN, borderRadius: 12, paddingVertical: 12, paddingHorizontal: 28, marginTop: 24 },
  retryBtnText: { color: '#000', fontSize: 15, fontWeight: '700' },

  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  header: { color: TEXT, fontSize: 26, fontWeight: '800', letterSpacing: -0.5 },
  headerSub: { color: MUTED, fontSize: 14, marginTop: 2, marginBottom: 24 },
  shareBtn: {
    width: 38, height: 38, borderRadius: 19, backgroundColor: CARD,
    borderWidth: 1, borderColor: BORDER, alignItems: 'center', justifyContent: 'center',
  },
  offscreen: { position: 'absolute', left: -9999, top: -9999 },

  scoreCard: {
    backgroundColor: CARD, borderWidth: 1, borderColor: BORDER, borderRadius: 18,
    padding: 24, alignItems: 'center', marginBottom: 16,
  },
  scoreNum: { fontSize: 56, fontWeight: '800' },
  scoreOutOf: { color: MUTED, fontSize: 14, marginTop: -8 },
  scoreTrack: { width: '100%', height: 8, backgroundColor: '#1a1a1a', borderRadius: 4, marginTop: 16, overflow: 'hidden' },
  scoreFill: { height: 8, borderRadius: 4 },
  matchedTo: { color: MUTED, fontSize: 13, marginTop: 14, textAlign: 'center' },

  compareBtn: {
    borderWidth: 1, borderColor: BORDER, borderRadius: 12,
    paddingVertical: 13, alignItems: 'center', marginBottom: 16,
  },
  compareBtnText: { color: GREEN, fontSize: 14, fontWeight: '700' },

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
