# RESUME — swing-score redesign (B1: strengthen the rubric)

---

## RESULT — B1 CPU run 2026-09-08 (steps 1–3 + 5 done; step 4 = Jack)

- **Step 1 `enrich_pro_racket_body.py`**: 623/648 entries (96.1%) now carry a
  real `racket_body_distance`; 25 null (pose/racket not confident). DB backed up
  before write. Counter:
  `forehand True/False 325/8, backhand 226/7, serve 72/10`.
- **Step 2 `redesign_similarity.py cache`**: grown to 124 cache files
  (~21 in-db / ~79 held-out pro / ~45 amateur).
- **Step 5 `npm run verify:db`**: all 98 invariants hold after the DB write.

### `axes` (view-conditioned, sep = held_out − amateur pro-likeness)

Forehand: wrist_path_ratio +16, follow_through_height +18, racket_body_dist +13,
racket_path_ratio +9, contact_wrist_height +5; **negative/weak:**
contact_elbow_angle −3, racket_body_range −2, tempo_peak_frac −9, rotation −13.
Backhand: nearly everything discriminative (tempo +48, contact_wrist_lateral
+46, backswing_depth +43, racket_body_range +38, contact_wrist_height +29).
Serve: tempo_peak_frac +24, contact_wrist_lateral +23, backswing_depth +22,
follow_through_height +20, contact_elbow_angle +14, wrist_path_ratio +11;
**negative:** racket_body_range −10, racket_body_dist −6, racket_path_ratio −2,
contact_wrist_height −28 (!).

### `rubric` (current CURATED_AXES, pre-recuration)

| shot     | held_out median | amateur median | gap    |
|----------|-----------------|----------------|--------|
| forehand | 60.2            | 54.4           | **+5.8** |
| backhand | 59.7            | 34.0 (n=5)     | +25.7  |
| serve    | 64.8            | 47.6           | +17.2  |
| combined | 61.6            | 52.6           | **+9.0** (DTW v0 ≈ +3) |

### Decision (per "Decision after step 4" below)

Forehand gap (+5.8) is **not** backhand-comparable → **"still weak" branch.**
Options: add axes (racket lag, swing-plane tilt) or build B2 with forehand
flagged `confidence: 'low'` + softer copy. Serve (+17.2) and backhand are fine.

### Step 4 still outstanding (Jack — judgement call)

Re-curate `CURATED_AXES` from the `axes` table above: drop the negatives now in
the lists — forehand `contact_elbow_angle`, `racket_body_range`; serve
`racket_body_range`, `racket_path_ratio` — reweight ∝ sep, re-run `rubric` to
confirm the gaps hold or improve.

**Status as of 2026-09-08:** code prep done + tested against the existing
84-clip cache. Two CPU-heavy jobs are queued (were blocked by net-model
training holding the CPU). This doc is the self-contained runbook to finish B1.

Full context: `~/.claude/plans/rosy-noodling-reef.md` and the memory note
`project_similarity_score_separation` (rounds 1–4).

---

## TL;DR of where we are

The old 0–100 score can't tell a pro swing from a decent amateur's (nearest-pro
DTW distance: amateur 0.48 vs held-out pro 0.45 — inside the noise). ~10 DTW
variants failed. **The rubric approach works**: grade a swing on independent
biomechanical axes (contact height, elbow extension, swing tempo, racket
looseness…) against the pro database's *own* distribution for that shot type
**and camera view**.

Bench result so far (view-conditioned, no racket data yet):
combined held-out-pro vs amateur gap **+3 (DTW) → +13 (rubric)**.
Backhand **+32**, serve **+23**, forehand **+10** (still weakest).

## What's already done (committed to the working tree, not git)

- `scripts/17_amateur_eval/calibrate_similarity.py` — the original 3-bucket
  separation harness (round 1–2).
- `scripts/17_amateur_eval/redesign_similarity.py` — the metric bench.
  Subcommands: `cache` / `eval` (DTW variants) / `axes` (per-axis pro-likeness)
  / `rubric` (combined curated score) / `decomp`.
- `scripts/07_ball_racket_tracking/track_racket_in_clip.py` — added
  `racket_body_features()` → `{mean, range, path_ratio}`.
- `scripts/00_utils/enrich_pro_racket_body.py` — **fixed** a relative-path bug
  (it resolved `clip_path` as an absolute path → would have written all-null),
  added resume/periodic-flush, now also stores `entry['racket_body_features']`.
