import { Platform } from 'react-native';
import { Audio } from 'expo-av';
import { storage } from './storage';

// Local, device-only preference -- not synced to the backend, unlike
// notifications_enabled (that's server data other clients/the backend care
// about; this is purely "does this phone make noise when you tap things").
const PREF_KEY = 'sound_effects_enabled';

let audioModeSet = false;

export async function isSoundEnabled() {
  const stored = await storage.getItem(PREF_KEY).catch(() => null);
  return stored !== 'false'; // default on
}

export async function setSoundEnabled(enabled) {
  await storage.setItem(PREF_KEY, enabled ? 'true' : 'false');
}

async function ensureAudioMode() {
  if (audioModeSet || Platform.OS === 'web') return;
  audioModeSet = true;
  // UI sound effects should be silenced by the phone's hardware mute switch
  // (same as iOS's own keyboard clicks) -- the opposite of what video
  // playback wants, so this is scoped to this module, not a global default.
  try {
    await Audio.setAudioModeAsync({ playsInSilentModeIOS: false });
  } catch {
    // Non-fatal -- a missing audio-mode config just means the sound might
    // ignore the mute switch on some devices, not that it fails to play.
  }
}

// Shared preload/play machinery for a single sound asset -- each call site
// below owns its own cached Sound object (module-level `require()` needs a
// static string literal per asset, so this can't be data-driven by path;
// each createPlayer() call inlines its own require()).
function createPlayer(loadAsset) {
  let soundObject = null;
  let loadingPromise = null;

  async function getSound() {
    if (soundObject) return soundObject;
    if (!loadingPromise) {
      loadingPromise = (async () => {
        await ensureAudioMode();
        const { sound } = await Audio.Sound.createAsync(loadAsset());
        soundObject = sound;
        return sound;
      })();
    }
    return loadingPromise;
  }

  // Fire-and-forget -- a missing/failed sound should never break whatever
  // it's attached to, so every failure mode here is swallowed.
  return function play() {
    isSoundEnabled()
      .then((enabled) => {
        if (!enabled) return;
        return getSound();
      })
      .then((sound) => sound?.replayAsync())
      .catch(() => {});
  };
}

// Primary CTA taps (Start analysis, Save, Submit, Send, etc.).
export const playTapSound = createPlayer(() => require('../assets/sounds/tap.mp3'));

// A fresh swing analysis finishing with a real score.
export const playCompleteSound = createPlayer(() => require('../assets/sounds/complete.mp3'));

// Genuinely special moments: a great swing (score >=75), a rank-tier
// upgrade, a friend/coach code successfully redeemed, or your confirmation
// being the one that verifies a community-submitted court.
export const playAchievementSound = createPlayer(() => require('../assets/sounds/achievement.mp3'));

// A new message arriving while its thread is open.
export const playNotificationSound = createPlayer(() => require('../assets/sounds/notification.mp3'));
