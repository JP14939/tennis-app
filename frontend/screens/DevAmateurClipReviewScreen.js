import React, { useEffect, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ActivityIndicator, Platform } from 'react-native';
import PlatformVideo from '../components/PlatformVideo';
import { useAuth } from '../context/AuthContext';
import { API_BASE } from '../config/api';
import { useWindowSize } from '../utils/responsive';
import RequireAdmin from '../components/RequireAdmin';
import { colors, fonts, radius } from '../theme';
import { SHOT_TYPES } from '../config/shotTypes';

// Re-review of the amateur eval set's 248 shot-type labels (roadmap 1b: the
// technique-score rubric's backhand axes are capped at only 10 real backhand
// examples across the whole set -- Jack wants a by-eye pass to catch any
// real backhand mislabeled as 'skip'/'forehand'/'serve'). Same free,
// no-Claude-cost, one-at-a-time pattern as Pro Clip Review, but simpler --
// no cut/split/contact-time correction, just a label. See
// list_amateur_clip_review_candidates.py for the candidate order (non-
// backhand-labeled clips first, since that's where a missed backhand hides).
const LABEL_OPTIONS = [...SHOT_TYPES, 'skip'];

// Tap-to-toggle play, no native controls -- same pattern as every other
// single-video Dev Page review tool (DevProClipReviewScreen.js etc.).
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
    <TouchableOpacity activeOpacity={1} style={[s.videoWrap, { width, height }]} onPress={toggle}>
      <PlatformVideo
        ref={videoRef}
        uri={uri}
        width={width}
        height={height}
        onStatusUpdate={(status) => setPlaying(!!status.isPlaying)}
      />
      {!playing && (
        <View pointerEvents="none" style={StyleSheet.absoluteFill}>
          <View style={s.playHint}><Text style={s.playHintText}>▶</Text></View>
        </View>
      )}
    </TouchableOpacity>
  );
}

