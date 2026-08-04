import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView,
  ScrollView, ActivityIndicator, Platform,
} from 'react-native';
import { API_BASE } from '../config/api';
import { useAuth } from '../context/AuthContext';
import { saveHistory } from '../api/history';

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

const PHASE_LABELS = {
  backswing: 'Backswing',
  contact: 'Contact',
  follow_through: 'Follow-through',
  body_rotation: 'Body Rotation',
};
const PHASE_ORDER = ['backswing', 'contact', 'follow_through', 'body_rotation'];

function phaseColor(score) {
  if (score == null) return MUTED;
  if (score >= 18.75) return GREEN;  // 75% of 25
  if (score >= 13.75) return YELLOW; // 55% of 25
  return RED;
}

function formatProId(proId) {
  // "forehand_0142" -> "Forehand Technique #142"
  const [shot, num] = proId.split('_');
  const label = shot.charAt(0).toUpperCase() + shot.slice(1);
  return `${label} Technique #${parseInt(num, 10)}`;
}

async function buildFormData(videoUri, shotType, contactTimeSec) {
  const formData = new FormData();
  if (Platform.OS === 'web') {
    const response = await fetch(videoUri);
    const blob = await response.blob();
    formData.append('video', blob, 'swing.mp4');
  } else {
    formData.append('video', { uri: videoUri, name: 'swing.mp4', type: 'video/mp4' });
  }
  formData.append('shotType', shotType);
  if (contactTimeSec !== undefined && contactTimeSec !== null) {
    formData.append('contactTime', String(contactTimeSec));
  }
  return formData;
}

