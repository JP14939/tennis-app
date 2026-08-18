import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView } from 'react-native';
import Svg, { Rect, Line, Circle } from 'react-native-svg';
import { playTapSound } from '../utils/sounds';
import { colors, fonts, radius, spacing } from '../theme';

const FENCE_STEPS = [
  {
    title: 'Find the diamond mesh',
    body: "The fences around most courts are made of diamond-shaped wire mesh — that's your mount.",
  },
  {
    title: 'Wrap it with two elastic bands',
    body: "Wrap two elastic bands around your phone and hook them into the mesh at roughly eye level — any orientation that holds the court in frame works. No tripod needed.",
  },
  {
    title: 'Make sure it\'s tight',
    body: "Wrap it tight and firm so the phone can't slip or fall while you're recording.",
  },
];

const NET_STEPS = [
  {
    title: 'Find the net post',
    body: "Use the metal net post itself, not the net cord/tape strung between posts — the cord sags under the phone's weight and can't hold a steady shot.",
  },
  {
    title: 'Two rubber bands, crossed',
    body: "Loop one band around the phone lengthwise (top to bottom) and one crosswise (side to side), so they cross in an X on the back of the phone, then wrap both around the post. Snug enough that the phone can't slide or droop, but not so tight it strains the case.",
  },
  {
    title: 'Height and framing',
    body: "Wrap it at roughly sternum height — not eye height, that tilts the shot down. Face the far baseline: you'll be filming yourself from across the net, so stand where you'll be hitting from clearly in view once you start recording, with room above for a full service toss.",
  },
  {
    title: 'Check it worked',
    body: "Before recording a real swing, open \"Record now\" and watch the live positioning badge — it'll tell you directly if the height or angle is off. This front-on angle shows your face and the front of your swing rather than a from-behind view — both work for scoring, this is just a different look.",
  },
];

// Simple palette-matched schematic (not a photo) of the X-shaped rubber-band
// wrap — the concrete "less generic" fix: plain numbered text cards read as
// a generic tutorial pattern, a small on-brand illustration doesn't.
function MountDiagram({ variant }) {
  return (
    <View style={s.diagramWrap}>
      <Svg width={104} height={150} viewBox="0 0 104 150">
        {variant === 'net' ? (
          // Net post: a vertical rounded post behind the phone
          <Rect x={44} y={8} width={16} height={134} rx={8} fill={colors.borderStrong} />
        ) : (
          // Fence mesh: a small criss-cross diamond pattern behind the phone
          <>
            {[10, 34, 58, 82].map((x) => (
              <Line key={`d${x}`} x1={x} y1={0} x2={x + 40} y2={150} stroke={colors.borderStrong} strokeWidth={2} />
            ))}
            {[10, 34, 58, 82].map((x) => (
              <Line key={`u${x}`} x1={x + 40} y1={0} x2={x} y2={150} stroke={colors.borderStrong} strokeWidth={2} />
            ))}
          </>
        )}

        {/* Phone body */}
        <Rect x={30} y={35} width={44} height={80} rx={8} fill={colors.ink} stroke={colors.primaryDark} strokeWidth={2} />
        <Rect x={36} y={41} width={32} height={68} rx={3} fill={colors.surface} />

        {/* Rubber bands, crossed in an X, hooked past the phone's edges */}
        <Line x1={16} y1={30} x2={88} y2={120} stroke={colors.primary} strokeWidth={5} strokeLinecap="round" />
        <Line x1={88} y1={30} x2={16} y2={120} stroke={colors.primary} strokeWidth={5} strokeLinecap="round" />

        {/* Sternum-height marker */}
        <Circle cx={52} cy={75} r={4} fill={colors.lime} />
      </Svg>
      <Text style={s.diagramCaption}>
        {variant === 'net' ? 'Bands wrapped around the post' : 'Bands hooked into the mesh'}
      </Text>
    </View>
  );
}

export default function FenceTutorialContent({ onDismiss, dismissLabel = 'Got it', variant = 'fence' }) {
  const steps = variant === 'net' ? NET_STEPS : FENCE_STEPS;
  return (
    <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
      <Text style={s.h1}>{variant === 'net' ? 'Mount your phone at the net' : 'Mount your phone with rubber bands'}</Text>
      <Text style={s.sub}>
        The pro comparisons work best when your phone is at a consistent, court-level
        height — here's the cheapest way to get that without buying a stand.
      </Text>

      <MountDiagram variant={variant} />

      {steps.map((step, i) => (
        <View key={i} style={s.stepCard}>
          <View style={s.stepNumberWrap}>
            <Text style={s.stepNumber}>{i + 1}</Text>
          </View>
          <View style={s.stepTextWrap}>
            <Text style={s.stepTitle}>{step.title}</Text>
            <Text style={s.stepBody}>{step.body}</Text>
          </View>
        </View>
      ))}

      {onDismiss && (
        <TouchableOpacity style={s.btn} onPress={() => { playTapSound(); onDismiss(); }}>
          <Text style={s.btnText}>{dismissLabel}</Text>
        </TouchableOpacity>
      )}
    </ScrollView>
  );
}

const s = StyleSheet.create({
  scroll: { padding: spacing.xxl, paddingTop: 32, paddingBottom: 48, flexGrow: 1, backgroundColor: colors.bg },
  h1: { color: colors.ink, fontSize: 26, fontFamily: fonts.serifItalic, marginBottom: 8 },
  sub: { color: colors.muted, fontSize: 14, lineHeight: 20, marginBottom: 20, fontFamily: fonts.regular },

  diagramWrap: { alignItems: 'center', marginBottom: 20 },
  diagramCaption: { color: colors.muted, fontSize: 11.5, marginTop: 6, fontFamily: fonts.semibold },

  stepCard: {
    flexDirection: 'row', gap: 14, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.lg, padding: 16, marginBottom: 12, alignItems: 'flex-start',
  },
  stepNumberWrap: {
    width: 26, height: 26, borderRadius: 13, backgroundColor: colors.primarySoft,
    borderWidth: 1, borderColor: colors.primary, alignItems: 'center', justifyContent: 'center',
  },
  stepNumber: { color: colors.primary, fontSize: 13, fontFamily: fonts.bold },
  stepTextWrap: { flex: 1 },
  stepTitle: { color: colors.ink, fontSize: 15, fontFamily: fonts.bold, marginBottom: 4 },
  stepBody: { color: colors.mutedDark, fontSize: 13, lineHeight: 19, fontFamily: fonts.regular },

  btn: { backgroundColor: colors.primary, borderRadius: radius.sm, paddingVertical: 15, alignItems: 'center', marginTop: 12 },
  btnText: { color: colors.white, fontSize: 15, fontFamily: fonts.bold },
});
