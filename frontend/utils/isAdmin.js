// UI-only convenience check (mirrors the backend's default ADMIN_EMAILS in
// backend/src/middleware/requireAdmin.js) -- the real gate is always
// server-side; this only decides whether to show admin-only UI at all
// (the Settings "Dev Page" row, LeaderboardSection's add-celebrity form).
// Extracted from LeaderboardSection.js's local copy so every admin-only UI
// check in the app reads from one place instead of risking two lists
// drifting out of sync.
const ADMIN_EMAILS = ['jack.p14370@gmail.com'];

export function isAdmin(user) {
  return ADMIN_EMAILS.includes((user?.email ?? '').toLowerCase());
}
