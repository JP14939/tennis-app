// m:ss formatting for a video-relative offset in seconds. Shared between
// HighlightReviewScreen.js and HighlightArchiveScreen.js's RallyBrowser --
// both display rally start times the same way.
export function formatTime(sec) {
  // Round the WHOLE value first, then split -- rounding sec%60 on its own
  // can hit 60 without carrying into minutes (e.g. sec=119.6 rounded that
  // way gave "1:60" instead of "2:00").
  const total = Math.round(sec);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}
