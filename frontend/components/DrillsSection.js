import { useCallback, useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { colors, fonts, radius, spacing } from '../theme';
import { DrillsIcon, TennisBallIcon } from './icons';
import { useAuth } from '../context/AuthContext';
import { listDrills } from '../api/drills';

const SHOT_TYPE_LABELS = {
  forehand: 'Forehand',
  backhand: 'Backhand',
  serve: 'Serve',
  footwork: 'Footwork & fitness',
};

function DrillCard({ item, onPress }) {
  return (
    <TouchableOpacity style={cc.card} activeOpacity={0.85} onPress={onPress}>
      <View style={cc.iconWrap}>
        <TennisBallIcon size={18} color={colors.primary} />
      </View>
      <View style={cc.body}>
        <Text style={cc.title}>{item.title}</Text>
        <Text style={cc.sub} numberOfLines={2}>{item.explanation}</Text>
      </View>
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
    alignItems: 'center', justifyContent: 'center', overflow: 'hidden',
  },
  body: { flex: 1 },
  title: { color: colors.ink, fontSize: 15, fontFamily: fonts.bold },
  sub: { color: colors.muted, fontSize: 12.5, marginTop: 2, fontFamily: fonts.regular },
});

export default function DrillsSection({ navigation }) {
  const { token } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [drills, setDrills] = useState([]);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);
    listDrills(token, { kind: 'drill' })
      .then((data) => { if (!cancelled) setDrills(data.items ?? []); })
      .catch(() => { if (!cancelled) setError(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [token]);

  useEffect(() => load(), [load]);

  const grouped = drills.reduce((acc, item) => {
    (acc[item.shot_type] ??= []).push(item);
    return acc;
  }, {});

  if (loading) {
    return <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 40 }} />;
  }

  if (error && drills.length === 0) {
    return (
      <View style={s.empty}>
        <View style={s.emptyIconWrap}>
          <DrillsIcon size={26} color={colors.primary} />
        </View>
        <Text style={s.emptyTitle}>Couldn't load drills</Text>
        <Text style={s.emptySub}>Check your connection and try again.</Text>
        <TouchableOpacity style={s.emptyBtn} onPress={load}>
          <Text style={s.emptyBtnText}>Tap to retry</Text>
        </TouchableOpacity>
      </View>
    );
  }

  if (drills.length === 0) {
    return (
      <View style={s.empty}>
        <View style={s.emptyIconWrap}>
          <DrillsIcon size={26} color={colors.primary} />
        </View>
        <Text style={s.emptyTitle}>Drills & exercises are on the way</Text>
        <Text style={s.emptySub}>
          We're building a library of drills tied to the coaching tips from
          your swing analyses, so you can practise exactly what's holding
          your technique back.
        </Text>
      </View>
    );
  }

  return (
    <View>
      {Object.entries(grouped).map(([shotType, items]) => (
        <View key={shotType}>
          <Text style={s.sectionTitle}>{SHOT_TYPE_LABELS[shotType] ?? shotType}</Text>
          {items.map((item) => (
            <DrillCard
              key={item.id}
              item={item}
              onPress={() => navigation.navigate('LessonDetail', { id: item.id })}
            />
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
