import { forwardRef } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, fonts, radius } from '../theme';
import TrendChart from './TrendChart';

const CARD_W = 320;
const CARD_H = 400;
const CHART_W = CARD_W - 56; // matches the card's horizontal padding

// Same off-screen-capture pattern as ResultShareCard.js -- see
// frontend/utils/shareCard.js. Reuses TrendChart.js directly rather than
// re-implementing the line chart for the share image.
const ProgressShareCard = forwardRef(function ProgressShareCard({ points, delta, filterLabel }, ref) {
  const latest = points?.length ? points[points.length - 1].score : null;

  return (
    <View ref={ref} collapsable={false} style={s.card}>
      <Text style={s.label}>{filterLabel} Progress</Text>
      {latest != null && <Text style={s.score}>{latest}</Text>}
      {delta != null && (
        <Text style={[s.delta, { color: delta >= 0 ? colors.lime : '#f8b4ae' }]}>
          {delta >= 0 ? '+' : ''}{delta} since first shot
        </Text>
      )}
      <View style={s.chartWrap}>
        <TrendChart points={points} width={CHART_W} />
      </View>
      <View style={s.footer}>
        <Text style={s.wordmark}>TennisAI</Text>
      </View>
    </View>
  );
});

export default ProgressShareCard;

const s = StyleSheet.create({
  card: {
    width: CARD_W, height: CARD_H, backgroundColor: colors.primary,
    borderRadius: radius.xxl, padding: 28,
    alignItems: 'center', justifyContent: 'center',
  },
  label: {
    color: 'rgba(255,255,255,0.75)', fontSize: 13, fontFamily: fonts.bold,
    textTransform: 'uppercase', letterSpacing: 1.5, marginBottom: 10,
  },
  score: { color: colors.white, fontSize: 56, fontFamily: fonts.serif, lineHeight: 60 },
  delta: { fontSize: 14, fontFamily: fonts.bold, marginTop: 4, marginBottom: 18 },
  chartWrap: { width: CHART_W, backgroundColor: colors.white, borderRadius: radius.md, padding: 8 },
  footer: { position: 'absolute', bottom: 26 },
  wordmark: { color: 'rgba(255,255,255,0.6)', fontSize: 13, fontFamily: fonts.extrabold, letterSpacing: 0.5 },
});
