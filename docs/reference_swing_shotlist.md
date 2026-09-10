# Reference "ideal swing" clips — shot list & generation brief

**Status: DELIVERED 2026-09-10.** The three clips exist in
`frontend/assets/reference/{forehand,backhand,serve}-ideal.mp4` and are wired
into `referenceClips.js` (uncommitted). The route was NOT the white-background
AI generation this brief describes — it was **Luma Dream Machine "Modify Video"**
on real behind-view pro footage (`forehand_0209` / `backhand_0246` /
`serve_0176`), with watermark removal + a CapCut crop. Real tennis-stadium
background, not white void. Full story: `HANDOVER.md` "Session 2026-09-10
(later)". The brief below is kept for historical context only.

## What these are (and are not)

Three short clips — **forehand, backhand, serve** — of a clean, near-model
amateur-appropriate swing on a plain white background. They are shown in the
**side-by-side viewer** (`SyncCompareScreen`) next to the user's own clip so a
player reading a tip like *"your elbow is too far from your body at contact"*
can **see** the difference instead of only reading it.

**Display only.** These clips are never sent through MediaPipe pose extraction
or DTW. They are not a scoring reference and not a pro-database entry. The real
pro-match comparison (the existing "Compare side-by-side" button driven by
`compare_swing.py`) is untouched. That means the clips only have to look right
to a human eye — physical-plausibility failures that would wreck pose
extraction don't matter here — but they must still be biomechanically sane
enough not to teach a bad habit.

"Perfect" is the wrong bar. There is no perfect swing and the audience is
amateurs. The bar is: **clean, unhurried, textbook fundamentals, nothing a
coach would flag.**

## Common spec (all three clips)

| Property | Value |
| --- | --- |
| Background | Seamless matte white (cyclorama / infinity wall look). No court lines, no net, no shadow clutter. A soft contact shadow under the feet is fine. |
| Subject | One player, mid-shot to full-body, athletic tennis attire in a **single flat mid-tone colour** (not white — must separate from the background; a mid-grey or muted navy). Racket clearly visible throughout. |
| Lighting | Even, soft, high-key. No harsh rim light, no colour cast. |
| Camera | Locked off (tripod, no handheld drift, no zoom, no pan). |
| Framing | Player centred with headroom above the racket at its highest point and full footwork in frame. |
| Motion | Real-time capture, then the app slows it — deliver at normal speed. One single swing, no rally. |
| Duration | 2.5–4 s: ~1 s pre-swing ready position, the swing, full follow-through, ~0.5 s hold on the finish. |
| Frame rate | 60 fps if possible (cleaner slow-mo in the scrubber), 30 fps acceptable. |
| Delivery | H.264 .mp4, ≤ 1080×1920 (portrait) or 1080×1080, ≤ ~4 MB each after encode (they ship inside the app bundle). |

### Camera angle

Primary angle: **rear three-quarter** — behind the player and offset ~30°
toward their dominant side, camera at roughly waist height. This is the angle
users are already told to film from ("behind the baseline"), so the
side-by-side reads as like-for-like, and it happens to show the
highest-value faults (elbow-away-from-body, racket staying cramped, follow-
through wrapping, hip rotation).

Side-on (perpendicular, player moving across frame) is a good **phase-2**
second angle — it's where contact height, head drop, shoulder drop and the
serve trophy position read best — but do rear three-quarter first.

## Per-shot generation prompts

Use these with a text-to-video model (Veo / Sora / Kling / Runway) **or** as
the brief for a real shoot. Expect to generate 10–20 takes per shot and keep
one; trim aggressively to the clean swing. Watch for the known AI failure
modes: racket morphing or vanishing, a second ball appearing, feet sliding
instead of stepping, a follow-through that goes limp.

### Forehand — `forehand-ideal.mp4`

