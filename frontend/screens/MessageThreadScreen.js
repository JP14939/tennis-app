import { useCallback, useEffect, useMemo, useRef, useState, memo } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, SafeAreaView,
  FlatList, KeyboardAvoidingView, Platform, ActivityIndicator,
} from 'react-native';
import Alert from '../utils/alert';
import { useFocusEffect } from '@react-navigation/native';
import { useAuth } from '../context/AuthContext';
import { getThread, sendMessage, reportMessage, blockUser } from '../api/messages';
import { colors, fonts, radius, spacing } from '../theme';
import { playTapSound, playNotificationSound } from '../utils/sounds';
import { parseServerDate } from '../utils/formatDate';
import { BackChevronIcon } from '../components/icons';

// Same idea as HighlightArchiveScreen's reel-job polling -- no websocket
// layer in this backend, so a short interval while the thread is focused
// is the simplest way to approximate live delivery.
const POLL_INTERVAL_MS = 3000;

function formatTime(isoString) {
  const d = parseServerDate(isoString);
  return d ? d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }) : '';
}

// Backend's GET /messages/thread has no LIMIT (backend/src/routes/messages.js)
// -- a long-running friend conversation is unbounded, and this used to be a
// plain ScrollView + .map() rendering every bubble at once. Memoized and
// virtualized the same way HistoryScreen's card list was.
const MessageBubble = memo(function MessageBubble({ message, mine, onReport }) {
  return (
    <View style={[s.bubbleRow, mine && s.bubbleRowMine]}>
      <TouchableOpacity
        activeOpacity={mine ? 1 : 0.7}
        onLongPress={() => onReport(message)}
        style={[s.bubble, mine ? s.bubbleMine : s.bubbleTheirs]}
      >
        <Text style={[s.bubbleText, mine && s.bubbleTextMine]}>{message.body}</Text>
      </TouchableOpacity>
      <Text style={s.bubbleTime}>{formatTime(message.created_at)}</Text>
    </View>
  );
});

