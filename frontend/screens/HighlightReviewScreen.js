import { useEffect, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView, ActivityIndicator, Dimensions } from 'react-native';
import PlatformVideo from '../components/PlatformVideo';
import { useAuth } from '../context/AuthContext';
import { API_BASE } from '../config/api';

const GREEN  = '#4ade80';
const DARK   = '#0d0d0d';
const CARD   = '#141414';
const BORDER = '#222';
const TEXT   = '#fff';
const MUTED  = '#888';

// First-pass outcome vocabulary covering what was actually asked for
// (winners, aces) plus a way to discard a mis-detected rally -- easy to
// extend later, not locked in.
const TAG_OPTIONS = [
  { value: 'winner', label: 'Winner', icon: '🏆' },
  { value: 'ace',    label: 'Ace',    icon: '🚀' },
  { value: 'error',  label: 'Error',  icon: '❌' },
  { value: 'skip',   label: 'Skip',   icon: '✕' },
];

const videoWidth = Math.min(Dimensions.get('window').width - 48, 500);
const videoHeight = Math.round(videoWidth * 0.56);

function formatTime(sec) {
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

function ClipRow({ clip, value, onTag }) {
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
    <View style={r.card}>
      <TouchableOpacity activeOpacity={1} style={r.videoWrap} onPress={toggle}>
        <PlatformVideo
          ref={videoRef}
          uri={`${API_BASE}${clip.clip_url}`}
          width={videoWidth}
          height={videoHeight}
          onStatusUpdate={(status) => setPlaying(!!status.isPlaying)}
        />
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
            <Text style={r.tagIcon}>{opt.icon}</Text>
            <Text style={[r.tagLabel, value === opt.value && r.tagLabelActive]}>{opt.label}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}
const r = StyleSheet.create({
  card: {
    backgroundColor: CARD, borderWidth: 1, borderColor: BORDER,
    borderRadius: 16, padding: 14, marginBottom: 12,
  },
  videoWrap: { borderRadius: 10, overflow: 'hidden', backgroundColor: '#000', marginBottom: 10 },
  playHint: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  playHintText: { color: 'rgba(255,255,255,0.75)', fontSize: 40 },
  metaRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 },
  time: { color: TEXT, fontSize: 15, fontWeight: '700' },
  duration: { color: MUTED, fontSize: 12 },
  tagRow: { flexDirection: 'row', gap: 6 },
  tagPill: {
    flex: 1, borderWidth: 1, borderColor: BORDER, borderRadius: 12,
    paddingVertical: 8, alignItems: 'center', gap: 2,
  },
  tagPillActive: { backgroundColor: '#1a2e1a', borderColor: '#2a4a2a' },
  tagIcon: { fontSize: 14 },
  tagLabel: { color: MUTED, fontSize: 10, fontWeight: '600' },
  tagLabelActive: { color: GREEN },
});

export default function HighlightReviewScreen({ route, navigation }) {
  const { jobId } = route.params ?? {};
  const { token } = useAuth();
  const [loading, setLoading] = useState(true);
  const [rallies, setRallies] = useState([]);
  const [tags, setTags] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/highlights/jobs/${jobId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const data = await res.json();
        setRallies(data.rallies ?? []);
        const initialTags = {};
        for (const clip of data.rallies ?? []) {
          if (clip.outcome_tag) initialTags[clip.id] = clip.outcome_tag;
        }
        setTags(initialTags);
      } finally {
        setLoading(false);
      }
    })();
  }, [jobId, token]);

  const setTag = (clipId, value) => setTags(prev => ({ ...prev, [clipId]: value }));

  const taggedCount = Object.values(tags).filter(v => v && v !== 'skip').length;

  const save = async () => {
    setSaving(true);
    try {
      await Promise.all(
        Object.entries(tags)
          .filter(([, value]) => value)
          .map(([clipId, value]) =>
            fetch(`${API_BASE}/api/highlights/rallies/${clipId}`, {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
              body: JSON.stringify({ outcome_tag: value, archived: value !== 'skip' }),
            })
          )
      );
      navigation.navigate('HighlightArchive');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.centerFill}><ActivityIndicator size="large" color={GREEN} /></View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        <Text style={s.h1}>Tag your rallies</Text>
        <Text style={s.sub}>We found {rallies.length} rallies. Watch each one and mark how the point ended, or skip the ones that aren't real rallies.</Text>

        {rallies.map(clip => (
          <ClipRow key={clip.id} clip={clip} value={tags[clip.id]} onTag={(v) => setTag(clip.id, v)} />
        ))}

        <TouchableOpacity
          style={[s.saveBtn, (taggedCount === 0 || saving) && s.saveDisabled]}
          onPress={save}
          disabled={taggedCount === 0 || saving}
        >
          <Text style={s.saveBtnText}>
            {saving ? 'Saving...' : taggedCount > 0 ? `Save ${taggedCount} to archive →` : 'Tag at least one rally'}
          </Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: DARK },
  scroll: { padding: 20, paddingTop: 24, paddingBottom: 48 },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center' },

  h1:  { color: TEXT, fontSize: 24, fontWeight: '800', letterSpacing: -0.5, marginBottom: 6 },
  sub: { color: MUTED, fontSize: 13, lineHeight: 19, marginBottom: 20 },

  saveBtn: { backgroundColor: GREEN, borderRadius: 12, paddingVertical: 15, alignItems: 'center', marginTop: 8 },
  saveDisabled: { opacity: 0.4 },
  saveBtnText: { color: '#000', fontSize: 15, fontWeight: '700' },
});
