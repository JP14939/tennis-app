import React, { useCallback, useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView,
  ScrollView, Alert, ActivityIndicator, Platform,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';
import { useAuth } from '../context/AuthContext';
import { fetchHistory, deleteHistory } from '../api/history';
import { colors, fonts, radius, spacing, scoreColor } from '../theme';
import CourtBackground from '../components/CourtBackground';
import TrendChart from '../components/TrendChart';
import ProgressShareCard from '../components/ProgressShareCard';
import { captureAndShare } from '../utils/shareCard';
import { TennisBallIcon, PlusIcon, VideoIcon, CheckIcon, ShareIcon } from '../components/icons';

const SHOT_TYPES = ['forehand', 'backhand', 'serve'];
const PROGRESS_FILTERS = ['all', ...SHOT_TYPES];

function ScoreBar({ value }) {
  return (
    <View style={sb.track}>
      <View style={[sb.fill, { width: `${value}%`, backgroundColor: scoreColor(value) }]} />
    </View>
  );
}
const sb = StyleSheet.create({
  track: { height: 5, backgroundColor: colors.border, borderRadius: 3, marginTop: 7, marginBottom: 10, overflow: 'hidden' },
  fill:  { height: 5, borderRadius: 3 },
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
          <TennisBallIcon size={18} color={colors.primary} />
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
      {item.tip && <Text style={c.tip} numberOfLines={2}>{item.tip}</Text>}
    </TouchableOpacity>
  );
}
const c = StyleSheet.create({
  card: {
    backgroundColor: colors.surface, borderRadius: radius.lg, padding: 16, marginBottom: 12,
  },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 },
  shotBadge:  { flexDirection: 'row', alignItems: 'center', gap: 8 },
  shotLabel:  { color: colors.ink, fontSize: 15, fontFamily: fonts.bold },
  metaRight:  { alignItems: 'flex-end', gap: 4 },
  date:       { color: colors.muted, fontSize: 11.5, fontFamily: fonts.regular },
  anglePill:  { color: colors.primary, fontSize: 10.5, fontFamily: fonts.bold,
    backgroundColor: colors.primarySoft, paddingHorizontal: 9, paddingVertical: 2, borderRadius: 10 },
  scoreRow:   { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  scoreLabel: { color: colors.muted, fontSize: 12, fontFamily: fonts.regular },
  scoreNum:   { color: colors.ink, fontSize: 19, fontFamily: fonts.extrabold },
  scoreSlash: { color: colors.divider, fontSize: 12, fontFamily: fonts.regular },
  proId:      { color: colors.muted, fontSize: 11, marginBottom: 6, fontFamily: fonts.regular },
  tip:        { color: colors.mutedDark, fontSize: 12.5, lineHeight: 18, fontFamily: fonts.regular },
});

// ── Progress trend (derived client-side from the already-fetched history --
// no new endpoint, /api/history already returns similarity/shot_type/created_at
// for every saved analysis) ───────────────────────────────────────────────────
function ProgressSection({ analyses }) {
  const [filter, setFilter] = useState('all');
  const [chartWidth, setChartWidth] = useState(0);
  const shareCardRef = useRef(null);

  const filtered = filter === 'all' ? analyses : analyses.filter(a => a.shot_type === filter);
  const points = [...filtered]
    .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
    .map(a => ({ date: a.created_at, score: Math.round(a.similarity ?? 0) }));

  const delta = points.length >= 2 ? points[points.length - 1].score - points[0].score : null;
  const filterLabel = filter === 'all' ? 'Overall' : filter.charAt(0).toUpperCase() + filter.slice(1);

  return (
    <View style={pg.wrap}>
      <View style={pg.header}>
        <View style={pg.headerLeft}>
          <Text style={pg.title}>Progress</Text>
          {delta !== null && (
            <Text style={[pg.delta, { color: scoreColor(points[points.length - 1].score) }]}>
              {delta >= 0 ? '+' : ''}{delta} since your first shot
            </Text>
          )}
        </View>
        {points.length > 0 && Platform.OS !== 'web' && (
          <TouchableOpacity
            style={pg.shareBtn}
            onPress={() => captureAndShare(shareCardRef, 'Share your TennisAI progress')}
          >
            <ShareIcon size={15} color={colors.mutedDark} />
          </TouchableOpacity>
        )}
      </View>

      <View style={pg.filterRow}>
        {PROGRESS_FILTERS.map(f => (
          <TouchableOpacity
            key={f}
            style={[pg.pill, filter === f && pg.pillActive]}
            onPress={() => setFilter(f)}
          >
            <Text style={[pg.pillText, filter === f && pg.pillTextActive]}>
              {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <View onLayout={(e) => setChartWidth(e.nativeEvent.layout.width)}>
        {points.length > 0 && chartWidth > 0 && <TrendChart points={points} width={chartWidth} />}
      </View>
      {points.length === 0 && (
        <Text style={pg.emptyNote}>
          No {filter === 'all' ? '' : `${filter} `}shots saved yet.
        </Text>
      )}
      {points.length === 1 && (
        <Text style={pg.emptyNote}>Log a few more shots to see your trend.</Text>
      )}

      {points.length > 0 && (
        <View style={pg.offscreen}>
          <ProgressShareCard ref={shareCardRef} points={points} delta={delta} filterLabel={filterLabel} />
        </View>
      )}
    </View>
  );
}
const pg = StyleSheet.create({
  wrap: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: 16, marginBottom: spacing.xl },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 },
  headerLeft: { flex: 1 },
  title: { color: colors.ink, fontSize: 16, fontFamily: fonts.bold },
  delta: { fontSize: 12, fontFamily: fonts.bold, marginTop: 2 },
  shareBtn: {
    width: 30, height: 30, borderRadius: 15, backgroundColor: colors.bg,
    alignItems: 'center', justifyContent: 'center',
  },
  filterRow: { flexDirection: 'row', gap: 6, marginBottom: 12 },
  pill: { flex: 1, backgroundColor: colors.bg, borderRadius: radius.pill, paddingVertical: 7, alignItems: 'center' },
  pillActive: { backgroundColor: colors.primary },
  pillText: { color: colors.mutedDark, fontSize: 11.5, fontFamily: fonts.semibold },
  pillTextActive: { color: colors.white, fontFamily: fonts.bold },
  emptyNote: { color: colors.muted, fontSize: 12.5, fontFamily: fonts.regular, textAlign: 'center', paddingVertical: 8 },
  offscreen: { position: 'absolute', left: -9999, top: -9999 },
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
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <TouchableOpacity style={up.pickBtn} onPress={pick} disabled={picking}>
        {videoUri ? (
          <>
            <View style={up.pickIconWrap}><CheckIcon size={20} color={colors.primary} /></View>
            <Text style={up.pickBtnText}>Video selected</Text>
            <Text style={up.pickBtnSub} numberOfLines={1}>{videoName}</Text>
            <Text style={up.changeText}>Tap to change</Text>
          </>
        ) : (
          <>
            <View style={up.pickIconWrap}><VideoIcon size={20} color={colors.primary} /></View>
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
    backgroundColor: colors.surface, borderRadius: radius.lg, padding: 20, marginBottom: 24,
  },
  title: { color: colors.ink, fontSize: 19, fontFamily: fonts.extrabold, marginBottom: 4 },
  sub:   { color: colors.muted, fontSize: 13, marginBottom: 20, fontFamily: fonts.regular },
  label: { color: colors.mutedDark, fontSize: 12.5, fontFamily: fonts.bold, marginBottom: 10, textTransform: 'uppercase', letterSpacing: 0.3 },
  shotRow:    { flexDirection: 'row', gap: 8, marginBottom: 20 },
  pill:       { flex: 1, backgroundColor: colors.bg, borderRadius: radius.pill, paddingVertical: 10, alignItems: 'center' },
  pillActive: { backgroundColor: colors.primary },
  pillText:       { color: colors.mutedDark, fontSize: 13, fontFamily: fonts.semibold },
  pillTextActive: { color: colors.white, fontFamily: fonts.bold },
  pickBtn: {
    backgroundColor: colors.bg, borderWidth: 1.5, borderColor: colors.borderDashed, borderStyle: 'dashed',
    borderRadius: radius.md, padding: 20, alignItems: 'center', gap: 4, marginBottom: 14,
  },
  pickIconWrap: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: colors.primarySoft,
    alignItems: 'center', justifyContent: 'center', marginBottom: 6,
  },
  pickBtnText: { color: colors.ink, fontSize: 14.5, fontFamily: fonts.bold },
  pickBtnSub:  { color: colors.muted, fontSize: 12, fontFamily: fonts.regular },
  changeText:  { color: colors.primary, fontSize: 12, marginTop: 4, fontFamily: fonts.semibold },
  submitBtn:     { backgroundColor: colors.primary, borderRadius: radius.pill, paddingVertical: 14, alignItems: 'center', marginBottom: 10 },
  submitDisabled: { opacity: 0.4 },
  submitText:    { color: colors.white, fontSize: 15, fontFamily: fonts.bold },
  cancelBtn:  { alignItems: 'center', paddingVertical: 8 },
  cancelText: { color: colors.muted, fontSize: 14, fontFamily: fonts.semibold },
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
        <CourtBackground />
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
      <CourtBackground />
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        {/* Header */}
        <View style={s.header}>
          <Text style={s.title}>History</Text>
          {!showUpload && (
            <TouchableOpacity style={s.newBtn} onPress={() => setShowUpload(true)}>
              <PlusIcon size={13} color={colors.white} />
              <Text style={s.newBtnText}>New</Text>
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
          <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 40 }} />
        )}

        {!loading && (
          <>
            {/* Progress trend */}
            {!showUpload && analyses.length > 0 && (
              <ProgressSection analyses={analyses} />
            )}

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
                <Text style={s.capText}>You've saved {limit}/{limit} shots on the free plan. Delete one, or <Text style={s.capTextBold}>upgrade to save unlimited →</Text></Text>
              </TouchableOpacity>
            )}

            {/* Analysis cards */}
            {analyses.map(item => (
              <AnalysisCard
                key={item.id}
                item={item}
                onPress={() => navigation.navigate('Results', {
                  savedResult: item.result,
                  analysisId: item.id,
                  shotType: item.shot_type,
                })}
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
  safe:   { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingBottom: 130 },

  header: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'center', marginBottom: spacing.xl, paddingTop: 8,
  },
  title: { color: colors.ink, fontSize: 32, fontFamily: fonts.serifItalic },
  newBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: colors.primary, borderRadius: radius.pill,
    paddingHorizontal: 16, paddingVertical: 9,
  },
  newBtnText: { color: colors.white, fontSize: 13, fontFamily: fonts.bold },

  statsRow: {
    flexDirection: 'row', backgroundColor: colors.surface,
    borderRadius: radius.lg, padding: 16, marginBottom: spacing.xl, alignItems: 'center',
  },
  stat:        { flex: 1, alignItems: 'center' },
  statNum:     { color: colors.ink, fontSize: 24, fontFamily: fonts.serif },
  statLabel:   { color: colors.muted, fontSize: 10.5, fontFamily: fonts.semibold, marginTop: 2 },
  statDivider: { width: 1, height: 30, backgroundColor: colors.border },

  capCard: {
    backgroundColor: colors.amberBg, borderRadius: radius.sm, padding: 13, marginBottom: spacing.lg,
  },
  capText: { color: colors.amberText, fontSize: 12.5, lineHeight: 18, fontFamily: fonts.regular },
  capTextBold: { fontFamily: fonts.bold },

  empty: { alignItems: 'center', paddingVertical: 60 },
  emptyIcon:  { fontSize: 48, marginBottom: 16 },
  emptyTitle: { color: colors.ink, fontSize: 20, fontFamily: fonts.extrabold, marginBottom: 8 },
  emptySub:   { color: colors.muted, fontSize: 14, textAlign: 'center', lineHeight: 21, marginBottom: 28, paddingHorizontal: 20, fontFamily: fonts.regular },
  emptyBtn:   { backgroundColor: colors.primary, borderRadius: radius.md, paddingVertical: 14, paddingHorizontal: 28 },
  emptyBtnText: { color: colors.white, fontSize: 15, fontFamily: fonts.bold },
});
