const db = require('../db');

// Plain fetch to Expo's push API -- no expo-server-sdk dependency needed
// for a single fire-and-forget call site like this one.
const EXPO_PUSH_URL = 'https://exp.host/--/api/v2/push/send';

// Best-effort by design: a failed push (bad token, Expo API hiccup) should
// never take down the job that triggered it -- the user can still see the
// result next time they open the app.
async function sendPushNotification(userId, title, body, data = {}) {
  const user = db.prepare('SELECT notifications_enabled FROM users WHERE id = ?').get(userId);
  if (!user?.notifications_enabled) return;

  const tokens = db.prepare('SELECT token FROM push_tokens WHERE user_id = ?').all(userId);
  if (tokens.length === 0) return;

  const messages = tokens.map(({ token }) => ({
    to: token,
    title,
    body,
    data,
  }));

  try {
    await fetch(EXPO_PUSH_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(messages),
    });
  } catch (err) {
    console.error('[pushNotifications] send failed:', err.message);
  }
}

module.exports = { sendPushNotification };
