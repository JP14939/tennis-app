import { View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator } from 'react-native';
import { useAuth } from '../context/AuthContext';
import { colors, fonts, radius, spacing } from '../theme';
import CourtBackground from '../components/CourtBackground';
import { PremiumIcon, LinesIcon, SettingsIcon, HelpIcon } from '../components/icons';

function MenuItem({ icon, label, sub, onPress, accent, danger }) {
  return (
    <TouchableOpacity style={s.menuItem} onPress={onPress} activeOpacity={0.7}>
      <View style={[s.menuIconWrap, accent && s.menuIconWrapAccent]}>{icon}</View>
      <View style={s.menuBody}>
        <Text style={[s.menuLabel, accent && { color: colors.primary }, danger && { color: colors.coral }]}>{label}</Text>
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
          <ActivityIndicator color={colors.primary} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      <CourtBackground />
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
                icon={<PremiumIcon size={16} color={colors.primary} filled />}
                label="Upgrade to Premium"
                sub="1v1 comparison, unlimited history & more"
                accent
                onPress={() => navigation.navigate('MainTabs', { screen: 'Premium' })}
              />
            )}
            <MenuItem icon={<LinesIcon size={15} color={colors.coral} />} label="Log out" danger onPress={logout} />
          </View>
        ) : (
          <View style={s.menu}>
            <MenuItem
              icon={<PremiumIcon size={16} color={colors.primary} filled />}
              label="Log in"
              sub="Sync your analyses across devices"
              accent
              onPress={() => navigation.navigate('Login')}
            />
            <MenuItem
              icon={<PremiumIcon size={16} color={colors.mutedDark} />}
              label="Create an account"
              sub="Free · 2 analyses per day"
              onPress={() => navigation.navigate('Signup')}
            />
          </View>
        )}

        <View style={s.menu}>
          <MenuItem icon={<SettingsIcon size={15} color={colors.mutedDark} />} label="Settings" onPress={() => navigation.navigate('Settings')} />
          {isAuthenticated && (
            <MenuItem icon={<LinesIcon size={15} color={colors.mutedDark} />} label="Coach mode" sub="Follow a student, or let a coach follow you" onPress={() => navigation.navigate('Coach')} />
          )}
          <MenuItem icon={<HelpIcon size={15} color={colors.mutedDark} />} label="Help & support" onPress={() => navigation.navigate('FenceTutorial')} />
        </View>

        <Text style={s.footer}>TennisAI · © 2026</Text>

      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingTop: 24, paddingBottom: 130 },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center' },

  avatarBlock: { alignItems: 'center', marginBottom: 28 },
  avatar: {
    width: 76, height: 76, borderRadius: 38, backgroundColor: colors.primary,
    alignItems: 'center', justifyContent: 'center', marginBottom: 12,
    shadowColor: colors.primary, shadowOpacity: 0.25, shadowRadius: 16, shadowOffset: { width: 0, height: 8 },
  },
  avatarText: { fontSize: 32, color: colors.lime, fontFamily: fonts.serif },
  name: { color: colors.ink, fontSize: 19, fontFamily: fonts.extrabold },
  status: { color: colors.muted, fontSize: 13, marginTop: 2, fontFamily: fonts.regular },

  tierBadge: {
    marginTop: 12, backgroundColor: colors.border,
    borderRadius: 20, paddingHorizontal: 13, paddingVertical: 5,
  },
  tierBadgePremium: { backgroundColor: colors.primarySoft },
  tierBadgeText: { color: colors.mutedDark, fontSize: 11, fontFamily: fonts.bold, letterSpacing: 0.4 },
  tierBadgeTextPremium: { color: colors.primary },

  menu: {
    backgroundColor: colors.surface, borderRadius: radius.lg, marginBottom: spacing.lg, overflow: 'hidden',
  },
  menuItem: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingVertical: 15, paddingHorizontal: 16,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  menuIconWrap: {
    width: 32, height: 32, borderRadius: 8, backgroundColor: colors.border,
    alignItems: 'center', justifyContent: 'center',
  },
  menuIconWrapAccent: { backgroundColor: colors.primarySoft },
  menuBody: { flex: 1 },
  menuLabel: { color: colors.ink, fontSize: 14.5, fontFamily: fonts.semibold },
  menuSub: { color: colors.muted, fontSize: 11.5, marginTop: 2, fontFamily: fonts.regular },
  chevron: { color: colors.divider, fontSize: 20 },

  footer: { color: colors.divider, fontSize: 12, textAlign: 'center', marginTop: 12, fontFamily: fonts.regular },
});
