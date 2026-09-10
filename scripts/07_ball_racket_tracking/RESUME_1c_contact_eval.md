# RESUME — Roadmap 1c contact-frame eval (CPU work, paused 2026-09-08)

---

## RESULT — serve gate run 2026-09-08 (CPU freed)

Ran the 70-serve BEFORE/AFTER exactly as below (`--anchor auto`, stash/pop of
`serve_anchor.py`). Outcome:

| run                              | median \|err\| | p90    | ≤3f   |
|----------------------------------|----------------|--------|-------|
| BEFORE (`_argmax_earliest`)      | 14.0f          | 80.8f  | 37.1% |
| AFTER (`_apex_plateau_frame`)    | 14.0f          | 80.8f  | 37.1% |

**Identical — no regression, no improvement.** Gate ("AFTER median ≤ BEFORE")
passes trivially. `within3` did not rise.

Why it doesn't move: serve median is dominated by `ball_occlusion_gap` blowups
on low camera angles (20–35°: n=21, bias +56f). The healthy subset
(`ball_racket_proximity`, mostly 50–90° camera, n=40) is already 5.0f median and
locks onto contact regardless of where the apex anchor seeds the ±0.3s
`find_contact_frame` search — so shifting the anchor a few frames changes
nothing. The real serve error source (occlusion-gap method + low-angle camera)
is outside 1c scope.

CSVs: `scratchpad/_serve_BEFORE.csv`, `_serve_AFTER.csv` (session scratchpad).

**Decision needed (Jack):** either (a) accept the recentring as safe-but-neutral
and ship 1c, moving the occlusion-gap/low-angle problem to its own item, or
(b) tune `APEX_PLATEAU_TOL` (0.04 → 0.02 / 0.06) / try Part B options 2–3 first.
The FH/BH "unchanged by construction" argument below still holds — not re-run.

Paused mid-run because the laptop CPU was needed elsewhere. All **code** for 1c
is done, committed-pending, and tested (105/105 green in
`07_ball_racket_tracking/` + `00_utils/`). What's left is **measurement only** —
the accuracy gate the plan requires before this ships.

Plan: `C:\Users\jackp\.claude\plans\hashed-imagining-stardust.md`
Session log: `HANDOVER.md` → "Session 2026-09-08 (later²)"

---

## The gate (from the plan)

> `eval_pro_clip_contact.py` — serve median |err| **improves** vs baseline;
> **FH/BH rows unchanged**.

### FH/BH "unchanged" — already guaranteed by construction, no run needed

`--anchor auto` routes non-serve clips through
`compare_swing.auto_contact_anchor_frame`, whose groundstroke branch is
*literally* `frames[find_peak_wrist_frame(frames, fps)]['frame']` — identical to
the legacy `--anchor wrist` path. `serve_anchor.py` is only called for
`shot_type == 'serve'`. And the eval never calls `compare()`, so the Part A
wiring changes don't touch it either. So FH/BH numbers cannot move. (Spot-check
a handful if paranoid: `--anchor auto --only <a few FH/BH ids>` vs the existing
`eval_pro_clip_contact.csv` rows.)

### Serves — this is the run that matters. 70 teacher-labelled serve clips.

Need **before vs after** on the *apex* anchor (production already uses the apex
anchor for serves — the change under test is `_apex_plateau_frame` recentring vs
the old earliest-frame `_argmax_earliest`).

---

## Step-by-step to finish (run when CPU is free — venv, ~70–90 min for serves)