export default function DevAmateurClipReviewScreen({ navigation }) {
  const { token } = useAuth();
  const { width: videoWidth, height: videoHeight } = useWindowSize();

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [candidates, setCandidates] = useState([]);
  const [progress, setProgress] = useState(null);
  const [index, setIndex] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [changedCount, setChangedCount] = useState(0);
  const [reviewedCount, setReviewedCount] = useState(0);

  useEffect(() => {
    setLoading(true);
    setLoadError(false);
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/dev/amateur-clip-review-candidates`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error(`Request failed (${res.status})`);
        const data = await res.json();
        setCandidates(data.candidates ?? []);
        setProgress(data.progress ?? null);
        setReviewedCount(data.progress?.reviewed ?? 0);
        setIndex(0);
      } catch {
        setLoadError(true);
      } finally {
        setLoading(false);
      }
    })();
  }, [token]);

  const current = candidates[index];

  const goNext = () => {
    setSubmitError(null);
    setIndex((i) => Math.min(i + 1, candidates.length));
  };
  const goPrev = () => {
    setSubmitError(null);
    setIndex((i) => Math.max(i - 1, 0));
  };

  // Every tap round-trips, even one that just confirms the current label --
  // the backend marks the candidate reviewed either way (2026-09-11: this is
  // what makes it stop resurfacing after you leave and come back).
  const setLabel = async (newLabel) => {
    if (!current || submitting) return;
    const changed = newLabel !== (current.label ?? 'skip');
    setSubmitting(true);
    setSubmitError(null);
    try {
      const res = await fetch(`${API_BASE}/api/dev/amateur-clip-review/label`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ id: current.id, new_label: newLabel }),
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || `Request failed (${res.status})`);
      if (changed) setChangedCount((n) => n + 1);
      setReviewedCount((n) => n + 1);
      goNext();
    } catch (e) {
      setSubmitError(e.message || 'Failed to save label');
    } finally {
      setSubmitting(false);
    }
  };

  // Web-only keyboard shortcut: "d" = Done (same action as the "✓ Done"
  // button). RN has no cross-platform keydown API, and this screen only
  // runs on the Dev Page, which is web-first for Jack's review sessions.
  useEffect(() => {
    if (Platform.OS !== 'web' || !current) return undefined;
    const onKeyDown = (e) => {
      if (e.key !== 'd' && e.key !== 'D') return;
      if (submitting) return;
      const target = e.target;
      const typing = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA');
      if (typing) return;
      e.preventDefault();
      setLabel(current.label ?? 'skip');
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [current, submitting]);

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
            <Text style={s.errorText}>Couldn't load amateur clip review candidates.</Text>
            <TouchableOpacity style={s.retryBtn} onPress={() => navigation.replace('DevAmateurClipReview')}>
              <Text style={s.retryBtnText}>Retry</Text>
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
            <Text style={s.doneHeadline}>All caught up</Text>
            <Text style={s.doneCountText}>
              {reviewedCount} / {progress?.total ?? reviewedCount} reviewed overall
            </Text>
            {progress && (
              <Text style={s.doneCountText}>
                By label: {Object.entries(progress.by_label || {}).map(([k, v]) => `${k || 'null'} ${v}`).join(' · ')}
              </Text>
            )}
            <Text style={s.doneCountText}>{changedCount} relabeled this session</Text>
            <Text style={s.doneCountText}>Come back later -- reviewed clips won't show up again.</Text>
            {index > 0 && (
              <TouchableOpacity style={s.retryBtn} onPress={goPrev}>
                <Text style={s.retryBtnText}>◀ Back through the list</Text>
              </TouchableOpacity>
            )}
          </View>
        </SafeAreaView>
      </RequireAdmin>
    );
  }

  const videoAreaHeight = videoHeight - (Platform.OS === 'web' ? 0 : 0);

  return (
    <RequireAdmin navigation={navigation}>
      <SafeAreaView style={s.safe}>
        <View style={s.stage}>
          <TappableVideo uri={`${API_BASE}${current.clip_url}`} width={videoWidth} height={videoAreaHeight} />

          <View style={s.progressRow}>
            <Text style={s.progressText}>{reviewedCount} / {progress?.total ?? '?'} reviewed</Text>
            <Text style={s.progressSub}>{index + 1} / {candidates.length} left in this queue · {current.video_id} swing {current.swing_id}</Text>
            {current.source === 'raw_ingest' && (
              <Text style={s.progressSub}>
                unverified auto-classifier guess
                {current.low_confidence ? ' · low confidence' : ''}
                {current.shot_scores ? ` · scores ${Object.entries(current.shot_scores).map(([k, v]) => `${k} ${v}`).join(', ')}` : ''}
              </Text>
            )}
          </View>

          <TouchableOpacity style={s.prevBtn} onPress={goPrev} disabled={index === 0}>
            <Text style={[s.prevBtnText, index === 0 && s.prevBtnTextDisabled]}>◀ Back</Text>
          </TouchableOpacity>

          <View style={s.verdictPanel}>
            <Text style={s.doneCountText}>
              Currently labeled {current.label ?? '(none)'}. What should it be?
            </Text>
            {submitError && <Text style={s.errorTextSmall}>{submitError}</Text>}

            {/* Explicit "already correct" action -- clearer than expecting a
                tap on the dimmed current-label pill below to register as a
                confirm. Same request either way (setLabel handles both). */}
            <TouchableOpacity
              style={[s.doneBtn, submitting && s.verdictBtnDisabled]}
              disabled={submitting}
              onPress={() => setLabel(current.label ?? 'skip')}
            >
              <Text style={s.doneBtnText}>✓ Done — this one's correct{Platform.OS === 'web' ? '  (D)' : ''}</Text>
            </TouchableOpacity>

            <View style={s.verdictBtnRow}>
              {LABEL_OPTIONS.map((lbl) => (
                <TouchableOpacity
                  key={lbl}
                  style={[
                    s.verdictBtn,
                    s.verdictBtnHalf,
                    lbl === current.label && s.verdictBtnCurrent,
                    submitting && s.verdictBtnDisabled,
                  ]}
                  disabled={submitting}
                  onPress={() => setLabel(lbl)}
                >
                  <Text style={s.verdictBtnText}>{lbl}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <Text style={s.doneCountText}>{changedCount} relabeled this session</Text>
          </View>
        </View>
      </SafeAreaView>
    </RequireAdmin>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#000' },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 24 },
  stage: { flex: 1, position: 'relative' },
  videoWrap: { backgroundColor: '#000' },
  playHint: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  playHintText: { color: 'rgba(255,255,255,0.75)', fontSize: 48 },

  progressRow: {
    position: 'absolute', top: 0, left: 0, right: 0, alignItems: 'center',
    paddingTop: 14, paddingBottom: 10, backgroundColor: 'rgba(0,0,0,0.5)',
  },
  progressText: { color: '#fff', fontSize: 16, fontFamily: fonts.semibold },
  progressSub: { color: 'rgba(255,255,255,0.75)', fontSize: 12.5, marginTop: 2, fontFamily: fonts.regular },

  prevBtn: { position: 'absolute', left: 14, top: 12, paddingVertical: 6, paddingHorizontal: 4 },
  prevBtnText: { color: colors.primary, fontSize: 14, fontFamily: fonts.semibold },
  prevBtnTextDisabled: { color: 'rgba(255,255,255,0.3)' },

  verdictPanel: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(20,20,20,0.9)', borderTopWidth: 1, borderColor: colors.border,
    borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    padding: 12, paddingBottom: 16, gap: 6,
  },
  doneBtn: {
    borderRadius: radius.lg, paddingVertical: 12, alignItems: 'center',
    backgroundColor: colors.primary, marginTop: 6,
  },
  doneBtnText: { color: '#fff', fontSize: 15.5, fontFamily: fonts.semibold },
  verdictBtnRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 },
  verdictBtn: {
    borderRadius: radius.lg, paddingVertical: 10, alignItems: 'center',
    backgroundColor: colors.primary,
  },
  verdictBtnHalf: { width: '47%' },
  verdictBtnCurrent: { opacity: 0.4 },
  verdictBtnDisabled: { opacity: 0.5 },
  verdictBtnText: { color: '#fff', fontSize: 14.5, fontFamily: fonts.semibold, textTransform: 'capitalize' },
  doneCountText: { color: 'rgba(255,255,255,0.7)', fontSize: 11.5, textAlign: 'center', marginTop: 2, fontFamily: fonts.regular },
  doneHeadline: { color: '#fff', fontSize: 18, fontFamily: fonts.semibold, textAlign: 'center', marginBottom: 8 },
  errorText: { color: '#fff', fontSize: 15, textAlign: 'center', fontFamily: fonts.regular, marginBottom: 12 },
  errorTextSmall: { color: colors.coral, fontSize: 12.5, textAlign: 'center', fontFamily: fonts.regular },
  retryBtn: { marginTop: 8, paddingVertical: 10, paddingHorizontal: 20, borderRadius: radius.lg, backgroundColor: colors.primary },
  retryBtnText: { color: '#fff', fontSize: 14, fontFamily: fonts.semibold },
});
