import { View, Text, StyleSheet } from 'react-native';
import Svg, { Polyline, Circle, Line } from 'react-native-svg';
import { colors, fonts, scoreColor } from '../theme';

const HEIGHT = 120;
const H_PAD = 12;
const V_PAD = 14;

function formatShortDate(iso) {
  const d = new Date(iso.includes('Z') ? iso : `${iso.replace(' ', 'T')}Z`);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

// points: [{ date: isoString, score: number }], already sorted ascending.
// No smoothing/interpolation -- straight segments between the real scores,
// since a fitted curve would imply data between points that doesn't exist.
export default function TrendChart({ points, width }) {
  if (!points || points.length === 0) return null;

  const plotW = width - H_PAD * 2;
  const plotH = HEIGHT - V_PAD * 2;

  const xFor = (i) => points.length === 1
    ? H_PAD + plotW / 2
    : H_PAD + (i / (points.length - 1)) * plotW;
  const yFor = (score) => V_PAD + plotH - (Math.max(0, Math.min(100, score)) / 100) * plotH;

  const coords = points.map((p, i) => ({ x: xFor(i), y: yFor(p.score) }));
  const polylinePoints = coords.map((c) => `${c.x},${c.y}`).join(' ');

  return (
    <View>
      <Svg width={width} height={HEIGHT}>
        {[25, 50, 75].map((mark) => (
          <Line
            key={mark}
            x1={H_PAD} x2={width - H_PAD}
            y1={yFor(mark)} y2={yFor(mark)}
            stroke={colors.border} strokeWidth={1}
          />
        ))}
        {points.length > 1 && (
          <Polyline points={polylinePoints} fill="none" stroke={colors.primary} strokeWidth={2.5} />
        )}
        {coords.map((c, i) => (
          <Circle key={i} cx={c.x} cy={c.y} r={4.5} fill={scoreColor(points[i].score)} />
        ))}
      </Svg>
      <View style={s.dateRow}>
        <Text style={s.dateText}>{formatShortDate(points[0].date)}</Text>
        {points.length > 1 && (
          <Text style={s.dateText}>{formatShortDate(points[points.length - 1].date)}</Text>
        )}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  dateRow: { flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: H_PAD, marginTop: 2 },
  dateText: { color: colors.muted, fontSize: 10.5, fontFamily: fonts.regular },
});
