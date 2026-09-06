import React, { useCallback, useEffect, useRef, useState, memo } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView,
  ScrollView, FlatList, ActivityIndicator, Platform,
} from 'react-native';
import Alert from '../utils/alert';
import { useFocusEffect } from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';
import { useAuth } from '../context/AuthContext';
import { fetchHistory, fetchHistoryItem, deleteHistory, flagNotShot, confirmRealShot, correctShotType } from '../api/history';
import { colors, fonts, radius, spacing, scoreColor } from '../theme';
import CourtBackground from '../components/CourtBackground';
import TrendChart from '../components/TrendChart';
import ProgressShareCard from '../components/ProgressShareCard';
import { captureAndShare } from '../utils/shareCard';
import { TennisBallIcon, PlusIcon, VideoIcon, CheckIcon, ShareIcon, FlagIcon } from '../components/icons';
import { API_BASE } from '../config/api';
import { SHOT_TYPES } from '../config/shotTypes';
import { parseServerDate } from '../utils/formatDate';
import FriendPickerModal from '../components/FriendPickerModal';
import { shareSwing } from '../api/friends';
import DrillsSection from '../components/DrillsSection';
import LessonsSection from '../components/LessonsSection';
import { playTapSound } from '../utils/sounds';

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
  const d = parseServerDate(isoString);
  if (!d) return '';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ', ' +
    d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

