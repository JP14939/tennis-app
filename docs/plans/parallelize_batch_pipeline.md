# Parallelize the overnight batch swing-analysis pipeline

_Parked plan from an earlier session — not yet executed. Preserved here so it isn't lost._

## Context

Tonight's flow (`scratchpad/analyze_rallies.py` + `overnight_pipeline.sh`,
driven by two already-uploaded match videos under Jack's account) processes
every detected swing sequentially: extract poses → classify shot type
(rule-based + Claude vision verifier) → compare against the pro database →
save to history. Two safe optimizations already landed tonight (single pose
extraction per swing instead of two; a shared pose-landmarker for
angle/view-direction detection instead of two more model reloads), cutting
per-swing time from ~73s to ~40s — verified bit-identical output before and
after, and confirmed the live `/api/analyse` route (which never passes the
new optional params) is untouched.

That's still one swing at a time. This dev machine has 22 logical CPU
cores and the work is CPU-bound (MediaPipe pose inference, DTW), so running
several swings concurrently is the next real lever — Python's GIL rules out
threads for this, so it needs real OS processes (`multiprocessing` /
`concurrent.futures.ProcessPoolExecutor`).

Jack also asked whether this would work on a host. Two separate questions
bundled in there, both worth answering plainly:
1. **Does the parallelization code itself port to Linux?** Yes, with two
   fixable gaps: `analyze_rallies.py` currently hardcodes Windows paths
   (`C:\Users\jackp\...` for the token file, log file, and video paths)
   instead of reusing `scripts/00_utils/paths.py`'s portable `DATA_DIR`/
   `BACKEND_DIR` pattern already used everywhere else in the codebase —
   these need to become OS-agnostic for this script to run unmodified on
   the VM. `multiprocessing` itself works fine on Linux (uses `fork`,
   actually cheaper than Windows' `spawn`), no code changes needed for that
   part specifically.
2. **Will it actually be faster there?** Not with the VM as currently
   provisioned. The Oracle instance Jack just created only got **1 OCPU /
   6GB RAM** (Ampere capacity was constrained to the minimum shape in every
   availability domain tried) — parallel workers on a single core would
   just context-switch against each other with zero real speedup, and
   could even net-negative from N sets of MediaPipe/YOLO models loaded into
   6GB RAM simultaneously. This only pays off on the host once/if Jack gets
   more OCPUs allocated (the free tier allows up to 4) by retrying instance
   creation later when Ampere capacity frees up, or by resizing the
   existing instance up if capacity becomes available in its AD.

Given that, the plan below builds this to run well on this dev machine now
(where it has 22 cores to actually use) and to be *correct and portable*
on the host today even if it can't yet be *fast* there — worker count is
auto-detected from `os.cpu_count()` so it naturally degrades to
effectively-sequential (1-2 workers) on the current VM shape without any
separate code path, and speeds back up automatically if Jack later gets a
bigger shape.

## Plan

### 1. Restructure into a coordinator + worker-pool shape
Split `analyze_rallies.py`'s current single loop into two roles:
- **Coordinator** (main process, unchanged responsibilities): fetch each
  job's rallies from `/api/highlights/jobs/:id` (already built,
  `backend/src/routes/highlights.js`), run `find_swings_in_clip()` per
  rally (this stays sequential — it's fast, and rally clips must be read
  one at a time anyway), and extract each swing's short clip via the
  existing `extract_clip()` (`scripts/04_clip_extraction/extract_clips.py`).
  This produces a flat worklist of `(rally_id, swing_index, swing_clip_path,
  contact_time_sec)` tuples.
- **Worker pool** (`concurrent.futures.ProcessPoolExecutor`): each worker
  takes one worklist item and does the expensive part — pose extraction
  (`extract_user_poses`, already deduped tonight), `get_verified_shot_type()`,
  `compare()`, and the `POST /api/history` call — then returns a small
  result summary (success/failure, shot_type, similarity, training-log
  tuple) to the coordinator rather than writing shared state directly.

