// Mirrors backend/src/config/shotTypes.js -- the three shot types the ML
// pipeline actually analyses. Was previously redefined verbatim as
// `['forehand', 'backhand', 'serve']` in 4 separate screens (each one also
// serving as that screen's shot-type picker), plus reimplemented as a
// `{value, label}`/`{label, value}` array in 3 more. Import this array
// (or map over it to build a labelled variant) instead of redeclaring it.
export const SHOT_TYPES = ['forehand', 'backhand', 'serve'];
