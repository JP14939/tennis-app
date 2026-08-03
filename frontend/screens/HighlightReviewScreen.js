import { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView } from 'react-native';

const GREEN  = '#4ade80';
const DARK   = '#0d0d0d';
const CARD   = '#141414';
const BORDER = '#222';
const TEXT   = '#fff';
const MUTED  = '#888';

const TAG_OPTIONS = [
  { value: 'forehand', label: 'Forehand', icon: '🎾' },
  { value: 'backhand', label: 'Backhand', icon: '🏓' },
  { value: 'serve',    label: 'Serve',    icon: '🚀' },
  { value: 'skip',     label: 'Skip',     icon: '✕' },
];

function ClipRow({ clip, value, onTag }) {
  return (
    <View style={r.card}>
      <View style={r.head}>
        <View style={r.thumb}>
          <Text style={r.thumbIcon}>▶</Text>
        </View>
        <View>
          <Text style={r.time}>{clip.timestamp}</Text>
          <Text style={r.duration}>{clip.duration}</Text>
        </View>
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
  head: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 12 },
  thumb: {
    width: 48, height: 48, borderRadius: 10, backgroundColor: '#0d0d0d',
    borderWidth: 1, borderColor: BORDER, alignItems: 'center', justifyContent: 'center',
  },
  thumbIcon: { color: '#555', fontSize: 16 },
  time: { color: TEXT, fontSize: 15, fontWeight: '700' },
  duration: { color: MUTED, fontSize: 12, marginTop: 1 },
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
  const { clips = [] } = route.params ?? {};
  const [tags, setTags] = useState({});

  const setTag = (clipId, value) => setTags(prev => ({ ...prev, [clipId]: value }));

  const taggedCount = Object.values(tags).filter(v => v && v !== 'skip').length;

  const save = () => {
    const newClips = clips
      .filter(c => tags[c.id] && tags[c.id] !== 'skip')
      .map(c => ({ id: c.id, shot_type: tags[c.id], timestamp: c.timestamp, date: 'Just now' }));
    navigation.navigate('HighlightArchive', { newClips });
  };

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        <Text style={s.h1}>Tag your shots</Text>
        <Text style={s.sub}>We found {clips.length} swings. Confirm what each one was, or skip the ones that aren't real shots.</Text>

        {clips.map(clip => (
          <ClipRow key={clip.id} clip={clip} value={tags[clip.id]} onTag={(v) => setTag(clip.id, v)} />
        ))}

        <TouchableOpacity
          style={[s.saveBtn, taggedCount === 0 && s.saveDisabled]}
          onPress={save}
          disabled={taggedCount === 0}
        >
          <Text style={s.saveBtnText}>
            {taggedCount > 0 ? `Save ${taggedCount} to archive →` : 'Tag at least one shot'}
          </Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: DARK },
  scroll: { padding: 20, paddingTop: 24, paddingBottom: 48 },

  h1:  { color: TEXT, fontSize: 24, fontWeight: '800', letterSpacing: -0.5, marginBottom: 6 },
  sub: { color: MUTED, fontSize: 13, lineHeight: 19, marginBottom: 20 },

  saveBtn: { backgroundColor: GREEN, borderRadius: 12, paddingVertical: 15, alignItems: 'center', marginTop: 8 },
  saveDisabled: { opacity: 0.4 },
  saveBtnText: { color: '#000', fontSize: 15, fontWeight: '700' },
});
