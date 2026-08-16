import { useCallback, useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, TextInput, StyleSheet,
  SafeAreaView, ScrollView, ActivityIndicator, Alert,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { useAuth } from '../context/AuthContext';
import {
  getFriendCode, linkFriend, getFriends, unfriend, getMatches, logMatch, deleteMatch,
  getSharedSwings, getSharedAnalysis,
} from '../api/friends';
import { colors, fonts, radius, spacing } from '../theme';
import { BackChevronIcon } from '../components/icons';
import MessagesSection from '../components/MessagesSection';
import { playTapSound, playAchievementSound } from '../utils/sounds';

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function formatDate(isoString) {
  if (!isoString) return '';
  const d = new Date(isoString.length <= 10 ? `${isoString}T00:00:00` : isoString);
  if (Number.isNaN(d.getTime())) return isoString;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function Section({ title, children }) {
  return (
    <View style={sec.wrap}>
      <Text style={sec.title}>{title}</Text>
      {children}
    </View>
  );
}
const sec = StyleSheet.create({
  wrap: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: 16, marginBottom: spacing.lg },
  title: { color: colors.ink, fontSize: 14.5, fontFamily: fonts.bold, marginBottom: 12 },
});

// ── One friend's head-to-head record + match log ────────────────────────────
function FriendDetail({ friend, onBack, onRecordChanged, navigation }) {
  const { token, user } = useAuth();
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [playedAt, setPlayedAt] = useState(todayISO());
  const [setsWon, setSetsWon] = useState('2');
  const [setsLost, setSetsLost] = useState('0');
  const [scoreDetail, setScoreDetail] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const [shared, setShared] = useState([]);
  const [loadingShared, setLoadingShared] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    getMatches(token, friend.id).then((data) => setMatches(data.matches)).catch(() => {}).finally(() => setLoading(false));
  }, [token, friend.id]);

  const loadShared = useCallback(() => {
    setLoadingShared(true);
    getSharedSwings(token, friend.id).then((data) => setShared(data.shared)).catch(() => {}).finally(() => setLoadingShared(false));
  }, [token, friend.id]);

  useFocusEffect(useCallback(() => { load(); loadShared(); }, [load, loadShared]));

  const openSharedSwing = async (item) => {
    try {
      const analysis = await getSharedAnalysis(token, item.analysis_id);
      navigation.navigate('Results', {
        savedResult: analysis.result,
        analysisId: analysis.id,
        shotType: analysis.shot_type,
        canAddNotes: false,
      });
    } catch (err) {
      Alert.alert('Could not open swing', err.message || 'Something went wrong');
    }
  };

  const record = matches.reduce((acc, m) => {
    if (m.my_sets > m.their_sets) acc.wins += 1;
    else if (m.my_sets < m.their_sets) acc.losses += 1;
    return acc;
  }, { wins: 0, losses: 0 });

  const submit = async () => {
    const sw = parseInt(setsWon, 10);
    const sl = parseInt(setsLost, 10);
    if (!playedAt || Number.isNaN(sw) || Number.isNaN(sl)) {
      Alert.alert('Missing info', 'Enter a date and sets won/lost.');
      return;
    }
    setSubmitting(true);
    try {
      await logMatch(token, friend.id, { playedAt, setsWon: sw, setsLost: sl, scoreDetail: scoreDetail.trim() || undefined });
      setScoreDetail('');
      load();
      onRecordChanged();
    } catch (err) {
      Alert.alert('Could not log match', err.message || 'Something went wrong');
    } finally {
      setSubmitting(false);
    }
  };

  const remove = (matchId) => {
    Alert.alert('Delete this match?', 'This only removes your own logged entry.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete', style: 'destructive', onPress: async () => {
          try {
            await deleteMatch(token, matchId);
            load();
            onRecordChanged();
          } catch (err) {
            Alert.alert('Could not delete', err.message || 'Something went wrong');
          }
        },
      },
    ]);
  };

  const displayName = friend.username ? `@${friend.username}` : friend.name;

  return (
    <View>
      <TouchableOpacity style={d.backLink} onPress={onBack}>
        <BackChevronIcon size={13} color={colors.muted} />
        <Text style={d.backLinkText}>Friends</Text>
      </TouchableOpacity>
      <Text style={d.name}>{displayName}</Text>
      <Text style={d.record}>{record.wins}–{record.losses} head-to-head</Text>

      <Section title="Log a match">
        <Text style={d.label}>Date (YYYY-MM-DD)</Text>
        <TextInput style={d.input} value={playedAt} onChangeText={setPlayedAt} placeholder={todayISO()} placeholderTextColor={colors.muted} />
        <View style={d.setsRow}>
          <View style={{ flex: 1 }}>
            <Text style={d.label}>Sets you won</Text>
            <TextInput style={d.input} value={setsWon} onChangeText={setSetsWon} keyboardType="number-pad" />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={d.label}>Sets you lost</Text>
            <TextInput style={d.input} value={setsLost} onChangeText={setSetsLost} keyboardType="number-pad" />
          </View>
        </View>
        <Text style={d.label}>Score detail (optional)</Text>
        <TextInput style={d.input} value={scoreDetail} onChangeText={setScoreDetail} placeholder="e.g. 6-4, 3-6, 7-5" placeholderTextColor={colors.muted} />
        <TouchableOpacity style={d.submitBtn} onPress={submit} disabled={submitting}>
          <Text style={d.submitBtnText}>{submitting ? 'Saving...' : 'Save match'}</Text>
        </TouchableOpacity>
      </Section>

      <Text style={d.sectionTitle}>Match history</Text>
      {loading ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 12 }} />
      ) : matches.length === 0 ? (
        <Text style={d.emptyText}>No matches logged yet.</Text>
      ) : (
        matches.map((m) => (
          <View key={m.id} style={d.matchCard}>
            <View style={{ flex: 1 }}>
              <Text style={d.matchScore}>{m.my_sets}–{m.their_sets} {m.my_sets > m.their_sets ? 'win' : m.my_sets < m.their_sets ? 'loss' : 'tie'}</Text>
              <Text style={d.matchDate}>{formatDate(m.played_at)}{m.score_detail ? ` · ${m.score_detail}` : ''}</Text>
              {!m.logged_by_me && <Text style={d.matchLoggedBy}>Logged by {displayName}</Text>}
            </View>
            {m.logged_by_me && (
              <TouchableOpacity onPress={() => remove(m.id)}>
                <Text style={d.deleteText}>Delete</Text>
              </TouchableOpacity>
            )}
          </View>
        ))
      )}

      <Text style={d.sectionTitle}>Shared swings</Text>
      {loadingShared ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 12 }} />
      ) : shared.length === 0 ? (
        <Text style={d.emptyText}>No swings sent between you yet — send one from Results or History.</Text>
      ) : (
        shared.map((item) => (
          <TouchableOpacity key={item.id} style={d.matchCard} onPress={() => openSharedSwing(item)}>
            <View style={{ flex: 1 }}>
              <Text style={d.matchScore}>
                {item.shot_type?.charAt(0).toUpperCase() + item.shot_type?.slice(1)} · {Math.round(item.similarity ?? 0)}/100
              </Text>
              <Text style={d.matchDate}>{item.direction === 'sent' ? 'You sent' : `${displayName} sent`} · {formatDate(item.shared_at)}</Text>
            </View>
          </TouchableOpacity>
        ))
      )}
    </View>
  );
}
const d = StyleSheet.create({
  backLink: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 14 },
  backLinkText: { color: colors.muted, fontSize: 13, fontFamily: fonts.semibold },
  name: { color: colors.ink, fontSize: 22, fontFamily: fonts.serifItalic },
  record: { color: colors.muted, fontSize: 13.5, marginTop: 4, marginBottom: 18, fontFamily: fonts.semibold },

  label: { color: colors.muted, fontSize: 11.5, fontFamily: fonts.semibold, marginBottom: 4 },
  input: {
    backgroundColor: colors.bg, borderRadius: radius.sm, paddingHorizontal: 12, paddingVertical: 10,
    color: colors.ink, fontSize: 13.5, fontFamily: fonts.regular, marginBottom: 10,
  },
  setsRow: { flexDirection: 'row', gap: 10 },
  submitBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingVertical: 12, alignItems: 'center' },
  submitBtnText: { color: colors.white, fontSize: 13.5, fontFamily: fonts.bold },

  sectionTitle: { color: colors.ink, fontSize: 15.5, fontFamily: fonts.bold, marginBottom: 10 },
  emptyText: { color: colors.muted, fontSize: 13, fontFamily: fonts.regular, textAlign: 'center', paddingVertical: 20 },
  matchCard: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: colors.surface, borderRadius: radius.md, padding: 13, marginBottom: 8,
  },
  matchScore: { color: colors.ink, fontSize: 14.5, fontFamily: fonts.bold },
  matchDate: { color: colors.muted, fontSize: 12, marginTop: 2, fontFamily: fonts.regular },
  matchLoggedBy: { color: colors.muted, fontSize: 11, marginTop: 2, fontStyle: 'italic', fontFamily: fonts.regular },
  deleteText: { color: colors.coral, fontSize: 12.5, fontFamily: fonts.bold },
});

