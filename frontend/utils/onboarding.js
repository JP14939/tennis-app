import { storage } from './storage';

// First-run gate. Set once the user has either finished the guided first-swing
// flow or explicitly skipped the welcome screen -- App.js reads this on boot to
// decide whether to open on OnboardingScreen or straight into the app.
// Mirrors utils/reviewPrompt.js's shape: thin wrappers over `storage`, every
// read defensive.
const KEY_COMPLETE = 'onboarding_complete';

export async function isOnboardingComplete() {
  const v = await storage.getItem(KEY_COMPLETE).catch(() => null);
  return v === '1';
}

export async function markOnboardingComplete() {
  await storage.setItem(KEY_COMPLETE, '1').catch(() => {});
}

// For a "replay the intro" affordance in Settings.
export async function resetOnboarding() {
  await storage.deleteItem(KEY_COMPLETE).catch(() => {});
}
