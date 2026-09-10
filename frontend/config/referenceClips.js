import { useEffect, useState } from 'react';
import { Asset } from 'expo-asset';

// Bundled "ideal swing" reference clips for the side-by-side viewer.
//
// DISPLAY ONLY. These are never fed to MediaPipe / DTW -- the real
// pro-database match is the separate "Compare side-by-side" button on
// ResultsScreen (compare_swing.py). These clips exist purely so a user
// reading a tip like "your elbow is too far from your body at contact" can
// watch a clean reference swing next to their own.
//
// The three clips live in frontend/assets/reference/ (see that folder's README
// and docs/reference_swing_shotlist.md for how they were produced). If a clip
// ever fails to resolve, useReferenceClip() returns null for that shot type and
// every entry point that uses it stays hidden -- nothing breaks.
const CLIP_MODULES = {
  forehand: require('../assets/reference/forehand-ideal.mp4'),
  backhand: require('../assets/reference/backhand-ideal.mp4'),
  serve:    require('../assets/reference/serve-ideal.mp4'),
};

// Racket-ball contact time (seconds from the clip's first frame) for each
// reference clip -- fixed per clip at authoring time. Used to align the
// reference against the user's clip on SyncCompareScreen's shared
// contact-relative scrubber. Set these to match the delivered clips.
// Measured from the delivered clips (racket-ball contact, seconds from frame 0).
// Eyeballed to ~1 frame (±0.03s) — nudge if the compare scrubber lands off.
const CONTACT_SEC = { forehand: 0.43, backhand: 1.0, serve: 0.3 };

// issue_id -> where to park the scrubber when a user taps "See this done
// right" on that specific tip, expressed in seconds relative to contact
// (backswing ≈ -0.5, contact = 0, follow-through ≈ +1.0, whole-swing
// rotation/extension issues ≈ -0.3). Mirrors the `phase` field of each issue
// in data/08_coaching_ai/coaching_tips_database.json.
const FOCUS_SEEK_T = {
  // forehand
  fh_elbow_flare: 0, fh_shoulder_drop: 0, fh_wrist_collapse: 0, fh_hip_rotation: 0,
  fh_short_backswing: -0.5, fh_big_loop: -0.5, fh_followthrough_short: 1.0,
  fh_head_drop: 0, fh_rotation_range: -0.3, fh_racket_distance: -0.3,
  // backhand
  bh_shoulder_turn: -0.5, bh_wrist_collapse: 0, bh_elbow_high: 0, bh_lead_hand: 0,
  bh_late_prep: -0.5, bh_weight_transfer: 0, bh_short_followthrough: 1.0,
  bh_head_movement: 0, bh_rotation_range: -0.3, bh_racket_distance: -0.3,
  // serve
  sv_toss_low: -0.5, sv_toss_position: -0.5, sv_elbow_drop: 0, sv_low_contact: 0,
  sv_pronation: 1.0, sv_head_drop: 0, sv_trophy_position: -0.5,
  sv_followthrough_across: 1.0, sv_rotation_range: -0.3, sv_racket_distance: -0.3,
};

/**
 * Resolves the bundled reference clip for a shot type to a playable URI.
 * Returns null while it's loading or if no clip is configured for that shot
 * type yet -- callers should hide their entry point when it's null.
 *
 * @param {'forehand'|'backhand'|'serve'} shotType
 * @returns {{ uri: string, contactSec: number } | null}
 */
export function useReferenceClip(shotType) {
  const mod = CLIP_MODULES[shotType] ?? null;
  const [uri, setUri] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setUri(null);
    if (!mod) return undefined;
    const asset = Asset.fromModule(mod);
    asset.downloadAsync()
      .then(() => { if (!cancelled) setUri(asset.localUri ?? asset.uri); })
      .catch(() => { if (!cancelled) setUri(null); });
    return () => { cancelled = true; };
  }, [mod]);

  if (!mod || !uri) return null;
  return { uri, contactSec: CONTACT_SEC[shotType] ?? 0 };
}

/**
 * For a coaching tip, the scrubber start position (seconds relative to
 * contact) that best shows the fault it describes. Falls back to contact.
 */
export function focusSeekTForTip(tip) {
  return FOCUS_SEEK_T[tip?.id] ?? 0;
}