- View-conditioned pro distributions (`_pro_dists_by_view`,
  `_axis_prolikeness`) + racket axes wired into `axes` and `rubric`.
- `CURATED_AXES` in `redesign_similarity.py` re-curated from the last
  view-conditioned `axes` run.
- `data/17_amateur_eval/traj_cache/` — 84 v2 cache files (21 in-db, ~45
  amateur, ~18 held-out), each with `user_traj` + `racket_frames`.

Nothing production / frontend / backend was touched. Nothing deployed.

---

## RUN THIS when the CPU is free

```powershell
cd C:\Users\jackp\tennis_app\scripts
.\venv\Scripts\activate

# 1. Pro racket-mechanics enrich (~35 min, ~413 clips). Backs up the DB first.
#    Resumable — safe to Ctrl-C and re-run. Also revives the racket half of
#    phase_breakdown.score_body_rotation() in the live app.
python 00_utils\enrich_pro_racket_body.py

#    sanity check it wrote real values:
python -c "import json; d=json.load(open(r'..\data\06_pro_database\pro_database.json')); import collections; print(collections.Counter((e['shot_type'], e.get('racket_body_distance') is not None) for e in d['entries']))"

# 2. Grow the held-out pro test set 18 -> ~58 (checkpointed — only the ~40 new
#    clips extract, ~30 min). Default args are already --in-db 21 --held-out 60
#    --amateur 45.
python 17_amateur_eval\redesign_similarity.py cache

# 3. Re-run the analysis (fast, no extraction):
python 17_amateur_eval\redesign_similarity.py axes
python 17_amateur_eval\redesign_similarity.py rubric

# 4. Re-curate CURATED_AXES in redesign_similarity.py from the step-3 `axes`
#    table: keep axes with sep >= ~ +7 for that shot; drop / down-weight the
#    rest. Weight ~ proportional to sep. Then re-run `rubric` to confirm.

# 5. DB integrity still OK after the enrich write:
cd ..\backend ; npm run verify:db
```

## Decision after step 4

Report the final per-shot held-out-vs-amateur gap + IQR overlap to Jack. Then:
- **forehand + serve gaps ≥ backhand-comparable (≈ +15, IQRs mostly disjoint)**
  → proceed to **B2** (build `scripts/08_comparison_engine/technique_score.py`).
- **still weak** → either add more axes (racket lag, swing-plane tilt, serve
  knee-bend — knee needs a wider-landmark re-extract) or build B2 with
  forehand/serve flagged `confidence: 'low'` and softer copy.

## B2 / B3 / B4 (deferred — see the plan file for detail)

- **B2** `technique_score.py` + `data/06_pro_database/technique_axis_stats.json`
  (per-shot, per-view axis median/IQR, rebuilt alongside the DB).
  `score_technique(user_traj, racket_frames, shot_type)` →
  `{overall, axes:[…], confidence}`. Reuse `phase_breakdown.rotation_range`,
  `racket_body_features`, and the `_angle` / `_win` / `axis_values` helpers
  now in `redesign_similarity.py`.
- **B3** wire into `compare_swing.compare()` (reuse the `track_racket_body`
  call it already makes for phase breakdown), persist `technique_score` in
  `backend/src/routes/history.js:211` (currently `top.overall_score ?? top.similarity`),
  headline it in `frontend/screens/ResultsScreen.js` (`:370`), demote the pro
  match to a "Closest pro: {X} · N% similar" line, same for
  `frontend/screens/VersusResultsScreen.js:137`. This folds in the cosmetic
  "two contradicting numbers" fix (Phase A) — not shipped separately.
- **B4** after Phase 0a (`sample_every` 3→1 + pro re-extraction): rebuild
  `technique_axis_stats.json`, re-validate. Nothing else in B needs redoing.

## Gotchas

- `redesign_similarity.py` imports from `calibrate_similarity.py` (same dir) —
  keep both.
- The cache is keyed by query id; `CACHE_VERSION = 2`. Bump it if the cache
  record shape changes again (forces re-extraction).
- Amateur backhand only has **5** real labels — a hard ceiling, don't fake it;
  backhand numbers are directional.
- `data/17_amateur_eval/` is under `data/` (gitignored) — none of the cache or
  results files are in git.
- The pro DB `pro_database.json` write in step 1 is **local only** — `data/` is
  gitignored and CD never touches it. Server transfer bundles with the Phase 0a
  pro-DB copy (see `JACK_TODO.md` roadmap).
