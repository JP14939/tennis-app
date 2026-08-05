import { useCallback, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView, Alert, ActivityIndicator } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { useAuth } from '../context/AuthContext';
import { API_BASE } from '../config/api';

const GREEN  = '#4ade80';
const YELLOW = '#facc15';
const DARK   = '#0d0d0d';
const CARD   = '#141414';
const BORDER = '#222';
const TEXT   = '#fff';
const MUTED  = '#888';

const TAG_ICONS = { winner: '🏆', ace: '🚀', error: '❌' };

function ArchiveRow({ clip }) {
  return (
    <View style={r.card}>
      <Text style={r.icon}>{TAG_ICONS[clip.outcome_tag] ?? '🎾'}</Text>
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
    backgroundColor: CARD, borderWidth: 1, borderColor: BORDER,
    borderRadius: 14, padding: 14, marginBottom: 10,
  },
  icon: { fontSize: 22 },
  body: { flex: 1 },
  title: { color: TEXT, fontSize: 14, fontWeight: '700' },
  meta: { color: MUTED, fontSize: 12, marginTop: 2 },
  analyseBtn: {
    borderWidth: 1, borderColor: '#2a4a2a', backgroundColor: '#1a2e1a',
    borderRadius: 10, paddingVertical: 8, paddingHorizontal: 14,
  },
  analyseBtnText: { color: GREEN, fontSize: 12, fontWeight: '700' },
});

export default function HighlightArchiveScreen({ navigation }) {
  const { token } = useAuth();
  const [loading, setLoading] = useState(true);
  const [clips, setClips] = useState([]);
  const [jobs, setJobs] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [archiveRes, jobsRes] = await Promise.all([
        fetch(`${API_BASE}/api/highlights/archive`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${API_BASE}/api/highlights/jobs`, { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      const archiveData = await archiveRes.json();
      const jobsData = await jobsRes.json();
      setClips(archiveData.clips ?? []);
      setJobs(jobsData.jobs ?? []);
    } catch {
      // Leave whatever was previously loaded rather than blanking the
      // screen on a transient network failure.
    } finally {
      setLoading(false);
    }
  }, [token]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const processingJobs = jobs.filter(j => j.status === 'pending' || j.status === 'processing');
  const readyToReview = jobs.filter(j => j.status === 'done' && j.pending_review > 0);
  const failedJobs = jobs.filter(j => j.status === 'failed');

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
            <ActivityIndicator size="small" color={YELLOW} />
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

        {failedJobs.length > 0 && (
          <View style={s.failedBanner}>
            <Text style={s.failedBannerText}>
              {failedJobs.length === 1 ? 'A match' : `${failedJobs.length} matches`} failed to process. Try uploading again.
            </Text>
          </View>
        )}

        {loading && clips.length === 0 ? (
          <ActivityIndicator size="large" color={GREEN} style={{ marginTop: 40 }} />
        ) : clips.length === 0 && jobs.length === 0 ? (
          <View style={s.empty}>
            <Text style={s.emptyIcon}>🎬</Text>
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
  safe: { flex: 1, backgroundColor: DARK },
  scroll: { padding: 20, paddingTop: 16, paddingBottom: 40 },

  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 },
  title: { color: TEXT, fontSize: 24, fontWeight: '800', letterSpacing: -0.5 },
  addBtn: { backgroundColor: GREEN, borderRadius: 20, paddingHorizontal: 14, paddingVertical: 8 },
  addBtnText: { color: '#000', fontSize: 13, fontWeight: '700' },

  processingBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: '#241a0d', borderWidth: 1, borderColor: '#4a3a1a',
    borderRadius: 12, padding: 14, marginBottom: 12,
  },
  processingBannerText: { color: YELLOW, fontSize: 13, lineHeight: 18, flex: 1 },

  reviewBanner: {
    backgroundColor: '#0d1f0d', borderWidth: 1, borderColor: '#1a3a1a',
    borderRadius: 12, padding: 14, marginBottom: 12,
  },
  reviewBannerText: { color: GREEN, fontSize: 13, fontWeight: '700', textAlign: 'center' },

  failedBanner: {
    backgroundColor: '#2a0f0f', borderWidth: 1, borderColor: '#4a1a1a',
    borderRadius: 12, padding: 14, marginBottom: 12,
  },
  failedBannerText: { color: '#f87171', fontSize: 13, textAlign: 'center' },

  empty: { alignItems: 'center', paddingVertical: 60 },
  emptyIcon: { fontSize: 44, marginBottom: 14 },
  emptyTitle: { color: TEXT, fontSize: 18, fontWeight: '700', marginBottom: 6 },
  emptySub: { color: MUTED, fontSize: 13, textAlign: 'center' },
});
