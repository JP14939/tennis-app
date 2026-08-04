import React, { useCallback, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView,
  ScrollView, Alert, ActivityIndicator,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';
import { SHOT_ICONS } from '../data/mockAnalyses';
import { useAuth } from '../context/AuthContext';
import { fetchHistory, deleteHistory } from '../api/history';

const SHOT_TYPES = ['forehand', 'backhand', 'serve'];

function ScoreBar({ value }) {
  const color = value >= 75 ? '#4ade80' : value >= 55 ? '#facc15' : '#f87171';
  return (
    <View style={sb.track}>
      <View style={[sb.fill, { width: `${value}%`, backgroundColor: color }]} />
    </View>
  );
}
const sb = StyleSheet.create({
  track: { height: 4, backgroundColor: '#222', borderRadius: 2, marginTop: 6, marginBottom: 4 },
  fill:  { height: 4, borderRadius: 2 },
});

function formatDate(isoString) {
  if (!isoString) return '';
  // SQLite's datetime('now') is UTC with no 'Z' suffix — append one so the
  // browser/RN Date parser treats it as UTC instead of local time.
  const d = new Date(isoString.includes('Z') ? isoString : `${isoString.replace(' ', 'T')}Z`);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ', ' +
    d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

function AnalysisCard({ item, onPress, onLongPress }) {
  const score = Math.round(item.similarity ?? 0);
  return (
    <TouchableOpacity style={c.card} onPress={onPress} onLongPress={onLongPress} activeOpacity={0.8}>
      <View style={c.cardHeader}>
        <View style={c.shotBadge}>
          <Text style={c.shotIcon}>{SHOT_ICONS[item.shot_type]}</Text>
          <Text style={c.shotLabel}>{item.shot_type.charAt(0).toUpperCase() + item.shot_type.slice(1)}</Text>
        </View>
        <View style={c.metaRight}>
          <Text style={c.date}>{formatDate(item.created_at)}</Text>
          <Text style={c.anglePill}>{item.angle_label ?? '—'}</Text>
        </View>
      </View>

      <View style={c.scoreRow}>
        <Text style={c.scoreLabel}>Match score</Text>
        <Text style={c.scoreNum}>{score}<Text style={c.scoreSlash}>/100</Text></Text>
      </View>
      <ScoreBar value={score} />

      <Text style={c.proId}>{formatProId(item.pro_id)}</Text>
      {item.tip && <Text style={c.tip} numberOfLines={2}>💬 {item.tip}</Text>}
    </TouchableOpacity>
  );
}
const c = StyleSheet.create({
  card: {
    backgroundColor: '#141414', borderWidth: 1, borderColor: '#222',
    borderRadius: 14, padding: 16, marginBottom: 12,
  },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 },
  shotBadge:  { flexDirection: 'row', alignItems: 'center', gap: 8 },
  shotIcon:   { fontSize: 20 },
  shotLabel:  { color: '#fff', fontSize: 15, fontWeight: '700' },
  metaRight:  { alignItems: 'flex-end', gap: 4 },
  date:       { color: '#555', fontSize: 12 },
  anglePill:  { color: '#4ade80', fontSize: 11, fontWeight: '600',
    backgroundColor: '#1a2e1a', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 },
  scoreRow:   { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  scoreLabel: { color: '#666', fontSize: 12 },
  scoreNum:   { color: '#fff', fontSize: 20, fontWeight: '800' },
  scoreSlash: { color: '#444', fontSize: 13, fontWeight: '400' },
  proId:      { color: '#555', fontSize: 11, marginBottom: 8 },
  tip:        { color: '#888', fontSize: 13, lineHeight: 18 },
});

// ── Upload modal (inline, shown in place of the list) ────────────────────────
function UploadPanel({ onCancel, onUpload }) {
  const [shotType, setShotType] = useState('forehand');
  const [videoUri, setVideoUri]  = useState(null);
  const [videoName, setVideoName] = useState(null);
  const [picking, setPicking]    = useState(false);

  const pick = async () => {
    setPicking(true);
    try {
      const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission needed', 'Allow access to your photo library.');
        return;
      }
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['videos'],
        quality: 1,
      });
      if (!result.canceled && result.assets?.[0]) {
        setVideoUri(result.assets[0].uri);
        // Show a friendly filename: last path segment
        const parts = result.assets[0].uri.split('/');
        setVideoName(parts[parts.length - 1] || 'video.mp4');
      }
    } finally {
      setPicking(false);
    }
  };

  const submit = () => {
    if (!videoUri) { Alert.alert('Pick a video first'); return; }
    onUpload({ videoUri, shotType });
  };

  return (
    <View style={up.panel}>
      <Text style={up.title}>New Analysis</Text>
      <Text style={up.sub}>Upload a video and we'll match you to a pro</Text>

      <Text style={up.label}>Shot type</Text>
      <View style={up.shotRow}>
        {SHOT_TYPES.map(t => (
          <TouchableOpacity
            key={t}
            style={[up.pill, shotType === t && up.pillActive]}
            onPress={() => setShotType(t)}
          >
            <Text style={[up.pillText, shotType === t && up.pillTextActive]}>
              {SHOT_ICONS[t]} {t.charAt(0).toUpperCase() + t.slice(1)}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <TouchableOpacity style={up.pickBtn} onPress={pick} disabled={picking}>
        {videoUri ? (
          <>
            <Text style={up.pickIcon}>✅</Text>
            <Text style={up.pickBtnText}>Video selected</Text>
            <Text style={up.pickBtnSub} numberOfLines={1}>{videoName}</Text>
            <Text style={up.changeText}>Tap to change</Text>
          </>
        ) : (
          <>
            <Text style={up.pickIcon}>📹</Text>
            <Text style={up.pickBtnText}>{picking ? 'Opening...' : 'Choose video from library'}</Text>
            <Text style={up.pickBtnSub}>MP4 · MOV · 5–30 seconds</Text>
          </>
        )}
      </TouchableOpacity>

      <TouchableOpacity
        style={[up.submitBtn, !videoUri && up.submitDisabled]}
        onPress={submit}
        disabled={!videoUri}
      >
        <Text style={up.submitText}>Analyse swing →</Text>
      </TouchableOpacity>

      <TouchableOpacity style={up.cancelBtn} onPress={onCancel}>
        <Text style={up.cancelText}>Cancel</Text>
      </TouchableOpacity>
    </View>
  );
}
const up = StyleSheet.create({
  panel: {
    backgroundColor: '#141414', borderWidth: 1, borderColor: '#222',
    borderRadius: 16, padding: 20, marginBottom: 24,
  },
  title: { color: '#fff', fontSize: 20, fontWeight: '800', marginBottom: 4 },
  sub:   { color: '#666', fontSize: 13, marginBottom: 20 },
  label: { color: '#aaa', fontSize: 13, fontWeight: '600', marginBottom: 10 },
  shotRow:    { flexDirection: 'row', gap: 8, marginBottom: 20 },
  pill:       { flex: 1, borderWidth: 1, borderColor: '#222', borderRadius: 20, paddingVertical: 9, alignItems: 'center' },
  pillActive: { backgroundColor: '#1a2e1a', borderColor: '#2a4a2a' },
  pillText:       { color: '#666', fontSize: 13 },
  pillTextActive: { color: '#4ade80', fontWeight: '700' },
  pickBtn: {
    backgroundColor: '#0d0d0d', borderWidth: 1, borderColor: '#2a2a2a',
    borderRadius: 12, padding: 20, alignItems: 'center', gap: 4, marginBottom: 14,
  },
  pickIcon:    { fontSize: 28, marginBottom: 4 },
  pickBtnText: { color: '#fff', fontSize: 15, fontWeight: '600' },
  pickBtnSub:  { color: '#555', fontSize: 12 },
  changeText:  { color: '#4ade80', fontSize: 12, marginTop: 4 },
  submitBtn:     { backgroundColor: '#4ade80', borderRadius: 12, paddingVertical: 14, alignItems: 'center', marginBottom: 10 },
  submitDisabled: { opacity: 0.4 },
  submitText:    { color: '#000', fontSize: 15, fontWeight: '700' },
  cancelBtn:  { alignItems: 'center', paddingVertical: 8 },
  cancelText: { color: '#555', fontSize: 14 },
});

// ── Main screen ───────────────────────────────────────────────────────────────
export default function HistoryScreen({ navigation }) {
  const { token, isAuthenticated, isPremium } = useAuth();
  const [showUpload, setShowUpload]   = useState(false);
  const [loading, setLoading]         = useState(true);
  const [analyses, setAnalyses]       = useState([]);
  const [limit, setLimit]             = useState(null);

  const load = useCallback(async () => {
    if (!isAuthenticated) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const data = await fetchHistory(token);
      setAnalyses(data.analyses);
      setLimit(data.limit);
    } catch {
      // Leave whatever was previously loaded rather than blanking the screen
      // on a transient network failure.
    } finally {
      setLoading(false);
    }
  }, [token, isAuthenticated]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const handleUpload = ({ videoUri, shotType }) => {
    setShowUpload(false);
    // Navigate to contact marking so they can pick the exact frame — saving
    // happens automatically from ResultsScreen once analysis completes, and
    // this list picks it up next time the tab regains focus.
    navigation.navigate('Upload', { videoUri, shotType });
  };

  const handleDelete = (item) => {
    Alert.alert('Delete this analysis?', `${formatProId(item.pro_id)} — this can't be undone.`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          try {
            await deleteHistory(token, item.id);
            load();
          } catch (err) {
            Alert.alert('Could not delete', err.message || 'Something went wrong');
          }
        },
      },
    ]);
  };

  const atCap = limit != null && analyses.length >= limit;

  // ── Guest state ─────────────────────────────────────────────────────────
  if (!isAuthenticated) {
    return (
      <SafeAreaView style={s.safe}>
        <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
          <View style={s.header}>
            <Text style={s.title}>History</Text>
          </View>
          <View style={s.empty}>
            <Text style={s.emptyIcon}>🔒</Text>
            <Text style={s.emptyTitle}>Log in to see your history</Text>
            <Text style={s.emptySub}>Your saved analyses live on your account — log in or sign up to start building your history.</Text>
            <TouchableOpacity style={s.emptyBtn} onPress={() => navigation.navigate('Login')}>
              <Text style={s.emptyBtnText}>Log in →</Text>
            </TouchableOpacity>
          </View>
        </ScrollView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        {/* Header */}
        <View style={s.header}>
          <Text style={s.title}>History</Text>
          {!showUpload && (
            <TouchableOpacity style={s.newBtn} onPress={() => setShowUpload(true)}>
              <Text style={s.newBtnText}>+ New</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Upload panel */}
        {showUpload && (
          <UploadPanel
            onCancel={() => setShowUpload(false)}
            onUpload={handleUpload}
          />
        )}

        {loading && (
          <ActivityIndicator size="large" color="#4ade80" style={{ marginTop: 40 }} />
        )}

        {!loading && (
          <>
            {/* Stats strip */}
            {!showUpload && analyses.length > 0 && (
              <View style={s.statsRow}>
                <View style={s.stat}>
                  <Text style={s.statNum}>{limit != null ? `${analyses.length}/${limit}` : analyses.length}</Text>
                  <Text style={s.statLabel}>{limit != null ? 'Saved' : 'Analyses'}</Text>
                </View>
                <View style={s.statDivider} />
                <View style={s.stat}>
                  <Text style={s.statNum}>
                    {Math.round(analyses.reduce((sum, a) => sum + a.similarity, 0) / Math.max(1, analyses.length))}
                  </Text>
                  <Text style={s.statLabel}>Avg score</Text>
                </View>
                <View style={s.statDivider} />
                <View style={s.stat}>
                  <Text style={s.statNum}>
                    {analyses.filter(a => a.similarity >= 75).length}
                  </Text>
                  <Text style={s.statLabel}>Great swings</Text>
                </View>
              </View>
            )}

            {/* Free-tier cap notice */}
            {!showUpload && atCap && !isPremium && (
              <TouchableOpacity
                style={s.capCard}
                onPress={() => navigation.navigate('MainTabs', { screen: 'Premium' })}
              >
                <Text style={s.capText}>You've saved {limit}/{limit} shots on the free plan. Delete one, or upgrade to save unlimited →</Text>
              </TouchableOpacity>
            )}

            {/* Analysis cards */}
            {analyses.map(item => (
              <AnalysisCard
                key={item.id}
                item={item}
                onPress={() => Alert.alert(formatProId(item.pro_id), `Similarity: ${item.similarity}/100\n\n${item.tip ?? ''}`)}
                onLongPress={() => handleDelete(item)}
              />
            ))}

            {/* Empty state */}
            {analyses.length === 0 && !showUpload && (
              <View style={s.empty}>
                <Text style={s.emptyIcon}>🎾</Text>
                <Text style={s.emptyTitle}>No analyses yet</Text>
                <Text style={s.emptySub}>Upload a swing video to get matched to a pro and receive personalised coaching tips.</Text>
                <TouchableOpacity style={s.emptyBtn} onPress={() => setShowUpload(true)}>
                  <Text style={s.emptyBtnText}>Upload your first swing →</Text>
                </TouchableOpacity>
              </View>
            )}
          </>
        )}

      </ScrollView>
    </SafeAreaView>
  );
}

function formatProId(proId) {
  if (!proId) return 'Analysis';
  const [shot, num] = proId.split('_');
  if (!shot || !num) return proId;
  return `${shot.charAt(0).toUpperCase() + shot.slice(1)} Technique #${parseInt(num, 10)}`;
}

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: '#0d0d0d' },
  scroll: { padding: 20, paddingBottom: 40 },

  header: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'center', marginBottom: 20, paddingTop: 8,
  },
  title: { color: '#fff', fontSize: 26, fontWeight: '800', letterSpacing: -0.5 },
  newBtn: {
    backgroundColor: '#4ade80', borderRadius: 20,
    paddingHorizontal: 16, paddingVertical: 8,
  },
  newBtnText: { color: '#000', fontSize: 14, fontWeight: '700' },

  statsRow: {
    flexDirection: 'row', backgroundColor: '#141414',
    borderWidth: 1, borderColor: '#222', borderRadius: 14,
    padding: 16, marginBottom: 20, alignItems: 'center',
  },
  stat:        { flex: 1, alignItems: 'center' },
  statNum:     { color: '#fff', fontSize: 22, fontWeight: '800' },
  statLabel:   { color: '#555', fontSize: 11, marginTop: 2 },
  statDivider: { width: 1, height: 32, backgroundColor: '#222' },

  capCard: {
    backgroundColor: '#241a0d', borderWidth: 1, borderColor: '#4a3a1a',
    borderRadius: 12, padding: 14, marginBottom: 16,
  },
  capText: { color: '#facc15', fontSize: 13, lineHeight: 18 },

  empty: { alignItems: 'center', paddingVertical: 60 },
  emptyIcon:  { fontSize: 48, marginBottom: 16 },
  emptyTitle: { color: '#fff', fontSize: 20, fontWeight: '700', marginBottom: 8 },
  emptySub:   { color: '#555', fontSize: 14, textAlign: 'center', lineHeight: 21, marginBottom: 28, paddingHorizontal: 20 },
  emptyBtn:   { backgroundColor: '#4ade80', borderRadius: 12, paddingVertical: 14, paddingHorizontal: 28 },
  emptyBtnText: { color: '#000', fontSize: 15, fontWeight: '700' },
});
