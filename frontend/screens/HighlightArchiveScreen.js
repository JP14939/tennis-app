import { useCallback, useEffect, useRef, useState, memo } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, FlatList, ActivityIndicator } from 'react-native';
import Alert from '../utils/alert';
import { useFocusEffect } from '@react-navigation/native';
import PlatformVideo from '../components/PlatformVideo';
import { useAuth } from '../context/AuthContext';
import { API_BASE } from '../config/api';
import { playTapSound } from '../utils/sounds';
import { useWindowWidth } from '../utils/responsive';
import { formatTime } from '../utils/formatTime';
import { colors, fonts, radius, spacing } from '../theme';

// How many rallies show before "See all N rallies" -- see RallyBrowser below.
const TOP_RALLIES_COUNT = 5;

// Backend's GET /highlights/archive has no LIMIT (backend/src/routes/
// highlights.js) -- an active user's tagged-rally archive is unbounded, and
// this used to be a plain ScrollView + .map(). Same fix as HistoryScreen and
// MessageThreadScreen: memoized row, virtualized via FlatList below.
const ArchiveRow = memo(function ArchiveRow({ clip }) {
  return (
    <View style={r.card}>
      <View style={r.body}>
        <Text style={r.title}>{clip.outcome_tag.charAt(0).toUpperCase() + clip.outcome_tag.slice(1)}</Text>
        <Text style={r.meta}>{clip.duration_sec.toFixed(1)}s · {new Date(clip.created_at.includes('Z') ? clip.created_at : `${clip.created_at.replace(' ', 'T')}Z`).toLocaleDateString()}</Text>
      </View>
      <TouchableOpacity
        style={r.analyseBtn}
        onPress={() => Alert.alert(
          'Coming soon',
          'Deep analysis of tagged rally footage is a separate future feature — not built yet.'
        )}
      >
        <Text style={r.analyseBtnText}>Analyse</Text>
      </TouchableOpacity>
    </View>
  );
});
const r = StyleSheet.create({
  card: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.md, padding: 14, marginBottom: 10,
  },
  body: { flex: 1 },
  title: { color: colors.ink, fontSize: 14, fontFamily: fonts.bold },
  meta: { color: colors.muted, fontSize: 12, marginTop: 2, fontFamily: fonts.regular },
  analyseBtn: {
    borderWidth: 1, borderColor: colors.primary, backgroundColor: colors.primarySoft,
    borderRadius: radius.sm, paddingVertical: 8, paddingHorizontal: 14,
  },
  analyseBtnText: { color: colors.primary, fontSize: 12, fontFamily: fonts.bold },
});

// The stitch itself runs as a background job server-side (see
// backend/src/routes/highlights.js) rather than blocking the request --
// POST just enqueues it, then the caller polls for completion. Avoids
// leaving the user with no way to know whether a slow stitch actually
// finished if a single request happened to time out or the app got
// backgrounded.
const REEL_POLL_INTERVAL_MS = 2000;

