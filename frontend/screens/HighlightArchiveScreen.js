import { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView, Alert, ActivityIndicator } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import PlatformVideo from '../components/PlatformVideo';
import { useAuth } from '../context/AuthContext';
import { API_BASE } from '../config/api';
import { playTapSound } from '../utils/sounds';
import { useWindowWidth } from '../utils/responsive';
import { colors, fonts, radius, spacing } from '../theme';

function ArchiveRow({ clip }) {
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
}
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

export default function HighlightArchiveScreen({ navigation }) {
  const { token } = useAuth();
  const [loading, setLoading] = useState(true);
  const [clips, setClips] = useState([]);
  const [jobs, setJobs] = useState([]);
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

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
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

        {doneJobs.map(job => <ReelCard key={job.id} job={job} token={token} />)}

        {failedJobs.length > 0 && (
          <View style={s.failedBanner}>
            <Text style={s.failedBannerText}>
              {failedJobs.length === 1 ? 'A match' : `${failedJobs.length} matches`} failed to process. Try uploading again.
            </Text>
          </View>
        )}

        {loading && clips.length === 0 ? (
          <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 40 }} />
        ) : clips.length === 0 && jobs.length === 0 ? (
          <View style={s.empty}>
            <Text style={s.emptyTitle}>No clips yet</Text>
            <Text style={s.emptySub}>Upload a match to start building your archive.</Text>
          </View>
        ) : (
          clips.map(clip => <ArchiveRow key={clip.id} clip={clip} />)
        )}
      </ScrollView>
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
