// Single source of truth for the three shot types the ML pipeline actually
// analyses (MediaPipe pose extraction + DTW against the pro database only
// covers these). Was previously redefined verbatim in 5 separate files
// (analyse.js, compareVideos.js, history.js, leaderboard.js,
// scripts/seedDrillsFromTips.js) -- each one doubling as this endpoint's
// validation gate, so adding a 4th shot type without updating every copy
// would silently 400 at whichever route got missed instead of failing loudly
// anywhere. Import this instead of redeclaring the array.
const SHOT_TYPES = ['forehand', 'backhand', 'serve'];

module.exports = { SHOT_TYPES };
