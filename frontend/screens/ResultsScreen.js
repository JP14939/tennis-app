import React, { useEffect, useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView,
  ScrollView, ActivityIndicator, Platform, Animated,
} from 'react-native';
import { API_BASE } from '../config/api';
import { useAuth } from '../context/AuthContext';
import { saveHistory } from '../api/history';
import { colors, fonts, radius, spacing, scoreColor } from '../theme';
import CourtBackground from '../components/CourtBackground';
import ResultShareCard from '../components/ResultShareCard';
import { captureAndShare } from '../utils/shareCard';
import { BackChevronIcon, ChevronDownIcon, ShareIcon } from '../components/icons';

const PHASE_LABELS = {
  backswing: 'Backswing',
  contact: 'Contact',
  follow_through: 'Follow-through',
  body_rotation: 'Body Rotation',
};
const PHASE_ORDER = ['backswing', 'contact', 'follow_through', 'body_rotation'];

function phaseColor(score) {
  if (score == null) return colors.muted;
  if (score >= 18.75) return colors.primary;  // 75% of 25
  if (score >= 13.75) return colors.gold;      // 55% of 25
  return colors.coral;
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

// Measured-height collapsible -- RN has no CSS max-height:auto equivalent,
// so natural content height is measured once via onLayout then animated
// between 0 and that value.
function Collapsible({ open, children }) {
  const [contentHeight, setContentHeight] = useState(0);
  const heightAnim = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(heightAnim, {
      toValue: open ? contentHeight : 0,
      duration: 300,
      useNativeDriver: false,
    }).start();
  }, [open, contentHeight]);
  return (
    <Animated.View style={{ height: heightAnim, overflow: 'hidden' }}>
      <View onLayout={(e) => setContentHeight(e.nativeEvent.layout.height)}>
        {children}
      </View>
    </Animated.View>
  );
}

function useRotate(open) {
  const rotateAnim = useRef(new Animated.Value(open ? 1 : 0)).current;
  useEffect(() => {
    Animated.timing(rotateAnim, { toValue: open ? 1 : 0, duration: 250, useNativeDriver: true }).start();
  }, [open]);
  return rotateAnim.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '180deg'] });
}

function TipRow({ tip }) {
  const [open, setOpen] = useState(false);
  const rotate = useRotate(open);

  if (!tip.drill) {
    return (
      <View style={t.row}>
        <Text style={t.fixText}><Text style={t.fixLabel}>Fix: </Text>{tip.tip_text ?? tip}</Text>
      </View>
    );
  }

  return (
    <View style={t.rowWrap}>
      <TouchableOpacity style={t.row} onPress={() => setOpen(o => !o)} activeOpacity={0.85}>
        <Text style={t.fixText}><Text style={t.fixLabel}>Fix: </Text>{tip.tip_text}</Text>
        <Animated.View style={{ transform: [{ rotate }] }}>
          <ChevronDownIcon size={12} color={colors.mutedDark} />
        </Animated.View>
      </TouchableOpacity>
      <Collapsible open={open}>
        <View style={t.drillPanel}>
          <Text style={t.drillText}><Text style={t.drillLabel}>Drill — </Text>{tip.drill}</Text>
        </View>
      </Collapsible>
    </View>
  );
}
const t = StyleSheet.create({
  rowWrap: { backgroundColor: colors.surface, borderRadius: radius.md, overflow: 'hidden', marginBottom: 9 },
  row: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10,
    padding: 14,
  },
  fixText: { flex: 1, color: colors.ink, fontSize: 13, lineHeight: 19.5, fontFamily: fonts.regular },
  fixLabel: { fontFamily: fonts.bold },
  drillPanel: { backgroundColor: colors.primarySoft, padding: 14 },
  drillText: { color: colors.limeText, fontSize: 13, lineHeight: 19.5, fontFamily: fonts.regular },
  drillLabel: { fontFamily: fonts.bold },
});