function ReelCard({ job, token }) {
  const [building, setBuilding] = useState(false);
  const [reelUrl, setReelUrl] = useState(null);
  const [error, setError] = useState(null);
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);
  const windowWidth = useWindowWidth();
  const reelWidth = Math.min(windowWidth - 48, 500);
  const reelHeight = Math.round(reelWidth * 0.56);

  const createReel = async () => {
    setBuilding(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/highlights/jobs/${job.id}/reel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ top: 3 }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to build reel');
      const { reelJobId } = data;

      while (mountedRef.current) {
        await new Promise((resolve) => setTimeout(resolve, REEL_POLL_INTERVAL_MS));
        if (!mountedRef.current) break;
        const pollRes = await fetch(`${API_BASE}/api/highlights/reel-jobs/${reelJobId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const pollData = await pollRes.json();
        if (!pollRes.ok) throw new Error(pollData.error || 'Failed to check reel status');

        if (pollData.status === 'done') {
          if (mountedRef.current) setReelUrl(pollData.reel_url);
          break;
        }
        if (pollData.status === 'failed') {
          throw new Error(pollData.error || 'Failed to build reel');
        }
        // pending/processing -- keep polling
      }
    } catch (err) {
      if (mountedRef.current) setError(err.message || 'Something went wrong');
    } finally {
      if (mountedRef.current) setBuilding(false);
    }
  };

  return (
    <View style={rc.card}>
      {reelUrl ? (
        <View style={rc.videoWrap}>
          <PlatformVideo uri={`${API_BASE}${reelUrl}`} width={reelWidth} height={reelHeight} />
        </View>
      ) : (
        <>
          <Text style={rc.title}>Highlight reel</Text>
          <Text style={rc.meta}>Stitches your top 3 longest rallies from this match into one clip.</Text>
          {error && <Text style={rc.error}>{error}</Text>}
          <TouchableOpacity style={rc.btn} onPress={() => { playTapSound(); createReel(); }} disabled={building}>
            {building
              ? <ActivityIndicator size="small" color={colors.white} />
              : <Text style={rc.btnText}>Create highlight reel</Text>}
          </TouchableOpacity>
        </>
      )}
    </View>
  );
}
const rc = StyleSheet.create({
  card: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.md, padding: 14, marginBottom: 12,
  },
  title: { color: colors.ink, fontSize: 14, fontFamily: fonts.bold, marginBottom: 4 },
  meta: { color: colors.muted, fontSize: 12, marginBottom: 12, fontFamily: fonts.regular },
  error: { color: colors.coral, fontSize: 12, marginBottom: 10, fontFamily: fonts.regular },
  btn: { backgroundColor: colors.primary, borderRadius: radius.sm, paddingVertical: 10, alignItems: 'center' },
  btnText: { color: colors.white, fontSize: 13, fontFamily: fonts.bold },
  videoWrap: { borderRadius: radius.sm, overflow: 'hidden', backgroundColor: '#000' },
});

// A rally's individual shots (per rally_shots -- see backend/src/db.js),
// undifferentiated by which player hit them (near/far-court player
// detection doesn't exist yet -- see TODO_MANUAL.md). Tapping a chip seeks
// the rally's own clip to that shot's contact frame for a quick preview,
// then "Analyze this shot" sends just that shot through the same
// pro-matcher pipeline /api/analyse uses.
function ShotChip({ shot, active, onPress }) {
  const label = shot.shot_type.charAt(0).toUpperCase() + shot.shot_type.slice(1);
  return (
    <TouchableOpacity style={[rb.shotChip, active && rb.shotChipActive]} onPress={onPress} activeOpacity={0.8}>
      <Text style={[rb.shotChipText, active && rb.shotChipTextActive]}>{label}</Text>
    </TouchableOpacity>
  );
}

function RallyCard({ rally, token, navigation }) {
  const [selectedShotIndex, setSelectedShotIndex] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const videoRef = useRef(null);
  const windowWidth = useWindowWidth();
  const videoWidth = Math.min(windowWidth - 48, 500);
  const videoHeight = Math.round(videoWidth * 0.56);

  const shots = rally.shots ?? [];
  const selectedShot = shots.find((sh) => sh.shot_index === selectedShotIndex) ?? null;

  const selectShot = (shot) => {
    setSelectedShotIndex(shot.shot_index);
    setLoaded(true); // deferred mount, same reasoning as HighlightReviewScreen's ClipRow
  };

  // Every shot in a rally shares the same underlying clip (rally.clip_url
  // never changes), so the video only ever mounts once -- onVideoReady
  // (below) fires exactly once too, the first time a shot is selected.
  // Tapping a DIFFERENT shot afterward must still re-seek even though the
  // video is already loaded and won't fire onReadyForDisplay/loadedmetadata
  // again -- this effect covers that case; onVideoReady covers the very
  // first selection, before the video element/ref even exists yet.
  useEffect(() => {
    if (loaded && selectedShot) {
      videoRef.current?.setPositionAsync(selectedShot.contact_time_sec * 1000);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedShotIndex, loaded]);

  // Fires once the video is actually ready to seek (onReadyForDisplay
  // native-side, loadedmetadata on web) -- see PlatformVideo's onVideoSize.
  // Needed in addition to the effect above because the ref isn't attached
  // (and the seek would silently no-op) until the video actually mounts.
  const onVideoReady = () => {
    if (selectedShot) videoRef.current?.setPositionAsync(selectedShot.contact_time_sec * 1000);
  };

  const analyzeShot = async () => {
    if (!selectedShot) return;
    setAnalyzing(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/highlights/rallies/${rally.id}/shots/${selectedShot.shot_index}/analyze`,
        { method: 'POST', headers: { Authorization: `Bearer ${token}` } }
      );
      // A 2xx whose body isn't JSON means something between us and the
      // backend answered instead (e.g. an ngrok/proxy interstitial) -- same
      // failure mode api/history.js's handle() guards against. Without this,
      // res.json() throwing here was still caught below, but as an opaque
      // "Unexpected token..." message instead of an honest one.
      let data;
      try {
        data = await res.json();
      } catch {
        throw new Error(res.ok ? `Unexpected non-JSON response from ${res.url}` : 'Analysis failed');
      }
      if (!res.ok) throw new Error(data.error || 'Analysis failed');
      navigation.navigate('Results', { savedResult: data, shotType: selectedShot.shot_type });
    } catch (err) {
      Alert.alert('Could not analyze shot', err.message || 'Something went wrong');
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <View style={rb.rallyCard}>
      <View style={rb.rallyMetaRow}>
        <Text style={rb.rallyTime}>{formatTime(rally.start_sec)}</Text>
        <Text style={rb.rallyMeta}>{rally.duration_sec.toFixed(1)}s · {rally.swing_count} swings</Text>
      </View>

      {shots.length > 0 ? (
        <View style={rb.shotRow}>
          {shots.map((shot) => (
            <ShotChip
              key={shot.shot_index}
              shot={shot}
              active={selectedShotIndex === shot.shot_index}
              onPress={() => selectShot(shot)}
            />
          ))}
        </View>
      ) : (
        <Text style={rb.noShotsText}>No individual shots detected for this rally yet.</Text>
      )}

      {selectedShot && (
        <View style={rb.previewWrap}>
          {loaded && (
            <View style={rb.videoWrap}>
              <PlatformVideo
                ref={videoRef}
                uri={`${API_BASE}${rally.clip_url}`}
                width={videoWidth}
                height={videoHeight}
                onVideoSize={onVideoReady}
              />
            </View>
          )}
          <TouchableOpacity
            style={[rb.analyzeBtn, analyzing && rb.analyzeBtnDisabled]}
            onPress={() => { playTapSound(); analyzeShot(); }}
            disabled={analyzing}
          >
            {analyzing
              ? <ActivityIndicator size="small" color={colors.white} />
              : <Text style={rb.analyzeBtnText}>Analyze this shot</Text>}
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

// Ranked "best rallies first" -- duration is the primary signal (same idea
// the reel builder's default already used), swing_count as a tiebreaker so a
// long rally that's mostly dead time doesn't outrank a shorter one with more
// actual shots. Top 5 visible by default, "See all" reveals the rest -- a
// plain toggle, not an animated accordion (a growing/shrinking list reads
// differently from a details panel; see TipsSection/PhaseBreakdown for that
// pattern instead).
function RallyBrowser({ rallies, token, navigation }) {
  const [expanded, setExpanded] = useState(false);
  if (rallies.length === 0) return null;

  const sorted = [...rallies].sort((a, b) => b.duration_sec - a.duration_sec || b.swing_count - a.swing_count);
  const visible = expanded ? sorted : sorted.slice(0, TOP_RALLIES_COUNT);

  return (
    <View style={rb.wrap}>
      <Text style={rb.sectionTitle}>Rallies</Text>
      {visible.map((rally) => (
        <RallyCard key={rally.id} rally={rally} token={token} navigation={navigation} />
      ))}
      {sorted.length > TOP_RALLIES_COUNT && (
        <TouchableOpacity onPress={() => setExpanded((e) => !e)} style={rb.seeAllBtn}>
          <Text style={rb.seeAllText}>
            {expanded ? 'Show fewer' : `See all ${sorted.length} rallies`}
          </Text>
        </TouchableOpacity>
      )}
    </View>
  );
}
const rb = StyleSheet.create({
  wrap: { marginBottom: 12 },
  sectionTitle: { color: colors.ink, fontSize: 16, fontFamily: fonts.bold, marginBottom: 10 },
  rallyCard: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.md, padding: 14, marginBottom: 10,
  },
  rallyMetaRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 },
  rallyTime: { color: colors.ink, fontSize: 14, fontFamily: fonts.bold },
  rallyMeta: { color: colors.muted, fontSize: 12, fontFamily: fonts.regular },
  noShotsText: { color: colors.muted, fontSize: 12, fontFamily: fonts.regular },
  shotRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  shotChip: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill,
    paddingHorizontal: 12, paddingVertical: 8,
  },
  shotChipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  shotChipText: { color: colors.mutedDark, fontSize: 12, fontFamily: fonts.bold },
  shotChipTextActive: { color: colors.white },
  previewWrap: { marginTop: 12 },
  videoWrap: { borderRadius: radius.sm, overflow: 'hidden', backgroundColor: '#000', marginBottom: 10 },
  analyzeBtn: { backgroundColor: colors.primary, borderRadius: radius.sm, paddingVertical: 11, alignItems: 'center' },
  analyzeBtnDisabled: { opacity: 0.6 },
  analyzeBtnText: { color: colors.white, fontSize: 13, fontFamily: fonts.bold },
  seeAllBtn: { alignItems: 'center', paddingVertical: 10 },
  seeAllText: { color: colors.primary, fontSize: 13, fontFamily: fonts.bold },
});

export default function HighlightArchiveScreen({ navigation }) {
  const { token } = useAuth();
  const [loading, setLoading] = useState(true);
  const [clips, setClips] = useState([]);
  const [jobs, setJobs] = useState([]);
  // jobId -> rallies[] (each carrying .shots) -- fetched per done job below,
  // since GET /highlights/jobs (the summary list) doesn't include rallies.
  const [rallyData, setRallyData] = useState({});
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [archiveRes, jobsRes] = await Promise.all([
        fetch(`${API_BASE}/api/highlights/archive`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${API_BASE}/api/highlights/jobs`, { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      const archiveData = await archiveRes.json();
      const jobsData = await jobsRes.json();
      if (!mountedRef.current) return;
      setClips(archiveData.clips ?? []);
      setJobs(jobsData.jobs ?? []);

      const doneJobIds = (jobsData.jobs ?? []).filter((j) => j.status === 'done').map((j) => j.id);
      const details = await Promise.all(doneJobIds.map(async (jobId) => {
        try {
          const res = await fetch(`${API_BASE}/api/highlights/jobs/${jobId}`, { headers: { Authorization: `Bearer ${token}` } });
          const data = await res.json();
          return [jobId, res.ok ? (data.rallies ?? []) : []];
        } catch {
          return [jobId, []];
        }
      }));
      if (mountedRef.current) setRallyData(Object.fromEntries(details));
    } catch {
      // Leave whatever was previously loaded rather than blanking the
      // screen on a transient network failure.
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [token]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const processingJobs = jobs.filter(j => j.status === 'pending' || j.status === 'processing');
  const readyToReview = jobs.filter(j => j.status === 'done' && j.pending_review > 0);
  const failedJobs = jobs.filter(j => j.status === 'failed');
  const doneJobs = jobs.filter(j => j.status === 'done');

  const renderArchiveRow = useCallback(({ item }) => <ArchiveRow clip={item} />, []);

  // Everything that isn't a per-clip row -- title, job-status banners, reel
  // builders -- moves into the FlatList's header rather than staying above a
  // ScrollView, same restructuring HistoryScreen's FlatList conversion used.
  const archiveHeader = (
    <>
      <View style={s.header}>
        <Text style={s.title}>Highlight Archive</Text>
        <TouchableOpacity style={s.addBtn} onPress={() => navigation.navigate('HighlightUpload')}>
          <Text style={s.addBtnText}>+ Match</Text>
        </TouchableOpacity>
      </View>

      {processingJobs.length > 0 && (
        <View style={s.processingBanner}>
          <ActivityIndicator size="small" color={colors.amberText} />
          <Text style={s.processingBannerText}>
            {processingJobs.length === 1 ? 'A match is' : `${processingJobs.length} matches are`} still being scanned for rallies — we'll notify you when ready.
          </Text>
        </View>
      )}

      {readyToReview.map(job => (
        <TouchableOpacity
          key={job.id}
          style={s.reviewBanner}
          onPress={() => navigation.navigate('HighlightReview', { jobId: job.id })}
        >
          <Text style={s.reviewBannerText}>
            {job.pending_review} rall{job.pending_review === 1 ? 'y' : 'ies'} ready to review →
          </Text>
        </TouchableOpacity>
      ))}

      {doneJobs.map(job => (
        <View key={job.id}>
          <ReelCard job={job} token={token} />
          <RallyBrowser rallies={rallyData[job.id] ?? []} token={token} navigation={navigation} />
        </View>
      ))}

      {failedJobs.length > 0 && (
        <View style={s.failedBanner}>
          <Text style={s.failedBannerText}>
            {failedJobs.length === 1 ? 'A match' : `${failedJobs.length} matches`} failed to process. Try uploading again.
          </Text>
        </View>
      )}
    </>
  );

  const archiveEmpty = loading && clips.length === 0 ? (
    <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 40 }} />
  ) : clips.length === 0 && jobs.length === 0 ? (
    <View style={s.empty}>
      <Text style={s.emptyTitle}>No clips yet</Text>
      <Text style={s.emptySub}>Upload a match to start building your archive.</Text>
    </View>
  ) : null;

  return (
    <SafeAreaView style={s.safe}>
      <FlatList
        data={clips}
        keyExtractor={(item) => String(item.id)}
        renderItem={renderArchiveRow}
        contentContainerStyle={s.scroll}
        showsVerticalScrollIndicator={false}
        ListHeaderComponent={archiveHeader}
        ListEmptyComponent={archiveEmpty}
      />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingTop: 16, paddingBottom: 40 },

  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 },
  title: { color: colors.ink, fontSize: 24, fontFamily: fonts.bold, letterSpacing: -0.5 },
  addBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingHorizontal: 14, paddingVertical: 8 },
  addBtnText: { color: colors.white, fontSize: 13, fontFamily: fonts.bold },

  processingBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: colors.amberBg, borderWidth: 1, borderColor: colors.gold,
    borderRadius: radius.md, padding: 14, marginBottom: 12,
  },
  processingBannerText: { color: colors.amberText, fontSize: 13, lineHeight: 18, flex: 1, fontFamily: fonts.regular },

  reviewBanner: {
    backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primary,
    borderRadius: radius.md, padding: 14, marginBottom: 12,
  },
  reviewBannerText: { color: colors.primary, fontSize: 13, fontFamily: fonts.bold, textAlign: 'center' },

  failedBanner: {
    backgroundColor: '#f3d4d0', borderWidth: 1, borderColor: colors.coral,
    borderRadius: radius.md, padding: 14, marginBottom: 12,
  },
  failedBannerText: { color: colors.coral, fontSize: 13, textAlign: 'center', fontFamily: fonts.regular },

  empty: { alignItems: 'center', paddingVertical: 60 },
  emptyTitle: { color: colors.ink, fontSize: 18, fontFamily: fonts.bold, marginBottom: 6 },
  emptySub: { color: colors.muted, fontSize: 13, textAlign: 'center', fontFamily: fonts.regular },
});