> A right-handed tennis player performing one textbook forehand groundstroke,
> filmed from behind and slightly to their right at waist height, against a
> seamless pure-white studio background. Real-time speed, locked-off tripod
> shot. The player starts side-on in a balanced ready position, takes a smooth
> unhurried unit turn with shoulders and hips coiling together, a compact
> low-to-high loop, contact out in front with a firm wrist and the hitting
> elbow close to the body, then a full follow-through with the racket wrapping
> up over the left shoulder, finishing balanced. Athletic mid-grey kit, racket
> clearly visible throughout, soft high-key lighting, soft contact shadow
> under the feet, no court, no net, no other people.

Key checkpoints for a keeper: elbow stays in near the ribs at contact • hips
clearly rotate open toward where the net would be • full loop back, not a
chopped backswing • racket finishes over the opposite shoulder.

### Backhand — `backhand-ideal.mp4`

> A right-handed tennis player performing one textbook two-handed backhand
> groundstroke, filmed from behind and slightly to their left at waist height,
> against a seamless pure-white studio background. Real-time speed, locked-off
> tripod shot. Early shoulder turn so the back faces the net, weight loaded on
> the back foot then transferring forward onto the front foot through contact,
> both hands firm on the grip, the lead (left) arm driving the racket through
> a contact point out in front, then a full extension through the ball and a
> finish with the hands up near the right shoulder, balanced. Athletic
> mid-grey kit, racket clearly visible throughout, soft high-key lighting,
> soft contact shadow under the feet, no court, no net, no other people.

Key checkpoints: shoulders turn fully in prep (early, not late) • visible
weight shift back-to-front • both wrists stay firm through contact • full
finish, hands high.

### Serve — `serve-ideal.mp4`

> A right-handed tennis player hitting one textbook flat/first serve, filmed
> from behind and slightly to their right at waist height, against a seamless
> pure-white studio background. Real-time speed, locked-off tripod shot. Calm
> rhythmic start, a consistent toss placed slightly in front and to the right
> peaking about a racket-length above the reach, a full classic trophy
> position with the tossing arm extended up and the hitting elbow high and the
> racket pointing skyward, knees bent, then a drive up with the legs, a deep
> racket drop behind the back, full upward extension to a high contact point,
> natural forearm pronation through the ball, and a relaxed follow-through
> down and across the body to the left hip, landing on the front foot,
> balanced. Athletic mid-grey kit, racket clearly visible throughout, soft
> high-key lighting, soft contact shadow, no court, no net, no other people.

Key checkpoints: toss is stable and slightly in front • clean trophy shape
with elbow high • contact point is high with the arm fully extended • wrist
snaps / pronates through, doesn't stay stiff • finish crosses the body.

## Acceptance checklist (per clip)

- [ ] Background is clean white edge-to-edge; no court/net artefacts
- [ ] Racket is continuously visible and keeps a consistent shape
- [ ] Exactly one ball, one swing, one player
- [ ] Feet plant and step — no sliding / skating
- [ ] The specific per-shot checkpoints above all hold
- [ ] Follow-through completes and the player holds a balanced finish
- [ ] 2.5–4 s, encodes under ~4 MB at ≤1080p
- [ ] Nothing a coach would flag as a fault

## Delivery & wiring

1. Encode each clip to H.264 .mp4, name them exactly:
   `forehand-ideal.mp4`, `backhand-ideal.mp4`, `serve-ideal.mp4`.
2. Drop them in `frontend/assets/reference/`.
3. In `frontend/config/referenceClips.js`, uncomment the three `require(...)`
   lines in `CLIP_MODULES` and set `CONTACT_SEC` for each clip to the time (in
   seconds from the clip's first frame) at which racket-ball contact happens —
   this is what aligns the reference against the user's clip on the shared
   contact-relative scrubber.
4. That's it. The "Watch the ideal swing" button on the results screen and the
   per-tip "See this done right" links are already wired and stay hidden until
   the clip for that shot type resolves.

Once done, tick the matching item in `TODO_MANUAL.md`.
