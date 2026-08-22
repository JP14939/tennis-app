import { useEffect, useRef } from 'react';
import { View, Text, StyleSheet, Animated } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { colors, fonts, scoreColor, easing, durations } from '../theme';
import { useCountUp } from '../utils/useCountUp';
import { useReducedMotion } from '../utils/useReducedMotion';

const AnimatedCircle = Animated.createAnimatedComponent(Circle);

// Circular score indicator for History rows -- RN has no conic-gradient
// equivalent, so this uses the standard SVG stroke-dasharray progress-ring
// technique instead (functionally the same result as the mockup's ring).
//
// `animate`: when true, the ring sweeps from 0 and the number counts up on
// mount instead of rendering already-filled -- used for the share-preview
// popup. Left off (default) anywhere the ring is captured to a static image
// or shown alongside already-settled content, so it doesn't render mid-fill.
export default function ScoreRing({ score, size = 46, strokeWidth = 4, animate = false }) {
  const color = scoreColor(score);
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = Math.max(0, Math.min(1, score / 100));

  const reducedMotion = useReducedMotion();
  const shouldAnimate = animate && !reducedMotion;

  const anim = useRef(new Animated.Value(shouldAnimate ? 0 : progress)).current;
  // The number used to be driven off this Animated.Value via an addListener
  // that setState'd on every frame. It now shares the app's one count-up hook
  // with HomeScreen's stat tiles -- same curve, same duration, no listener.
  const displayScore = useCountUp(score, durations.reveal, shouldAnimate);

  useEffect(() => {
    if (!shouldAnimate) {
      anim.setValue(progress);
      return;
    }
    anim.setValue(0);
    Animated.timing(anim, {
      toValue: progress,
      duration: durations.reveal,
      // The signature curve: the ring whips out and settles long, the same
      // shape as the swing it's scoring. Was the default ease-in-out, which
      // made a 1100ms sweep spend its first third barely moving.
      easing: easing.swing,
      useNativeDriver: false,
    }).start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldAnimate, score]);

  const dashOffset = anim.interpolate({
    inputRange: [0, 1],
    outputRange: [circumference, 0],
    extrapolate: 'clamp',
  });

  return (
    <View style={[styles.wrap, { width: size, height: size }]}>
      <Svg width={size} height={size} style={StyleSheet.absoluteFillObject}>
        <Circle cx={size / 2} cy={size / 2} r={radius} stroke={colors.border} strokeWidth={strokeWidth} fill="none" />
        <AnimatedCircle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={color}
          strokeWidth={strokeWidth}
          fill="none"
          strokeDasharray={`${circumference} ${circumference}`}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          rotation={-90}
          origin={`${size / 2}, ${size / 2}`}
        />
      </Svg>
      <View style={styles.inner}>
        <Text style={[styles.text, { color, fontFamily: fonts.bold }]}>{shouldAnimate ? displayScore : score}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: 'center', justifyContent: 'center' },
  inner: { alignItems: 'center', justifyContent: 'center' },
  text: { fontSize: 13 },
});
