import { View, Text, StyleSheet } from 'react-native';
import { colors, fonts, radius } from '../theme';

export default function StatCard({ label, value, sub }) {
  return (
    <View style={s.card}>
      <Text style={s.label}>{label}</Text>
      <Text style={s.value}>{value}</Text>
      {sub != null && <Text style={s.sub}>{sub}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md, padding: 15, alignItems: 'center',
    marginBottom: 26,
  },
  label: { color: colors.muted, fontSize: 11.5, fontFamily: fonts.regular },
  value: { color: colors.ink, fontSize: 16, fontFamily: fonts.extrabold, marginTop: 4 },
  sub: { color: colors.muted, fontSize: 11, marginTop: 2, fontFamily: fonts.regular },
});
