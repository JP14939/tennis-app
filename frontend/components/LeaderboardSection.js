import { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, TextInput, StyleSheet, ActivityIndicator } from 'react-native';
import Alert from '../utils/alert';
import { useFocusEffect } from '@react-navigation/native';
import { useAuth } from '../context/AuthContext';
import { getFriendsLeaderboard, getWorldwideLeaderboard, addCelebrity } from '../api/leaderboard';
import { colors, fonts, radius } from '../theme';
import { playTapSound } from '../utils/sounds';
import { isAdmin } from '../utils/isAdmin';
import { SHOT_TYPES as SHOT_TYPE_VALUES } from '../config/shotTypes';

const SHOT_TYPES = SHOT_TYPE_VALUES.map((value) => ({ label: value[0].toUpperCase() + value.slice(1), value }));

function Row({ rank, name, score, badge, highlighted }) {
  return (
    <View style={[r.row, highlighted && r.rowHighlighted]}>
      <Text style={[r.rank, highlighted && r.rankHighlighted]}>{rank}</Text>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={[r.name, highlighted && r.nameHighlighted]} numberOfLines={1}>{name}</Text>
      </View>
      {badge && (
        <View style={r.badge}>
          <Text style={r.badgeText}>{badge}</Text>
        </View>
      )}
      <Text style={[r.score, highlighted && r.scoreHighlighted]}>{Math.round(score)}</Text>
    </View>
  );
}
const r = StyleSheet.create({
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: colors.surface, borderRadius: radius.md, padding: 13, marginBottom: 8,
  },
  rowHighlighted: { backgroundColor: colors.primary },
  rank: { color: colors.muted, fontSize: 14, fontFamily: fonts.extrabold, width: 24, textAlign: 'center' },
  rankHighlighted: { color: 'rgba(255,255,255,0.7)' },
  name: { color: colors.ink, fontSize: 14, fontFamily: fonts.semibold },
  nameHighlighted: { color: colors.white },
  score: { color: colors.ink, fontSize: 16, fontFamily: fonts.extrabold },
  scoreHighlighted: { color: colors.white },
  badge: {
    backgroundColor: colors.gold, borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 3,
  },
  badgeText: { color: colors.white, fontSize: 9.5, fontFamily: fonts.extrabold, letterSpacing: 0.4 },
});

