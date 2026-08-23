import { useCallback, useRef, useState } from 'react';
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
//
// `style` is passed to AnimatedPressable as a PLAIN ARRAY, not a function --
// a `({pressed}) => [...]` style function on a component wrapped by
// Animated.createAnimatedComponent doesn't reliably resolve on a real
// device: backgroundColor/borderRadius/overflow clipping and percentage or
// cross-axis child sizing (an Image at width:'100%', a Text needing its
// width constrained) were all found broken on-device this session, while
// the SAME properties render correctly literally everywhere else in the
// app. `pressed` is now tracked as local state (set in the onPressIn/
// onPressOut handlers this component already has for the scale spring)
// instead of relying on Pressable's callback-style API, so `style` can go
// back to being the plain array form Animated.createAnimatedComponent is
// actually built for.
export default function PressableScale({
  children,
  style,
  scaleTo = 0.97,
  disabled,
  ...props
}) {
  const scale = useRef(new Animated.Value(1)).current;
  const reducedMotion = useReducedMotion();
  const [pressed, setPressed] = useState(false);

  const springTo = useCallback((toValue) => {
    Animated.spring(scale, { toValue, ...springs.press }).start();
  }, [scale]);

  const onPressIn = useCallback((e) => {
    setPressed(true);
    if (!reducedMotion) springTo(scaleTo);
    props.onPressIn?.(e);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reducedMotion, scaleTo, springTo, props.onPressIn]);

  const onPressOut = useCallback((e) => {
    setPressed(false);
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
      style={[
        style,
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
