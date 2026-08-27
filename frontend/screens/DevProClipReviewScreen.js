import { useEffect, useRef, useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, SafeAreaView, ActivityIndicator } from 'react-native';
import PlatformVideo from '../components/PlatformVideo';
import { useAuth } from '../context/AuthContext';
import { API_BASE } from '../config/api';
import { playTapSound } from '../utils/sounds';
import { useWindowSize } from '../utils/responsive';
import RequireAdmin from '../components/RequireAdmin';
import { colors, fonts, radius } from '../theme';
import { SHOT_TYPES } from '../config/shotTypes';

// Free, no-Claude-cost manual data-quality review of the pro database
// itself -- direct report: a lot of clips are mismatched, some are
// slow-motion, some contain the tail end of one player's/swing's motion
// butted against the start of a different one. Not a teacher-student ML
// loop like the other Dev Page review tools -- this is data-quality
// curation, logged into clip_review_log.py's flat verdict log so a later
// one-off pass (same shape as filter_by_ball_visibility.py) can rebuild
// pro_database.json excluding flagged entries once enough review data exists.
const VERDICTS = [
  { value: 'ok', label: 'Looks good' },
  { value: 'mismatched', label: 'Mismatched footage' },
  { value: 'slow_motion', label: 'Slow-motion' },
  { value: 'wrong_boundary', label: 'Spans two swings/players' },
  { value: 'excluded', label: "Don't use this" },
];

// Cut mode needs the trimmed clip to still be long enough to be worth
// keeping -- same floor cut_pro_clip.py enforces server-side, checked here
// too so the Confirm button disables before a doomed request round-trips.
const MIN_CUT_SEC = 0.2;

// PlatformVideo never autoplays and has no native controls -- same
// tap-to-toggle pattern established across every other Dev Page review tool.
// forwardedRef + onProgress let the parent drive seeking and read
// position/duration for Cut mode's trim controls, without every other
// caller of this pattern elsewhere needing to change.
function TappableVideo({ uri, width, height, onProgress, videoRef: externalRef }) {
  const internalRef = useRef(null);
  const videoRef = externalRef || internalRef;
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
        onStatusUpdate={(status) => {
          setPlaying(!!status.isPlaying);
          onProgress?.(status);
        }}
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
  wrap: { backgroundColor: '#000' },
  playHint: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  playHintText: { color: 'rgba(255,255,255,0.75)', fontSize: 48 },
});