// Memoized, and every callback prop below is now the screen's stable
// (useCallback'd) handler passed straight through -- previously the parent's
// .map() built a fresh `() => handler(item)` closure per card per render, so
// every card's props failed a shallow-equality check on every HistoryScreen
// re-render (e.g. opening the send-to-friend modal from one card re-rendered
// every other card too). Handlers here take `item` themselves; this
// component's own onPress={() => onPress(item)} wrappers are cheap because
// they only run when this card actually re-renders, which memo now prevents
// for renders unrelated to this specific item.
const AnalysisCard = memo(function AnalysisCard({ item, onPress, onLongPress, onWatchCompare, onToggleFlag, onToggleConfirm, onCorrectType, onSendToFriend }) {
  const score = Math.round(item.similarity ?? 0);
  const top = item.result?.matches?.[0];
  const canWatchCompare = !!(top?.pro_clip_url && item.result?.user_clip_url);
  const flagged = !!item.flagged_not_shot;
  const confirmed = !!item.confirmed_real_shot;
  const [showTypePicker, setShowTypePicker] = useState(false);
  return (
    <TouchableOpacity
      style={[c.card, flagged && c.cardFlagged]}
      onPress={() => onPress(item)}
      onLongPress={() => onLongPress(item)}
      activeOpacity={0.8}
    >
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

      {flagged && (
        <View style={c.flaggedBanner}>
          <FlagIcon size={11} color={colors.coral} />
          <Text style={c.flaggedBannerText}>Flagged: not a real shot</Text>
        </View>
      )}
      {confirmed && (
        <View style={c.confirmedBanner}>
          <CheckIcon size={11} color={colors.primary} />
          <Text style={c.confirmedBannerText}>Confirmed: real shot</Text>
        </View>
      )}

      <View style={c.scoreRow}>
        <Text style={c.scoreLabel}>Match score</Text>
        <Text style={c.scoreNum}>{score}<Text style={c.scoreSlash}>/100</Text></Text>
      </View>
      <ScoreBar value={score} />

      <Text style={c.proId}>{formatProId(item.pro_id, top?.player_name)}</Text>
      {item.tip && <Text style={c.tip} numberOfLines={2}>{item.tip}</Text>}

      {/* Real human ground truth for scripts/16_shot_verification/'s
          teacher-student loop -- confirming or flagging is what actually
          teaches the system, on top of Claude's own batch-verified passes. */}
      <Text style={c.verifyLabel}>Is this actually a shot?</Text>
      <View style={c.verifyRow}>
        <TouchableOpacity
          style={[c.verifyBtn, confirmed && c.verifyBtnConfirmed]}
          onPress={(e) => { e.stopPropagation?.(); onToggleConfirm(item); }}
          activeOpacity={0.8}
        >
          <CheckIcon size={12} color={confirmed ? colors.white : colors.primary} />
          <Text style={[c.verifyBtnText, confirmed && c.verifyBtnTextOn]}>Yes, real shot</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[c.verifyBtn, flagged && c.verifyBtnFlagged]}
          onPress={(e) => { e.stopPropagation?.(); onToggleFlag(item); }}
          activeOpacity={0.8}
        >
          <FlagIcon size={12} color={flagged ? colors.white : colors.coral} />
          <Text style={[c.verifyBtnText, flagged && c.verifyBtnTextOn]}>No, not a shot</Text>
        </TouchableOpacity>
      </View>

      {/* Real human ground truth for scripts/14_shot_classifier/'s
          teacher-student loop, same idea as the verify row above but for
          shot TYPE instead of real-vs-not-real. */}
      <TouchableOpacity
        style={c.wrongTypeBtn}
        onPress={(e) => { e.stopPropagation?.(); setShowTypePicker((v) => !v); }}
        activeOpacity={0.7}
      >
        <Text style={c.wrongTypeText}>{showTypePicker ? 'Cancel' : 'Wrong shot type?'}</Text>
      </TouchableOpacity>
      {showTypePicker && (
        <View style={c.typePickerRow}>
          {SHOT_TYPES.map((st) => (
            <TouchableOpacity
              key={st}
              style={[c.typePickerBtn, st === item.shot_type && c.typePickerBtnActive]}
              onPress={(e) => { e.stopPropagation?.(); setShowTypePicker(false); onCorrectType(item, st); }}
              activeOpacity={0.8}
            >
              <Text style={[c.typePickerBtnText, st === item.shot_type && c.typePickerBtnTextActive]}>
                {st.charAt(0).toUpperCase() + st.slice(1)}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      )}

      {canWatchCompare && (
        <TouchableOpacity
          style={c.watchBtn}
          onPress={(e) => { e.stopPropagation?.(); onWatchCompare(item); }}
          activeOpacity={0.8}
        >
          <VideoIcon size={13} color={colors.primary} />
          <Text style={c.watchBtnText}>Watch & compare →</Text>
        </TouchableOpacity>
      )}

      <TouchableOpacity
        style={c.sendBtn}
        onPress={(e) => { e.stopPropagation?.(); onSendToFriend(item); }}
        activeOpacity={0.8}
      >
        <Text style={c.sendBtnText}>Send to a friend</Text>
      </TouchableOpacity>
    </TouchableOpacity>
  );
});
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
  cardFlagged: { opacity: 0.85 },
  flaggedBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start',
    backgroundColor: colors.coralSoft ?? '#fbe2df', borderRadius: radius.pill,
    paddingHorizontal: 10, paddingVertical: 4, marginBottom: 10,
  },
  flaggedBannerText: { color: colors.coral, fontSize: 11, fontFamily: fonts.bold },
  confirmedBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start',
    backgroundColor: colors.primarySoft, borderRadius: radius.pill,
    paddingHorizontal: 10, paddingVertical: 4, marginBottom: 10,
  },
  confirmedBannerText: { color: colors.primary, fontSize: 11, fontFamily: fonts.bold },
  verifyLabel: { color: colors.muted, fontSize: 11, fontFamily: fonts.semibold, marginTop: 10, marginBottom: 6 },
  verifyRow: { flexDirection: 'row', gap: 8 },
  verifyBtn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    backgroundColor: colors.bg, borderRadius: radius.pill,
    paddingHorizontal: 10, paddingVertical: 8,
  },
  verifyBtnConfirmed: { backgroundColor: colors.primary },
  verifyBtnFlagged: { backgroundColor: colors.coral },
  verifyBtnText: { color: colors.mutedDark, fontSize: 11.5, fontFamily: fonts.bold },
  verifyBtnTextOn: { color: colors.white },
  wrongTypeBtn: {
    alignSelf: 'flex-start', marginTop: 10, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 6,
  },
  wrongTypeText: { color: colors.mutedDark, fontSize: 11.5, fontFamily: fonts.bold },
  typePickerRow: { flexDirection: 'row', gap: 8, marginTop: 8 },
  typePickerBtn: {
    flex: 1, alignItems: 'center', backgroundColor: colors.bg, borderRadius: radius.pill,
    paddingHorizontal: 10, paddingVertical: 8,
  },
  typePickerBtnActive: { backgroundColor: colors.primary },
  typePickerBtnText: { color: colors.mutedDark, fontSize: 11.5, fontFamily: fonts.bold },
  typePickerBtnTextActive: { color: colors.white },
  watchBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start',
    marginTop: 10, backgroundColor: colors.primarySoft, borderRadius: radius.pill,
    paddingHorizontal: 12, paddingVertical: 7,
  },
  watchBtnText: { color: colors.primary, fontSize: 12, fontFamily: fonts.bold },
  sendBtn: {
    alignSelf: 'flex-start', marginTop: 8, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 7,
  },
  sendBtnText: { color: colors.mutedDark, fontSize: 12, fontFamily: fonts.bold },
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
  const avgScore = points.length > 0
    ? Math.round(points.reduce((sum, p) => sum + p.score, 0) / points.length)
    : null;

  return (
    <View style={pg.wrap}>
      <View style={pg.header}>
        <View style={pg.headerLeft}>
          <Text style={pg.title}>Progress — {filterLabel}</Text>
          {avgScore !== null && (
            <Text style={pg.avgText}>Avg score {avgScore}/100{filter === 'all' ? '' : ` (${filter} only)`}</Text>
          )}
          {delta !== null && (
            <Text style={[pg.delta, { color: scoreColor(points[points.length - 1].score) }]}>
              {delta >= 0 ? '+' : ''}{delta} since your first shot
            </Text>
          )}
        </View>
        {points.length > 0 && Platform.OS !== 'web' && (
          <TouchableOpacity
            style={pg.shareBtn}
            onPress={() => captureAndShare(shareCardRef, 'Share your RallyMax progress')}
          >
            <ShareIcon size={15} color={colors.mutedDark} />
          </TouchableOpacity>
        )}
      </View>

      <View style={pg.filterRow}>
        <TouchableOpacity
          style={[pg.pill, pg.overallPill, filter === 'all' && pg.pillActive]}
          onPress={() => setFilter('all')}
        >
          <Text style={[pg.pillText, filter === 'all' && pg.pillTextActive]}>Overall Improvement</Text>
        </TouchableOpacity>
      </View>
      <View style={pg.filterRow}>
        {SHOT_TYPES.map(f => (
          <TouchableOpacity
            key={f}
            style={[pg.pill, filter === f && pg.pillActive]}
            onPress={() => setFilter(f)}
          >
            <Text style={[pg.pillText, filter === f && pg.pillTextActive]}>
              {f.charAt(0).toUpperCase() + f.slice(1)}
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
  avgText: { color: colors.mutedDark, fontSize: 12, fontFamily: fonts.semibold, marginTop: 3 },
  delta: { fontSize: 12, fontFamily: fonts.bold, marginTop: 2 },
  shareBtn: {
    width: 30, height: 30, borderRadius: 15, backgroundColor: colors.bg,
    alignItems: 'center', justifyContent: 'center',
  },
  filterRow: { flexDirection: 'row', gap: 6, marginBottom: 8 },
  pill: { flex: 1, backgroundColor: colors.bg, borderRadius: radius.pill, paddingVertical: 7, alignItems: 'center' },
  overallPill: { backgroundColor: colors.primarySoft },
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
        onPress={() => { playTapSound(); submit(); }}
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
export default function HistoryScreen({ navigation, route }) {
  const { token, isAuthenticated, isPremium } = useAuth();
  const [sendItem, setSendItem] = useState(null);
  const [friendPickerVisible, setFriendPickerVisible] = useState(false);
  const handleSendToFriend = async (friend) => {
    setFriendPickerVisible(false);
    try {
      await shareSwing(token, friend.id, sendItem.id);
      Alert.alert('Sent!', `${friend.name} can now see this swing on Friends.`);
    } catch (err) {
      Alert.alert('Could not send', err.message || 'Something went wrong');
    }
  };
  const [segment, setSegment] = useState('history'); // history | drills | lessons
  const [showUpload, setShowUpload]   = useState(false);
  const [loading, setLoading]         = useState(true);
  const [analyses, setAnalyses]       = useState([]);
  const [limit, setLimit]             = useState(null);
  // Seeded from Home's "Great swings" tile (navigation.navigate('MainTabs',
  // { screen: 'History', params: { initialFilter: 'great' } })) -- re-synced
  // whenever that param changes (e.g. tapping the tile again from Home while
  // already on this tab), but otherwise left alone so the user's own "Clear
  // filter" tap sticks instead of being fought by a stale param.
  const [listFilter, setListFilter] = useState(route.params?.initialFilter ?? null);
  useEffect(() => {
    if (route.params?.initialFilter) setListFilter(route.params.initialFilter);
  }, [route.params?.initialFilter]);

  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  const load = useCallback(async () => {
    if (!isAuthenticated) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const data = await fetchHistory(token);
      if (!mountedRef.current) return;
      setAnalyses(data.analyses ?? []);
      setLimit(data.limit ?? null);
    } catch {
      // Leave whatever was previously loaded rather than blanking the screen
      // on a transient network failure.
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [token, isAuthenticated]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  // All six handlers below are wrapped in useCallback and take `item`
  // explicitly (rather than closing over it) so AnalysisCard receives the
  // same function reference across HistoryScreen re-renders -- required for
  // memo(AnalysisCard) above to actually skip re-rendering cards whose data
  // hasn't changed. See the comment on AnalysisCard.
  const handleUpload = useCallback(({ videoUri, shotType }) => {
    setShowUpload(false);
    // Navigate to contact marking so they can pick the exact frame — saving
    // happens automatically from ResultsScreen once analysis completes, and
    // this list picks it up next time the tab regains focus.
    navigation.navigate('Upload', { videoUri, shotType });
  }, [navigation]);

  const handleToggleFlag = useCallback(async (item) => {
    const nextFlagged = !item.flagged_not_shot;
    // Optimistic update -- toggling this should feel instant, and a failed
    // request just gets corrected back on the next load() below. Mutually
    // exclusive with confirmed_real_shot, same as the backend enforces.
    setAnalyses((prev) => prev.map((a) => (a.id === item.id
      ? { ...a, flagged_not_shot: nextFlagged, confirmed_real_shot: nextFlagged ? false : a.confirmed_real_shot }
      : a)));
    try {
      await flagNotShot(token, item.id, nextFlagged);
    } catch (err) {
      Alert.alert('Could not update flag', err.message || 'Something went wrong');
      load();
    }
  }, [token, load]);

  const handleToggleConfirm = useCallback(async (item) => {
    const nextConfirmed = !item.confirmed_real_shot;
    setAnalyses((prev) => prev.map((a) => (a.id === item.id
      ? { ...a, confirmed_real_shot: nextConfirmed, flagged_not_shot: nextConfirmed ? false : a.flagged_not_shot }
      : a)));
    try {
      await confirmRealShot(token, item.id, nextConfirmed);
    } catch (err) {
      Alert.alert('Could not update confirmation', err.message || 'Something went wrong');
      load();
    }
  }, [token, load]);

  const handleCorrectType = useCallback(async (item, newShotType) => {
    if (newShotType === item.shot_type) return;
    const prevShotType = item.shot_type;
    setAnalyses((prev) => prev.map((a) => (a.id === item.id ? { ...a, shot_type: newShotType } : a)));
    try {
      await correctShotType(token, item.id, newShotType);
    } catch (err) {
      Alert.alert('Could not update shot type', err.message || 'Something went wrong');
      setAnalyses((prev) => prev.map((a) => (a.id === item.id ? { ...a, shot_type: prevShotType } : a)));
    }
  }, [token]);

  // History cards only carry a slimmed-down result (no overlay trajectories
  // -- see backend/src/routes/history.js's serializeRowSummary), so opening
  // a card needs the real thing fetched fresh, not whatever's already on
  // the item.
  const openResult = useCallback(async (item) => {
    try {
      const full = await fetchHistoryItem(token, item.id);
      navigation.navigate('Results', {
        savedResult: full.result,
        analysisId: item.id,
        shotType: item.shot_type,
        flaggedNotShot: item.flagged_not_shot,
        confirmedRealShot: item.confirmed_real_shot,
      });
    } catch (err) {
      Alert.alert('Could not open analysis', err.message || 'Something went wrong');
    }
  }, [token, navigation]);

  const handleDelete = useCallback((item) => {
    Alert.alert('Delete this analysis?', `${formatProId(item.pro_id, item.result?.matches?.[0]?.player_name)} — this can't be undone.`, [
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
  }, [token, load]);

  const handleWatchCompare = useCallback((item) => {
    navigateToWatchCompare(navigation, token, item);
  }, [navigation, token]);

  const handleSendToFriendPress = useCallback((item) => {
    setSendItem(item);
    setFriendPickerVisible(true);
  }, []);

  const atCap = limit != null && analyses.length >= limit;
  const filteredAnalyses = listFilter === 'great' ? analyses.filter(a => a.similarity >= 75) : analyses;

  const SegmentToggle = (
    <View style={s.segmentRow}>
      <TouchableOpacity style={[s.segmentBtn, segment === 'history' && s.segmentBtnActive]} onPress={() => setSegment('history')}>
        <Text style={[s.segmentText, segment === 'history' && s.segmentTextActive]}>History</Text>
      </TouchableOpacity>
      <TouchableOpacity style={[s.segmentBtn, segment === 'drills' && s.segmentBtnActive]} onPress={() => setSegment('drills')}>
        <Text style={[s.segmentText, segment === 'drills' && s.segmentTextActive]}>Drills</Text>
      </TouchableOpacity>
      <TouchableOpacity style={[s.segmentBtn, segment === 'lessons' && s.segmentBtnActive]} onPress={() => setSegment('lessons')}>
        <Text style={[s.segmentText, segment === 'lessons' && s.segmentTextActive]}>Lessons</Text>
      </TouchableOpacity>
    </View>
  );

  // ── Guest state ─────────────────────────────────────────────────────────
  if (!isAuthenticated) {
    return (
      <SafeAreaView style={s.safe}>
        <CourtBackground />
        <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
          <View style={s.header}>
            <Text style={s.title}>{segment === 'drills' ? 'Drills' : segment === 'lessons' ? 'Lessons' : 'History'}</Text>
          </View>
          {SegmentToggle}
          {segment === 'drills' ? (
            <DrillsSection navigation={navigation} />
          ) : segment === 'lessons' ? (
            <LessonsSection navigation={navigation} />
          ) : (
            <View style={s.empty}>
              <Text style={s.emptyTitle}>Log in to see your history</Text>
              <Text style={s.emptySub}>Your saved analyses live on your account — log in or sign up to start building your history.</Text>
              <TouchableOpacity style={s.emptyBtn} onPress={() => navigation.navigate('Login')}>
                <Text style={s.emptyBtnText}>Log in →</Text>
              </TouchableOpacity>
            </View>
          )}
        </ScrollView>
      </SafeAreaView>
    );
  }

  // The card list used to be a plain `.map()` inside the screen's one big
  // ScrollView -- every saved analysis rendered (and re-rendered) at once,
  // unbounded, with no windowing. Fine for 3 free-tier rows, real for a
  // premium account with hundreds. Only the 'history' segment has this
  // problem (drills/lessons don't render per-analysis rows), so only it
  // gets a FlatList; everything that used to sit above the cards (title,
  // segment toggle, upload panel, progress/stats, cap notice, filter
  // banner) moves into ListHeaderComponent, and the two empty-state
  // messages move into ListEmptyComponent.
  const renderAnalysisCard = useCallback(({ item }) => (
    <AnalysisCard
      item={item}
      onPress={openResult}
      onLongPress={handleDelete}
      onWatchCompare={handleWatchCompare}
      onToggleFlag={handleToggleFlag}
      onToggleConfirm={handleToggleConfirm}
      onCorrectType={handleCorrectType}
      onSendToFriend={handleSendToFriendPress}
    />
  ), [openResult, handleDelete, handleWatchCompare, handleToggleFlag, handleToggleConfirm, handleCorrectType, handleSendToFriendPress]);

  // Matches the original `{!loading && (...)}` gate, which hid the cards
  // (and both empty states) during a refetch even though stale `analyses`
  // was still sitting in state -- preserved rather than "improved" here,
  // since changing that is a separate, unrequested behaviour change.
  const historyListData = loading ? [] : filteredAnalyses;

  const historyListHeader = (
    <>
      <View style={s.header}>
        <Text style={s.title}>History</Text>
        {!showUpload && (
          <TouchableOpacity style={s.newBtn} onPress={() => setShowUpload(true)}>
            <PlusIcon size={13} color={colors.white} />
            <Text style={s.newBtnText}>New</Text>
          </TouchableOpacity>
        )}
      </View>

      {SegmentToggle}

      {showUpload && (
        <UploadPanel onCancel={() => setShowUpload(false)} onUpload={handleUpload} />
      )}

      {loading && (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 40 }} />
      )}

      {!loading && !showUpload && analyses.length > 0 && (
        <ProgressSection analyses={analyses} />
      )}

      {!loading && !showUpload && analyses.length > 0 && (
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

      {!loading && !showUpload && atCap && !isPremium && (
        <TouchableOpacity
          style={s.capCard}
          onPress={() => navigation.navigate('Premium')}
        >
          <Text style={s.capText}>You've saved {limit}/{limit} shots on the free plan. Delete one, or <Text style={s.capTextBold}>upgrade to save unlimited →</Text></Text>
        </TouchableOpacity>
      )}

      {!loading && listFilter === 'great' && (
        <View style={s.filterBanner}>
          <Text style={s.filterBannerText}>Showing {filteredAnalyses.length} great swing{filteredAnalyses.length === 1 ? '' : 's'} (score ≥ 75)</Text>
          <TouchableOpacity onPress={() => setListFilter(null)}>
            <Text style={s.filterBannerClear}>Clear filter</Text>
          </TouchableOpacity>
        </View>
      )}
    </>
  );

  const historyListEmpty = loading ? null : (
    <>
      {analyses.length === 0 && !showUpload && (
        <View style={s.empty}>
          <Text style={s.emptyTitle}>No analyses yet</Text>
          <Text style={s.emptySub}>Upload a swing video to get matched to a pro and receive personalised coaching tips.</Text>
          <TouchableOpacity style={s.emptyBtn} onPress={() => setShowUpload(true)}>
            <Text style={s.emptyBtnText}>Upload your first swing →</Text>
          </TouchableOpacity>
        </View>
      )}
      {analyses.length > 0 && filteredAnalyses.length === 0 && (
        <Text style={s.emptySub}>No great swings yet — keep practising, or clear the filter to see everything.</Text>
      )}
    </>
  );

  return (
    <SafeAreaView style={s.safe}>
      <CourtBackground />
      {segment === 'history' ? (
        <FlatList
          data={historyListData}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderAnalysisCard}
          contentContainerStyle={s.scroll}
          showsVerticalScrollIndicator={false}
          ListHeaderComponent={historyListHeader}
          ListEmptyComponent={historyListEmpty}
        />
      ) : (
        <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
          <View style={s.header}>
            <Text style={s.title}>{segment === 'drills' ? 'Drills' : 'Lessons'}</Text>
          </View>
          {SegmentToggle}
          {segment === 'drills' && <DrillsSection navigation={navigation} />}
          {segment === 'lessons' && <LessonsSection navigation={navigation} />}
        </ScrollView>
      )}

      <FriendPickerModal
        visible={friendPickerVisible}
        onClose={() => setFriendPickerVisible(false)}
        onSelect={handleSendToFriend}
      />
    </SafeAreaView>
  );
}

// Same nav params ResultsScreen's "Compare side-by-side" button builds,
// triggered one level earlier so a saved swing's synced video view is
// reachable directly from the History list. Needs the full (non-slimmed)
// result for the overlay/racket-path data, same reasoning as openResult()
// above -- the list's own item.result has had those stripped.
async function navigateToWatchCompare(navigation, token, item) {
  let result;
  try {
    result = (await fetchHistoryItem(token, item.id)).result;
  } catch {
    Alert.alert('Could not open comparison', 'Something went wrong');
    return;
  }
  const top = result?.matches?.[0];
  if (!top?.pro_clip_url || !result?.user_clip_url) return;
  navigation.navigate('SyncCompare', {
    videoAUrl: `${API_BASE}${top.pro_clip_url}`,
    videoBUrl: `${API_BASE}${result.user_clip_url}`,
    contactASec: top.pro_contact_time_sec ?? 0,
    contactBSec: result.contact_time_sec ?? 0,
    overlayA: top.pro_overlay_trajectory ?? null,
    overlayB: result.user_overlay_trajectory ?? null,
    racketPathA: top.pro_racket_overlay_trajectory ?? null,
    racketPathB: result.racket_overlay_trajectory ?? null,
    labelA: formatProId(top.pro_id, top.player_name),
    labelB: 'You',
    analysisId: item.id,
    canAddNotes: false,
    phaseMarkers: top.phase_markers ?? undefined,
  });
}

function formatProId(proId, playerName) {
  if (!proId) return 'Analysis';
  const [shot, num] = proId.split('_');
  if (!shot || !num) return proId;
  const label = shot.charAt(0).toUpperCase() + shot.slice(1);
  if (playerName) return `${playerName}'s ${label}`;
  return `${label} Technique #${parseInt(num, 10)}`;
}

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingBottom: 130 },

  header: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'center', marginBottom: spacing.xl, paddingTop: 8,
  },
  title: { color: colors.ink, fontSize: 32, fontFamily: fonts.serifItalic },
  segmentRow: { flexDirection: 'row', gap: 8, marginBottom: spacing.xl },
  segmentBtn: { flex: 1, alignItems: 'center', backgroundColor: colors.surface, borderRadius: radius.pill, paddingVertical: 11 },
  segmentBtnActive: { backgroundColor: colors.primary },
  segmentText: { color: colors.mutedDark, fontSize: 13.5, fontFamily: fonts.bold },
  segmentTextActive: { color: colors.white },
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

  filterBanner: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    backgroundColor: colors.primarySoft, borderRadius: radius.sm, padding: 13, marginBottom: spacing.lg,
  },
  filterBannerText: { color: colors.primary, fontSize: 12.5, fontFamily: fonts.semibold, flex: 1, marginRight: 10 },
  filterBannerClear: { color: colors.primary, fontSize: 12.5, fontFamily: fonts.bold },

  empty: { alignItems: 'center', paddingVertical: 60 },
  emptyTitle: { color: colors.ink, fontSize: 20, fontFamily: fonts.extrabold, marginBottom: 8 },
  emptySub:   { color: colors.muted, fontSize: 14, textAlign: 'center', lineHeight: 21, marginBottom: 28, paddingHorizontal: 20, fontFamily: fonts.regular },
  emptyBtn:   { backgroundColor: colors.primary, borderRadius: radius.md, paddingVertical: 14, paddingHorizontal: 28 },
  emptyBtnText: { color: colors.white, fontSize: 15, fontFamily: fonts.bold },
});
