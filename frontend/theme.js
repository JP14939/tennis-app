// Shared design tokens for the "Pine & Lime" redesign (Home, History,
// Premium, Profile, Upload's pick phase, Results, Live Camera). Every other
// screen (Login, Signup, VersusPick, VersusResults, Highlight*, FenceTutorial)
// is out of scope for this pass and keeps its own local dark-theme literals.
//
// Colors were computed from the design mockup's oklch() values via the real
// OKLab->sRGB formula (React Native's style engine can't parse oklch()).

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

// score >= 75: primary, >= 55: gold, else coral -- matches the mockup's
// scoreColor() and the app's existing scoreColor() convention in ResultsScreen.
export function scoreColor(score) {
  if (score >= 75) return colors.primary;
  if (score >= 55) return colors.gold;
  return colors.coral;
}