### 2. Make the shared training-log write safe across processes
`scripts/14_shot_classifier/shot_classifier_training_log.py`'s
`log_example()` currently does an unguarded file append. Multiple worker
processes calling this concurrently risks interleaved/corrupted lines on
Windows (less of a risk but still not guaranteed on Linux either). Fix:
add an optional `lock=None` parameter to `log_example()` (same
optional-parameter-preserves-default-behavior pattern used for tonight's
`frames_fps` additions) and have the coordinator create one
`multiprocessing.Lock()`, pass it to each worker via the pool's
`initializer`, and have workers acquire it only around the `log_example()`
call itself — not the whole classification step, so the Claude API calls
(network-bound, safe to run concurrently) aren't needlessly serialized.

### 3. Add checkpointing so a restart never double-saves
Right now, killing and re-running the script would re-process every rally
from scratch, creating duplicate `analyses` rows in Jack's history (already
identified as a real risk tonight when deciding not to touch the running
job). Fix: the coordinator writes a `(job_id, rally_id, swing_index)` key
to an append-only `completed_swings.jsonl` checkpoint file the moment each
worker reports success, and on startup reads that file into a skip-set
before building the worklist. Cheap, portable (plain JSONL, no DB), and
makes the whole pipeline safely resumable/interruptible from now on —
including on the host later.

### 4. Auto-size the worker pool from real resources, not a guess
`worker_count = max(1, min(os.cpu_count() - 2, MAX_WORKERS, ram_budget))`:
- Reserve 2 cores for the Node backend + calibration server already
  running alongside this.
- Cap `MAX_WORKERS` conservatively (start at 6) to avoid hammering the
  Anthropic API with too many concurrent verifier calls at once (rate-limit
  risk, same `TooManyRequests` class of error already seen tonight with the
  Oracle CLI — worth backing off the same way if it shows up here).
- A rough RAM budget check (`psutil.virtual_memory().available`, already a
  pinned dependency in `scripts/requirements.txt`) divided by an estimated
  ~1-1.5GB per worker (MediaPipe + YOLO model weights loaded per process)
  stops it from over-committing on a small host — this is what makes the
  *same* script safely degrade to ~1 worker on the current 6GB VM instead
  of needing a separate low-resource code path.

### 5. Make paths portable
Replace `analyze_rallies.py`'s hardcoded `C:\Users\jackp\...` literals
(token file, log path, `SCRIPTS_DIR`) with `scripts/00_utils/paths.py`'s
existing `DATA_DIR`/`BACKEND_DIR`/`SCRIPTS_DIR` constants, and take the
API base URL from `EXPO_PUBLIC_API_BASE`-style env var (or default to
`localhost:5000`) instead of a hardcoded `http://localhost:5000` — same
convention the frontend already uses in `config/api.js`. This is what
actually makes "runs on a host" true rather than aspirational.

## Verification
- Before touching the live 22-core run pattern: re-verify with the same
  identity check used tonight (run one known rally through both the old
  sequential path and the new pooled path, confirm bit-identical
  `similarity`/`matches`/`tips` output) so parallelizing doesn't
  accidentally change results, only speed.
- Kill and restart the pipeline mid-run on a small test batch, confirm the
  checkpoint file prevents any duplicate `analyses` rows in
  `backend/data/app.db`.
- Force a small worker pool (e.g. `MAX_WORKERS=2`) and confirm
  `shot_classifier_training_log.jsonl` has no truncated/malformed lines
  after a run with real concurrent writes.
- Once the Oracle VM is reachable, run the same script there unmodified
  and confirm `worker_count` naturally resolves to 1-2 given its current
  1 OCPU/6GB shape — proving portability without expecting a speedup yet.

## Note

There is now also `scripts/15_batch_analysis/analyze_rallies_parallel.py`
in the repo — a fully built, tested, and validated implementation of this
plan (coordinator/worker split, checkpointing, locked training-log writes,
auto-sized worker pool, portable paths). It has been verified bit-identical
against the sequential path and stress-tested for the shared-model-weights
race condition, but has never been run against real production job data.
Treat this plan document as the design record; the script is the
implementation to actually run next time a batch job is needed.