```powershell
cd C:\Users\jackp\tennis_app\scripts
.\venv\Scripts\activate
cd 07_ball_racket_tracking

# 0. list the 70 serve entry ids
python -c "import eval_pro_clip_contact as e; l,b=e.teacher_labels(); print(','.join(i for i in sorted(l) if b[i]['shot_type']=='serve'))" > _serve_ids.txt

# 1. BEFORE — stash the Part B change, run serves into a baseline CSV
git stash push scripts/00_utils/serve_anchor.py     # from repo root; or: git -C ..\.. stash push scripts/00_utils/serve_anchor.py
del ..\..\data\07_ball_racket_tracking\eval_pro_clip_contact_auto_anchor.csv   # 36 BH/FH rows, not needed
python eval_pro_clip_contact.py --anchor auto --only (Get-Content _serve_ids.txt)
copy ..\..\data\07_ball_racket_tracking\eval_pro_clip_contact_auto_anchor.csv _serve_BEFORE.csv
git stash pop

# 2. AFTER — restore, wipe, re-run the same 70
del ..\..\data\07_ball_racket_tracking\eval_pro_clip_contact_auto_anchor.csv
python eval_pro_clip_contact.py --anchor auto --only (Get-Content _serve_ids.txt)
copy ..\..\data\07_ball_racket_tracking\eval_pro_clip_contact_auto_anchor.csv _serve_AFTER.csv

# 3. compare — the report prints a "BY SHOT TYPE" section; for serves compare
#    median|err|, p90, <=3f between the two runs. Or diff the CSVs directly:
python -c "
import csv,statistics as s
def stats(p):
    e=[abs(float(r['err_frames_heuristic'])) for r in csv.DictReader(open(p)) if r['err_frames_heuristic']]
    e.sort(); n=len(e)
    return dict(n=n, median=round(s.median(e),1), p90=round(e[int(0.9*(n-1))],1),
               within3=round(sum(x<=3 for x in e)/n,3))
print('BEFORE', stats('_serve_BEFORE.csv'))
print('AFTER ', stats('_serve_AFTER.csv'))
"
```

**Pass:** AFTER serve `median` ≤ BEFORE serve `median` (and ideally `within3` up).
If it regresses → the plateau tol (`APEX_PLATEAU_TOL = 0.04` in
`scripts/00_utils/serve_anchor.py`) is the knob; try 0.02 / 0.06, or fall back
to plan Part B options 2 (toss-arm gate) / 3 (`APEX_TO_CONTACT_LEAD_SEC` sweep).

### Optional — full eval refresh for the record

`python eval_pro_clip_contact.py --anchor auto` with no `--only` runs all ~540
labelled clips (~9 h now — the review log grew from ~197 to 540). Not required
for the gate. Resumable: it skips ids already in
`eval_pro_clip_contact_auto_anchor.csv`.

---

## After Phase 0a (`sample_every` 3→1) lands

The pose cache is stride-3. Before re-running anything:
```
rmdir /s /q C:\Users\jackp\tennis_app\data\07_ball_racket_tracking\.eval_pose_cache
```
then repeat the serve run above as a regression check at the new stride.

---

## Then: finish 1c verification (plan "Verification" section)

- [ ] serve gate above passes
- [ ] `python scripts/00_utils/ml_status_report.py` shows the `onset_classifier` row (done — verified 2026-09-08)
- [ ] local full-stack: `POST /api/analyse` no-audio clip + no `contactTime` →
      response JSON has `contact_source` (`ball_occlusion_gap` / `wrist_peak` /
      `serve_apex`); audio clip → `audio_onset`
- [ ] `cd backend && npm test` (~620, confirm green — `contact_source` is
      additive, shouldn't disturb anything)
- [ ] `cd scripts && pytest` full suite
- [ ] then commit (branch off master; files listed in the HANDOVER session entry)

---

## ⚠️ Unrelated uncommitted changes noticed this session (NOT mine, NOT touched)

`git status` showed these two modified before I started and I left them alone —
someone/something else has WIP here:
- `scripts/00_utils/enrich_pro_racket_body.py`
- `scripts/07_ball_racket_tracking/track_racket_in_clip.py`

Check with whoever's been working racket keypoints (roadmap 2d) before committing
1c so they don't get swept up.
