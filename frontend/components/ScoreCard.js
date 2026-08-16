import { View, Text, StyleSheet } from 'react-native';
import { colors, fonts, radius } from '../theme';

export default function ScoreCard({ score, caption }) {
  return (
    <View style={s.scoreCard}>
      <View style={s.scoreTopRow}>
        <Text style={s.scoreNum}>{score}</Text>
        <Text style={s.scoreOutOf}>/ 100</Text>
      </View>
      <View style={s.scoreTrack}>
        <View style={[s.scoreFill, { width: `${score}%`, backgroundColor: colors.lime }]} />
      </View>
      <Text style={s.matchedTo}>{caption}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  scoreCard: {
    backgroundColor: colors.primary, borderRadius: radius.xxl,
    padding: 26, alignItems: 'center', marginBottom: 14,
  },
  scoreTopRow: { flexDirection: 'row', alignItems: 'baseline', gap: 4 },
  scoreNum: { fontSize: 56, fontFamily: fonts.serif, color: colors.white, lineHeight: 60 },
  scoreOutOf: { color: 'rgba(255,255,255,0.6)', fontSize: 15, fontFamily: fonts.regular },
  scoreTrack: { width: '100%', height: 6, backgroundColor: 'rgba(255,255,255,0.2)', borderRadius: 3, marginTop: 18, marginBottom: 14, overflow: 'hidden' },
  scoreFill: { height: 6, borderRadius: 3 },
  matchedTo: { color: 'rgba(255,255,255,0.75)', fontSize: 13, fontFamily: fonts.regular },
});
