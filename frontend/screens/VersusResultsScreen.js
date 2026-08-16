import { useRef, useState, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView,
  ScrollView, ActivityIndicator, Platform, Modal,
} from 'react-native';
import { API_BASE } from '../config/api';
import { useAuth } from '../context/AuthContext';
import { colors, fonts, radius, spacing } from '../theme';
import { playTapSound } from '../utils/sounds';
import CourtBackground from '../components/CourtBackground';
import ResultShareCard from '../components/ResultShareCard';
import { captureAndShare } from '../utils/shareCard';
import { BackChevronIcon, ShareIcon } from '../components/icons';
import ScoreCard from '../components/ScoreCard';
import AngleRow from '../components/AngleRow';
import PhaseBreakdown, { PHASE_LABELS, PHASE_ORDER, phaseColor } from '../components/PhaseBreakdown';
import TipsSection from '../components/TipsSection';

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
  const { token } = useAuth();

  const [status, setStatus] = useState('loading'); // loading | error | done
  const [errorMsg, setErrorMsg] = useState('');
  const [result, setResult] = useState(null);
  const shareCardRef = useRef(null);
  const [shareModalVisible, setShareModalVisible] = useState(false);
  // Bumped every time the share popup opens so ResultShareCard/ScoreRing
  // remount and the fill-up animation replays instead of only running once.
  const [shareModalKey, setShareModalKey] = useState(0);

  const runComparison = async () => {
    setStatus('loading');
    setErrorMsg('');
    try {
      const formData = await buildCompareFormData(reference, yours, shotType);
      const response = await fetch(`${API_BASE}/api/compare-videos`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
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

  // ── Loading ───────────────────────────────────────────────────────────────
  if (status === 'loading') {
    return (
      <SafeAreaView style={s.safe}>
        <CourtBackground />
        <View style={s.centerFill}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={s.loadingTitle}>Comparing your swing...</Text>
          <Text style={s.loadingSub}>Analysing both videos frame by frame</Text>
        </View>
      </SafeAreaView>
    );
  }

  // ── Error ─────────────────────────────────────────────────────────────────
  if (status === 'error') {
    return (
      <SafeAreaView style={s.safe}>
        <CourtBackground />
        <View style={s.centerFill}>
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

  // ── Results ───────────────────────────────────────────────────────────────
  const score = result.overall_score ?? result.similarity ?? 0;
  const phases = result.phases;

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
            <Text style={s.header}>Comparison results</Text>
            <Text style={s.headerSub}>{shotType?.charAt(0).toUpperCase() + shotType?.slice(1)}</Text>
          </View>
          {Platform.OS !== 'web' && (
            <TouchableOpacity
              style={s.shareBtn}
              onPress={() => { setShareModalKey((k) => k + 1); setShareModalVisible(true); }}
            >
              <ShareIcon size={17} color={colors.ink} />
            </TouchableOpacity>
          )}
        </View>

        <ScoreCard score={score} caption="Matched to the reference video" />

        {result.reference_clip_url && result.your_clip_url && (
          <TouchableOpacity
            style={s.compareBtn}
            onPress={() => navigation.navigate('SyncCompare', {
              videoAUrl: `${API_BASE}${result.reference_clip_url}`,
              videoBUrl: `${API_BASE}${result.your_clip_url}`,
              contactASec: result.reference_contact_time_sec ?? 0,
              contactBSec: result.your_contact_time_sec ?? 0,
              overlayA: result.reference_overlay_trajectory ?? null,
              overlayB: result.your_overlay_trajectory ?? null,
              labelA: 'Reference',
              labelB: 'You',
              phaseMarkers: result.phase_markers ?? undefined,
            })}
          >
            <Text style={s.compareBtnText}>Compare side-by-side →</Text>
          </TouchableOpacity>
        )}

        <AngleRow
          leftLabel="Your angle"
          leftValue={result.your_angle_label ?? '—'}
          leftSub={result.your_angle != null ? `${result.your_angle}°` : null}
          rightLabel="Reference angle"
          rightValue={result.reference_angle_label ?? '—'}
          rightSub={result.reference_angle != null ? `${result.reference_angle}°` : null}
        />

        {result.angle_mismatch_warning && (
          <View style={s.warnCard}>
            <Text style={s.warnText}>⚠ These videos were filmed from noticeably different angles — the score may be less reliable than usual.</Text>
          </View>
        )}

        <PhaseBreakdown phases={phases} />

        {result.tips?.length > 0 && <TipsSection tips={result.tips} />}

        <TouchableOpacity style={s.primaryBtn} onPress={() => { playTapSound(); navigation.navigate('VersusPick'); }}>
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

      <Modal
        visible={shareModalVisible}
        animationType="fade"
        transparent
        onRequestClose={() => setShareModalVisible(false)}
      >
        <View style={s.shareModalBackdrop}>
          <View style={s.shareModalCard}>
            <View style={s.shareModalHeader}>
              <Text style={s.shareModalTitle}>Share your result</Text>
              <TouchableOpacity onPress={() => setShareModalVisible(false)} hitSlop={10}>
                <Text style={s.shareModalClose}>✕</Text>
              </TouchableOpacity>
            </View>

            <ScrollView contentContainerStyle={s.shareModalScroll} showsVerticalScrollIndicator={false}>
              <View style={s.shareModalPreviewWrap}>
                <ResultShareCard
                  key={shareModalKey}
                  score={score}
                  shotType={shotType}
                  caption="Compared to your reference video"
                  animate
                />
              </View>

              {phases && (
                <View style={s.shareModalBreakdown}>
                  <Text style={s.shareModalBreakdownTitle}>Swing breakdown</Text>
                  {PHASE_ORDER.map((key) => {
                    const phase = phases[key];
                    if (!phase) return null;
                    const pScore = phase.score;
                    return (
                      <View key={key} style={s.shareModalPhaseRow}>
                        <View style={s.shareModalPhaseHead}>
                          <Text style={s.shareModalPhaseName}>{PHASE_LABELS[key]}</Text>
                          <Text style={[s.shareModalPhaseScore, { color: phaseColor(pScore) }]}>
                            {pScore ?? '—'}/25
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
                      </View>
                    );
                  })}
                </View>
              )}
            </ScrollView>

            <View style={s.shareModalFooter}>
              <TouchableOpacity
                style={[s.secondaryBtn, s.shareModalFooterBtn]}
                onPress={() => setShareModalVisible(false)}
              >
                <Text style={s.secondaryBtnText}>Close</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[s.primaryBtn, s.shareModalFooterBtn]}
                onPress={async () => {
                  await captureAndShare(shareCardRef, 'Share your RallyMax comparison');
                  setShareModalVisible(false);
                }}
              >
                <Text style={s.primaryBtnText}>Share image</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
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

  compareBtn: {
    backgroundColor: colors.surface, borderRadius: radius.pill,
    paddingVertical: 13, alignItems: 'center', marginBottom: 14,
  },
  compareBtnText: { color: colors.primary, fontSize: 13.5, fontFamily: fonts.bold },

  warnCard: {
    backgroundColor: colors.amberBg, borderRadius: radius.sm, padding: 14, marginBottom: 20,
  },
  warnText: { color: colors.amberText, fontSize: 12, lineHeight: 18, fontFamily: fonts.regular },

  phaseTrack: { height: 5, backgroundColor: colors.border, borderRadius: 3, overflow: 'hidden' },
  phaseFill: { height: 5, borderRadius: 3 },

  primaryBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingVertical: 15, alignItems: 'center', marginTop: 16 },
  primaryBtnText: { color: colors.white, fontSize: 14.5, fontFamily: fonts.bold },
  secondaryBtn: {
    backgroundColor: colors.surface, borderRadius: radius.pill,
    paddingVertical: 14, alignItems: 'center', marginTop: 10,
  },
  secondaryBtnText: { color: colors.mutedDark, fontSize: 14.5, fontFamily: fonts.bold },

  shareModalBackdrop: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.55)',
    alignItems: 'center', justifyContent: 'center', padding: spacing.xl,
  },
  shareModalCard: {
    width: '100%', maxWidth: 400, maxHeight: '85%',
    backgroundColor: colors.bg, borderRadius: radius.xxl, padding: spacing.lg,
  },
  shareModalHeader: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    marginBottom: spacing.md,
  },
  shareModalTitle: { color: colors.ink, fontSize: 17, fontFamily: fonts.bold },
  shareModalClose: { color: colors.muted, fontSize: 18, fontFamily: fonts.semibold, padding: 4 },
  shareModalScroll: { alignItems: 'center', paddingBottom: spacing.sm },
  shareModalPreviewWrap: { marginBottom: spacing.lg },
  shareModalBreakdown: { width: '100%' },
  shareModalBreakdownTitle: {
    color: colors.ink, fontSize: 15, fontFamily: fonts.bold, marginBottom: spacing.sm,
  },
  shareModalPhaseRow: { marginBottom: spacing.sm },
  shareModalPhaseHead: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5,
  },
  shareModalPhaseName: { color: colors.ink, fontSize: 13.5, fontFamily: fonts.semibold },
  shareModalPhaseScore: { fontSize: 13.5, fontFamily: fonts.bold },
  shareModalFooter: { flexDirection: 'row', gap: 10, marginTop: spacing.md },
  shareModalFooterBtn: { flex: 1, marginTop: 0 },
});
