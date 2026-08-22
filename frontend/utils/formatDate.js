// SQLite's datetime('now') returns UTC with no 'Z' suffix, so the browser/
// RN Date parser would otherwise treat it as local time -- append one so
// it's parsed as UTC. Was reimplemented identically (workaround line + NaN
// guard) in HomeScreen.js, HistoryScreen.js, CoachScreen.js, and
// MessageThreadScreen.js, each then formatting the result differently for
// their own display -- this is the one place the parsing logic lives now;
// callers keep their own display formatting on top of the returned Date.
export function parseServerDate(isoString) {
  if (!isoString) return null;
  const d = new Date(isoString.includes('Z') ? isoString : `${isoString.replace(' ', 'T')}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}
