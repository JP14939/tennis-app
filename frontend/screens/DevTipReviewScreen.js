import { useEffect, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView, ActivityIndicator } from 'react-native';
import PlatformVideo from '../components/PlatformVideo';
import { useAuth } from '../context/AuthContext';
import { API_BASE } from '../config/api';
import { playTapSound } from '../utils/sounds';
import { useWindowSize } from '../utils/responsive';
import RequireAdmin from '../components/RequireAdmin';
import { colors, fonts, radius, spacing } from '../theme';

// Free, no-Claude-cost manual review for coaching-tip selection -- the one
// pipeline stage that previously had no review tool at all (see
// TODO_MANUAL.md's pipeline backlog). Shows the swing next to the matched
// pro, which tip(s) actually got surfaced, and the FULL scored candidate
// list (tip_selector.score_issues() -- deviation/severity/phase for every
// issue considered, not just the ones picked) so Jack can judge the whole
// decision, not just rubber-stamp the final output. Submitting logs into
// tip_training_log.py with source='user_flag', same free substitute
// pattern log_manual_review.py already established for shot verification.
function severityColor(severity) {
  if (severity === 'severe') return colors.coral;
  if (severity === 'moderate') return colors.primary;
  return colors.muted;
}

// PlatformVideo never autoplays and has no native controls (see
// DevRallyBoundaryReviewScreen.js's ClipRow, which established this same
// tap-to-toggle pattern) -- without a ref + an explicit playAsync()/
// pauseAsync() call, the video just sits there inert. Missed this the
// first time this screen was built; every other video-playing screen in
// this app already drives playback imperatively like this.
function TappableVideo({ uri, width, height }) {
  const videoRef = useRef(null);
  const [playing, setPlaying] = useState(false);

  const toggle = () => {
    if (playing) {
      videoRef.current?.pauseAsync();
      setPlaying(false);
    } else {
      videoRef.current?.playAsync();
      setPlaying(true);
    }
  };

  return (
    <TouchableOpacity activeOpacity={1} style={[tv.wrap, { width, height }]} onPress={toggle}>
      <PlatformVideo
        ref={videoRef}
        uri={uri}
        width={width}
        height={height}
        onStatusUpdate={(status) => setPlaying(!!status.isPlaying)}
      />
      {!playing && (
        <View pointerEvents="none" style={StyleSheet.absoluteFill}>
          <View style={tv.playHint}>
            <Text style={tv.playHintText}>▶</Text>
          </View>
        </View>
      )}
    </TouchableOpacity>
  );
}
const tv = StyleSheet.create({
  wrap: { borderRadius: radius.sm, overflow: 'hidden', backgroundColor: '#000' },
  playHint: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  playHintText: { color: 'rgba(255,255,255,0.75)', fontSize: 32 },
});

