import { useCallback, useState } from 'react';
import {
  View, Text, TouchableOpacity, TextInput, StyleSheet, SafeAreaView,
  ScrollView, ActivityIndicator, Platform, Switch,
} from 'react-native';
import Alert from '../utils/alert';
import { useFocusEffect } from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';
import { useAuth } from '../context/AuthContext';
import { API_BASE } from '../config/api';
import { colors, fonts, radius, spacing } from '../theme';
import { playTapSound } from '../utils/sounds';
import RequireAdmin from '../components/RequireAdmin';
import { SHOT_TYPES as ANALYSIS_SHOT_TYPES } from '../config/shotTypes';

const KINDS = [
  { value: 'drill', label: 'Drill (free)' },
  { value: 'lesson', label: 'Lesson (watch + learn + practice)' },
];
// 'footwork' isn't one of the three shot types the ML pipeline actually
// analyses (config/shotTypes.js) -- it's a drill-only category, so it's
// kept as a local addition on top of the shared list rather than folded
// into it.
const SHOT_TYPES = [
  ...ANALYSIS_SHOT_TYPES.map((value) => ({ value, label: value[0].toUpperCase() + value.slice(1) })),
  { value: 'footwork', label: 'Footwork' },
];

const EMPTY_FORM = {
  id: null, kind: 'drill', shot_type: 'forehand', title: '', explanation: '',
  emphasis: '', diagram_tip_id: '', is_premium: false, sort_order: '0', steps: [],
};

async function fetchDrills(token) {
  const res = await fetch(`${API_BASE}/api/dev/drills`, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) throw new Error('Failed to load');
  return res.json();
}

