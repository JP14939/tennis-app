import { useCallback, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, Image } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { useAuth } from '../context/AuthContext';
import { fetchHistory } from '../api/history';
import { getRank, getPlayerType } from '../api/profile';
import { colors, fonts, radius, spacing, scoreColor } from '../theme';
import CourtBackground from '../components/CourtBackground';
import ScoreRing from '../components/ScoreRing';
import PlayerCard from '../components/PlayerCard';
import FirstSwingCard from '../components/FirstSwingCard';
import LeaderboardSection from '../components/LeaderboardSection';
import PremiumFeaturesSection from '../components/PremiumFeaturesSection';
import PressableScale from '../components/PressableScale';
import { TennisBallIcon, ChevronRightIcon } from '../components/icons';
import { playTapSound, playAchievementSound } from '../utils/sounds';
import { useCountUp } from '../utils/useCountUp';
import { parseServerDate } from '../utils/formatDate';
import { storage } from '../utils/storage';

const QUICK_SHOTS = [
  { label: 'Forehand', value: 'forehand' },
  { label: 'Backhand', value: 'backhand' },
  { label: 'Serve',    value: 'serve' },
];

// Rank tiers only ever go up (earned by cumulative great-swing count, no
// demotion mechanic exists) -- so any change from a previously-seen rank
// name is genuinely a promotion. Guarded on `previous` existing so the
// very first time this ever runs (nothing stored yet) doesn't fire.
const LAST_SEEN_RANK_KEY = 'last_seen_rank';
async function checkRankUp(rankName) {
  const previous = await storage.getItem(LAST_SEEN_RANK_KEY).catch(() => null);
  if (previous && previous !== rankName) {
    playAchievementSound();
  }
  await storage.setItem(LAST_SEEN_RANK_KEY, rankName).catch(() => {});
}

// useCountUp used to be defined here, with a second, differently-implemented
// copy inside ScoreRing. It now lives in utils/useCountUp.js and is shared by
// both, so the stat tiles, the history rings and the Results score all count
// on one curve for one duration -- and all honour reduce-motion together.

function formatDate(isoString) {
  const d = parseServerDate(isoString);
  return d ? d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '';
}

function RecentRow({ item }) {
  const score = Math.round(item.similarity ?? 0);
  return (
    <View style={r.row}>
      <ScoreRing score={score} />
      <View style={r.body}>
        <Text style={r.title}>{item.shot_type.charAt(0).toUpperCase() + item.shot_type.slice(1)}</Text>
        <Text style={r.date}>{formatDate(item.created_at)} · {item.pro_id ?? 'Technique'}</Text>
      </View>
      <ChevronRightIcon size={7} color={colors.muted} />
    </View>
  );
}
const r = StyleSheet.create({
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 14,
    backgroundColor: colors.surface, borderRadius: radius.lg,
    padding: 13, marginBottom: 10,
  },
  body: { flex: 1, minWidth: 0 },
  title: { color: colors.ink, fontSize: 14.5, fontFamily: fonts.bold },
  date: { color: colors.muted, fontSize: 12, marginTop: 2, fontFamily: fonts.regular },
});