// ── Main screen ────────────────────────────────────────────────────────────
export default function FriendsScreen({ navigation, route }) {
  const { token } = useAuth();
  const [segment, setSegment] = useState(route?.params?.initialSegment === 'messages' ? 'messages' : 'friends');
  useEffect(() => {
    if (route?.params?.initialSegment) setSegment(route.params.initialSegment);
  }, [route?.params?.initialSegment]);
  const [inviteCode, setInviteCode] = useState(null);
  const [generating, setGenerating] = useState(false);

  const [linkCodeInput, setLinkCodeInput] = useState('');
  const [linking, setLinking] = useState(false);

  const [friends, setFriends] = useState([]);
  const [loadingFriends, setLoadingFriends] = useState(true);
  const [selectedFriend, setSelectedFriend] = useState(null);

  const loadFriends = useCallback(() => {
    setLoadingFriends(true);
    getFriends(token)
      .then((data) => setFriends(data.friends))
      .catch(() => {})
      .finally(() => setLoadingFriends(false));
  }, [token]);

  useFocusEffect(useCallback(() => { loadFriends(); }, [loadFriends]));

  const generateCode = async () => {
    setGenerating(true);
    try {
      const data = await getFriendCode(token);
      setInviteCode(data.code);
    } catch (err) {
      Alert.alert('Could not generate code', err.message || 'Something went wrong');
    } finally {
      setGenerating(false);
    }
  };

  const submitLink = async () => {
    if (!linkCodeInput.trim()) return;
    setLinking(true);
    try {
      const data = await linkFriend(token, linkCodeInput.trim().toUpperCase());
      setLinkCodeInput('');
      playAchievementSound();
      Alert.alert('Added!', `You're now friends with ${data.friend.name}.`);
      loadFriends();
    } catch (err) {
      Alert.alert('Could not add friend', err.message || 'Invalid or already-used code');
    } finally {
      setLinking(false);
    }
  };

  const handleUnfriend = (friend) => {
    Alert.alert(`Remove ${friend.name}?`, 'This removes the friendship and your shared match history view.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Remove', style: 'destructive', onPress: async () => {
          try {
            await unfriend(token, friend.id);
            loadFriends();
          } catch (err) {
            Alert.alert('Could not remove', err.message || 'Something went wrong');
          }
        },
      },
    ]);
  };

  if (selectedFriend) {
    return (
      <SafeAreaView style={s.safe}>
        <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
          <FriendDetail
            friend={selectedFriend}
            onBack={() => setSelectedFriend(null)}
            onRecordChanged={loadFriends}
            navigation={navigation}
          />
        </ScrollView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        <Text style={s.h1}>{segment === 'messages' ? 'Messages' : 'Friends'}</Text>
        <Text style={s.sub}>
          {segment === 'messages'
            ? "Chat with players you've matched with on Find Games."
            : "Add friends and keep track of who's winning your head-to-head."}
        </Text>

        <View style={s.segmentRow}>
          <TouchableOpacity style={[s.segmentBtn, segment === 'friends' && s.segmentBtnActive]} onPress={() => setSegment('friends')}>
            <Text style={[s.segmentText, segment === 'friends' && s.segmentTextActive]}>Friends</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[s.segmentBtn, segment === 'messages' && s.segmentBtnActive]} onPress={() => setSegment('messages')}>
            <Text style={[s.segmentText, segment === 'messages' && s.segmentTextActive]}>Messages</Text>
          </TouchableOpacity>
        </View>

        {segment === 'messages' ? (
          <MessagesSection navigation={navigation} />
        ) : (
          <>
            <Section title="Your friend code">
              <Text style={s.helpText}>Share this with a friend so they can add you.</Text>
              {inviteCode ? <Text style={s.codeDisplay}>{inviteCode}</Text> : null}
              <TouchableOpacity style={s.actionBtn} onPress={() => { playTapSound(); generateCode(); }} disabled={generating}>
                <Text style={s.actionBtnText}>
                  {generating ? 'Generating...' : inviteCode ? 'Generate new code' : 'Generate friend code'}
                </Text>
              </TouchableOpacity>
            </Section>

            <Section title="Add a friend">
              <Text style={s.helpText}>Enter a friend's code to add them.</Text>
              <TextInput
                style={s.input}
                value={linkCodeInput}
                onChangeText={setLinkCodeInput}
                placeholder="Friend code"
                placeholderTextColor={colors.muted}
                autoCapitalize="characters"
              />
              <TouchableOpacity
                style={[s.actionBtn, !linkCodeInput.trim() && s.actionBtnDisabled]}
                onPress={() => { playTapSound(); submitLink(); }}
                disabled={linking || !linkCodeInput.trim()}
              >
                <Text style={s.actionBtnText}>{linking ? 'Adding...' : 'Add friend'}</Text>
              </TouchableOpacity>
            </Section>

            <Section title="Your friends">
              {loadingFriends && <ActivityIndicator color={colors.primary} />}
              {!loadingFriends && friends.length === 0 && (
                <Text style={s.helpText}>No friends added yet.</Text>
              )}
              {!loadingFriends && friends.map((friend) => (
                <TouchableOpacity
                  key={friend.id}
                  style={s.friendRow}
                  onPress={() => setSelectedFriend(friend)}
                  onLongPress={() => handleUnfriend(friend)}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={s.friendRowText}>{friend.username ? `@${friend.username}` : friend.name}</Text>
                    <Text style={s.friendRowRecord}>{friend.record.wins}–{friend.record.losses} head-to-head</Text>
                  </View>
                  <Text style={s.chevron}>›</Text>
                </TouchableOpacity>
              ))}
            </Section>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingTop: 24, paddingBottom: 60 },

  h1: { color: colors.ink, fontSize: 28, fontFamily: fonts.serifItalic, marginBottom: 6 },
  sub: { color: colors.muted, fontSize: 13.5, lineHeight: 19, marginBottom: 20, fontFamily: fonts.regular },

  segmentRow: { flexDirection: 'row', gap: 8, marginBottom: 20 },
  segmentBtn: { flex: 1, alignItems: 'center', backgroundColor: colors.surface, borderRadius: radius.pill, paddingVertical: 11 },
  segmentBtnActive: { backgroundColor: colors.primary },
  segmentText: { color: colors.mutedDark, fontSize: 13.5, fontFamily: fonts.bold },
  segmentTextActive: { color: colors.white },

  helpText: { color: colors.muted, fontSize: 12.5, lineHeight: 18, marginBottom: 12, fontFamily: fonts.regular },
  codeDisplay: {
    color: colors.primary, fontSize: 24, fontFamily: fonts.extrabold, letterSpacing: 2,
    textAlign: 'center', backgroundColor: colors.bg, borderRadius: radius.sm,
    paddingVertical: 14, marginBottom: 12,
  },
  input: {
    backgroundColor: colors.bg, borderRadius: radius.sm, paddingHorizontal: 14, paddingVertical: 12,
    color: colors.ink, fontSize: 14, fontFamily: fonts.regular, marginBottom: 10, letterSpacing: 1,
  },
  actionBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingVertical: 12, alignItems: 'center' },
  actionBtnDisabled: { opacity: 0.4 },
  actionBtnText: { color: colors.white, fontSize: 13.5, fontFamily: fonts.bold },

  friendRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingVertical: 13, borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  friendRowText: { color: colors.ink, fontSize: 14.5, fontFamily: fonts.semibold },
  friendRowRecord: { color: colors.muted, fontSize: 12, marginTop: 2, fontFamily: fonts.regular },
  chevron: { color: colors.divider, fontSize: 20 },
});
