import { useCallback, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator, Image } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { useAuth } from '../context/AuthContext';
import { getRank } from '../api/profile';
import { colors, fonts, radius, spacing } from '../theme';
import CourtBackground from '../components/CourtBackground';
import { PremiumIcon, LinesIcon, SettingsIcon, HelpIcon, MessageIcon } from '../components/icons';

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
  const { user, token, isAuthenticated, isPremium, loading, logout } = useAuth();
  const [rank, setRank] = useState(null);

  useFocusEffect(useCallback(() => {
    if (!isAuthenticated) { setRank(null); return; }
    getRank(token).then(setRank).catch(() => {});
  }, [token, isAuthenticated]));

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
            <Image source={require('../assets/mascot.png')} style={s.avatarImage} resizeMode="cover" />
          </View>
          <Text style={s.name}>{isAuthenticated ? user.name : 'Guest'}</Text>
          {isAuthenticated && (
            user.username ? (
              <Text style={s.username}>@{user.username}</Text>
            ) : (
              <TouchableOpacity onPress={() => navigation.navigate('Settings')}>
                <Text style={s.usernamePrompt}>Set a username →</Text>
              </TouchableOpacity>
            )
          )}
          <Text style={s.status}>{isAuthenticated ? user.email : 'Not signed in'}</Text>
          {isAuthenticated && (
            <View style={s.badgeRow}>
              <View style={[s.tierBadge, isPremium && s.tierBadgePremium]}>
                <Text style={[s.tierBadgeText, isPremium && s.tierBadgeTextPremium]}>
                  {isPremium ? 'PREMIUM' : 'FREE PLAN'}
                </Text>
              </View>
              {rank && (
                <View style={s.rankBadge}>
                  <Text style={s.rankBadgeText}>{rank.rank.name}</Text>
                </View>
              )}
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
                onPress={() => navigation.navigate('Premium')}
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
          {isAuthenticated && (
            <MenuItem icon={<MessageIcon size={15} color={colors.mutedDark} />} label="Messages" sub="Chat with players you've matched with on Find Games" onPress={() => navigation.navigate('Friends', { initialSegment: 'messages' })} />
          )}
          <MenuItem icon={<SettingsIcon size={15} color={colors.mutedDark} />} label="Settings" onPress={() => navigation.navigate('Settings')} />
          {isAuthenticated && (
            <MenuItem icon={<LinesIcon size={15} color={colors.mutedDark} />} label="Coach mode" sub="Follow a student, or let a coach follow you" onPress={() => navigation.navigate('Coach')} />
          )}
          <MenuItem icon={<HelpIcon size={15} color={colors.mutedDark} />} label="Help & support" onPress={() => navigation.navigate('FenceTutorial')} />
        </View>

        <Text style={s.footer}>RallyMax · © 2026</Text>

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
    alignItems: 'center', justifyContent: 'center', marginBottom: 12, overflow: 'hidden',
    shadowColor: colors.primary, shadowOpacity: 0.25, shadowRadius: 16, shadowOffset: { width: 0, height: 8 },
  },
  avatarImage: { width: '100%', height: '100%' },
  name: { color: colors.ink, fontSize: 19, fontFamily: fonts.extrabold },
  username: { color: colors.muted, fontSize: 13, marginTop: 2, fontFamily: fonts.semibold },
  usernamePrompt: { color: colors.primary, fontSize: 13, marginTop: 2, fontFamily: fonts.semibold },
  status: { color: colors.muted, fontSize: 13, marginTop: 2, fontFamily: fonts.regular },

  badgeRow: { flexDirection: 'row', gap: 8, marginTop: 12 },
  tierBadge: {
    backgroundColor: colors.border,
    borderRadius: 20, paddingHorizontal: 13, paddingVertical: 5,
  },
  tierBadgePremium: { backgroundColor: colors.primarySoft },
  tierBadgeText: { color: colors.mutedDark, fontSize: 11, fontFamily: fonts.bold, letterSpacing: 0.4 },
  tierBadgeTextPremium: { color: colors.primary },
  rankBadge: {
    backgroundColor: colors.primary,
    borderRadius: 20, paddingHorizontal: 13, paddingVertical: 5,
  },
  rankBadgeText: { color: colors.white, fontSize: 11, fontFamily: fonts.bold, letterSpacing: 0.4 },

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