async function saveDrill(token, form, videoUri) {
  const formData = new FormData();
  if (form.id) formData.append('id', String(form.id));
  formData.append('kind', form.kind);
  formData.append('shot_type', form.shot_type);
  formData.append('title', form.title);
  formData.append('explanation', form.explanation);
  formData.append('emphasis', form.emphasis || '');
  formData.append('diagram_tip_id', form.diagram_tip_id || '');
  formData.append('is_premium', form.is_premium ? '1' : '0');
  formData.append('sort_order', form.sort_order || '0');
  formData.append('steps', JSON.stringify(form.steps.filter((s) => s.label.trim())));

  if (videoUri) {
    if (Platform.OS === 'web') {
      const response = await fetch(videoUri);
      const blob = await response.blob();
      formData.append('video', blob, 'drill.mp4');
    } else {
      formData.append('video', { uri: videoUri, name: 'drill.mp4', type: 'video/mp4' });
    }
  }

  const res = await fetch(`${API_BASE}/api/dev/drills`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Save failed');
  return data;
}

async function archiveDrill(token, id) {
  const res = await fetch(`${API_BASE}/api/dev/drills/${id}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error('Archive failed');
}

function Pill({ label, active, onPress }) {
  return (
    <TouchableOpacity style={[s.pill, active && s.pillActive]} onPress={onPress}>
      <Text style={[s.pillText, active && s.pillTextActive]}>{label}</Text>
    </TouchableOpacity>
  );
}

export default function DevDrillsEditorScreen({ navigation }) {
  const { token } = useAuth();
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [videoUri, setVideoUri] = useState(null);
  const [videoName, setVideoName] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    fetchDrills(token).then((data) => setItems(data.items ?? [])).catch(() => {}).finally(() => setLoading(false));
  }, [token]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const resetForm = () => {
    setForm(EMPTY_FORM);
    setVideoUri(null);
    setVideoName(null);
  };

  const editItem = (item) => {
    playTapSound();
    setForm({
      id: item.id, kind: item.kind, shot_type: item.shot_type, title: item.title,
      explanation: item.explanation, emphasis: item.emphasis || '',
      diagram_tip_id: item.diagram_tip_id || '', is_premium: !!item.is_premium,
      sort_order: String(item.sort_order ?? 0),
      // id carried through so the backend can update this step in place
      // instead of deleting/recreating it -- recreating would orphan any
      // drill_practice_attempts already logged against its old id.
      steps: (item.steps ?? []).map((st) => ({ id: st.id, label: st.label, shot_type: st.shot_type || '', target_reps: st.target_reps ? String(st.target_reps) : '' })),
    });
    setVideoUri(null);
    setVideoName(null);
  };

  const pickVideo = async () => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission needed', 'Allow access to your photo library.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['videos'], quality: 1 });
    if (!result.canceled && result.assets?.[0]?.uri) {
      setVideoUri(result.assets[0].uri);
      setVideoName(result.assets[0].uri.split('/').pop() || 'video.mp4');
    }
  };

  const addStep = () => setForm((f) => ({ ...f, steps: [...f.steps, { label: '', shot_type: '', target_reps: '' }] }));
  const updateStep = (i, patch) => setForm((f) => ({ ...f, steps: f.steps.map((st, idx) => (idx === i ? { ...st, ...patch } : st)) }));
  const removeStep = (i) => setForm((f) => ({ ...f, steps: f.steps.filter((_, idx) => idx !== i) }));

  const submit = async () => {
    if (!form.title.trim() || !form.explanation.trim()) {
      Alert.alert('Missing fields', 'Title and explanation are required.');
      return;
    }
    playTapSound();
    setSaving(true);
    try {
      await saveDrill(token, form, videoUri);
      resetForm();
      load();
    } catch (err) {
      Alert.alert('Could not save', err.message || 'Something went wrong');
    } finally {
      setSaving(false);
    }
  };

  const archive = (item) => {
    Alert.alert('Archive this item?', item.title, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Archive', style: 'destructive',
        onPress: async () => {
          try { await archiveDrill(token, item.id); load(); }
          catch (err) { Alert.alert('Could not archive', err.message || 'Something went wrong'); }
        },
      },
    ]);
  };

  return (
    <RequireAdmin navigation={navigation}>
      <SafeAreaView style={s.safe}>
        <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
          <Text style={s.h1}>Drills & Lessons</Text>
          <Text style={s.sub}>{form.id ? `Editing #${form.id}` : 'New item'} — {items.length} total (incl. archived)</Text>

          <View style={s.formCard}>
            <Text style={s.label}>Kind</Text>
            <View style={s.pillRow}>
              {KINDS.map((k) => (
                <Pill key={k.value} label={k.label} active={form.kind === k.value} onPress={() => setForm((f) => ({ ...f, kind: k.value }))} />
              ))}
            </View>

            <Text style={s.label}>Shot type</Text>
            <View style={s.pillRow}>
              {SHOT_TYPES.map((t) => (
                <Pill key={t.value} label={t.label} active={form.shot_type === t.value} onPress={() => setForm((f) => ({ ...f, shot_type: t.value }))} />
              ))}
            </View>

            <Text style={s.label}>Title</Text>
            <TextInput style={s.input} value={form.title} onChangeText={(v) => setForm((f) => ({ ...f, title: v }))} placeholder="e.g. Crosscourt forehand consistency" placeholderTextColor={colors.muted} />

            <Text style={s.label}>Explanation (the "learn" text)</Text>
            <TextInput style={[s.input, s.textarea]} value={form.explanation} onChangeText={(v) => setForm((f) => ({ ...f, explanation: v }))} placeholder="What this drill/lesson teaches" placeholderTextColor={colors.muted} multiline />

            <Text style={s.label}>What to emphasize (optional)</Text>
            <TextInput style={[s.input, s.textarea]} value={form.emphasis} onChangeText={(v) => setForm((f) => ({ ...f, emphasis: v }))} placeholder="Key cues to focus on while practising" placeholderTextColor={colors.muted} multiline />

            <Text style={s.label}>Diagram tip id (optional, reuses TipDiagram)</Text>
            <TextInput style={s.input} value={form.diagram_tip_id} onChangeText={(v) => setForm((f) => ({ ...f, diagram_tip_id: v }))} placeholder="e.g. contact_extension" placeholderTextColor={colors.muted} />

            <Text style={s.label}>Video</Text>
            <TouchableOpacity style={s.videoBtn} onPress={pickVideo}>
              <Text style={s.videoBtnText}>{videoName ? `Selected: ${videoName}` : 'Pick a video (leave empty to keep existing)'}</Text>
            </TouchableOpacity>

            <View style={s.switchRow}>
              <Text style={s.label}>Premium (locked for free users)</Text>
              <Switch value={form.is_premium} onValueChange={(v) => setForm((f) => ({ ...f, is_premium: v }))} trackColor={{ true: colors.primary }} />
            </View>

            <Text style={s.label}>Sort order</Text>
            <TextInput style={s.input} value={form.sort_order} onChangeText={(v) => setForm((f) => ({ ...f, sort_order: v.replace(/[^0-9-]/g, '') }))} keyboardType="number-pad" />

            {form.kind === 'lesson' && (
              <>
                <Text style={s.label}>Practice routine steps</Text>
                {form.steps.map((step, i) => (
                  <View key={i} style={s.stepRow}>
                    <TextInput
                      style={[s.input, s.stepInput]}
                      value={step.label}
                      onChangeText={(v) => updateStep(i, { label: v })}
                      placeholder="e.g. Crosscourt forehand x10"
                      placeholderTextColor={colors.muted}
                    />
                    <View style={s.pillRow}>
                      <Pill label="No practice" active={!step.shot_type} onPress={() => updateStep(i, { shot_type: '' })} />
                      {SHOT_TYPES.filter((t) => t.value !== 'footwork').map((t) => (
                        <Pill key={t.value} label={t.label} active={step.shot_type === t.value} onPress={() => updateStep(i, { shot_type: t.value })} />
                      ))}
                    </View>
                    <TouchableOpacity onPress={() => removeStep(i)}><Text style={s.removeStepText}>Remove step</Text></TouchableOpacity>
                  </View>
                ))}
                <TouchableOpacity style={s.addStepBtn} onPress={addStep}>
                  <Text style={s.addStepBtnText}>+ Add step</Text>
                </TouchableOpacity>
              </>
            )}

            <View style={s.actionsRow}>
              {form.id && (
                <TouchableOpacity style={s.cancelBtn} onPress={resetForm}>
                  <Text style={s.cancelBtnText}>Cancel edit</Text>
                </TouchableOpacity>
              )}
              <TouchableOpacity style={[s.saveBtn, saving && s.saveDisabled]} onPress={submit} disabled={saving}>
                <Text style={s.saveBtnText}>{saving ? 'Saving...' : form.id ? 'Save changes' : 'Create'}</Text>
              </TouchableOpacity>
            </View>
          </View>

          <Text style={s.listTitle}>All items</Text>
          {loading ? (
            <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 20 }} />
          ) : items.length === 0 ? (
            <Text style={s.sub}>Nothing created yet.</Text>
          ) : (
            items.map((item) => (
              <View key={item.id} style={[s.itemCard, item.archived && s.itemCardArchived]}>
                <Text style={s.itemTitle}>
                  {item.title} {item.archived ? '(archived)' : ''}
                </Text>
                <Text style={s.itemSub}>
                  {item.kind} · {item.shot_type} · {item.is_premium ? 'Premium' : 'Free'} · {item.steps?.length ?? 0} step(s)
                </Text>
                <View style={s.itemActions}>
                  <TouchableOpacity onPress={() => editItem(item)}><Text style={s.itemActionText}>Edit</Text></TouchableOpacity>
                  {!item.archived && (
                    <TouchableOpacity onPress={() => archive(item)}><Text style={s.itemActionTextDanger}>Archive</Text></TouchableOpacity>
                  )}
                </View>
              </View>
            ))
          )}
        </ScrollView>
      </SafeAreaView>
    </RequireAdmin>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingTop: 24, paddingBottom: 48 },

  h1: { color: colors.ink, fontSize: 22, fontFamily: fonts.bold, marginBottom: 4 },
  sub: { color: colors.muted, fontSize: 12.5, marginBottom: 18, fontFamily: fonts.regular },

  formCard: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: 16, marginBottom: 24 },
  label: { color: colors.ink, fontSize: 12.5, fontFamily: fonts.bold, marginTop: 12, marginBottom: 6 },
  input: {
    backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: 12, paddingVertical: 10, color: colors.ink, fontSize: 13.5, fontFamily: fonts.regular,
  },
  textarea: { minHeight: 70, textAlignVertical: 'top' },

  pillRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  pill: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 7, backgroundColor: colors.bg },
  pillActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  pillText: { color: colors.muted, fontSize: 12, fontFamily: fonts.semibold },
  pillTextActive: { color: colors.white },

  videoBtn: { backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, padding: 12 },
  videoBtnText: { color: colors.mutedDark, fontSize: 12.5, fontFamily: fonts.regular },

  switchRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 14 },

  stepRow: { backgroundColor: colors.bg, borderRadius: radius.sm, padding: 12, marginBottom: 10 },
  stepInput: { marginBottom: 8 },
  removeStepText: { color: colors.coral, fontSize: 12, fontFamily: fonts.semibold, marginTop: 8 },
  addStepBtn: { alignItems: 'center', paddingVertical: 8 },
  addStepBtnText: { color: colors.primary, fontSize: 13, fontFamily: fonts.bold },

  actionsRow: { flexDirection: 'row', gap: 10, marginTop: 18 },
  cancelBtn: { flex: 1, alignItems: 'center', paddingVertical: 13, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border },
  cancelBtnText: { color: colors.mutedDark, fontSize: 13.5, fontFamily: fonts.bold },
  saveBtn: { flex: 2, alignItems: 'center', paddingVertical: 13, borderRadius: radius.pill, backgroundColor: colors.primary },
  saveDisabled: { opacity: 0.5 },
  saveBtnText: { color: colors.white, fontSize: 13.5, fontFamily: fonts.bold },

  listTitle: { color: colors.ink, fontSize: 16, fontFamily: fonts.bold, marginBottom: 12 },
  itemCard: { backgroundColor: colors.surface, borderRadius: radius.md, padding: 14, marginBottom: 10 },
  itemCardArchived: { opacity: 0.5 },
  itemTitle: { color: colors.ink, fontSize: 14, fontFamily: fonts.bold },
  itemSub: { color: colors.muted, fontSize: 11.5, marginTop: 3, fontFamily: fonts.regular },
  itemActions: { flexDirection: 'row', gap: 16, marginTop: 10 },
  itemActionText: { color: colors.primary, fontSize: 12.5, fontFamily: fonts.bold },
  itemActionTextDanger: { color: colors.coral, fontSize: 12.5, fontFamily: fonts.bold },
});