export default function LeaderboardSection() {
  const { token, user } = useAuth();
  const [tab, setTab] = useState('friends'); // friends | worldwide
  const [shotType, setShotType] = useState('forehand');
  const [leaderboard, setLeaderboard] = useState([]);
  const [loading, setLoading] = useState(true);

  const [celebName, setCelebName] = useState('');
  const [celebScore, setCelebScore] = useState('');
  const [celebNote, setCelebNote] = useState('');
  const [submittingCeleb, setSubmittingCeleb] = useState(false);

  // load() re-runs on every tab/shotType change -- without this guard,
  // rapidly tapping between shot-type filter pills could let an older,
  // slower response overwrite the list after a newer selection's response
  // already landed.
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  const load = useCallback(() => {
    setLoading(true);
    const fetcher = tab === 'friends' ? getFriendsLeaderboard : getWorldwideLeaderboard;
    fetcher(token, shotType)
      .then((data) => { if (mountedRef.current) setLeaderboard(data.leaderboard); })
      .catch(() => {})
      .finally(() => { if (mountedRef.current) setLoading(false); });
  }, [token, tab, shotType]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const userIsAdmin = isAdmin(user);

  const submitCelebrity = async () => {
    const score = parseFloat(celebScore);
    if (!celebName.trim() || Number.isNaN(score)) {
      Alert.alert('Missing info', 'Enter a name and a numeric score.');
      return;
    }
    setSubmittingCeleb(true);
    try {
      await addCelebrity(token, { name: celebName.trim(), shotType, score, note: celebNote.trim() || undefined });
      setCelebName('');
      setCelebScore('');
      setCelebNote('');
      load();
    } catch (err) {
      Alert.alert('Could not add', err.message || 'Something went wrong');
    } finally {
      setSubmittingCeleb(false);
    }
  };

  return (
    <View>
      <View style={s.tabRow}>
        <TouchableOpacity style={[s.tab, tab === 'friends' && s.tabActive]} onPress={() => setTab('friends')}>
          <Text style={[s.tabText, tab === 'friends' && s.tabTextActive]}>Friends</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[s.tab, tab === 'worldwide' && s.tabActive]} onPress={() => setTab('worldwide')}>
          <Text style={[s.tabText, tab === 'worldwide' && s.tabTextActive]}>Worldwide</Text>
        </TouchableOpacity>
      </View>

      <View style={s.shotRow}>
        {SHOT_TYPES.map((st) => (
          <TouchableOpacity
            key={st.value}
            style={[s.shotPill, shotType === st.value && s.shotPillActive]}
            onPress={() => setShotType(st.value)}
          >
            <Text style={[s.shotPillText, shotType === st.value && s.shotPillTextActive]}>{st.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 30 }} />
      ) : leaderboard.length === 0 ? (
        <Text style={s.empty}>
          {tab === 'friends'
            // Home only renders this section once the user has at least one
            // analysis (see HomeScreen.js), so by the time this can show,
            // the one thing actually missing is friends -- not "add friends
            // and analyse a swing", which asked for two things and reads as
            // neither.
            ? 'No scores yet — add friends to see how you compare.'
            : 'No scores yet for this category.'}
        </Text>
      ) : (
        leaderboard.map((entry, i) => (
          <Row
            key={entry.type === 'celebrity' ? `c${entry.id}` : `u${entry.user_id}`}
            rank={i + 1}
            name={entry.type === 'celebrity' ? entry.name : (entry.username ? `@${entry.username}` : entry.name)}
            score={entry.score}
            badge={entry.type === 'celebrity' ? 'PRO' : null}
            highlighted={entry.is_me}
          />
        ))
      )}

      {tab === 'worldwide' && userIsAdmin && (
        <View style={s.adminForm}>
          <Text style={s.adminTitle}>Add a pro/celebrity score</Text>
          <TextInput
            style={s.input}
            value={celebName}
            onChangeText={setCelebName}
            placeholder="Name, e.g. Roger Federer"
            placeholderTextColor={colors.muted}
          />
          <TextInput
            style={s.input}
            value={celebScore}
            onChangeText={setCelebScore}
            placeholder={`Score for ${shotType} (0-100)`}
            placeholderTextColor={colors.muted}
            keyboardType="decimal-pad"
          />
          <TextInput
            style={s.input}
            value={celebNote}
            onChangeText={setCelebNote}
            placeholder="Note (optional)"
            placeholderTextColor={colors.muted}
          />
          <TouchableOpacity style={s.adminBtn} onPress={() => { playTapSound(); submitCelebrity(); }} disabled={submittingCeleb}>
            <Text style={s.adminBtnText}>{submittingCeleb ? 'Adding...' : `Add to ${shotType} leaderboard`}</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  tabRow: { flexDirection: 'row', gap: 8, marginBottom: 14 },
  tab: { flex: 1, alignItems: 'center', backgroundColor: colors.surface, borderRadius: radius.pill, paddingVertical: 11 },
  tabActive: { backgroundColor: colors.primary },
  tabText: { color: colors.mutedDark, fontSize: 13.5, fontFamily: fonts.bold },
  tabTextActive: { color: colors.white },

  shotRow: { flexDirection: 'row', gap: 8, marginBottom: 16 },
  shotPill: { flex: 1, alignItems: 'center', backgroundColor: colors.surface, borderRadius: radius.pill, paddingVertical: 9 },
  shotPillActive: { backgroundColor: colors.lime },
  shotPillText: { color: colors.mutedDark, fontSize: 12.5, fontFamily: fonts.bold },
  shotPillTextActive: { color: colors.primary },

  empty: { color: colors.muted, fontSize: 13, textAlign: 'center', marginTop: 20, lineHeight: 19, fontFamily: fonts.regular },

  adminForm: {
    backgroundColor: colors.surface, borderRadius: radius.lg, padding: 16, marginTop: 12,
  },
  adminTitle: { color: colors.ink, fontSize: 14, fontFamily: fonts.bold, marginBottom: 10 },
  input: {
    backgroundColor: colors.bg, borderRadius: radius.sm, paddingHorizontal: 12, paddingVertical: 10,
    color: colors.ink, fontSize: 13.5, fontFamily: fonts.regular, marginBottom: 8,
  },
  adminBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingVertical: 12, alignItems: 'center' },
  adminBtnText: { color: colors.white, fontSize: 13, fontFamily: fonts.bold },
});
