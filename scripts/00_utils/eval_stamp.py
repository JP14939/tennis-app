"""
Shared eval-result provenance stamping -- extracted from the pattern
hand-rolled in 17_amateur_eval/evaluate_amateur_dataset.py, which existed
because an unstamped results.jsonl silently mixed rows from different code/
model versions (this is what made the 2026-09 "64.5% -> 54.4%" comparison
meaningless -- it wasn't a real regression, just two versions in one file).

Any eval/benchmark script whose number gets quoted in HANDOVER.md/STATUS.md
should stamp its output rows with this instead of re-deriving git_sha/model
hashing per script. See CLAUDE.md's "Eval hygiene" section.
"""
import os
import subprocess

from paths import SCRIPTS_DIR

_git_sha_cache = None


def git_sha():
    """Short git SHA of the current HEAD, or 'unknown' outside a git checkout."""
    global _git_sha_cache
    if _git_sha_cache is None:
        try:
            _git_sha_cache = subprocess.check_output(
                ['git', 'rev-parse', '--short', 'HEAD'], cwd=SCRIPTS_DIR,
                text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:
            _git_sha_cache = 'unknown'
    return _git_sha_cache


def file_fingerprint(path):
    """A cheap stand-in for a content hash: mtime + size, keyed by the
    parent directory name (e.g. a training run's output folder). Good enough
    to detect "this model file changed since the last eval row" without
    hashing potentially large model weights on every row."""
    try:
        st = os.stat(path)
        label = os.path.basename(os.path.dirname(path)) or os.path.basename(path)
        return f'{label}:{int(st.st_mtime)}:{st.st_size}'
    except OSError:
        return None


def provenance(**model_paths):
    """Build a provenance dict: {'git_sha': ..., <name>_model: fingerprint, ...}
    for each keyword model path given, e.g. provenance(ball='path/to/best.pt')."""
    stamp = {'git_sha': git_sha()}
    for name, path in model_paths.items():
        stamp[f'{name}_model'] = file_fingerprint(path) if path else None
    return stamp


def check_single_version(records, *version_keys):
    """Return (ok, versions) where versions maps each key to its set of
    distinct values across records. ok is False if any key has more than one
    distinct value -- i.e. the records span multiple code/model versions and
    aren't a comparable baseline. Call this before trusting a headline number
    computed from a possibly-stale, append-only results file."""
    versions = {}
    ok = True
    for key in version_keys:
        seen = {r.get(key, 'unstamped') for r in records}
        versions[key] = seen
        if len(seen) > 1:
            ok = False
    return ok, versions
