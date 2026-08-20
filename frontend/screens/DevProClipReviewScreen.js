import { useEffect, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ActivityIndicator } from 'react-native';
import PlatformVideo from '../components/PlatformVideo';
import { useAuth } from '../context/AuthContext';
import { API_BASE } from '../config/api';
import { playTapSound } from '../utils/sounds';
import { useWindowSize } from '../utils/responsive';
import RequireAdmin from '../components/RequireAdmin';
import { colors, fonts, radius, spacing } from '../theme';

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
];

// PlatformVideo never autoplays and has no native controls -- same
// tap-to-toggle pattern established across every other Dev Page review tool.
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

  const submit = async (verdict) => {
    if (!current || submitting) return;
    playTapSound();
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/api/dev/pro-clip-review/label`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ id: current.id, verdict }),
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
          />

          <View style={s.progressRow} pointerEvents="box-none">
            <Text style={s.progressText}>Clip {index + 1} of {candidates.length}</Text>
            <Text style={s.progressSub}>
              {current.id} · {current.shot_type}
              {current.camera_angle != null ? ` · ${current.camera_angle}°` : ''}
            </Text>
          </View>

          <View style={s.verdictPanel}>
            {VERDICTS.map((v) => (
              <TouchableOpacity
                key={v.value}
                style={[s.verdictBtn, v.value === 'ok' && s.verdictBtnOk]}
                onPress={() => submit(v.value)}
                disabled={submitting}
              >
                <Text style={s.verdictBtnText}>{v.label}</Text>
              </TouchableOpacity>
            ))}
            <Text style={s.doneCountText}>{doneCount} reviewed this session</Text>
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

  progressRow: {
    position: 'absolute', top: 0, left: 0, right: 0, alignItems: 'center',
    paddingTop: 14, paddingBottom: 10, backgroundColor: 'rgba(0,0,0,0.5)',
  },
  progressText: { color: '#fff', fontSize: 16, fontFamily: fonts.extrabold },
  progressSub: { color: 'rgba(255,255,255,0.75)', fontSize: 12.5, marginTop: 2, fontFamily: fonts.regular },

  verdictPanel: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(20,20,20,0.9)', borderTopWidth: 1, borderColor: colors.border,
    borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    padding: spacing.xl, paddingBottom: 28, gap: 10,
  },
  verdictBtn: {
    borderRadius: radius.lg, paddingVertical: 15, alignItems: 'center',
    backgroundColor: colors.coral,
  },
  verdictBtnOk: { backgroundColor: colors.primary },
  verdictBtnText: { color: colors.white, fontSize: 14.5, fontFamily: fonts.extrabold },
  doneCountText: { color: 'rgba(255,255,255,0.7)', fontSize: 11.5, textAlign: 'center', marginTop: 4, fontFamily: fonts.regular },

  doneTitle: { color: colors.primary, fontSize: 22, fontFamily: fonts.extrabold, marginBottom: 10 },
  errorText: { color: colors.muted, fontSize: 13.5, textAlign: 'center', lineHeight: 19, fontFamily: fonts.regular },
  retryBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingHorizontal: 20, paddingVertical: 11, marginTop: 14 },
  retryBtnText: { color: colors.white, fontSize: 13.5, fontFamily: fonts.bold },
});
