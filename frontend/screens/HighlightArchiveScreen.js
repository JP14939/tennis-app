import { useMemo } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView, Alert } from 'react-native';
import { MOCK_ARCHIVE_CLIPS } from '../data/mockHighlights';

const GREEN  = '#4ade80';
const DARK   = '#0d0d0d';
const CARD   = '#141414';
const BORDER = '#222';
const TEXT   = '#fff';
const MUTED  = '#888';

const SHOT_ICONS = { forehand: '🎾', backhand: '🏓', serve: '🚀' };

function ArchiveRow({ clip }) {
  return (
    <View style={r.card}>
      <Text style={r.icon}>{SHOT_ICONS[clip.shot_type] ?? '🎾'}</Text>
      <View style={r.body}>
        <Text style={r.title}>{clip.shot_type.charAt(0).toUpperCase() + clip.shot_type.slice(1)}</Text>
        <Text style={r.meta}>{clip.timestamp} · {clip.date}</Text>
      </View>
      <TouchableOpacity
        style={r.analyseBtn}
        onPress={() => Alert.alert(
          'Coming soon',
          'Sending archived clips straight into analysis needs the backend clipping pipeline — not built yet.'
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

export default function HighlightArchiveScreen({ route, navigation }) {
  const newClips = route.params?.newClips ?? [];
  // TODO: this archive is session-local (mock starter list + whatever was
  // just tagged). Needs a real backend store once clipping is wired up.
  const clips = useMemo(() => [...newClips, ...MOCK_ARCHIVE_CLIPS], [newClips]);

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        <View style={s.header}>
          <Text style={s.title}>Highlight Archive</Text>
          <TouchableOpacity style={s.addBtn} onPress={() => navigation.navigate('HighlightUpload')}>
            <Text style={s.addBtnText}>+ Match</Text>
          </TouchableOpacity>
        </View>

        {newClips.length > 0 && (
          <View style={s.savedBanner}>
            <Text style={s.savedBannerText}>✓ Saved {newClips.length} new clip{newClips.length === 1 ? '' : 's'}</Text>
          </View>
        )}

        {clips.length === 0 ? (
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

  savedBanner: {
    backgroundColor: '#0d1f0d', borderWidth: 1, borderColor: '#1a3a1a',
    borderRadius: 12, padding: 12, marginBottom: 16,
  },
  savedBannerText: { color: GREEN, fontSize: 13, fontWeight: '600', textAlign: 'center' },

  empty: { alignItems: 'center', paddingVertical: 60 },
  emptyIcon: { fontSize: 44, marginBottom: 14 },
  emptyTitle: { color: TEXT, fontSize: 18, fontWeight: '700', marginBottom: 6 },
  emptySub: { color: MUTED, fontSize: 13, textAlign: 'center' },
});
