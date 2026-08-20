import { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { colors, fonts, radius, spacing } from '../theme';
import { FilmIcon, TennisBallIcon, LockIcon } from './icons';
import { useAuth } from '../context/AuthContext';
import { useGatedNavigate } from '../utils/premiumGate';
import { listDrills } from '../api/drills';

const SHOT_TYPE_LABELS = {
  forehand: 'Forehand',
  backhand: 'Backhand',
  serve: 'Serve',
  footwork: 'Footwork & fitness',
};

function LessonCard({ item, onPress }) {
  return (
    <TouchableOpacity style={cc.card} activeOpacity={0.85} onPress={onPress}>
      <View style={[cc.iconWrap, item.locked && cc.iconWrapLocked]}>
        <TennisBallIcon size={18} color={item.locked ? colors.mutedDark : colors.primary} />
      </View>
      <View style={cc.body}>
        <Text style={cc.title}>{item.title}</Text>
        <Text style={cc.sub} numberOfLines={2}>
          {item.locked ? 'Watch, learn what to emphasize, then practise with analysis on every shot.' : item.explanation}
        </Text>
      </View>
      {item.locked && (
        <View style={cc.lockBadge}>
          <LockIcon size={11} color={colors.mutedDark} />
          <Text style={cc.lockBadgeText}>Premium</Text>
        </View>
      )}
    </TouchableOpacity>
  );
}
const cc = StyleSheet.create({
  card: {
    flexDirection: 'row', alignItems: 'center', gap: 14,
    backgroundColor: colors.surface, borderRadius: radius.lg,
    padding: 16, marginBottom: 12,
  },
  iconWrap: {
    width: 40, height: 40, borderRadius: 20, backgroundColor: colors.primarySoft,
    alignItems: 'center', justifyContent: 'center',
  },
  iconWrapLocked: { backgroundColor: colors.borderSoft },
  body: { flex: 1 },
  title: { color: colors.ink, fontSize: 15, fontFamily: fonts.bold },
  sub: { color: colors.muted, fontSize: 12.5, marginTop: 2, fontFamily: fonts.regular },
  lockBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: colors.borderSoft, borderRadius: radius.pill,
    paddingHorizontal: 9, paddingVertical: 5,
  },
  lockBadgeText: { color: colors.mutedDark, fontSize: 10.5, fontFamily: fonts.bold },
});

export default function LessonsSection({ navigation }) {
  const { token, isPremium } = useAuth();
  const gatedNavigate = useGatedNavigate(navigation);
  const [loading, setLoading] = useState(true);
  const [lessons, setLessons] = useState([]);

  useEffect(() => {
    let cancelled = false;
    listDrills(token, { kind: 'lesson' })
      .then((data) => { if (!cancelled) setLessons(data.items ?? []); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [token]);

  const grouped = lessons.reduce((acc, item) => {
    (acc[item.shot_type] ??= []).push(item);
    return acc;
  }, {});

  // item.locked is per-lesson (some lessons are free even without
  // Premium, see the empty-state copy below) -- only gate the ones
  // actually flagged locked, straight to checkout now (useGatedNavigate),
  // same "press it and payment appears" behavior as PremiumFeaturesSection
  // on Home, no confirm-alert step first. Unlocked lessons navigate
  // directly regardless of the viewer's own premium status.
  const onPressLesson = (item) => {
    if (item.locked) {
      gatedNavigate('Premium');
      return;
    }
    navigation.navigate('LessonDetail', { id: item.id });
  };

  if (loading) {
    return <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 40 }} />;
  }

  if (lessons.length === 0) {
    return (
      <View style={s.empty}>
        <View style={s.emptyIconWrap}>
          <FilmIcon size={26} color={colors.primary} />
        </View>
        <Text style={s.emptyTitle}>Lessons are on the way</Text>
        <Text style={s.emptySub}>
          Structured routines — watch a demo, learn what to emphasize, then
          practise each shot with real analysis. Some free, some Premium.
        </Text>
        {!isPremium && (
          <TouchableOpacity style={s.emptyBtn} onPress={() => navigation.navigate('Premium')}>
            <Text style={s.emptyBtnText}>See Premium →</Text>
          </TouchableOpacity>
        )}
      </View>
    );
  }

  return (
    <View>
      {Object.entries(grouped).map(([shotType, items]) => (
        <View key={shotType}>
          <Text style={s.sectionTitle}>{SHOT_TYPE_LABELS[shotType] ?? shotType}</Text>
          {items.map((item) => (
            <LessonCard key={item.id} item={item} onPress={() => onPressLesson(item)} />
          ))}
        </View>
      ))}
    </View>
  );
}

const s = StyleSheet.create({
  empty: {
    alignItems: 'center', backgroundColor: colors.surface, borderRadius: radius.lg,
    padding: 24, marginBottom: spacing.xl,
  },
  emptyIconWrap: {
    width: 52, height: 52, borderRadius: 26, backgroundColor: colors.primarySoft,
    alignItems: 'center', justifyContent: 'center', marginBottom: 14,
  },
  emptyTitle: { color: colors.ink, fontSize: 17, fontFamily: fonts.extrabold, marginBottom: 8, textAlign: 'center' },
  emptySub:   { color: colors.muted, fontSize: 13.5, lineHeight: 20, textAlign: 'center', fontFamily: fonts.regular },
  emptyBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingHorizontal: 18, paddingVertical: 10, marginTop: 16 },
  emptyBtnText: { color: colors.white, fontSize: 13, fontFamily: fonts.bold },

  sectionTitle: { color: colors.ink, fontSize: 16, fontFamily: fonts.bold, marginBottom: 12, marginTop: 4 },
});
