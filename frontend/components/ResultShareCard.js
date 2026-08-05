import { forwardRef } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, fonts, radius } from '../theme';
import ScoreRing from './ScoreRing';

const CARD_W = 320;
const CARD_H = 400;

// Rendered off-screen and captured via react-native-view-shot -- see
// frontend/utils/shareCard.js. Deliberately a purpose-built layout, not a
// screenshot of the live results screen (which has scroll content, buttons,
// nav chrome etc. that shouldn't end up in a shared image).
const ResultShareCard = forwardRef(function ResultShareCard({ score, shotType, caption }, ref) {
  return (
    <View ref={ref} collapsable={false} style={s.card}>
      <Text style={s.shotType}>{shotType?.charAt(0).toUpperCase() + shotType?.slice(1)}</Text>
      <View style={s.ringWrap}>
        <ScoreRing score={score} size={140} strokeWidth={10} />
      </View>
      <Text style={s.caption}>{caption}</Text>
      <View style={s.footer}>
        <Text style={s.wordmark}>TennisAI</Text>
      </View>
    </View>
  );
});

export default ResultShareCard;

const s = StyleSheet.create({
  card: {
    width: CARD_W, height: CARD_H, backgroundColor: colors.primary,
    borderRadius: radius.xxl, padding: 28,
    alignItems: 'center', justifyContent: 'center',
  },
  shotType: {
    color: 'rgba(255,255,255,0.75)', fontSize: 15, fontFamily: fonts.bold,
    textTransform: 'uppercase', letterSpacing: 1.5, position: 'absolute', top: 30,
  },
  ringWrap: { backgroundColor: colors.white, borderRadius: 999, padding: 14 },
  caption: {
    color: colors.white, fontSize: 14, fontFamily: fonts.regular,
    textAlign: 'center', marginTop: 22, paddingHorizontal: 16,
  },
  footer: { position: 'absolute', bottom: 26 },
  wordmark: { color: 'rgba(255,255,255,0.6)', fontSize: 13, fontFamily: fonts.extrabold, letterSpacing: 0.5 },
});
