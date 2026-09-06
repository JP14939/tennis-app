import { useEffect, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView, ActivityIndicator } from 'react-native';
import Alert from '../utils/alert';
import PlatformVideo from '../components/PlatformVideo';
import { useAuth } from '../context/AuthContext';
import { API_BASE } from '../config/api';
import { playTapSound } from '../utils/sounds';
import { useWindowWidth } from '../utils/responsive';
import { formatTime } from '../utils/formatTime';
import { colors, fonts, radius, spacing } from '../theme';

// Outcome vocabulary: who won the point, not how -- in tennis, almost every
// non-ace point ends in an error by the losing side anyway ("winner (this
// side)" already implies the other side missed the return), so a separate
// Error button would mostly just re-describe the same event from the other
// angle. 'skip' keeps its original value for backward compatibility with
// anything already saved under the old 4-option set (winner/ace/error/skip)
// -- only the label changed, so previously-saved 'skip' tags still show as
// selected under their new "Not a rally" label.
//
// Rally BOUNDARY review (was start/end points right?) moved to the hidden
// Dev Page (DevRallyBoundaryReviewScreen.js) -- that's ML training-data
// collection, not something a real user should be asked to judge. This
// screen only ever reads/writes outcome_tag now, never boundary_note.
const TAG_OPTIONS = [
  { value: 'ace',                label: 'Ace' },
  { value: 'winner_this_side',   label: 'Winner (this side)' },
  { value: 'winner_other_side',  label: 'Winner (other side)' },
  { value: 'skip',               label: 'Not a rally' },
];

function ClipRow({ clip, value, onTag }) {
  const videoRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  // Mounting a PlatformVideo starts it buffering immediately even without
  // playing -- this row used to mount one unconditionally for every pending
  // rally the moment the screen rendered, so a long match with many detected
  // rallies tried to buffer all of them at once. DevRallyBoundaryReviewScreen
  // already fixed the identical issue on its own (dev-only) rally list by
  // deferring the mount until the row is tapped; mirrored here on the
  // user-facing path real uploads actually hit.
  const [loaded, setLoaded] = useState(false);
  const windowWidth = useWindowWidth();
  const videoWidth = Math.min(windowWidth - 48, 500);
  const videoHeight = Math.round(videoWidth * 0.56);

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
      <TouchableOpacity activeOpacity={1} style={r.videoWrap} onPress={toggle}>
        {loaded && (
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
      <View style={r.metaRow}>
        <Text style={r.time}>{formatTime(clip.start_sec)}</Text>
        <Text style={r.duration}>{clip.duration_sec.toFixed(1)}s · {clip.swing_count} swings</Text>
      </View>
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
    </View>
  );
}
const r = StyleSheet.create({
  card: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.lg, padding: 14, marginBottom: 12,
  },
  videoWrap: { borderRadius: radius.sm, overflow: 'hidden', backgroundColor: '#000', marginBottom: 10 },
  playHint: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  playHintText: { color: 'rgba(255,255,255,0.75)', fontSize: 40 },
  metaRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 },
  time: { color: colors.ink, fontSize: 15, fontFamily: fonts.bold },
  duration: { color: colors.muted, fontSize: 12, fontFamily: fonts.regular },
  tagRow: { flexDirection: 'row', gap: 6 },
  tagPill: {
    flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingVertical: 8, alignItems: 'center', gap: 2,
  },
  tagPillActive: { backgroundColor: colors.primarySoft, borderColor: colors.primary },
  tagLabel: { color: colors.muted, fontSize: 10, fontFamily: fonts.semibold },
  tagLabelActive: { color: colors.primary },
  errorText: { color: colors.muted, fontSize: 13.5, textAlign: 'center', marginBottom: 14, paddingHorizontal: 24, fontFamily: fonts.regular },
  retryBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingHorizontal: 20, paddingVertical: 11 },
  retryBtnText: { color: colors.white, fontSize: 13.5, fontFamily: fonts.bold },
});

export default function HighlightReviewScreen({ route, navigation }) {
  const { jobId } = route.params ?? {};
  const { token } = useAuth();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [rallies, setRallies] = useState([]);
  const [tags, setTags] = useState({});
  const [saving, setSaving] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

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
        // Already-outcome-tagged clips don't reappear -- otherwise every
        // reviewed clip resurfaced on every reload, and nothing ever left
        // the queue.
        const pending = (data.rallies ?? []).filter((clip) => !clip.outcome_tag);
        setRallies(pending);
        const initialTags = {};
        for (const clip of pending) {
          if (clip.outcome_tag) initialTags[clip.id] = clip.outcome_tag;
        }
        setTags(initialTags);
      } catch {
        // A failed/unparseable response used to be an unhandled rejection --
        // rallies stayed [], loading still went false via finally, so the
        // user just saw "We found 0 rallies" with no error and no retry.
        setLoadError(true);
      } finally {
        setLoading(false);
      }
    })();
  }, [jobId, token, reloadKey]);

  const setTag = (clipId, value) => setTags(prev => ({ ...prev, [clipId]: value }));

  const reviewedCount = Object.keys(tags).filter((id) => tags[id]).length;

  const save = async () => {
    setSaving(true);
    try {
      const results = await Promise.all(
        Object.keys(tags)
          .filter((clipId) => tags[clipId])
          .map(async (clipId) => {
            const value = tags[clipId];
            const res = await fetch(`${API_BASE}/api/highlights/rallies/${clipId}`, {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
              body: JSON.stringify({ outcome_tag: value, archived: value !== 'skip' }),
            });
            return { clipId, ok: res.ok };
          })
      );
      // Previously never checked res.ok -- a failed PATCH (expired token,
      // validation error, 500) was silent, and navigation to the archive
      // proceeded as if every tag had saved.
      const failedCount = results.filter((r) => !r.ok).length;
      if (failedCount > 0) {
        Alert.alert(
          'Some tags didn\'t save',
          `${failedCount} of ${results.length} clip${results.length === 1 ? '' : 's'} failed to save — try again before leaving.`
        );
        return;
      }
      navigation.navigate('HighlightArchive');
    } catch {
      Alert.alert('Could not save', 'Something went wrong saving your tags — try again.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.centerFill}><ActivityIndicator size="large" color={colors.primary} /></View>
      </SafeAreaView>
    );
  }

  if (loadError) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.centerFill}>
          <Text style={r.errorText}>Couldn't load these rallies — check your connection.</Text>
          <TouchableOpacity style={r.retryBtn} onPress={() => setReloadKey((k) => k + 1)}>
            <Text style={r.retryBtnText}>Try again</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  if (rallies.length === 0) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.centerFill}>
          <Text style={r.errorText}>All caught up — every rally in this match has been reviewed.</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        <Text style={s.h1}>Tag your rallies</Text>
        <Text style={s.sub}>{rallies.length} left to review. Watch each one and mark how the point ended (or flag the ones that aren't real rallies).</Text>

        {rallies.map(clip => (
          <ClipRow
            key={clip.id}
            clip={clip}
            value={tags[clip.id]}
            onTag={(v) => setTag(clip.id, v)}
          />
        ))}

        <TouchableOpacity
          style={[s.saveBtn, (reviewedCount === 0 || saving) && s.saveDisabled]}
          onPress={() => { playTapSound(); save(); }}
          disabled={reviewedCount === 0 || saving}
        >
          <Text style={s.saveBtnText}>
            {saving ? 'Saving...' : reviewedCount > 0 ? `Save ${reviewedCount} reviewed →` : 'Tag at least one rally'}
          </Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
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
