import { useCallback, useRef } from 'react';
import { Animated, Pressable } from 'react-native';
import { springs } from '../theme';
import { useReducedMotion } from '../utils/useReducedMotion';

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

// Press feedback with actual physicality.
//
// Everything in this app previously used TouchableOpacity's `activeOpacity`,
// which on the primary Home CTA was set to 0.9 -- a 10% fade, near-invisible.
// Nothing depressed and nothing sprang back, so the app's most important
// button gave almost no acknowledgement that it had been hit.
//
// This depresses on touch-down and springs back on release. `springs.press`
// is damped hard enough not to visibly overshoot: the point is that the
// control feels like a physical thing being pushed, not that it bounces.
//
// Under reduce-motion the scale is skipped entirely and it falls back to an
// opacity dip, which still confirms the press without moving anything.
export default function PressableScale({
  children,
  style,
  scaleTo = 0.97,
  disabled,
  ...props
}) {
  const scale = useRef(new Animated.Value(1)).current;
  const reducedMotion = useReducedMotion();

  const springTo = useCallback((toValue) => {
    Animated.spring(scale, { toValue, ...springs.press }).start();
  }, [scale]);

  const onPressIn = useCallback((e) => {
    if (!reducedMotion) springTo(scaleTo);
    props.onPressIn?.(e);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reducedMotion, scaleTo, springTo, props.onPressIn]);

  const onPressOut = useCallback((e) => {
    if (!reducedMotion) springTo(1);
    props.onPressOut?.(e);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reducedMotion, springTo, props.onPressOut]);

  return (
    <AnimatedPressable
      {...props}
      disabled={disabled}
      onPressIn={onPressIn}
      onPressOut={onPressOut}
      style={({ pressed }) => [
        // Flattening the caller's style here keeps the API drop-in compatible
        // with the TouchableOpacity call sites this replaces, which all pass
        // a plain style object or array rather than a function.
        typeof style === 'function' ? style({ pressed }) : style,
        {
          transform: [{ scale }],
          opacity: disabled ? 0.5 : (reducedMotion && pressed ? 0.8 : 1),
        },
      ]}
    >
      {children}
    </AnimatedPressable>
  );
}
