import { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, Modal, ScrollView, ActivityIndicator, StyleSheet } from 'react-native';
import { useAuth } from '../context/AuthContext';
import { getFriends } from '../api/friends';
import { colors, fonts, radius, spacing } from '../theme';
import { playTapSound } from '../utils/sounds';

// Reused by any screen that lets a user pick one friend to act on (e.g.
// "send this swing to..."). Purely a picker -- the caller supplies onSelect
// and handles the actual action (share call, alert, etc).
export default function FriendPickerModal({ visible, onClose, onSelect, title = 'Send to a friend' }) {
  const { token } = useAuth();
  const [friends, setFriends] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!visible) return;
    setLoading(true);
    getFriends(token).then((data) => setFriends(data.friends)).catch(() => {}).finally(() => setLoading(false));
  }, [visible, token]);

  return (
    <Modal visible={visible} animationType="fade" transparent onRequestClose={onClose}>
      <View style={s.backdrop}>
        <View style={s.card}>
          <View style={s.header}>
            <Text style={s.title}>{title}</Text>
            <TouchableOpacity onPress={onClose} hitSlop={10}>
              <Text style={s.close}>✕</Text>
            </TouchableOpacity>
          </View>

          <ScrollView style={s.scroll} showsVerticalScrollIndicator={false}>
            {loading ? (
              <ActivityIndicator color={colors.primary} style={{ marginVertical: 20 }} />
            ) : friends.length === 0 ? (
              <Text style={s.empty}>No friends yet — add one from the Friends screen first.</Text>
            ) : (
              friends.map((friend) => (
                <TouchableOpacity key={friend.id} style={s.row} onPress={() => { playTapSound(); onSelect(friend); }}>
                  <Text style={s.rowText}>{friend.username ? `@${friend.username}` : friend.name}</Text>
                  <Text style={s.chevron}>›</Text>
                </TouchableOpacity>
              ))
            )}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', alignItems: 'center', justifyContent: 'center', padding: spacing.xl },
  card: {
    width: '100%', maxWidth: 400, maxHeight: '70%',
    backgroundColor: colors.bg, borderRadius: radius.xxl, padding: spacing.lg,
  },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.md },
  title: { color: colors.ink, fontSize: 17, fontFamily: fonts.bold },
  close: { color: colors.muted, fontSize: 18, fontFamily: fonts.semibold, padding: 4 },
  scroll: { maxHeight: 320 },
  empty: { color: colors.muted, fontSize: 13, textAlign: 'center', paddingVertical: 20, fontFamily: fonts.regular },
  row: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingVertical: 13, borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  rowText: { color: colors.ink, fontSize: 14.5, fontFamily: fonts.semibold },
  chevron: { color: colors.divider, fontSize: 20 },
});
