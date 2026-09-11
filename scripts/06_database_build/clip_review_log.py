"""
Log of Jack's manual data-quality verdicts on pro-database clips (Dev
Page's Pro Clip Review tool, DevProClipReviewScreen.js) -- mismatched
footage, slow-motion clips, clips spanning the tail of one swing/player
into the start of another. Mirrors tip_reviewed_log.py's identity-log
pattern exactly (append-only JSONL, get_reviewed_set() for "don't re-serve
this one"), plus the verdict itself so a later pass can rebuild
pro_database.json excluding flagged entries (same shape as
filter_by_ball_visibility.py's audit-then-filter pattern) -- not a
teacher-student training log, this is data-quality curation, not an ML loop.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import DATA_DIR  # noqa: E402

LOG_PATH = os.path.join(DATA_DIR, '06_pro_database', 'clip_review_log.jsonl')

# 'excluded' is a catch-all "don't use this clip" verdict for clips that are
# bad but don't cleanly fit the more specific reasons below. 'cut' is logged
# automatically by cut_pro_clip.py, not chosen directly in the review UI --
# it means the clip was fixed by trimming rather than flagged for exclusion.
# 'shot_type_corrected' is likewise logged automatically, by
# correct_shot_type.py -- the clip was fixed by relabeling/moving it to the
# right shot type, not excluded. 'contact_time_corrected' is the same pattern
# for correct_contact_time.py. 'label_confirmed' is chosen directly in the
# review UI when Jack explicitly checked contact time + shot type this pass
# and found both correct -- distinct from 'ok', which historically only ever
# meant "boundary/footage looks fine," not "the labels are correct." 'split'
# is logged automatically by split_pro_clip.py, against the ORIGINAL entry's
# id only, when a clip turned out to contain two real swings and got divided
# into two separate database entries instead of one trimmed one -- the new
# entry gets no verdict of its own, so it surfaces as unreviewed later.
VERDICTS = (
    'ok', 'mismatched', 'slow_motion', 'wrong_boundary', 'excluded', 'cut',
    'shot_type_corrected', 'contact_time_corrected', 'label_confirmed', 'split',
)


def log_verdict(entry_id, verdict, note=None, name=None):
    if verdict not in VERDICTS:
        raise ValueError(f'Unknown verdict {verdict!r}, expected one of {VERDICTS}')
    record = {'entry_id': entry_id, 'verdict': verdict, 'note': note, 'name': name, 'timestamp': time.time()}
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, 'a') as f:
        f.write(json.dumps(record) + '\n')


def get_reviewed_set():
    """Returns a set of already-reviewed entry_ids."""
    if not os.path.exists(LOG_PATH):
        return set()
    reviewed = set()
    with open(LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            reviewed.add(json.loads(line)['entry_id'])
    return reviewed


def get_latest_verdicts():
    """Returns {entry_id: verdict} using each id's most recent logged line
    (in case of a re-review) -- what a later filter-and-rebuild pass would
    read to decide which entries to drop."""
    if not os.path.exists(LOG_PATH):
        return {}
    verdicts = {}
    with open(LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            verdicts[r['entry_id']] = r['verdict']
    return verdicts


def latest_verdict_notes():
    """{entry_id: (verdict, note)} from each id's most recent logged line.
    Lets a caller tell a human contact correction (note 'a -> b') apart from a
    machine audio fill (note ends '(audio)') without re-parsing the jsonl."""
    if not os.path.exists(LOG_PATH):
        return {}
    out = {}
    with open(LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            out[r['entry_id']] = (r['verdict'], r.get('note'))
    return out


def original_shot_type_for(entry_id):
    """If this entry was ever shot-type-corrected, return the shot type it
    STARTED as (the left side of the earliest 'shot_type_corrected' note,
    e.g. 'forehand' from 'forehand -> backhand'). Returns None if it was
    never relabelled. Used by the trajectory rebuild to find the entry's
    original pose/swings file -- swing_id // 1000 job bucketing is keyed on
    the ORIGINAL shot type, not the current (relabelled) one."""
    if not os.path.exists(LOG_PATH):
        return None
    with open(LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r['entry_id'] == entry_id and r['verdict'] == 'shot_type_corrected' and r.get('note'):
                left = r['note'].split('->')[0].strip()
                if left:
                    return left
    return None


LABEL_REVIEW_VERDICTS = {'label_confirmed', 'contact_time_corrected', 'shot_type_corrected'}


def get_label_reviewed_ids():
    """Ids whose most recent verdict means contact time + shot type were both
    actually checked this pass (confirmed correct, or corrected) -- stricter
    than get_reviewed_set(), which also counts pre-sprint boundary-only
    verdicts like 'ok'/'mismatched' that never checked label accuracy."""
    return {eid for eid, v in get_latest_verdicts().items() if v in LABEL_REVIEW_VERDICTS}


# ── quality tiering (roadmap 1b B1.6, 2026-09-11) ─────────────────────────
#
# A SEPARATE, ORTHOGONAL dimension from everything above -- "is the label/
# boundary right" (the log above) vs "is this textbook technique" (this
# one). Deliberately kept in its OWN log file rather than folded into
# VERDICTS/LOG_PATH: get_latest_verdicts() and the ~5 other scripts that
# consume it (rebuild_pro_database_from_verdicts.py,
# extract_training_features_from_pro_verdicts.py, etc.) all treat "the most
# recent logged line for this id" as authoritative state (e.g. "was this
# entry excluded"). If quality tags shared that stream, tagging an already-
# excluded entry 'quality_ok' later would make it look UN-excluded to any
# caller reading get_latest_verdicts() -- a real, silent, cross-cutting
# corruption risk for no benefit. Two independent logs, two independent
# "most recent" answers, no interaction. DevProQualityReviewScreen.js.
QUALITY_LOG_PATH = os.path.join(DATA_DIR, '06_pro_database', 'quality_review_log.jsonl')
QUALITY_TIERS = ('gold', 'ok', 'exclude')


def log_quality_tier(entry_id, tier, name=None):
    if tier not in QUALITY_TIERS:
        raise ValueError(f'Unknown quality tier {tier!r}, expected one of {QUALITY_TIERS}')
    record = {'entry_id': entry_id, 'tier': tier, 'name': name, 'timestamp': time.time()}
    os.makedirs(os.path.dirname(QUALITY_LOG_PATH), exist_ok=True)
    with open(QUALITY_LOG_PATH, 'a') as f:
        f.write(json.dumps(record) + '\n')


def get_quality_tiers():
    """{entry_id: 'gold'|'ok'|'exclude'} using each id's most recent tag --
    the bulk form for _pro_dists_by_view's prefer_gold mode / the review
    tool's list route, so callers don't re-scan the log per entry."""
    if not os.path.exists(QUALITY_LOG_PATH):
        return {}
    tiers = {}
    with open(QUALITY_LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            tiers[r['entry_id']] = r['tier']
    return tiers


def get_quality_tier(entry_id):
    """'gold'|'ok'|'exclude'|None for one entry."""
    return get_quality_tiers().get(entry_id)
