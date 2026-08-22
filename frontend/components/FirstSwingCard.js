import { View, Text, StyleSheet } from 'react-native';
import { colors, fonts, radius } from '../theme';
import { TennisBallIcon, LeaderboardIcon, DrillsIcon } from './icons';

const ROWS = [
  { Icon: TennisBallIcon, text: 'Your closest pro match, from 631 tour swings' },
  { Icon: LeaderboardIcon, text: 'A similarity score out of 100' },
  { Icon: DrillsIcon, text: 'Specific fixes, ranked by what’s costing you most' },
];

// Replaces the stats row (two tiles reading 0 and 0) for a brand-new account
// with zero analyses. Deliberately states the payoff rather than faking one:
// no ghost score, no skeleton ring -- a placeholder ring reads as *broken*,
// not *forthcoming*, and a fabricated number would be a lie the user catches
// within a minute of their first real upload.
export default function FirstSwingCard() {
  return (
    <View style={s.card}>
      <Text style={s.heading}>Here's what comes back</Text>
      {ROWS.map(({ Icon, text }, i) => (
        <View key={i} style={[s.row, i === ROWS.length - 1 && s.rowLast]}>
          <View style={s.iconWrap}>
            <Icon size={15} color={colors.primary} />
          </View>
          <Text style={s.rowText}>{text}</Text>
        </View>
      ))}
    </View>
  );
}

const s = StyleSheet.create({
  card: {
    backgroundColor: colors.surface, borderRadius: radius.lg,
    padding: 18, marginBottom: 26,
  },
  heading: { color: colors.ink, fontSize: 17, fontFamily: fonts.serif, marginBottom: 14 },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingBottom: 12, marginBottom: 12,
    borderBottomWidth: 1, borderBottomColor: colors.borderSoft,
  },
  rowLast: { borderBottomWidth: 0, paddingBottom: 0, marginBottom: 0 },
  iconWrap: {
    width: 30, height: 30, borderRadius: 15, backgroundColor: colors.primarySoft,
    alignItems: 'center', justifyContent: 'center',
  },
  rowText: { flex: 1, color: colors.ink, fontSize: 13.5, lineHeight: 19, fontFamily: fonts.medium },
});
