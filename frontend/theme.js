// Shared design tokens for the "Pine & Lime" redesign (Home, History,
// Premium, Profile, Upload's pick phase, Results, Live Camera, Login,
// Signup, FenceTutorial). Remaining screens (VersusPick, VersusResults,
// Highlight*) are still out of scope for this pass and keep their own
// local dark-theme literals.
//
// Colors were computed from the design mockup's oklch() values via the real
// OKLab->sRGB formula (React Native's style engine can't parse oklch()).

import { Easing } from 'react-native';

export const colors = {
  bg: '#ebe8df',
  surface: '#fcfaf4',
  ink: '#211d12',
  muted: '#6f6c62',
  mutedDark: '#595549',

  primary: '#024726',
  primaryDark: '#003919',
  primarySoft: '#c3eac9',

  lime: '#c3ea43',
  limeText: '#133716',

  gold: '#d9a440',
  coral: '#e15a50',

  amberBg: '#ffd2be',
  amberText: '#723311',

  border: '#e0ded7',
  borderSoft: '#f1eee7',
  borderMed: '#e7e4dd',
  borderStrong: '#dad7d0',
  borderDashed: '#c3bdb0',
  divider: '#a19e98',
  dividerStrong: '#918f88',

  white: '#ffffff',
};

export const fonts = {
  serifItalic: 'InstrumentSerif_400Regular_Italic',
  serif: 'InstrumentSerif_400Regular',
  regular: 'Manrope_400Regular',
  medium: 'Manrope_500Medium',
  semibold: 'Manrope_600SemiBold',
  bold: 'Manrope_700Bold',
  extrabold: 'Manrope_800ExtraBold',
};

export const radius = {
  sm: 12,
  md: 14,
  lg: 16,
  xl: 18,
  xxl: 22,
  pill: 100,
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 26,
};

// Motion tokens.
//
// Before this existed, not one Animated.timing() in the app passed an
// `easing`, so every one of them silently got RN's default
// Easing.inOut(Easing.ease) -- a symmetric curve that *starts slow*. On
// anything responding to a tap that reads as lag, and it was the single
// biggest reason the app felt sluggish.
//
// The curves below come from the thing this app actually measures. A tennis
// swing accelerates hard out of the backswing and decelerates long through
// the follow-through: that shape is an ease-out, and it's the default here
// for anything the user initiated. `inOut` is reserved for the few things
// that both open and close in place (collapsibles), where a symmetric curve
// is genuinely correct.
export const easing = {
  // Signature curve. Very sharp attack, long settle -- reserved for the
  // score reveal, the one place the app is allowed to be dramatic.
  swing: Easing.bezier(0.16, 1, 0.3, 1),
  // The workhorse. Everything the user initiated arrives on this.
  out: Easing.bezier(0.22, 1, 0.36, 1),
  // Only for elements that expand and collapse in place.
  inOut: Easing.bezier(0.65, 0, 0.35, 1),
};

export const durations = {
  instant: 120,   // micro-feedback: press states
  fast: 180,      // high-frequency controls: tabs, chevrons
  base: 240,      // standard UI: panels, chips
  slow: 320,      // larger surfaces travelling further
  reveal: 900,    // the score reveal only
};

// Spring configs for things that read as physical objects being moved
// rather than states being crossfaded. `damping` is high enough that
// neither of these visibly overshoots -- the point is the settle, not bounce.
export const springs = {
  // Tab indicator sliding between items.
  slide: { stiffness: 260, damping: 26, mass: 1, useNativeDriver: true },
  // Press-down / release on buttons and cards.
  press: { stiffness: 420, damping: 30, mass: 0.7, useNativeDriver: true },
};

// score >= 75: primary, >= 55: gold, else coral -- matches the mockup's
// scoreColor() and the app's existing scoreColor() convention in ResultsScreen.
export function scoreColor(score) {
  if (score >= 75) return colors.primary;
  if (score >= 55) return colors.gold;
  return colors.coral;
}