export default function HomeScreen({ navigation }) {
  const { token, isAuthenticated, user } = useAuth();
  const [analyses, setAnalyses] = useState([]);
  const [rank, setRank] = useState(null);
  const [playerType, setPlayerType] = useState(null);

  useFocusEffect(useCallback(() => {
    if (!isAuthenticated) {
      setAnalyses([]);
      setRank(null);
      setPlayerType(null);
      return;
    }
    fetchHistory(token).then(data => setAnalyses(data.analyses)).catch(() => {});
    getRank(token).then((data) => {
      setRank(data);
      if (data?.rank?.name) checkRankUp(data.rank.name);
    }).catch(() => {});
    getPlayerType(token).then(setPlayerType).catch(() => {});
  }, [token, isAuthenticated]));

  const recents = analyses.slice(0, 2);
  const avg = analyses.length
    ? Math.round(analyses.reduce((sum, a) => sum + a.similarity, 0) / analyses.length)
    : 0;

  const analysesCount = useCountUp(analyses.length);
  const avgCount = useCountUp(avg);

  const playerName = isAuthenticated ? user.name.split(' ')[0] : 'there';

  const dayLabel = new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });

  return (
    <SafeAreaView style={s.safe}>
      <CourtBackground />
      {/* Missing `style={{flex:1}}` used to let this ScrollView collapse to
          its own content height instead of filling the screen -- invisible
          on web (react-native-web's block layout doesn't need it), but on a
          real phone it left everything squeezed into a thin strip while
          CourtBackground's absolute-positioned overlay still filled the
          whole screen underneath it. */}
      <ScrollView style={s.scrollFlex} contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        <View style={s.topRow}>
          <View style={{ flex: 1 }}>
            <Text style={s.dayLabel}>{dayLabel}</Text>
            <Text style={s.greeting}>Let's play, {playerName}.</Text>
          </View>
          <PressableScale style={s.avatar} onPress={() => navigation.navigate('Profile')} scaleTo={0.92}>
            <Image source={require('../assets/mascot.png')} style={s.avatarImage} resizeMode="cover" />
          </PressableScale>
        </View>

        {/* Primary CTA. Was activeOpacity={0.9} -- a 10% fade, which on the
            single most important button in the app was near-invisible. */}
        <PressableScale
          style={s.ctaCard}
          scaleTo={0.98}
          onPress={() => { playTapSound(); navigation.navigate('Upload'); }}
        >
          <View style={s.ctaTopRow}>
            <View style={s.ctaBadge}>
              <Text style={s.ctaBadgeText}>NEW ANALYSIS</Text>
            </View>
            <Text style={s.ctaHint}>Perfect your swing in under 60s</Text>
          </View>
          <View style={s.ctaPill}>
            <Text style={s.ctaPillText}>Start analysis</Text>
            <Text style={s.ctaPillArrow}>→</Text>
          </View>
        </PressableScale>

        {/* Quick shot picks */}
        <View style={s.quickRow}>
          {QUICK_SHOTS.map(shot => (
            <PressableScale
              key={shot.value}
              style={s.quickPill}
              scaleTo={0.94}
              onPress={() => navigation.navigate('Upload', { shotType: shot.value })}
            >
              <TennisBallIcon size={15} color={colors.primary} />
              <Text style={s.quickLabel}>{shot.label}</Text>
            </PressableScale>
          ))}
        </View>

        {/* Stats -- replaced with FirstSwingCard for a zero-analysis account
            (also true of a logged-out user) so nobody's greeted by tiles
            reading 0 and 0. */}
        {analyses.length === 0 ? (
          <FirstSwingCard />
        ) : (
          <View style={s.statsRow}>
            <View style={s.stat}>
              <View style={[s.statAccent, { backgroundColor: colors.primary }]} />
              <Text style={s.statNum}>{analysesCount}</Text>
              <Text style={s.statLabel}>Analyses</Text>
            </View>
            <View style={s.stat}>
              <View style={[s.statAccent, { backgroundColor: colors.gold }]} />
              <Text style={s.statNum}>{avgCount}</Text>
              <Text style={s.statLabel}>Avg score</Text>
            </View>
          </View>
        )}

        {/* Rank + playing style -- great-swing count now lives here (with a
            progress bar toward the next rank) instead of a bare stat tile. */}
        {isAuthenticated && rank && (
          <PressableScale
            scaleTo={0.98}
            onPress={() => navigation.navigate('MainTabs', { screen: 'History', params: { initialFilter: 'great' } })}
          >
            <PlayerCard rank={rank} playerType={playerType} />
          </PressableScale>
        )}

        {/* Recent activity -- dropped entirely (not just the apology line)
            for an authenticated zero-analysis account: FirstSwingCard above
            already covers "what happens next", so a header, a dead "See all"
            link into an equally-empty History, and an apology added nothing.
            Unchanged for everyone else. */}
        {isAuthenticated && recents.length > 0 && (
          <>
            <View style={s.sectionHeader}>
              <Text style={s.sectionTitle}>Recent activity</Text>
              <TouchableOpacity onPress={() => navigation.jumpTo('History')}>
                <Text style={s.seeAll}>See all</Text>
              </TouchableOpacity>
            </View>
            {recents.map(item => <RecentRow key={item.id} item={item} />)}
          </>
        )}
        {!isAuthenticated && (
          <TouchableOpacity style={s.loginPrompt} onPress={() => navigation.navigate('Login')}>
            <Text style={s.loginPromptText}>Log in to track your analysis history →</Text>
          </TouchableOpacity>
        )}

        {/* Leaderboard -- hidden rather than shown-empty at zero analyses.
            The instinct might be to default to the worldwide tab instead
            (pro/celebrity rows would be motivating pre-first-swing), but the
            celebrity_scores table has 0 seeded rows right now, so that tab is
            just as empty as friends -- showing it would be the same dead
            chrome on a different tab. Revisit defaulting to worldwide once
            celebrity rows actually exist. */}
        {isAuthenticated && analyses.length > 0 && (
          <>
            <View style={s.sectionHeader}>
              <Text style={s.sectionTitle}>Leaderboard</Text>
            </View>
            <LeaderboardSection />
          </>
        )}

        {/* Premium features -- moved here from the old standalone Premium
            tab (see PremiumFeaturesSection.js) so they're visible without
            needing to already know a separate page exists. */}
        <PremiumFeaturesSection navigation={navigation} />

      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scrollFlex: { flex: 1 },
  scroll: { padding: spacing.xl, paddingTop: 20, paddingBottom: 130 },

  topRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: spacing.xxl },
  dayLabel: { color: colors.muted, fontSize: 13, fontFamily: fonts.semibold, marginBottom: 4 },
  greeting: { color: colors.ink, fontSize: 32, fontFamily: fonts.serifItalic, lineHeight: 36 },
  avatar: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: colors.primary,
    alignItems: 'center', justifyContent: 'center', marginTop: 4, overflow: 'hidden',
    shadowColor: colors.primary, shadowOpacity: 0.3, shadowRadius: 10, shadowOffset: { width: 0, height: 4 },
  },
  // Explicit pixels, not '100%' -- percentage sizing on an Image nested
  // inside PressableScale (an Animated-wrapped Pressable) couldn't reliably
  // resolve against the animated style computation, which cascaded into
  // topRow (this avatar's flex-row parent) measuring itself as nearly full
  // screen height. Matches `avatar`'s own fixed 44x44 exactly.
  avatarImage: { width: 44, height: 44 },

  ctaCard: {
    backgroundColor: colors.primary, borderRadius: radius.xl, padding: 18, marginBottom: spacing.xl,
    overflow: 'hidden',
  },
  ctaTopRow: { flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 14 },
  ctaBadge: { backgroundColor: colors.lime, borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 4 },
  ctaBadgeText: { color: colors.primary, fontSize: 10, fontFamily: fonts.extrabold, letterSpacing: 0.6 },
  ctaHint: { color: 'rgba(255,255,255,0.85)', fontSize: 12.5, fontFamily: fonts.semibold, flexShrink: 1 },
  ctaPill: {
    flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: colors.white,
    alignSelf: 'flex-start', paddingVertical: 10, paddingHorizontal: 18, borderRadius: radius.pill,
  },
  ctaPillText: { color: colors.primary, fontSize: 14, fontFamily: fonts.bold },
  ctaPillArrow: { color: colors.primary, fontSize: 14, fontFamily: fonts.bold },

  quickRow: { flexDirection: 'row', gap: 9, marginBottom: spacing.xxl },
  quickPill: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    backgroundColor: colors.surface, borderRadius: radius.pill, paddingVertical: 12,
  },
  quickLabel: { color: colors.ink, fontSize: 12.5, fontFamily: fonts.bold },

  statsRow: {
    flexDirection: 'row', gap: 10, marginBottom: spacing.xxl,
  },
  stat: {
    flex: 1, backgroundColor: colors.surface, borderRadius: radius.lg,
    paddingTop: 16, paddingBottom: 14, paddingHorizontal: 10, alignItems: 'center', overflow: 'hidden',
  },
  statAccent: { position: 'absolute', top: 0, left: 0, right: 0, height: 3 },
  statNum: { color: colors.ink, fontSize: 26, fontFamily: fonts.serif },
  statLabel: { color: colors.muted, fontSize: 10.5, fontFamily: fonts.semibold, marginTop: 3 },

  sectionHeader: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: spacing.md,
  },
  sectionTitle: { color: colors.ink, fontSize: 19, fontFamily: fonts.serif },
  seeAll: { color: colors.primary, fontSize: 13, fontFamily: fonts.semibold },

  loginPrompt: {
    backgroundColor: colors.surface, borderRadius: radius.lg, padding: 16, alignItems: 'center',
  },
  loginPromptText: { color: colors.primary, fontSize: 13, fontFamily: fonts.semibold },
});
