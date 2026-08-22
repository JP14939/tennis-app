import { useEffect, useRef } from 'react';
import { View, Text, StyleSheet, Animated } from 'react-native';
import { colors, fonts, radius, easing, durations } from '../theme';
import { useCountUp } from '../utils/useCountUp';
import { useReducedMotion } from '../utils/useReducedMotion';

// The payoff moment of the whole product: the score the analysis produced.
//
// This used to be completely static -- the bar rendered pre-filled via
// `width: ${score}%` and the 56pt number simply appeared -- while Home's far
// less important stat tiles counted up. The hierarchy was backwards: the
// smallest numbers in the app were the only ones that moved.
//
// The reveal is deliberately one orchestrated beat rather than several
// competing effects. The bar sweeps and the number counts on the same curve
// and the same duration so they land together, then the caption arrives once
// they've settled. Nothing scales, nothing glows, nothing pulses: this is the
// only place in the app allowed to be dramatic, and it stays legible because
// it does exactly one thing.
//
// `animate` is on by default -- unlike ScoreRing, this component is never
// captured into a share image, so there's no case where it needs to render
// already-settled.
export default function ScoreCard({ score, caption, animate = true }) {
  const reducedMotion = useReducedMotion();
  const shouldAnimate = animate && !reducedMotion;

  const sweep = useRef(new Animated.Value(shouldAnimate ? 0 : 1)).current;
  const captionOpacity = useRef(new Animated.Value(shouldAnimate ? 0 : 1)).current;
  const captionShift = useRef(new Animated.Value(shouldAnimate ? 8 : 0)).current;

  const displayScore = useCountUp(score, durations.reveal, shouldAnimate);

  useEffect(() => {
    if (!shouldAnimate) {
      sweep.setValue(1);
      captionOpacity.setValue(1);
      captionShift.setValue(0);
      return;
    }

    sweep.setValue(0);
    captionOpacity.setValue(0);
    captionShift.setValue(8);

    Animated.parallel([
      // Same duration and curve as the count-up hook driving the number, so
      // the bar finishes filling on the exact frame the number lands.
      Animated.timing(sweep, {
        toValue: 1,
        duration: durations.reveal,
        easing: easing.swing,
        // Animating `width` can't run on the native thread.
        useNativeDriver: false,
      }),
      // The caption is the quiet second beat: it waits until the sweep has
      // essentially settled, so it reads as a consequence of the score rather
      // than a third thing happening at once.
      Animated.sequence([
        Animated.delay(durations.reveal - durations.base),
        Animated.parallel([
          Animated.timing(captionOpacity, {
            toValue: 1,
            duration: durations.slow,
            easing: easing.out,
            useNativeDriver: true,
          }),
          Animated.timing(captionShift, {
            toValue: 0,
            duration: durations.slow,
            easing: easing.out,
            useNativeDriver: true,
          }),
        ]),
      ]),
    ]).start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldAnimate, score]);

  const fillWidth = sweep.interpolate({
    inputRange: [0, 1],
    outputRange: ['0%', `${Math.max(0, Math.min(100, score))}%`],
    extrapolate: 'clamp',
  });

  return (
    <View style={s.scoreCard}>
      <View style={s.scoreTopRow}>
        <View>
          {/* The count-up gains digits on the way (0 -> 9 -> 87), which would
              shove "/ 100" sideways twice during the reveal. This in-flow
              copy of the *final* value is invisible but reserves the exact
              width and supplies the baseline the row aligns to; the live
              number is overlaid on top, right-aligned to match. Measuring the
              real glyphs this way avoids guessing Instrument Serif's digit
              metrics, and tabular-figure support is too patchy across
              platforms to rely on here. */}
          <Text style={[s.scoreNum, s.scoreNumGhost]} accessibilityElementsHidden importantForAccessibility="no">
            {score}
          </Text>
          <Text style={[s.scoreNum, s.scoreNumLive]}>{shouldAnimate ? displayScore : score}</Text>
        </View>
        <Text style={s.scoreOutOf}>/ 100</Text>
      </View>
      <View style={s.scoreTrack}>
        <Animated.View style={[s.scoreFill, { width: fillWidth, backgroundColor: colors.lime }]} />
      </View>
      <Animated.Text
        style={[
          s.matchedTo,
          { opacity: captionOpacity, transform: [{ translateY: captionShift }] },
        ]}
      >
        {caption}
      </Animated.Text>
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
  scoreNumGhost: { opacity: 0 },
  scoreNumLive: { position: 'absolute', right: 0, top: 0, textAlign: 'right' },
  scoreOutOf: { color: 'rgba(255,255,255,0.6)', fontSize: 15, fontFamily: fonts.regular },
  scoreTrack: { width: '100%', height: 6, backgroundColor: 'rgba(255,255,255,0.2)', borderRadius: 3, marginTop: 18, marginBottom: 14, overflow: 'hidden' },
  scoreFill: { height: 6, borderRadius: 3 },
  matchedTo: { color: 'rgba(255,255,255,0.75)', fontSize: 13, fontFamily: fonts.regular },
});
