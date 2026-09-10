import * as StoreReview from 'expo-store-review';
import { storage } from './storage';

// "Ask for a rating at a happy moment" -- the single highest-leverage ASO
// lever after the store listing itself (ratings feed the ranking algorithm
// AND the conversion rate). The rules here are the ones every credible
// version of that advice shares:
//
//   - Only ever ask right after a *genuine win* -- here, a fresh swing
//     analysis that finished successfully and saved. Never during
//     onboarding, never after an error. The caller is responsible for only
//     invoking this from a success path; this module assumes every call is a
//     happy moment.
//   - Not on the very first one. A brand-new user hasn't decided whether
//     they like the app yet; asking then burns the ask for a lukewarm
//     rating. We wait for HAPPY_EVENTS_BEFORE_PROMPT.
//   - Not repeatedly. If they didn't act the first time, leave them alone
//     for MIN_DAYS_BETWEEN_PROMPTS, and stop entirely after MAX_PROMPTS
//     lifetime attempts.
//   - The OS is the final gate. StoreReview.requestReview() shows Apple's /
//     Google's own native sheet, which they rate-limit hard (iOS: at most a
//     few times a year, and only if the system feels like it) and which
//     gives us NO callback -- we can't know if the user rated, dismissed, or
//     never saw it. So all we can responsibly track is "did we attempt an
//     ask", and back off accordingly.
//
// Web is a no-op: StoreReview.isAvailableAsync() resolves false there.
//
// NOTE: the in-app native review sheet works on iOS and Android 5+ without
// any extra config. StoreReview.storeUrl() (the manual fallback) additionally
// needs ios.appStoreUrl / android.playStoreUrl in app.json -- add those once
// the real store listings exist so hasAction() can still succeed on older
// Android. Tracked in TODO_MANUAL.md.

const KEY_HAPPY_COUNT = 'review_prompt_happy_events';
const KEY_PROMPT_COUNT = 'review_prompt_attempts';
const KEY_LAST_PROMPT_AT = 'review_prompt_last_at';

const HAPPY_EVENTS_BEFORE_PROMPT = 2; // ask after the 2nd successful analysis
const MIN_DAYS_BETWEEN_PROMPTS = 60;
const MAX_PROMPTS = 3; // lifetime -- mirrors iOS's own annual ceiling
const DAY_MS = 24 * 60 * 60 * 1000;

async function readInt(key) {
  const raw = await storage.getItem(key).catch(() => null);
  const n = parseInt(raw ?? '', 10);
  return Number.isFinite(n) ? n : 0;
}

// Call this the instant a genuine win lands (a fresh analysis saved), BEFORE
// any delay -- so the count reflects "analyses completed", not "analyses after
// which the user lingered on the screen for another 2 seconds". Separate from
// considerReviewPrompt() precisely so a user who leaves fast still accrues the
// event.
export async function recordHappyEvent() {
  try {
    const n = (await readInt(KEY_HAPPY_COUNT)) + 1;
    await storage.setItem(KEY_HAPPY_COUNT, String(n));
  } catch {
    // best-effort
  }
}

// Checks every back-off rule against the events recorded so far and, if
// they all pass, asks the OS to show its native rating sheet. Does NOT record
// the happy event itself (recordHappyEvent does, immediately). Fire-and-forget:
// every failure mode is swallowed. Returns true only when a review request was
// actually issued (useful for tests / debugging; callers can ignore it).
export async function considerReviewPrompt() {
  try {
    const happyCount = await readInt(KEY_HAPPY_COUNT);
    if (happyCount < HAPPY_EVENTS_BEFORE_PROMPT) return false;

    const promptCount = await readInt(KEY_PROMPT_COUNT);
    if (promptCount >= MAX_PROMPTS) return false;

    const lastPromptAt = await readInt(KEY_LAST_PROMPT_AT);
    if (lastPromptAt && Date.now() - lastPromptAt < MIN_DAYS_BETWEEN_PROMPTS * DAY_MS) {
      return false;
    }

    if (!(await StoreReview.isAvailableAsync())) return false;
    // hasAction() is false when neither the native sheet nor a store-URL
    // fallback is possible -- don't burn an attempt slot on a no-op.
    if (StoreReview.hasAction && !(await StoreReview.hasAction())) return false;

    await StoreReview.requestReview();

    // Count the attempt and stamp the time only once we've actually asked.
    await storage.setItem(KEY_PROMPT_COUNT, String(promptCount + 1));
    await storage.setItem(KEY_LAST_PROMPT_AT, String(Date.now()));
    return true;
  } catch {
    return false;
  }
}

// Test / dev-menu helper -- wipes the back-off state so the next happy event
// can prompt again.
export async function resetReviewPromptState() {
  await Promise.all([
    storage.deleteItem(KEY_HAPPY_COUNT).catch(() => {}),
    storage.deleteItem(KEY_PROMPT_COUNT).catch(() => {}),
    storage.deleteItem(KEY_LAST_PROMPT_AT).catch(() => {}),
  ]);
}

export const _config = {
  HAPPY_EVENTS_BEFORE_PROMPT,
  MIN_DAYS_BETWEEN_PROMPTS,
  MAX_PROMPTS,
};