export default function DevTipReviewScreen({ navigation }) {
  const { token } = useAuth();

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [candidates, setCandidates] = useState([]);
  const [index, setIndex] = useState(0);
  const [selectedIds, setSelectedIds] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [doneCount, setDoneCount] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);

  // Videos fill the top of the screen, full-screen style; the review
  // content (shown tips, scored issue list, submit) is real substantial
  // content someone needs to read and tap through, so it lives in a
  // scrollable bottom-sheet overlay rather than a single floating control
  // row -- sized to roughly half the screen, videos take the rest.
  const { width: windowWidth, height: windowHeight } = useWindowSize();
  const SHEET_HEIGHT = Math.max(260, Math.round(windowHeight * 0.5));
  const videoAreaHeight = Math.max(160, windowHeight - SHEET_HEIGHT);
  const videoWidth = Math.min((windowWidth - 24) / 2, videoAreaHeight / 1.4);
  const videoHeight = Math.round(videoWidth * 1.4);

  useEffect(() => {
    setLoading(true);
    setLoadError(false);
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/dev/tip-review-candidates`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error(`Request failed (${res.status})`);
        const data = await res.json();
        setCandidates(data.candidates ?? []);
        setIndex(0);
        setDoneCount(0);
      } catch {
        setLoadError(true);
      } finally {
        setLoading(false);
      }
    })();
  }, [token, reloadKey]);

  const current = candidates[index];

  // Pre-select whatever was actually shown -- a sensible starting point
  // Jack then adjusts (deselect if a shown tip wasn't actually warranted,
  // select others the real scored list surfaces that got missed) rather
  // than building his picks from nothing every time.
  useEffect(() => {
    if (current) setSelectedIds(current.shown_tip_ids ?? []);
  }, [current]);

  const toggleIssue = (issueId) => {
    playTapSound();
    setSelectedIds((prev) => (
      prev.includes(issueId) ? prev.filter((id) => id !== issueId) : [...prev, issueId]
    ));
  };

  const submit = async () => {
    if (!current || submitting) return;
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/api/dev/tip-review/label`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          analysis_id: current.analysis_id,
          shot_type: current.shot_type,
          deviation_features: current.candidate_issues,
          shown_tip_ids: current.shown_tip_ids,
          reviewer_pick_ids: selectedIds,
        }),
      });
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      setDoneCount((c) => c + 1);
      setIndex((i) => i + 1);
    } catch {
      // Leave the candidate in place so Jack can just try again -- same
      // recovery pattern as DevSwingReviewScreen.js's submit failure.
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <RequireAdmin navigation={navigation}>
        <SafeAreaView style={s.safe}>
          <View style={s.centerFill}><ActivityIndicator size="large" color={colors.primary} /></View>
        </SafeAreaView>
      </RequireAdmin>
    );
  }

  if (loadError) {
    return (
      <RequireAdmin navigation={navigation}>
        <SafeAreaView style={s.safe}>
          <View style={s.centerFill}>
            <Text style={s.errorText}>Couldn't load tip review candidates — check your connection.</Text>
            <TouchableOpacity style={s.retryBtn} onPress={() => setReloadKey((k) => k + 1)}>
              <Text style={s.retryBtnText}>Try again</Text>
            </TouchableOpacity>
          </View>
        </SafeAreaView>
      </RequireAdmin>
    );
  }

  if (!current) {
    return (
      <RequireAdmin navigation={navigation}>
        <SafeAreaView style={s.safe}>
          <View style={s.centerFill}>
            <Text style={s.doneTitle}>All done!</Text>
            <Text style={s.errorText}>
              {candidates.length === 0
                ? 'No reviewable analyses found -- saved swings need a matched pro and a still-present clip.'
                : `You reviewed all ${candidates.length} candidates. Nice work.`}
            </Text>
          </View>
        </SafeAreaView>
      </RequireAdmin>
    );
  }

  return (
    <RequireAdmin navigation={navigation}>
      <SafeAreaView style={s.safe}>
        <View style={s.stage}>
          <View style={[s.videoRow, { height: videoAreaHeight }]}>
            <View style={s.videoCol}>
              {current.user_clip_url && (
                <TappableVideo
                  uri={`${API_BASE}${current.user_clip_url}`}
                  width={videoWidth}
                  height={videoHeight}
                />
              )}
              <View style={s.videoLabelOverlay} pointerEvents="none">
                <Text style={s.videoLabel}>Your swing</Text>
              </View>
            </View>
            <View style={s.videoCol}>
              {current.pro_clip_url && (
                <TappableVideo
                  uri={`${API_BASE}${current.pro_clip_url}`}
                  width={videoWidth}
                  height={videoHeight}
                />
              )}
              <View style={s.videoLabelOverlay} pointerEvents="none">
                <Text style={s.videoLabel}>Matched pro</Text>
              </View>
            </View>
          </View>

          {/* Review content is real content to read/tap through, not a
              single control row -- lives in a scrollable bottom-sheet
              overlay over the videos rather than stacked below them. */}
          <View style={[s.sheet, { height: SHEET_HEIGHT }]}>
            <ScrollView contentContainerStyle={s.sheetScroll} showsVerticalScrollIndicator={false}>
              <View style={s.sheetHandle} />
              <View style={s.progressRow}>
                <Text style={s.progressText}>Analysis {index + 1} of {candidates.length}</Text>
                <Text style={s.progressSub}>#{current.analysis_id} · {current.shot_type}{current.pro_player_name ? ` vs ${current.pro_player_name}` : ''}</Text>
              </View>

              <View style={s.block}>
                <Text style={s.blockTitle}>Tip(s) actually shown</Text>
                {(current.shown_tips ?? []).length === 0 && (
                  <Text style={s.emptyNote}>None -- "Great technique" fallback was shown.</Text>
                )}
                {(current.shown_tips ?? []).map((tip) => (
                  <Text key={tip.id ?? tip.tip_text} style={s.shownTipText}>• {tip.tip_text}</Text>
                ))}
              </View>

              <View style={s.block}>
                <Text style={s.blockTitle}>Every issue that was scored</Text>
                <Text style={s.blockSub}>Tap to pick which ones SHOULD be flagged -- shown tips are pre-selected, adjust as needed.</Text>
                {(current.candidate_issues ?? []).map((issue) => {
                  const selected = selectedIds.includes(issue.issue_id);
                  return (
                    <TouchableOpacity
                      key={issue.issue_id}
                      style={[s.issueCard, selected && s.issueCardSelected]}
                      onPress={() => toggleIssue(issue.issue_id)}
                    >
                      <View style={s.issueHeader}>
                        <Text style={[s.issueDesc, selected && s.issueDescSelected]}>{issue.description}</Text>
                        <View style={[s.severityPill, { borderColor: severityColor(issue.severity) }]}>
                          <Text style={[s.severityPillText, { color: severityColor(issue.severity) }]}>{issue.severity}</Text>
                        </View>
                      </View>
                      <Text style={s.issueMeta}>{issue.phase} · {issue.landmark} · magnitude {issue.magnitude}</Text>
                    </TouchableOpacity>
                  );
                })}
                {(current.candidate_issues ?? []).length === 0 && (
                  <Text style={s.emptyNote}>No issues scored above the mild threshold for this swing.</Text>
                )}
              </View>

              <TouchableOpacity style={s.submitBtn} onPress={submit} disabled={submitting}>
                <Text style={s.submitBtnText}>{submitting ? 'Saving...' : 'Confirm and next →'}</Text>
              </TouchableOpacity>
              <Text style={s.doneCountText}>{doneCount} reviewed this session</Text>
            </ScrollView>
          </View>
        </View>
      </SafeAreaView>
    </RequireAdmin>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#000' },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 24 },

  stage: { flex: 1 },

  progressRow: { marginBottom: 14, alignItems: 'center' },
  progressText: { color: colors.ink, fontSize: 16, fontFamily: fonts.extrabold },
  progressSub: { color: colors.muted, fontSize: 12.5, marginTop: 2, fontFamily: fonts.regular },

  // Full-width, fills the space above the bottom sheet -- the two clips
  // sit side by side at essentially full screen size instead of a small
  // fixed thumbnail pair, with their labels floating on top of them.
  videoRow: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 8, backgroundColor: '#000' },
  videoCol: { alignItems: 'center', justifyContent: 'center', position: 'relative' },
  videoLabelOverlay: {
    position: 'absolute', top: 8, alignSelf: 'center',
    backgroundColor: 'rgba(0,0,0,0.6)', borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 3,
  },
  videoLabel: { color: '#fff', fontSize: 11, fontFamily: fonts.bold, textTransform: 'uppercase', letterSpacing: 0.3 },

  sheet: {
    backgroundColor: colors.bg, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    borderTopWidth: 1, borderColor: colors.border,
  },
  sheetScroll: { padding: spacing.xl, paddingTop: 10, paddingBottom: 40 },
  sheetHandle: {
    width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border,
    alignSelf: 'center', marginBottom: 12,
  },

  block: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.lg, padding: 16, marginBottom: 14,
  },
  blockTitle: { color: colors.ink, fontSize: 14.5, fontFamily: fonts.bold, marginBottom: 4 },
  blockSub: { color: colors.muted, fontSize: 12, lineHeight: 17, marginBottom: 12, fontFamily: fonts.regular },
  emptyNote: { color: colors.muted, fontSize: 12.5, fontStyle: 'italic', fontFamily: fonts.regular },
  shownTipText: { color: colors.ink, fontSize: 13, lineHeight: 19, marginBottom: 6, fontFamily: fonts.regular },

  issueCard: {
    borderWidth: 1.5, borderColor: colors.border, borderRadius: radius.md,
    padding: 12, marginBottom: 8, backgroundColor: colors.bg,
  },
  issueCardSelected: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  issueHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8, marginBottom: 4 },
  issueDesc: { flex: 1, color: colors.ink, fontSize: 13, lineHeight: 18, fontFamily: fonts.semibold },
  issueDescSelected: { color: colors.primary },
  severityPill: { borderWidth: 1, borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 2 },
  severityPillText: { fontSize: 10, fontFamily: fonts.bold, textTransform: 'uppercase' },
  issueMeta: { color: colors.muted, fontSize: 11, fontFamily: fonts.regular },

  submitBtn: { backgroundColor: colors.primary, borderRadius: radius.lg, paddingVertical: 16, alignItems: 'center', marginTop: 4 },
  submitBtnText: { color: colors.white, fontSize: 14, fontFamily: fonts.extrabold },
  doneCountText: { color: colors.muted, fontSize: 11.5, textAlign: 'center', marginTop: 10, fontFamily: fonts.regular },

  doneTitle: { color: colors.primary, fontSize: 22, fontFamily: fonts.extrabold, marginBottom: 10 },
  errorText: { color: colors.muted, fontSize: 13.5, textAlign: 'center', lineHeight: 19, fontFamily: fonts.regular },
  retryBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingHorizontal: 20, paddingVertical: 11, marginTop: 14 },
  retryBtnText: { color: colors.white, fontSize: 13.5, fontFamily: fonts.bold },
});
