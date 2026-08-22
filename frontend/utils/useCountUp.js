import { useEffect, useRef, useState } from 'react';
import { durations } from '../theme';
import { useReducedMotion } from './useReducedMotion';

// Same ease-out shape as theme's `easing.swing`, expressed as a plain
// function because this counts up a JS number rather than driving an
// Animated node -- Easing.bezier() can't be applied to a raw rAF tick.
function easeOutSwing(t) {
  return 1 - Math.pow(1 - t, 3);
}

// Animates a number from 0 up to `target`.
//
// This used to exist twice with two different implementations: a rAF loop in
// HomeScreen and an Animated.Value + listener in ScoreRing, both hardcoded to
// the same 1100ms. One hook now, and it honours reduce-motion by jumping
// straight to the final value (a rapidly churning number is exactly the kind
// of motion that setting exists to suppress).
export function useCountUp(target, durationMs = durations.reveal, enabled = true) {
  const reducedMotion = useReducedMotion();
  const shouldAnimate = enabled && !reducedMotion;

  const [value, setValue] = useState(shouldAnimate ? 0 : target);
  const frame = useRef(null);

  useEffect(() => {
    if (!shouldAnimate) {
      setValue(target);
      return undefined;
    }

    const start = performance.now();
    const tick = (now) => {
      const t = Math.min(1, (now - start) / durationMs);
      setValue(Math.round(target * easeOutSwing(t)));
      if (t < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);

    return () => {
      if (frame.current) cancelAnimationFrame(frame.current);
    };
  }, [target, durationMs, shouldAnimate]);

  return value;
}

export default useCountUp;
