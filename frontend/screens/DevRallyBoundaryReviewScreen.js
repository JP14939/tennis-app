import { useEffect, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView, ActivityIndicator } from 'react-native';
import Alert from '../utils/alert';
import { useIsFocused } from '@react-navigation/native';
import PlatformVideo from '../components/PlatformVideo';
import { useAuth } from '../context/AuthContext';
import { API_BASE } from '../config/api';
import { playTapSound } from '../utils/sounds';
import { useWindowWidth } from '../utils/responsive';
import RequireAdmin from '../components/RequireAdmin';
import { colors, fonts, radius, spacing } from '../theme';

// Dev-only: the full 8-button review tool, moved here wholesale from the
// user-facing HighlightReviewScreen.js -- a real user only ever answers the
// outcome question (who won); the boundary question is pure ML training
// data collection for tuning detect_rallies.py, and belongs here instead.
const TAG_OPTIONS = [
  { value: 'ace',                label: 'Ace' },
  { value: 'winner_this_side',   label: 'Winner (this side)' },
  { value: 'winner_other_side',  label: 'Winner (other side)' },
  { value: 'skip',               label: 'Not a rally' },
];

// Real ground truth for tuning detect_rallies.py's RALLY_GAP_SEC/
// detect_swings.py's THRESHOLD_PERCENTILE (see tune_rally_gap.py) plus, for
// 'started_too_late', a future pass over PRE_PAD_SEC (not swept by that
// script yet -- see its module comment). Optional: leaving it unset just
// means "didn't look closely," not "boundary is correct" -- only an
// explicit 'ok' counts as a positive signal.
const BOUNDARY_OPTIONS = [
  { value: 'ok',                label: 'Perfect' },
  { value: 'started_too_late',  label: 'Started too late' },
  { value: 'cut_off_early',     label: 'Cut off early' },
  { value: 'should_split',      label: 'Should be split' },
];

// 'started_too_late' and 'cut_off_early' are independent problems (a clip
// can be wrong on both ends at once) so both can be active together --
// everything else ('ok', 'should_split') is a single exclusive status that
// replaces whatever was selected before. Stored/sent as a comma-joined
// string in boundary_note (still a plain TEXT column, no schema change) --
// see tune_rally_gap.py's score_candidate() for the other place that
// deserializes this same format.
const INDEPENDENT_BOUNDARY_VALUES = ['started_too_late', 'cut_off_early'];

function toggleBoundary(current, value) {
  const set = new Set(current);
  if (INDEPENDENT_BOUNDARY_VALUES.includes(value)) {
    set.delete('ok');
    set.delete('should_split');
    if (set.has(value)) set.delete(value); else set.add(value);
  } else {
    // 'ok' / 'should_split' -- tapping the already-active exclusive option
    // clears it back to "undecided" instead of being stuck on forever.
    set.clear();
    if (!current.includes(value)) set.add(value);
  }
  return [...set];
}