export default function DevProClipReviewScreen({ navigation }) {
  const { token } = useAuth();

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [candidates, setCandidates] = useState([]);
  const [index, setIndex] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [doneCount, setDoneCount] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);

  // Cut mode: cutStart/cutEnd are captured from the video's own playback
  // position (seconds), not typed in -- matches this screen's tap-driven
  // style rather than adding a numeric input. positionSec/durationSec track
  // the live video for rendering the trim bar and "Set start/end" captures.
  const [cutMode, setCutMode] = useState(false);
  const [cutStart, setCutStart] = useState(null);
  const [cutEnd, setCutEnd] = useState(null);
  const [positionSec, setPositionSec] = useState(0);
  const [durationSec, setDurationSec] = useState(0);
  const [cutError, setCutError] = useState(null);
  const videoRef = useRef(null);

  // Wrong-shot-type mode: same reveal-a-sub-panel pattern as cutMode above,
  // not a 4th top-level button, to keep the panel compact.
  const [shotTypeMode, setShotTypeMode] = useState(false);
  const [shotTypeError, setShotTypeError] = useState(null);

  // Custom clip names, keyed by candidate id, kept client-side only --
  // going back to re-visit a candidate should still show what was typed
  // without a re-fetch. Sent along with every verdict/cut submission.
  const [names, setNames] = useState({});

  // Full-screen video, floating overlays -- same pattern established
  // across the other single-video Dev Page tools this session.
  const { width: videoWidth, height: videoHeight } = useWindowSize();

  useEffect(() => {
    setLoading(true);
    setLoadError(false);
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/dev/pro-clip-review-candidates`, {
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

  // New clip -- any trim points picked for the previous one are meaningless now.
  useEffect(() => {
    setCutMode(false);
    setCutStart(null);
    setCutEnd(null);
    setCutError(null);
    setShotTypeMode(false);
    setShotTypeError(null);
  }, [index]);

  const submit = async (verdict) => {
    if (!current || submitting) return;
    playTapSound();
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/api/dev/pro-clip-review/label`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ id: current.id, verdict, name: names[current.id] || null }),
      });
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      setDoneCount((c) => c + 1);
      setIndex((i) => i + 1);
    } catch {
      // Leave the candidate in place so Jack can just try again -- same
      // recovery pattern as the other review screens' submit failure.
    } finally {
      setSubmitting(false);
    }
  };

  const submitCut = async () => {
    if (!current || submitting || cutStart == null || cutEnd == null) return;
    if (cutEnd - cutStart < MIN_CUT_SEC) {
      setCutError(`Trimmed clip must be at least ${MIN_CUT_SEC}s`);
      return;
    }
    playTapSound();
    setSubmitting(true);
    setCutError(null);
    try {
      const res = await fetch(`${API_BASE}/api/dev/pro-clip-review/cut`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ id: current.id, start_sec: cutStart, end_sec: cutEnd, name: names[current.id] || null }),
      });
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      setDoneCount((c) => c + 1);
      setIndex((i) => i + 1);
    } catch {
      setCutError("Couldn't cut this clip — try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const submitShotType = async (newShotType) => {
    if (!current || submitting) return;
    playTapSound();
    setSubmitting(true);
    setShotTypeError(null);
    try {
      const res = await fetch(`${API_BASE}/api/dev/pro-clip-review/correct-shot-type`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ id: current.id, new_shot_type: newShotType, name: names[current.id] || null }),
      });
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      setDoneCount((c) => c + 1);
      setIndex((i) => i + 1);
    } catch {
      setShotTypeError("Couldn't correct the shot type — try again.");
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
            <Text style={s.errorText}>Couldn't load pro clip review candidates — check your connection.</Text>
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
                ? 'No reviewable pro clips found.'
                : `You reviewed all ${candidates.length} clips this batch. Reopen to load more.`}
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
          <TappableVideo
            uri={`${API_BASE}${current.clip_url}`}
            width={videoWidth}
            height={videoHeight}
            videoRef={videoRef}
            onProgress={(status) => {
              if (status.positionMillis != null) setPositionSec(status.positionMillis / 1000);
              if (status.durationMillis != null) setDurationSec(status.durationMillis / 1000);
            }}
          />

          <View style={s.progressRow} pointerEvents="box-none">
            {index > 0 && (
              <TouchableOpacity
                style={s.prevBtn}
                onPress={() => { playTapSound(); setIndex((i) => Math.max(0, i - 1)); }}
                disabled={submitting}
              >
                <Text style={s.prevBtnText}>‹ Previous</Text>
              </TouchableOpacity>
            )}
            <Text style={s.progressText}>Clip {index + 1} of {candidates.length}</Text>
            <Text style={s.progressSub}>
              {current.id} · {current.shot_type}
              {current.camera_angle != null ? ` · ${current.camera_angle}°` : ''}
            </Text>
            <TextInput
              style={s.nameInput}
              value={names[current.id] || ''}
              onChangeText={(text) => setNames((n) => ({ ...n, [current.id]: text }))}
              placeholder="Name this clip (optional)"
              placeholderTextColor="rgba(255,255,255,0.4)"
            />
          </View>

          {cutMode ? (
            <View style={s.verdictPanel}>
              <View style={s.trimBar}>
                {durationSec > 0 && cutStart != null && (
                  <View style={[s.trimRange, {
                    left: `${(cutStart / durationSec) * 100}%`,
                    width: `${(((cutEnd ?? durationSec) - cutStart) / durationSec) * 100}%`,
                  }]} />
                )}
                {durationSec > 0 && (
                  <View style={[s.trimPlayhead, { left: `${(positionSec / durationSec) * 100}%` }]} />
                )}
              </View>
              <Text style={s.trimTimeText}>
                {positionSec.toFixed(2)}s / {durationSec.toFixed(2)}s
                {'  ·  '}start {cutStart != null ? `${cutStart.toFixed(2)}s` : '—'}
                {'  '}end {cutEnd != null ? `${cutEnd.toFixed(2)}s` : '—'}
              </Text>
              {cutError && <Text style={s.trimErrorText}>{cutError}</Text>}

              <View style={s.trimBtnRow}>
                <TouchableOpacity style={s.trimSetBtn} onPress={() => { setCutStart(positionSec); setCutError(null); }} disabled={submitting}>
                  <Text style={s.verdictBtnText}>Set start</Text>
                </TouchableOpacity>
                <TouchableOpacity style={s.trimSetBtn} onPress={() => { setCutEnd(positionSec); setCutError(null); }} disabled={submitting}>
                  <Text style={s.verdictBtnText}>Set end</Text>
                </TouchableOpacity>
              </View>

              <View style={s.trimBtnRow}>
                <TouchableOpacity
                  style={s.trimCancelBtn}
                  onPress={() => { setCutMode(false); setCutStart(null); setCutEnd(null); setCutError(null); }}
                  disabled={submitting}
                >
                  <Text style={s.verdictBtnText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.trimConfirmBtn, (cutStart == null || cutEnd == null) && s.trimBtnDisabled]}
                  onPress={submitCut}
                  disabled={submitting || cutStart == null || cutEnd == null}
                >
                  <Text style={s.verdictBtnText}>Confirm cut</Text>
                </TouchableOpacity>
              </View>
            </View>
          ) : shotTypeMode ? (
            <View style={s.verdictPanel}>
              <Text style={s.doneCountText}>Currently labeled {current.shot_type}. What should it be?</Text>
              {shotTypeError && <Text style={s.trimErrorText}>{shotTypeError}</Text>}
              <View style={s.verdictBtnRow}>
                {SHOT_TYPES.filter((st) => st !== current.shot_type).map((st) => (
                  <TouchableOpacity
                    key={st}
                    style={[s.verdictBtn, s.verdictBtnHalf]}
                    onPress={() => submitShotType(st)}
                    disabled={submitting}
                  >
                    <Text style={s.verdictBtnText}>{st.charAt(0).toUpperCase() + st.slice(1)}</Text>
                  </TouchableOpacity>
                ))}
                <TouchableOpacity
                  style={[s.cutModeBtn, s.verdictBtnHalf]}
                  onPress={() => { setShotTypeMode(false); setShotTypeError(null); }}
                  disabled={submitting}
                >
                  <Text style={s.verdictBtnText}>Cancel</Text>
                </TouchableOpacity>
              </View>
            </View>
          ) : (
            <View style={s.verdictPanel}>
              <View style={s.verdictBtnRow}>
                {VERDICTS.map((v) => (
                  <TouchableOpacity
                    key={v.value}
                    style={[s.verdictBtn, s.verdictBtnHalf, v.value === 'ok' && s.verdictBtnOk]}
                    onPress={() => submit(v.value)}
                    disabled={submitting}
                  >
                    <Text style={s.verdictBtnText}>{v.label}</Text>
                  </TouchableOpacity>
                ))}
                <TouchableOpacity
                  style={[s.cutModeBtn, s.verdictBtnHalf]}
                  onPress={() => setShotTypeMode(true)}
                  disabled={submitting}
                >
                  <Text style={s.verdictBtnText}>Wrong shot type?</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.cutModeBtn, s.verdictBtnHalf]}
                  onPress={() => { videoRef.current?.pauseAsync(); setCutMode(true); }}
                  disabled={submitting}
                >
                  <Text style={s.verdictBtnText}>Cut...</Text>
                </TouchableOpacity>
              </View>
              <Text style={s.doneCountText}>{doneCount} reviewed this session</Text>
            </View>
          )}
        </View>
      </SafeAreaView>
    </RequireAdmin>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#000' },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 24 },

  stage: { flex: 1, position: 'relative' },

  progressRow: {
    position: 'absolute', top: 0, left: 0, right: 0, alignItems: 'center',
    paddingTop: 14, paddingBottom: 10, backgroundColor: 'rgba(0,0,0,0.5)',
  },
  progressText: { color: '#fff', fontSize: 16, fontFamily: fonts.extrabold },
  progressSub: { color: 'rgba(255,255,255,0.75)', fontSize: 12.5, marginTop: 2, fontFamily: fonts.regular },

  prevBtn: { position: 'absolute', left: 14, top: 12, paddingVertical: 6, paddingHorizontal: 4 },
  prevBtnText: { color: colors.primary, fontSize: 14, fontFamily: fonts.bold },

  nameInput: {
    marginTop: 10, width: '80%', color: '#fff', fontSize: 13.5, fontFamily: fonts.regular,
    backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: radius.md,
    paddingHorizontal: 12, paddingVertical: 8, textAlign: 'center',
  },

  verdictPanel: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(20,20,20,0.9)', borderTopWidth: 1, borderColor: colors.border,
    borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    // ~50% of the original panel height (padding: spacing.xl (20)/28/gap 10).
    padding: 10, paddingBottom: 14, gap: 5,
  },
  verdictBtnRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  verdictBtn: {
    borderRadius: radius.lg, paddingVertical: 7, alignItems: 'center',
    backgroundColor: colors.coral,
  },
  // Two per row instead of one full-width button per row -- halves the
  // panel's height since it no longer stacks every verdict vertically.
  verdictBtnHalf: { width: '47%' },
  verdictBtnOk: { backgroundColor: colors.primary },
  verdictBtnText: { color: colors.white, fontSize: 14.5, fontFamily: fonts.extrabold },
  doneCountText: { color: 'rgba(255,255,255,0.7)', fontSize: 11.5, textAlign: 'center', marginTop: 2, fontFamily: fonts.regular },

  cutModeBtn: {
    borderRadius: radius.lg, paddingVertical: 7, alignItems: 'center',
    backgroundColor: 'transparent', borderWidth: 1, borderColor: colors.border,
  },

  trimBar: {
    height: 8, borderRadius: 4, backgroundColor: 'rgba(255,255,255,0.15)',
    position: 'relative', overflow: 'visible', marginBottom: 4,
  },
  trimRange: {
    position: 'absolute', top: 0, bottom: 0, backgroundColor: colors.primary,
    borderRadius: 4, minWidth: 2,
  },
  trimPlayhead: {
    position: 'absolute', top: -3, width: 2, height: 14,
    backgroundColor: '#fff', marginLeft: -1,
  },
  trimTimeText: { color: 'rgba(255,255,255,0.85)', fontSize: 12.5, fontFamily: fonts.regular, marginBottom: 4 },
  trimErrorText: { color: colors.coral, fontSize: 12.5, fontFamily: fonts.bold, marginBottom: 4 },
  trimBtnRow: { flexDirection: 'row', gap: 10 },
  trimSetBtn: {
    flex: 1, borderRadius: radius.lg, paddingVertical: 6, alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.12)',
  },
  trimCancelBtn: {
    flex: 1, borderRadius: radius.lg, paddingVertical: 6, alignItems: 'center',
    backgroundColor: 'transparent', borderWidth: 1, borderColor: colors.border,
  },
  trimConfirmBtn: {
    flex: 1, borderRadius: radius.lg, paddingVertical: 6, alignItems: 'center',
    backgroundColor: colors.primary,
  },
  trimBtnDisabled: { opacity: 0.4 },

  doneTitle: { color: colors.primary, fontSize: 22, fontFamily: fonts.extrabold, marginBottom: 10 },
  errorText: { color: colors.muted, fontSize: 13.5, textAlign: 'center', lineHeight: 19, fontFamily: fonts.regular },
  retryBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingHorizontal: 20, paddingVertical: 11, marginTop: 14 },
  retryBtnText: { color: colors.white, fontSize: 13.5, fontFamily: fonts.bold },
});