export default function MessageThreadScreen({ route, navigation }) {
  const { otherUserId, otherUserName } = route.params ?? {};
  const { token, user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  // Only set on the initial (non-silent) load, then compared on later
  // silent polls -- opening a thread with existing unread history should
  // never retroactively play a notification for messages already there.
  const lastSeenIdRef = useRef(null);

  const load = useCallback((silent) => {
    if (!silent) setLoading(true);
    getThread(token, otherUserId)
      .then((data) => {
        if (!mountedRef.current) return;
        const msgs = data.messages;
        const newest = msgs[msgs.length - 1];
        if (silent && lastSeenIdRef.current != null && newest
          && newest.id !== lastSeenIdRef.current && newest.sender_id !== user?.id) {
          playNotificationSound();
        }
        if (newest) lastSeenIdRef.current = newest.id;
        setMessages(msgs);
      })
      .catch(() => {})
      .finally(() => { if (mountedRef.current && !silent) setLoading(false); });
  }, [token, otherUserId, user?.id]);

  useFocusEffect(useCallback(() => {
    load(false);
    const interval = setInterval(() => load(true), POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [load]));

  // useCallback so MessageBubble's memo() actually holds across polls --
  // otherwise a fresh closure every 3s poll would defeat it, same reasoning
  // as HistoryScreen's card handlers.
  const handleReport = useCallback((message) => {
    if (message.sender_id === user?.id) return; // reporting your own message makes no sense
    Alert.alert('Report this message?', 'This sends the message to us for review.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Report', style: 'destructive',
        onPress: () => {
          reportMessage(token, message.id).then(
            () => Alert.alert('Reported', 'Thanks — we’ll take a look.'),
            () => Alert.alert('Could not report', 'Something went wrong, try again.'),
          );
        },
      },
    ]);
  }, [token, user?.id]);

  const handleBlock = () => {
    Alert.alert(
      `Block ${otherUserName ?? 'this user'}?`,
      'They won’t be able to message you anymore, and this conversation will disappear from your list.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Block', style: 'destructive',
          onPress: () => {
            blockUser(token, otherUserId).then(
              () => navigation.goBack(),
              () => Alert.alert('Could not block', 'Something went wrong, try again.'),
            );
          },
        },
      ],
    );
  };

  const submit = async () => {
    const body = text.trim();
    if (!body) return;
    setText('');
    setSending(true);
    try {
      await sendMessage(token, otherUserId, body);
      load(true);
    } catch {
      setText(body); // restore on failure so the user doesn't lose their draft
    } finally {
      setSending(false);
    }
  };

  // Newest-first for an inverted FlatList -- this also replaces the old
  // ScrollView's onContentSizeChange->scrollToEnd hack for pinning to the
  // bottom, which raced content layout on some platforms; `inverted` makes
  // "stay at the bottom" the list's natural resting position instead.
  const reversedMessages = useMemo(() => [...messages].reverse(), [messages]);
  const renderMessage = useCallback(({ item }) => (
    <MessageBubble message={item} mine={item.sender_id === user?.id} onReport={handleReport} />
  ), [user?.id, handleReport]);

  return (
    <SafeAreaView style={s.safe}>
      <View style={s.header}>
        <TouchableOpacity style={s.backLink} onPress={() => navigation.goBack()}>
          <BackChevronIcon size={13} color={colors.muted} />
        </TouchableOpacity>
        <Text style={s.headerTitle}>{otherUserName ?? 'Conversation'}</Text>
        <TouchableOpacity style={s.blockLink} onPress={handleBlock}>
          <Text style={s.blockLinkText}>Block</Text>
        </TouchableOpacity>
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        {loading ? (
          <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 40 }} />
        ) : messages.length === 0 ? (
          // Rendered directly rather than via ListEmptyComponent below --
          // an inverted FlatList visually flips its header/empty content
          // through the same transform it uses to pin newest-at-bottom,
          // which would render this text upside down.
          <Text style={s.empty}>Say hello — organise a game!</Text>
        ) : (
          <FlatList
            inverted
            data={reversedMessages}
            keyExtractor={(m) => String(m.id)}
            renderItem={renderMessage}
            contentContainerStyle={s.scroll}
          />
        )}

        <View style={s.composer}>
          <TextInput
            style={s.input}
            value={text}
            onChangeText={setText}
            placeholder="Message..."
            placeholderTextColor={colors.muted}
            multiline
          />
          <TouchableOpacity style={s.sendBtn} onPress={() => { playTapSound(); submit(); }} disabled={sending || !text.trim()}>
            <Text style={s.sendBtnText}>Send</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: spacing.lg, paddingTop: 14, paddingBottom: 10,
  },
  backLink: { padding: 4 },
  blockLink: { padding: 4 },
  blockLinkText: { color: colors.muted, fontSize: 12, fontFamily: fonts.regular },
  headerTitle: { color: colors.ink, fontSize: 16, fontFamily: fonts.bold, flex: 1, textAlign: 'center' },

  scroll: { padding: spacing.lg, paddingBottom: 20 },
  empty: { color: colors.muted, fontSize: 13, textAlign: 'center', marginTop: 30, fontFamily: fonts.regular },

  bubbleRow: { marginBottom: 10, alignItems: 'flex-start' },
  bubbleRowMine: { alignItems: 'flex-end' },
  bubble: { maxWidth: '78%', borderRadius: radius.lg, paddingHorizontal: 14, paddingVertical: 10 },
  bubbleTheirs: { backgroundColor: colors.surface },
  bubbleMine: { backgroundColor: colors.primary },
  bubbleText: { color: colors.ink, fontSize: 14, lineHeight: 19, fontFamily: fonts.regular },
  bubbleTextMine: { color: colors.white },
  bubbleTime: { color: colors.muted, fontSize: 10.5, marginTop: 3, fontFamily: fonts.regular },

  composer: {
    flexDirection: 'row', alignItems: 'flex-end', gap: 10,
    padding: spacing.lg, borderTopWidth: 1, borderTopColor: colors.border,
  },
  input: {
    flex: 1, backgroundColor: colors.surface, borderRadius: radius.lg,
    paddingHorizontal: 14, paddingVertical: 10, color: colors.ink,
    fontSize: 14, fontFamily: fonts.regular, maxHeight: 100,
  },
  sendBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingHorizontal: 16, paddingVertical: 11 },
  sendBtnText: { color: colors.white, fontSize: 13.5, fontFamily: fonts.bold },
});
