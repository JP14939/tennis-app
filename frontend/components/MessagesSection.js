import { useCallback, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator, Image } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { useAuth } from '../context/AuthContext';
import { getThreads } from '../api/messages';
import { colors, fonts, radius } from '../theme';

function formatWhen(isoString) {
  if (!isoString) return '';
  const d = new Date(isoString.includes('Z') ? isoString : `${isoString.replace(' ', 'T')}Z`);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function ThreadRow({ thread, onPress }) {
  const name = thread.user?.username ? `@${thread.user.username}` : (thread.user?.name ?? 'Unknown');
  return (
    <TouchableOpacity style={t.row} onPress={onPress} activeOpacity={0.8}>
      <View style={t.avatar}>
        <Image source={require('../assets/mascot.png')} style={t.avatarImage} resizeMode="cover" />
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={t.name}>{name}</Text>
        <Text style={t.preview} numberOfLines={1}>{thread.last_body}</Text>
      </View>
      <View style={{ alignItems: 'flex-end' }}>
        <Text style={t.time}>{formatWhen(thread.last_at)}</Text>
        {thread.unread_count > 0 && (
          <View style={t.badge}><Text style={t.badgeText}>{thread.unread_count}</Text></View>
        )}
      </View>
    </TouchableOpacity>
  );
}
const t = StyleSheet.create({
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: colors.surface, borderRadius: radius.lg, padding: 13, marginBottom: 10,
  },
  avatar: {
    width: 42, height: 42, borderRadius: 21, backgroundColor: colors.primary,
    alignItems: 'center', justifyContent: 'center', overflow: 'hidden',
  },
  avatarImage: { width: '100%', height: '100%' },
  name: { color: colors.ink, fontSize: 14.5, fontFamily: fonts.bold },
  preview: { color: colors.muted, fontSize: 12.5, marginTop: 2, fontFamily: fonts.regular },
  time: { color: colors.muted, fontSize: 11, fontFamily: fonts.regular },
  badge: {
    backgroundColor: colors.primary, borderRadius: 10, minWidth: 20, height: 20,
    alignItems: 'center', justifyContent: 'center', marginTop: 4, paddingHorizontal: 5,
  },
  badgeText: { color: colors.white, fontSize: 11, fontFamily: fonts.bold },
});

export default function MessagesSection({ navigation }) {
  const { token } = useAuth();
  const [threads, setThreads] = useState([]);
  const [loading, setLoading] = useState(true);

  useFocusEffect(useCallback(() => {
    setLoading(true);
    getThreads(token).then((data) => setThreads(data.threads)).catch(() => {}).finally(() => setLoading(false));
  }, [token]));

  return (
    <View>
      {loading ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 20 }} />
      ) : threads.length === 0 ? (
        <Text style={s.empty}>No conversations yet — message someone from a court's availability list on Find Games.</Text>
      ) : (
        threads.map((thread) => (
          <ThreadRow
            key={thread.other_id}
            thread={thread}
            onPress={() => navigation.navigate('MessageThread', {
              otherUserId: thread.other_id,
              otherUserName: thread.user?.username ? `@${thread.user.username}` : thread.user?.name,
            })}
          />
        ))
      )}
    </View>
  );
}

const s = StyleSheet.create({
  empty: { color: colors.muted, fontSize: 13, textAlign: 'center', marginTop: 20, lineHeight: 19, fontFamily: fonts.regular },
});
