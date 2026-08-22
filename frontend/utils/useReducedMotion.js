import { useEffect, useState } from 'react';
import { AccessibilityInfo } from 'react-native';

// Whether the OS-level "reduce motion" setting is on. On iOS/Android this
// reads Settings > Accessibility > Motion; under react-native-web
// AccessibilityInfo maps to the `prefers-reduced-motion` media query, so the
// same hook covers all three platforms.
//
// Callers should use this to skip *decorative* motion (sweeps, count-ups,
// staggers) -- not to disable functional animation like the tab indicator,
// which still needs to move so the selected tab is identifiable. For those,
// shorten rather than remove.
export function useReducedMotion() {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    let cancelled = false;

    AccessibilityInfo.isReduceMotionEnabled()
      .then((enabled) => { if (!cancelled) setReduced(enabled); })
      .catch(() => {});

    const sub = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduced);
    return () => {
      cancelled = true;
      // RN >= 0.65 returns a subscription with .remove(); guard anyway since
      // react-native-web's shim has historically returned undefined here.
      sub?.remove?.();
    };
  }, []);

  return reduced;
}

export default useReducedMotion;
