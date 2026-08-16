import { View, Text, StyleSheet } from 'react-native';
import { colors, fonts, radius } from '../theme';

export default function PlayerCard({ rank, playerType }) {
  if (!rank) return null;

  const progress = rank.next
    ? Math.max(0, Math.min(1, (rank.greatCount - rank.rank.threshold) / (rank.next.threshold - rank.rank.threshold)))
    : 1;

  return (
    <View style={s.card}>
      <View style={s.topRow}>
        <View>
          <Text style={s.eyebrow}>YOUR RANK</Text>
          <Text style={s.rankName}>{rank.rank.name}</Text>
        </View>
        <Text style={s.greatCount}>{rank.greatCount} great swing{rank.greatCount === 1 ? '' : 's'}</Text>
      </View>

      <View style={s.track}>
        <View style={[s.fill, { width: `${progress * 100}%` }]} />
      </View>
      <Text style={s.progressLabel}>
        {rank.next
          ? `${rank.remaining} more great swing${rank.remaining === 1 ? '' : 's'} to reach ${rank.next.name}`
          : 'Top rank reached'}
      </Text>

      <View style={s.divider} />

      {playerType?.type ? (
        <View>
          <Text style={s.eyebrow}>PLAYING STYLE</Text>
          <Text style={s.playerTypeLabel}>{playerType.label}</Text>
          <Text style={s.playerTypeDesc}>{playerType.description}</Text>
        </View>
      ) : (
        <Text style={s.locked}>
          {playerType?.swingsNeeded
            ? `Log ${playerType.swingsNeeded} more swing${playerType.swingsNeeded === 1 ? '' : 's'} to reveal your playing style`
            : 'Keep swinging to reveal your playing style'}
        </Text>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  card: {
    backgroundColor: colors.primary, borderRadius: radius.xxl,
    padding: 22, marginBottom: 24,
  },
  topRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 14 },
  eyebrow: { color: 'rgba(255,255,255,0.6)', fontSize: 10.5, fontFamily: fonts.extrabold, letterSpacing: 0.6 },
  rankName: { color: colors.white, fontSize: 24, fontFamily: fonts.serif, marginTop: 4 },
  greatCount: { color: 'rgba(255,255,255,0.75)', fontSize: 12.5, fontFamily: fonts.semibold },

  track: { height: 6, backgroundColor: 'rgba(255,255,255,0.2)', borderRadius: 3, overflow: 'hidden' },
  fill: { height: 6, borderRadius: 3, backgroundColor: colors.lime },
  progressLabel: { color: 'rgba(255,255,255,0.7)', fontSize: 12, marginTop: 8, fontFamily: fonts.regular },

  divider: { height: 1, backgroundColor: 'rgba(255,255,255,0.15)', marginVertical: 16 },

  playerTypeLabel: { color: colors.white, fontSize: 17, fontFamily: fonts.extrabold, marginTop: 4 },
  playerTypeDesc: { color: 'rgba(255,255,255,0.75)', fontSize: 12.5, lineHeight: 18, marginTop: 4, fontFamily: fonts.regular },

  locked: { color: 'rgba(255,255,255,0.65)', fontSize: 12.5, lineHeight: 18, fontFamily: fonts.regular },
});
