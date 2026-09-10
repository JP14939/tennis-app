# Reference "ideal swing" clips

Drop three files here:

- `forehand-ideal.mp4`
- `backhand-ideal.mp4`
- `serve-ideal.mp4`

They are **display only** — shown in `SyncCompareScreen` next to the user's
own clip so a player can see what a clean swing looks like for the fault a tip
describes. They are never run through pose extraction / DTW.

Spec, generation prompts and acceptance criteria:
`docs/reference_swing_shotlist.md`.

The files are wired up in `frontend/config/referenceClips.js` (`CLIP_MODULES` +
`CONTACT_SEC`). `CONTACT_SEC` values are eyeball estimates — refine against the
delivered clips if the compare scrubber lands off.
