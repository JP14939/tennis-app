import { View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator } from 'react-native';
import { useAuth } from '../context/AuthContext';

const GREEN  = '#4ade80';
const DARK   = '#0d0d0d';
const CARD   = '#141414';
const BORDER = '#222';
const TEXT   = '#fff';
const MUTED  = '#888';

function MenuItem({ icon, label, sub, onPress, accent, danger }) {
  return (
    <TouchableOpacity style={s.menuItem} onPress={onPress} activeOpacity={0.7}>
      <View style={s.menuIconWrap}>
        <Text style={s.menuIcon}>{icon}</Text>
      </View>
      <View style={s.menuBody}>
        <Text style={[s.menuLabel, accent && { color: GREEN }, danger && { color: '#f87171' }]}>{label}</Text>
        {sub ? <Text style={s.menuSub}>{sub}</Text> : null}
      </View>
      <Text style={s.chevron}>›</Text>
    </TouchableOpacity>
  );
}

export default function ProfileScreen({ navigation }) {
  const { user, isAuthenticated, isPremium, loading, logout } = useAuth();

  if (loading) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.centerFill}>
          <ActivityIndicator color={GREEN} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        <View style={s.avatarBlock}>
          <View style={s.avatar}>
            <Text style={s.avatarText}>{isAuthenticated ? user.name.charAt(0).toUpperCase() : '🎾'}</Text>
          </View>
          <Text style={s.name}>{isAuthenticated ? user.name : 'Guest'}</Text>
          <Text style={s.status}>{isAuthenticated ? user.email : 'Not signed in'}</Text>
          {isAuthenticated && (
            <View style={[s.tierBadge, isPremium && s.tierBadgePremium]}>
              <Text style={[s.tierBadgeText, isPremium && s.tierBadgeTextPremium]}>
                {isPremium ? '✨ PREMIUM' : 'FREE PLAN'}
              </Text>
            </View>
          )}
        </View>

        {isAuthenticated ? (
          <View style={s.menu}>
            {!isPremium && (
              <MenuItem
                icon="✨"
                label="Upgrade to Premium"
                sub="1v1 comparison, unlimited history & more"
                accent
                onPress={() => navigation.navigate('MainTabs', { screen: 'Premium' })}
              />
            )}
            <MenuItem icon="🚪" label="Log out" danger onPress={logout} />
          </View>
        ) : (
          <View style={s.menu}>
            <MenuItem
              icon="🔑"
              label="Log in"
              sub="Sync your analyses across devices"
              accent
              onPress={() => navigation.navigate('Login')}
            />
            <MenuItem
              icon="✨"
              label="Create an account"
              sub="Free · 2 analyses per day"
              onPress={() => navigation.navigate('Signup')}
            />
          </View>
        )}

        <View style={s.menu}>
          <MenuItem icon="⚙️" label="Settings" onPress={() => {}} />
          <MenuItem icon="❓" label="Help & support" onPress={() => {}} />
        </View>

        <Text style={s.footer}>🎾 TennisAI · © 2026</Text>

      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: DARK },
  scroll: { padding: 20, paddingTop: 24, paddingBottom: 40 },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center' },

  avatarBlock: { alignItems: 'center', marginBottom: 32 },
  avatar: {
    width: 72, height: 72, borderRadius: 36,
    backgroundColor: '#1a2e1a', borderWidth: 1, borderColor: '#2a4a2a',
    alignItems: 'center', justifyContent: 'center', marginBottom: 12,
  },
  avatarText: { fontSize: 30, color: GREEN, fontWeight: '800' },
  name: { color: TEXT, fontSize: 19, fontWeight: '800' },
  status: { color: MUTED, fontSize: 13, marginTop: 2 },

  tierBadge: {
    marginTop: 12, backgroundColor: '#1a1a1a', borderWidth: 1, borderColor: BORDER,
    borderRadius: 20, paddingHorizontal: 12, paddingVertical: 5,
  },
  tierBadgePremium: { backgroundColor: '#1a2e1a', borderColor: '#2a4a2a' },
  tierBadgeText: { color: MUTED, fontSize: 11, fontWeight: '700', letterSpacing: 0.5 },
  tierBadgeTextPremium: { color: GREEN },

  menu: {
    backgroundColor: CARD, borderWidth: 1, borderColor: BORDER,
    borderRadius: 16, marginBottom: 16, overflow: 'hidden',
  },
  menuItem: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingVertical: 14, paddingHorizontal: 16,
    borderBottomWidth: 1, borderBottomColor: BORDER,
  },
  menuIconWrap: {
    width: 32, height: 32, borderRadius: 8, backgroundColor: '#1a1a1a',
    alignItems: 'center', justifyContent: 'center',
  },
  menuIcon: { fontSize: 16 },
  menuBody: { flex: 1 },
  menuLabel: { color: TEXT, fontSize: 15, fontWeight: '600' },
  menuSub: { color: MUTED, fontSize: 12, marginTop: 2 },
  chevron: { color: '#444', fontSize: 20 },

  footer: { color: '#444', fontSize: 12, textAlign: 'center', marginTop: 12 },
});