function TipsSection({ tips }) {
  const [open, setOpen] = useState(false);
  const rotate = useRotate(open);

  return (
    <>
      <TouchableOpacity style={ts.toggle} onPress={() => setOpen(o => !o)} activeOpacity={0.85}>
        <Text style={ts.toggleText}>Tips & drills to fix</Text>
        <Animated.View style={{ transform: [{ rotate }] }}>
          <ChevronDownIcon size={14} color={colors.mutedDark} />
        </Animated.View>
      </TouchableOpacity>
      <Collapsible open={open}>
        <View style={ts.reveal}>
          {tips.map((tip, i) => <TipRow key={i} tip={tip} />)}
        </View>
      </Collapsible>
    </>
  );
}
const ts = StyleSheet.create({
  toggle: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: colors.surface, borderRadius: radius.md, padding: 15, marginBottom: 22,
  },
  toggleText: { color: colors.ink, fontSize: 14.5, fontFamily: fonts.bold },
  reveal: { marginTop: -12, paddingTop: 10 },
});

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
  const shareCardRef = useRef(null);

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
        <CourtBackground />
        <View style={s.centerFill}>
          <ActivityIndicator size="large" color={colors.primary} />
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
        <CourtBackground />
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
      <CourtBackground />
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        <TouchableOpacity style={s.backLink} onPress={() => navigation.goBack()}>
          <BackChevronIcon size={13} color={colors.muted} />
          <Text style={s.backLinkText}>Back</Text>
        </TouchableOpacity>

        <View style={s.headerRow}>
          <View>
            <Text style={s.header}>Your results</Text>
            <Text style={s.headerSub}>{shotType?.charAt(0).toUpperCase() + shotType?.slice(1)}</Text>
          </View>
          {top && Platform.OS !== 'web' && (
            <TouchableOpacity
              style={s.shareBtn}
              onPress={() => captureAndShare(shareCardRef, 'Share your TennisAI result')}
            >
              <ShareIcon size={17} color={colors.ink} />
            </TouchableOpacity>
          )}
        </View>

        {top ? (
          <>
            {/* Score */}
            <View style={s.scoreCard}>
              <View style={s.scoreTopRow}>
                <Text style={s.scoreNum}>{score}</Text>
                <Text style={s.scoreOutOf}>/ 100</Text>
              </View>
              <View style={s.scoreTrack}>
                <View style={[s.scoreFill, { width: `${score}%`, backgroundColor: colors.lime }]} />
              </View>
              <Text style={s.matchedTo}>Matched to {formatProId(top.pro_id)}</Text>
            </View>

            {top.pro_clip_url && result.user_clip_url && (
              <TouchableOpacity
                style={s.compareBtn}
                onPress={() => navigation.navigate('SyncCompare', {
                  videoAUrl: `${API_BASE}${top.pro_clip_url}`,
                  videoBUrl: `${API_BASE}${result.user_clip_url}`,
                  croppedAUrl: top.pro_clip_cropped_url ? `${API_BASE}${top.pro_clip_cropped_url}` : null,
                  croppedBUrl: result.user_clip_cropped_url ? `${API_BASE}${result.user_clip_cropped_url}` : null,
                  contactASec: top.pro_contact_time_sec ?? 0,
                  contactBSec: result.contact_time_sec ?? 0,
                  labelA: formatProId(top.pro_id),
                  labelB: 'You',
                })}
              >
                <Text style={s.compareBtnText}>Compare side-by-side →</Text>
              </TouchableOpacity>
            )}

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
                <Text style={s.sectionTitle}>Phase breakdown</Text>
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
                      <View style={s.phaseTrack}>
                        <View
                          style={[
                            s.phaseFill,
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
            {top.tips?.length > 0 && <TipsSection tips={top.tips} />}

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

      {top && (
        <View style={s.offscreen}>
          <ResultShareCard
            ref={shareCardRef}
            score={score}
            shotType={shotType}
            caption={`Matched to ${formatProId(top.pro_id)}`}
          />
        </View>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingTop: 60, paddingBottom: 48 },

  backLink: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 18, alignSelf: 'flex-start' },
  backLinkText: { color: colors.muted, fontSize: 13, fontFamily: fonts.semibold },

  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32 },
  loadingTitle: { color: colors.ink, fontSize: 18, fontFamily: fonts.bold, marginTop: 20, textAlign: 'center' },
  loadingSub: { color: colors.muted, fontSize: 14, marginTop: 8, textAlign: 'center', lineHeight: 20, fontFamily: fonts.regular },
  errorIcon: { fontSize: 40 },
  retryBtn: { backgroundColor: colors.primary, borderRadius: radius.md, paddingVertical: 12, paddingHorizontal: 28, marginTop: 24 },
  retryBtnText: { color: colors.white, fontSize: 15, fontFamily: fonts.bold },

  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  header: { color: colors.ink, fontSize: 30, fontFamily: fonts.serifItalic },
  headerSub: { color: colors.muted, fontSize: 14, marginTop: 2, marginBottom: 22, fontFamily: fonts.regular },
  shareBtn: {
    width: 38, height: 38, borderRadius: 19, backgroundColor: colors.surface,
    alignItems: 'center', justifyContent: 'center',
  },
  offscreen: { position: 'absolute', left: -9999, top: -9999 },

  scoreCard: {
    backgroundColor: colors.primary, borderRadius: radius.xxl,
    padding: 26, alignItems: 'center', marginBottom: 14,
  },
  scoreTopRow: { flexDirection: 'row', alignItems: 'baseline', gap: 4 },
  scoreNum: { fontSize: 56, fontFamily: fonts.serif, color: colors.white, lineHeight: 60 },
  scoreOutOf: { color: 'rgba(255,255,255,0.6)', fontSize: 15, fontFamily: fonts.regular },
  scoreTrack: { width: '100%', height: 6, backgroundColor: 'rgba(255,255,255,0.2)', borderRadius: 3, marginTop: 18, marginBottom: 14, overflow: 'hidden' },
  scoreFill: { height: 6, borderRadius: 3 },
  matchedTo: { color: 'rgba(255,255,255,0.75)', fontSize: 13, fontFamily: fonts.regular },

  compareBtn: {
    backgroundColor: colors.surface, borderRadius: radius.pill,
    paddingVertical: 13, alignItems: 'center', marginBottom: 14,
  },
  compareBtnText: { color: colors.primary, fontSize: 13.5, fontFamily: fonts.bold },

  saveBanner: {
    backgroundColor: colors.primarySoft,
    borderRadius: radius.sm, padding: 11, marginBottom: 22, alignItems: 'center',
  },
  saveBannerText: { color: colors.primary, fontSize: 12.5, fontFamily: fonts.bold },
  saveBannerAction: {
    backgroundColor: colors.amberBg,
    borderRadius: radius.sm, padding: 12, marginBottom: 22, alignItems: 'center',
  },
  saveBannerActionText: { color: colors.amberText, fontSize: 12.5, fontFamily: fonts.bold, textAlign: 'center' },

  angleRow: { flexDirection: 'row', gap: 10, marginBottom: 26 },
  angleCard: {
    flex: 1, backgroundColor: colors.surface,
    borderRadius: radius.md, padding: 15, alignItems: 'center',
  },
  angleLabel: { color: colors.muted, fontSize: 11.5, fontFamily: fonts.regular },
  angleValue: { color: colors.ink, fontSize: 16, fontFamily: fonts.extrabold, marginTop: 4 },
  angleSub: { color: colors.muted, fontSize: 11, marginTop: 2, fontFamily: fonts.regular },

  sectionTitle: { color: colors.ink, fontSize: 19, fontFamily: fonts.serif, marginBottom: 12 },
  phaseCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.md, padding: 14, marginBottom: 9,
  },
  phaseHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  phaseName: { color: colors.ink, fontSize: 14, fontFamily: fonts.bold },
  phaseScore: { fontSize: 14, fontFamily: fonts.bold },
  phaseTrack: { height: 5, backgroundColor: colors.border, borderRadius: 3, overflow: 'hidden' },
  phaseFill: { height: 5, borderRadius: 3 },
  phaseTip: { color: colors.mutedDark, fontSize: 12.5, lineHeight: 18, marginTop: 9, fontFamily: fonts.regular },
  phaseNote: { color: colors.muted, fontSize: 12, marginTop: 8, fontStyle: 'italic', fontFamily: fonts.regular },

  otherCard: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: radius.sm, padding: 14, marginBottom: 8,
  },
  otherName: { color: colors.mutedDark, fontSize: 13.5, fontFamily: fonts.regular },
  otherScore: { fontSize: 13.5, fontFamily: fonts.bold },

  primaryBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingVertical: 15, alignItems: 'center', marginTop: 16 },
  primaryBtnText: { color: colors.white, fontSize: 14.5, fontFamily: fonts.bold },
  secondaryBtn: {
    backgroundColor: colors.surface, borderRadius: radius.pill,
    paddingVertical: 14, alignItems: 'center', marginTop: 10,
  },
  secondaryBtnText: { color: colors.mutedDark, fontSize: 14.5, fontFamily: fonts.bold },
});