function formatTime(sec) {
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

function ClipRow({ clip, value, onTag, boundaryValues, onBoundary, focused }) {
  const videoRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  // Every pending rally in the job renders as a row in one scrollable list
  // (unlike Swing Review's one-candidate-at-a-time flow), so there's no
  // single "next" clip to prefetch -- instead, the video itself is only
  // mounted once this row has actually been tapped. Mounting a
  // PlatformVideo starts it buffering immediately even without playing, so
  // a job with 30+ pending clips used to try loading 30+ videos at once the
  // moment the screen opened.
  const [loaded, setLoaded] = useState(false);
  const windowWidth = useWindowWidth();
  // Bigger than before within its card -- the tag/boundary controls now
  // overlay directly on top of the video instead of stacking below it, so
  // the video itself can claim the space those rows used to occupy.
  const videoWidth = Math.min(windowWidth - 32, 640);
  const videoHeight = Math.round(videoWidth * 0.62);

  // React Navigation keeps this whole screen mounted underneath when you
  // navigate to another job's review (or back to the job list) rather than
  // unmounting it -- without this, any clip already tapped open here kept
  // buffering/playing in the background while a different job's screen was
  // on top, competing for bandwidth with whatever the user was actually
  // looking at. `focused` (from the parent's useIsFocused()) tears the
  // video down whenever this screen isn't the visible one.
  const showVideo = loaded && focused;

  // The video unmounts on blur (showVideo above), so no further
  // onStatusUpdate calls arrive to correct `playing` -- reset it directly
  // so the play-hint overlay is right if/when this row scrolls back into a
  // focused screen instead of showing a stale "already playing" state.
  useEffect(() => {
    if (!focused) setPlaying(false);
  }, [focused]);

  const toggle = () => {
    if (!loaded) {
      setLoaded(true);
      return;
    }
    if (playing) {
      videoRef.current?.pauseAsync();
      setPlaying(false);
    } else {
      videoRef.current?.playAsync();
      setPlaying(true);
    }
  };

  return (
    <View style={r.card}>
      <View style={[r.videoWrap, { width: videoWidth, height: videoHeight }]}>
        <TouchableOpacity activeOpacity={1} style={StyleSheet.absoluteFill} onPress={toggle}>
          {showVideo && (
            <PlatformVideo
              ref={videoRef}
              uri={`${API_BASE}${clip.clip_url}`}
              width={videoWidth}
              height={videoHeight}
              onStatusUpdate={(status) => setPlaying(!!status.isPlaying)}
            />
          )}
          {!playing && (
            <View pointerEvents="none" style={StyleSheet.absoluteFill}>
              <View style={r.playHint}>
                <Text style={r.playHintText}>▶</Text>
              </View>
            </View>
          )}
        </TouchableOpacity>

        {/* Meta strip floats over the top of the video instead of sitting
            in its own row below it. */}
        <View style={r.metaOverlay} pointerEvents="none">
          <Text style={r.time}>{formatTime(clip.start_sec)}</Text>
          <Text style={r.duration}>{clip.duration_sec.toFixed(1)}s · {clip.swing_count} swings</Text>
        </View>

        {/* Tag/boundary controls float on top of the video's bottom edge
            (semi-transparent strip) instead of stacking below it -- same
            "controls overlay the video" principle as the other review
            screens, applied per-card here rather than per-viewport. */}
        <View style={r.controlsOverlay}>
          {boundaryValues.includes('cut_off_early') ? (
            <Text style={r.outcomeHiddenNote}>Outcome skipped — clip is cut off before the point ends, so there's nothing to judge here.</Text>
          ) : (
            <View style={r.tagRow}>
              {TAG_OPTIONS.map(opt => (
                <TouchableOpacity
                  key={opt.value}
                  style={[r.tagPill, value === opt.value && r.tagPillActive]}
                  onPress={() => onTag(opt.value)}
                >
                  <Text style={[r.tagLabel, value === opt.value && r.tagLabelActive]}>{opt.label}</Text>
                </TouchableOpacity>
              ))}
            </View>
          )}

          <Text style={r.boundaryLabel}>Are the start/end points right?</Text>
          <View style={r.tagRow}>
            {BOUNDARY_OPTIONS.map(opt => (
              <TouchableOpacity
                key={opt.value}
                style={[r.tagPill, boundaryValues.includes(opt.value) && r.boundaryPillActive]}
                onPress={() => onBoundary(opt.value)}
              >
                <Text style={[r.tagLabel, boundaryValues.includes(opt.value) && r.tagLabelActive]}>{opt.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      </View>
    </View>
  );
}
const r = StyleSheet.create({
  card: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.lg, padding: 8, marginBottom: 12,
  },
  videoWrap: { borderRadius: radius.sm, overflow: 'hidden', backgroundColor: '#000', position: 'relative' },
  playHint: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  playHintText: { color: 'rgba(255,255,255,0.75)', fontSize: 40 },

  // Floating over the top of the video rather than a row above it.
  metaOverlay: {
    position: 'absolute', top: 0, left: 0, right: 0,
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline',
    paddingHorizontal: 10, paddingVertical: 8, backgroundColor: 'rgba(0,0,0,0.45)',
  },
  time: { color: '#fff', fontSize: 15, fontFamily: fonts.bold },
  duration: { color: 'rgba(255,255,255,0.8)', fontSize: 12, fontFamily: fonts.regular },

  // Floating over the bottom of the video instead of stacked below it.
  controlsOverlay: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    backgroundColor: 'rgba(0,0,0,0.6)', paddingHorizontal: 10, paddingTop: 10, paddingBottom: 10,
  },
  tagRow: { flexDirection: 'row', gap: 6, marginBottom: 10 },
  tagPill: {
    flex: 1, borderWidth: 1, borderColor: 'rgba(255,255,255,0.3)', borderRadius: radius.sm,
    paddingVertical: 8, alignItems: 'center', gap: 2, backgroundColor: 'rgba(255,255,255,0.06)',
  },
  tagPillActive: { backgroundColor: colors.primarySoft, borderColor: colors.primary },
  boundaryPillActive: { backgroundColor: colors.lime, borderColor: colors.limeText },
  tagLabel: { color: 'rgba(255,255,255,0.85)', fontSize: 10, fontFamily: fonts.semibold },
  tagLabelActive: { color: colors.primary },
  boundaryLabel: { color: 'rgba(255,255,255,0.8)', fontSize: 11, fontFamily: fonts.semibold, marginBottom: 6 },
  outcomeHiddenNote: { color: 'rgba(255,255,255,0.8)', fontSize: 11.5, lineHeight: 16, fontStyle: 'italic', marginBottom: 12, fontFamily: fonts.regular },
  errorText: { color: colors.muted, fontSize: 13.5, textAlign: 'center', marginBottom: 14, paddingHorizontal: 24, fontFamily: fonts.regular },
  retryBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingHorizontal: 20, paddingVertical: 11 },
  retryBtnText: { color: colors.white, fontSize: 13.5, fontFamily: fonts.bold },
});

export default function DevRallyBoundaryReviewScreen({ route, navigation }) {
  const { jobId } = route.params ?? {};
  const { token } = useAuth();
  const isFocused = useIsFocused();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [rallies, setRallies] = useState([]);
  const [tags, setTags] = useState({});
  const [boundaryNotes, setBoundaryNotes] = useState({});
  const [saving, setSaving] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  // A clip is fully reviewed once it has a boundary note AND (either an
  // outcome tag, or its boundary is 'cut_off_early' -- the one case where
  // the outcome question is skipped entirely because the ending isn't in
  // frame, so no outcome tag will ever arrive for it).
  const isReviewed = (clip) => {
    const notes = (clip.boundary_note || '').split(',').filter(Boolean);
    if (notes.length === 0) return false;
    if (notes.includes('cut_off_early')) return true;
    return !!clip.outcome_tag;
  };

  useEffect(() => {
    setLoading(true);
    setLoadError(false);
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/highlights/jobs/${jobId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error(`Request failed (${res.status})`);
        const data = await res.json();
        // Already-fully-reviewed clips don't reappear -- otherwise every
        // reviewed clip resurfaced on every reload.
        const pending = (data.rallies ?? []).filter((clip) => !isReviewed(clip));
        setRallies(pending);
        const initialTags = {};
        const initialBoundaryNotes = {};
        for (const clip of pending) {
          if (clip.outcome_tag) initialTags[clip.id] = clip.outcome_tag;
          if (clip.boundary_note) initialBoundaryNotes[clip.id] = clip.boundary_note.split(',').filter(Boolean);
        }
        setTags(initialTags);
        setBoundaryNotes(initialBoundaryNotes);
      } catch {
        setLoadError(true);
      } finally {
        setLoading(false);
      }
    })();
  }, [jobId, token, reloadKey]);

  const setTag = (clipId, value) => setTags(prev => ({ ...prev, [clipId]: value }));
  const setBoundaryNote = (clipId, value) =>
    setBoundaryNotes(prev => ({ ...prev, [clipId]: toggleBoundary(prev[clipId] || [], value) }));

  const reviewedCount = new Set([
    ...Object.keys(tags).filter((id) => tags[id]),
    ...Object.keys(boundaryNotes).filter((id) => boundaryNotes[id]?.length > 0),
  ]).size;

  const save = async () => {
    setSaving(true);
    try {
      const clipIds = new Set([...Object.keys(tags), ...Object.keys(boundaryNotes)]);
      const results = await Promise.all(
        [...clipIds]
          .filter((clipId) => tags[clipId] || boundaryNotes[clipId]?.length > 0)
          .map(async (clipId) => {
            const value = tags[clipId];
            // Only include boundary_note when this clip's boxes were actually
            // touched this session -- omitting the key means "leave it
            // alone" on the backend. When touched but ending up empty (every
            // box unchecked), send an explicit '' rather than leaving the
            // key out: JSON.stringify drops undefined-valued keys, and an
            // omitted key can't be told apart from "no change intended".
            const body = {};
            if (Object.prototype.hasOwnProperty.call(boundaryNotes, clipId)) {
              body.boundary_note = boundaryNotes[clipId].length ? boundaryNotes[clipId].join(',') : '';
            }
            if (value) {
              body.outcome_tag = value;
              body.archived = value !== 'skip';
            }
            const res = await fetch(`${API_BASE}/api/highlights/rallies/${clipId}`, {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
              body: JSON.stringify(body),
            });
            return { clipId, ok: res.ok };
          })
      );
      const failedCount = results.filter((r) => !r.ok).length;
      if (failedCount > 0) {
        Alert.alert(
          'Some tags didn\'t save',
          `${failedCount} of ${results.length} clip${results.length === 1 ? '' : 's'} failed to save — try again before leaving.`
        );
        return;
      }
      navigation.goBack();
    } catch {
      Alert.alert('Could not save', 'Something went wrong saving your tags — try again.');
    } finally {
      setSaving(false);
    }
  };

  let content;
  if (loading) {
    content = <View style={s.centerFill}><ActivityIndicator size="large" color={colors.primary} /></View>;
  } else if (loadError) {
    content = (
      <View style={s.centerFill}>
        <Text style={r.errorText}>Couldn't load these rallies — check your connection.</Text>
        <TouchableOpacity style={r.retryBtn} onPress={() => setReloadKey((k) => k + 1)}>
          <Text style={r.retryBtnText}>Try again</Text>
        </TouchableOpacity>
      </View>
    );
  } else if (rallies.length === 0) {
    content = (
      <View style={s.centerFill}>
        <Text style={r.errorText}>All caught up — every rally in this match has been fully reviewed.</Text>
      </View>
    );
  } else {
    content = (
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        <Text style={s.h1}>Rally review</Text>
        <Text style={s.sub}>{rallies.length} left to review. Mark how the point ended and flag whether the clip's start/end points look right — that's what tunes detect_rallies.py's gap/threshold.</Text>

        {rallies.map(clip => (
          <ClipRow
            key={clip.id}
            clip={clip}
            value={tags[clip.id]}
            onTag={(v) => setTag(clip.id, v)}
            boundaryValues={boundaryNotes[clip.id] || []}
            onBoundary={(v) => setBoundaryNote(clip.id, v)}
            focused={isFocused}
          />
        ))}

        <TouchableOpacity
          style={[s.saveBtn, (reviewedCount === 0 || saving) && s.saveDisabled]}
          onPress={() => { playTapSound(); save(); }}
          disabled={reviewedCount === 0 || saving}
        >
          <Text style={s.saveBtnText}>
            {saving ? 'Saving...' : reviewedCount > 0 ? `Save ${reviewedCount} reviewed →` : 'Tag or flag at least one rally'}
          </Text>
        </TouchableOpacity>
      </ScrollView>
    );
  }

  return (
    <RequireAdmin navigation={navigation}>
      <SafeAreaView style={s.safe}>{content}</SafeAreaView>
    </RequireAdmin>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingTop: 24, paddingBottom: 48 },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center' },

  h1:  { color: colors.ink, fontSize: 24, fontFamily: fonts.bold, letterSpacing: -0.5, marginBottom: 6 },
  sub: { color: colors.muted, fontSize: 13, lineHeight: 19, marginBottom: 20, fontFamily: fonts.regular },

  saveBtn: { backgroundColor: colors.primary, borderRadius: radius.md, paddingVertical: 15, alignItems: 'center', marginTop: 8 },
  saveDisabled: { opacity: 0.4 },
  saveBtnText: { color: colors.white, fontSize: 15, fontFamily: fonts.bold },
});
