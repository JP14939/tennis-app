import { View, Text, StyleSheet } from 'react-native';
import { colors, fonts, radius } from '../theme';

export default function AngleRow({ leftLabel, leftValue, leftSub, rightLabel, rightValue, rightSub }) {
  return (
    <View style={s.angleRow}>
      <View style={s.angleCard}>
        <Text style={s.angleLabel}>{leftLabel}</Text>
        <Text style={s.angleValue}>{leftValue ?? '—'}</Text>
        {leftSub != null && <Text style={s.angleSub}>{leftSub}</Text>}
      </View>
      <View style={s.angleCard}>
        <Text style={s.angleLabel}>{rightLabel}</Text>
        <Text style={s.angleValue}>{rightValue ?? '—'}</Text>
        {rightSub != null && <Text style={s.angleSub}>{rightSub}</Text>}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  angleRow: { flexDirection: 'row', gap: 10, marginBottom: 26 },
  angleCard: {
    flex: 1, backgroundColor: colors.surface,
    borderRadius: radius.md, padding: 15, alignItems: 'center',
  },
  angleLabel: { color: colors.muted, fontSize: 11.5, fontFamily: fonts.regular },
  angleValue: { color: colors.ink, fontSize: 16, fontFamily: fonts.extrabold, marginTop: 4 },
  angleSub: { color: colors.muted, fontSize: 11, marginTop: 2, fontFamily: fonts.regular },
});