export default function ResultsScreen({ navigation, route }) {
  const { videoUri, shotType, contactTimeSec } = route.params ?? {};
  const { token, isAuthenticated } = useAuth();

  const [status, setStatus] = useState('loading'); // loading | error | done
  const [errorMsg, setErrorMsg] = useState('');
  const [errorCode, setErrorCode] = useState(null);
  const [result, setResult] = useState(null);
  // idle | saving | saved | limit | guest | error — purely informational,
  // never blocks the analysis result itself from displaying.
  const [saveStatus, setSaveStatus] = useState('idle');

  const runAnalysis = async () => {
    setStatus('loading');
    setErrorMsg('');
    setErrorCode(null);
    try {
      const formData = await buildFormData(videoUri, shotType, contactTimeSec);
      const response = await fetch(`${API_BASE}/api/analyse`, {
        method: 'POST',
        body: formData,
      });
      const data = await response.json();
      if (!response.ok) {
        setErrorCode(data.code ?? null);
        throw new Error(data.error || 'Analysis failed');
      }
      setResult(data);
      setStatus('done');
      saveToHistory(data);
    } catch (err) {
      setErrorMsg(err.message || 'Something went wrong');
      setStatus('error');
    }
  };

  const saveToHistory = async (data) => {
    if (!isAuthenticated) {
      setSaveStatus('guest');
      return;
    }
    setSaveStatus('saving');
    try {
      await saveHistory(token, data, shotType);
      setSaveStatus('saved');
    } catch (err) {
      setSaveStatus(err.code === 'HISTORY_LIMIT' ? 'limit' : 'error');
    }
  };

  useEffect(() => {
    if (videoUri && shotType) {
      runAnalysis();
    } else {
      setErrorMsg('Missing video or shot type — go back and try again.');
      setStatus('error');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Loading ───────────────────────────────────────────────────────────────
  if (status === 'loading') {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.centerFill}>
          <ActivityIndicator size="large" color={GREEN} />
          <Text style={s.loadingTitle}>Analysing your swing...</Text>
          <Text style={s.loadingSub}>Comparing your technique against our pro database</Text>
        </View>
      </SafeAreaView>
    );
  }

  // ── Error ─────────────────────────────────────────────────────────────────
  if (status === 'error') {
    const isDailyLimit = errorCode === 'DAILY_LIMIT';
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.centerFill}>
          <Text style={s.errorIcon}>{isDailyLimit ? '⏳' : '⚠️'}</Text>
          <Text style={s.loadingTitle}>{isDailyLimit ? 'Daily limit reached' : 'Analysis failed'}</Text>
          <Text style={s.loadingSub}>{errorMsg}</Text>
          {isDailyLimit ? (
            <TouchableOpacity
              style={s.retryBtn}
              onPress={() => navigation.navigate('MainTabs', { screen: 'Premium' })}
            >
              <Text style={s.retryBtnText}>Upgrade to Premium</Text>
            </TouchableOpacity>
          ) : (
            <TouchableOpacity style={s.retryBtn} onPress={runAnalysis}>
              <Text style={s.retryBtnText}>Try again</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity style={s.secondaryBtn} onPress={() => navigation.popToTop()}>
            <Text style={s.secondaryBtnText}>Back to home</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  // ── Results ───────────────────────────────────────────────────────────────
  const top = result.matches?.[0];
  const otherMatches = result.matches?.slice(1) ?? [];
  const score = top?.overall_score ?? top?.similarity ?? 0;
  const phases = top?.phases;

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        <Text style={s.header}>Your Results</Text>
        <Text style={s.headerSub}>{shotType?.charAt(0).toUpperCase() + shotType?.slice(1)}</Text>

        {top ? (
          <>
            {/* Score */}
            <View style={s.scoreCard}>
              <Text style={[s.scoreNum, { color: scoreColor(score) }]}>{score}</Text>
              <Text style={s.scoreOutOf}>/ 100</Text>
              <View style={s.scoreTrack}>
                <View style={[s.scoreFill, { width: `${score}%`, backgroundColor: scoreColor(score) }]} />
              </View>
              <Text style={s.matchedTo}>Matched to {formatProId(top.pro_id)}</Text>
            </View>

            {/* Save-to-history status */}
            {saveStatus === 'saved' && (
              <View style={s.saveBanner}>
                <Text style={s.saveBannerText}>✓ Saved to your history</Text>
              </View>
            )}
            {saveStatus === 'guest' && (
              <TouchableOpacity style={s.saveBannerAction} onPress={() => navigation.navigate('Login')}>
                <Text style={s.saveBannerActionText}>Log in to save this result →</Text>
              </TouchableOpacity>
            )}
            {saveStatus === 'limit' && (
              <TouchableOpacity
                style={s.saveBannerAction}
                onPress={() => navigation.navigate('MainTabs', { screen: 'Premium' })}
              >
                <Text style={s.saveBannerActionText}>Free plan limit reached (3/3) — upgrade to save unlimited →</Text>
              </TouchableOpacity>
            )}

            {/* Angle info */}
            <View style={s.angleRow}>
              <View style={s.angleCard}>
                <Text style={s.angleLabel}>Your angle</Text>
                <Text style={s.angleValue}>{result.angle_label ?? '—'}</Text>
                {result.user_angle != null && (
                  <Text style={s.angleSub}>{result.user_angle}°</Text>
                )}
              </View>
              <View style={s.angleCard}>
                <Text style={s.angleLabel}>Pro's angle</Text>
                <Text style={s.angleValue}>{top.pro_angle != null ? `${top.pro_angle}°` : '—'}</Text>
              </View>
            </View>

            {/* Phase breakdown */}
            {phases && (
              <>
                <Text style={s.sectionTitle}>Phase Breakdown</Text>
                {PHASE_ORDER.map((key) => {
                  const phase = phases[key];
                  if (!phase) return null;
                  const pScore = phase.score;
                  return (
                    <View key={key} style={s.phaseCard}>
                      <View style={s.phaseHeader}>
                        <Text style={s.phaseName}>{PHASE_LABELS[key]}</Text>
                        <Text style={[s.phaseScore, { color: phaseColor(pScore) }]}>
                          {pScore != null ? `${pScore}/25` : '—'}
                        </Text>
                      </View>
                      <View style={s.scoreTrack}>
                        <View
                          style={[
                            s.scoreFill,
                            { width: `${((pScore ?? 0) / 25) * 100}%`, backgroundColor: phaseColor(pScore) },
                          ]}
                        />
                      </View>
                      {key === 'body_rotation' && phase.has_racket_data === false && (
                        <Text style={s.phaseNote}>Racket not clearly visible — scored on body rotation only.</Text>
                      )}
                      {phase.tips?.[0] && <Text style={s.phaseTip}>{phase.tips[0]}</Text>}
                    </View>
                  );
                })}
              </>
            )}

            {/* Coaching tips */}
            <Text style={s.sectionTitle}>Coaching tips</Text>
            {top.tips?.map((tip, i) => (
              <View key={i} style={s.tipCard}>
                <Text style={s.tipIcon}>💡</Text>
                <Text style={s.tipText}>{tip}</Text>
              </View>
            ))}

            {/* Other matches */}
            {otherMatches.length > 0 && (
              <>
                <Text style={s.sectionTitle}>Other close matches</Text>
                {otherMatches.map((m) => (
                  <View key={m.pro_id} style={s.otherCard}>
                    <Text style={s.otherName}>{formatProId(m.pro_id)}</Text>
                    <Text style={[s.otherScore, { color: scoreColor(m.similarity) }]}>{m.similarity}/100</Text>
                  </View>
                ))}
              </>
            )}
          </>
        ) : (
          <Text style={s.loadingSub}>No matches found for this swing.</Text>
        )}

        <TouchableOpacity
          style={s.primaryBtn}
          onPress={() => navigation.navigate('MainTabs', { screen: 'History' })}
        >
          <Text style={s.primaryBtnText}>Try another shot</Text>
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
  errorIcon: { fontSize: 40 },
  retryBtn: { backgroundColor: GREEN, borderRadius: 12, paddingVertical: 12, paddingHorizontal: 28, marginTop: 24 },
  retryBtnText: { color: '#000', fontSize: 15, fontWeight: '700' },

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
  matchedTo: { color: MUTED, fontSize: 13, marginTop: 14 },

  saveBanner: {
    backgroundColor: '#0f2a1a', borderWidth: 1, borderColor: '#1e4a2e',
    borderRadius: 12, padding: 12, marginBottom: 16, alignItems: 'center',
  },
  saveBannerText: { color: GREEN, fontSize: 13, fontWeight: '600' },
  saveBannerAction: {
    backgroundColor: '#241a0d', borderWidth: 1, borderColor: '#4a3a1a',
    borderRadius: 12, padding: 12, marginBottom: 16, alignItems: 'center',
  },
  saveBannerActionText: { color: YELLOW, fontSize: 13, fontWeight: '600', textAlign: 'center' },

  angleRow: { flexDirection: 'row', gap: 12, marginBottom: 24 },
  angleCard: {
    flex: 1, backgroundColor: CARD, borderWidth: 1, borderColor: BORDER,
    borderRadius: 14, padding: 16, alignItems: 'center',
  },
  angleLabel: { color: MUTED, fontSize: 12 },
  angleValue: { color: TEXT, fontSize: 17, fontWeight: '700', marginTop: 4 },
  angleSub: { color: MUTED, fontSize: 12, marginTop: 2 },

  sectionTitle: { color: TEXT, fontSize: 16, fontWeight: '700', marginBottom: 12 },
  phaseCard: {
    backgroundColor: CARD, borderWidth: 1, borderColor: BORDER,
    borderRadius: 14, padding: 14, marginBottom: 10,
  },
  phaseHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  phaseName: { color: TEXT, fontSize: 14, fontWeight: '700' },
  phaseScore: { fontSize: 14, fontWeight: '700' },
  phaseTip: { color: '#ccc', fontSize: 13, lineHeight: 18, marginTop: 10 },
  phaseNote: { color: MUTED, fontSize: 12, marginTop: 8, fontStyle: 'italic' },
  tipCard: {
    flexDirection: 'row', gap: 10, backgroundColor: CARD, borderWidth: 1, borderColor: BORDER,
    borderRadius: 14, padding: 14, marginBottom: 10, alignItems: 'flex-start',
  },
  tipIcon: { fontSize: 16 },
  tipText: { color: '#ccc', fontSize: 14, lineHeight: 20, flex: 1 },

  otherCard: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    backgroundColor: CARD, borderWidth: 1, borderColor: BORDER,
    borderRadius: 12, padding: 14, marginBottom: 8,
  },
  otherName: { color: '#ccc', fontSize: 14 },
  otherScore: { fontSize: 14, fontWeight: '700' },

  primaryBtn: { backgroundColor: GREEN, borderRadius: 12, paddingVertical: 15, alignItems: 'center', marginTop: 16 },
  primaryBtnText: { color: '#000', fontSize: 15, fontWeight: '700' },
  secondaryBtn: {
    borderWidth: 1, borderColor: BORDER, borderRadius: 12,
    paddingVertical: 14, alignItems: 'center', marginTop: 10,
  },
  secondaryBtnText: { color: '#aaa', fontSize: 15, fontWeight: '600' },
});
