# Tip photos

Drop generated tip images here, one file per issue, named after the tip's
`issue_id` from `data/08_coaching_ai/coaching_tips_database.json` (the same
30 ids already used as keys in `frontend/components/tipDiagrams/tipVisuals.js`).

`.jpg` or `.png` both work.

## Status (2026-08-10)

25 of the 30 existing ids now have a real photo, wired into
`tipDiagrams/tipPhotos.js`, from Jack's first ChatGPT-generated batch —
matched by reading each image's content (and, where present, an embedded
title) rather than assumed from download order:

```
fh_elbow_flare      fh_shoulder_drop     fh_wrist_collapse
fh_hip_rotation     fh_short_backswing   fh_big_loop
fh_followthrough_short  fh_head_drop     fh_rotation_range
fh_racket_distance
bh_shoulder_turn    bh_wrist_collapse    bh_elbow_high
bh_lead_hand        bh_late_prep         bh_weight_transfer
bh_short_followthrough  bh_head_movement bh_rotation_range
bh_racket_distance
sv_toss_low         sv_toss_position     sv_elbow_drop
sv_low_contact      sv_pronation
```

**Still missing a photo** (falls back to the SVG diagram): `sv_head_drop`,
`sv_trophy_position`, `sv_followthrough_across`, `sv_rotation_range`,
`sv_racket_distance`.

**5 generated images didn't match anything in this list** — they describe
serve issues that don't exist in `coaching_tips_database.json` today
(`sv_wrist_cock`, `sv_racquet_drop`, `sv_flat_contact_point`,
`sv_follow_through_finish`, `sv_balance_landing`). Saved under
`_unmatched_new_serve_tips/` rather than wired in, since there's nothing
for them to attach to yet — either they're new tip issues worth adding to
the database (real content: description + 3-severity phrasings, same shape
as the other 30), or they were a mid-session rename of an existing id and
should replace one of the 5 still-missing photos above. Worth Jack's
judgment call before spending more effort here.

## After adding a file

React Native/Metro can't `require()` an asset path built from a variable —
every image needs a static `require(...)` line. After saving a new photo
here, add one line to `frontend/components/tipDiagrams/tipPhotos.js`
mapping that `issue_id` to the file, e.g.:

```js
fh_elbow_flare: require('../../assets/tipPhotos/fh_elbow_flare.jpg'),
```

Any `issue_id` not yet in that map automatically falls back to the existing
SVG diagram — nothing breaks while photos are still being added
incrementally.
