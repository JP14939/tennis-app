"""
Serve-specific contact-frame anchor.

The generic contact anchor (`compare_swing.find_peak_wrist_frame` on the live
side, `detect_swings.compute_wrist_velocity` on the pro side) picks the frame
of maximum wrist speed. On a serve that is NOT contact -- the toss-arm release
and the racket-hand follow-through both move faster than the instant of
impact -- so the anchor lands a median ~38 frames off and, on ~62% of serves,
outside the +-0.3s window `racket_tracker.find_contact_frame` refines within
(measured 2026-09-06, see HANDOVER.md).

A serve's geometry is unambiguous instead: the hitting wrist rises to full
overhead extension and contact happens a few frames AFTER that apex, on the
way down. This module finds that apex from pose data alone (no video / YOLO)
and adds a small forward lead to land on contact.

The overhead math mirrors `scripts/14_shot_classifier/classify_shot_geom.py`
(`_overhead_reach`, `_max_above_head`) and its `WRIST_MIN_VIS` / torso-scale
normalisation, but is reimplemented self-contained here so `00_utils` stays a
dependency leaf (that module pulls `extract_clips` @04 + `extract_training_
features` @14 through sys.path hacks). Keep the two conceptually in sync.

RETURN CONTRACT: these functions return a FRAME NUMBER, not a list index --
unlike `find_peak_wrist_frame`, which returns an index into its `frames` list.
The offline caller has a `{frame_number: landmarks}` index and no list; live
callers must NOT wrap the result in `frames[...]`.

Handedness-independent: every check takes the max over both wrists, so it
works even when handedness is wrong or unknown (same as the serve gate).
"""
import math

# a wrist this far above the shoulder (torso-normalised) counts as "overhead"
# -- kept equal to classify_shot_geom.SUSTAINED_REACH_MIN.
SUSTAINED_REACH_MIN = 0.15
# hitting wrists are motion-blurred at extension -> low MediaPipe visibility;
# the geometry only needs a rough height. == classify_shot_geom.WRIST_MIN_VIS.
MIN_WRIST_VIS = 0.15
# visibility bar for the structural landmarks (shoulders / hips / nose).
STRUCT_MIN_VIS = 0.4

# how far around a rough prior anchor to hunt for the apex (offline side).
APEX_SEARCH_RADIUS_SEC = 0.6
# Overhead reach (torso-normalised) within this much of the frame-wise maximum
# counts as "on the apex plateau". On distant / foreshortened poses the wrist y
# barely moves across the top of the service arc, so the raw argmax (with an
# earliest-frame tie-break) lands on the wide LEADING edge of that plateau --
# well before contact. Picking the plateau's centre instead removes that early
# error mode without disturbing a sharp, well-resolved apex (whose plateau is
# 1-2 frames wide). Swept against eval_pro_clip_contact.py's human-marked
# serves.
APEX_PLATEAU_TOL = 0.04
# Forward lead from the overhead apex onto contact. Swept against
# eval_pro_clip_contact.py's 60 human-marked serves 2026-09-06: median
# (apex_frame - teacher_frame) came out at -1f, so the apex IS contact for the
# bulk of serves -- no lead needed. Kept as a tunable, at 0.
APEX_TO_CONTACT_LEAD_SEC = 0.0

_WRISTS = (('right_wrist', 'right_shoulder'), ('left_wrist', 'left_shoulder'))


def _vis(lm, threshold):
    return lm is not None and lm.get('visibility', 0.0) >= threshold


def _torso_scale(lm):
    """Torso length (shoulder-mid -> hip-mid), fallback shoulder width.
    None when the shoulders aren't visible or the result is degenerate.
    Self-contained copy of extract_training_features.torso_scale."""
    rs, ls = lm.get('right_shoulder'), lm.get('left_shoulder')
    if not (_vis(rs, STRUCT_MIN_VIS) and _vis(ls, STRUCT_MIN_VIS)):
        return None
    sh_mid = ((rs['x'] + ls['x']) / 2, (rs['y'] + ls['y']) / 2)
    scale = None
    rh, lh = lm.get('right_hip'), lm.get('left_hip')
    if _vis(rh, STRUCT_MIN_VIS) and _vis(lh, STRUCT_MIN_VIS):
        hip_mid = ((rh['x'] + lh['x']) / 2, (rh['y'] + lh['y']) / 2)
        scale = math.hypot(sh_mid[0] - hip_mid[0], sh_mid[1] - hip_mid[1])
    if not scale:
        scale = abs(rs['x'] - ls['x'])
    if scale is not None and scale < 1e-4:
        return None
    return scale


def _above_head(lm):
    """max over both wrists of (nose.y - wrist.y) / torso_scale -- how far
    above the head a wrist reaches (y is DOWN, so higher = larger positive).
    None if the nose or torso scale isn't usable, or no wrist is visible."""
    nose = lm.get('nose')
    scale = _torso_scale(lm)
    if not (_vis(nose, STRUCT_MIN_VIS) and scale):
        return None
    best = None
    for wname, _ in _WRISTS:
        w = lm.get(wname)
        if _vis(w, MIN_WRIST_VIS):
            r = (nose['y'] - w['y']) / scale
            if best is None or r > best:
                best = r
    return best


def _overhead_reach(lm):
    """max over both wrists of (shoulder.y - wrist.y) / torso_scale -- a
    wrist above its shoulder. Fallback for _above_head when the nose isn't
    reliably visible (head tips back looking up at the toss). None if
    unusable."""
    scale = _torso_scale(lm)
    if not scale:
        return None
    best = None
    for wname, sname in _WRISTS:
        w, sh = lm.get(wname), lm.get(sname)
        if _vis(w, MIN_WRIST_VIS) and _vis(sh, STRUCT_MIN_VIS):
            r = (sh['y'] - w['y']) / scale
            if best is None or r > best:
                best = r
    return best


def _argmax_earliest(scored):
    """scored: list of (frame_number, value|None). Returns the earliest frame
    at the maximum value (the apex is first reached on the way up), or None
    if nothing is measurable."""
    usable = [(f, v) for f, v in scored if v is not None]
    if not usable:
        return None
    top = max(v for _, v in usable)
    return min(f for f, v in usable if v >= top - 1e-9)


def _apex_plateau_frame(scored, tol=APEX_PLATEAU_TOL):
    """scored: list of (frame_number, value|None), in frame order. Finds the
    contiguous run of measurable frames (around the global argmax) whose value
    stays within `tol` of the maximum -- the apex "plateau" -- and returns the
    measurable frame closest to that run's centre. On a sharp apex the run is
    1-2 frames and this reduces to the argmax; on a flat plateau it moves the
    pick off the early leading edge toward where contact actually is. None if
    nothing is measurable."""
    usable = [(f, v) for f, v in scored if v is not None]
    if not usable:
        return None
    usable.sort()
    top = max(v for _, v in usable)
    star = min(i for i, (_, v) in enumerate(usable) if v >= top - 1e-9)
    lo = hi = star
    while lo - 1 >= 0 and usable[lo - 1][1] >= top - tol:
        lo -= 1
    while hi + 1 < len(usable) and usable[hi + 1][1] >= top - tol:
        hi += 1
    mid_frame = (usable[lo][0] + usable[hi][0]) / 2
    return min((f for f, _ in usable[lo:hi + 1]), key=lambda f: abs(f - mid_frame))


def find_serve_apex_frame(pose_by_frame, fps, center_frame=None,
                          radius_sec=APEX_SEARCH_RADIUS_SEC):
    """Frame number of maximum overhead extension.

    pose_by_frame: {frame_number: {landmark_name: {x, y, z, visibility}}}.
    center_frame None  -> search every frame (live path, no better prior).
    center_frame set   -> only frames within radius_sec (offline path: hunt
                          around the wrist-velocity peak so a spurious high
                          wrist far away can't win).

    Tries wrist-above-head first, falls back to wrist-above-shoulder, then
    None (caller keeps its generic anchor).
    """
    if not pose_by_frame:
        return None
    frames = sorted(pose_by_frame)
    if center_frame is not None:
        r = radius_sec * (fps or 30.0)
        frames = [f for f in frames if abs(f - center_frame) <= r]
        if not frames:
            return None

    # NB: restricting the search to the longest sustained-overhead RUN was
    # tried (2026-09-06) and measured WORSE (|err| median 19f -> 34f, bias
    # -21f): the run's own argmax still lands on the wide early plateau. The
    # current approach keeps the global argmax but recentres it within the
    # plateau (_apex_plateau_frame) -- targets the same early-error mode
    # without the run restriction's downside.
    apex = _apex_plateau_frame([(f, _above_head(pose_by_frame[f])) for f in frames])
    if apex is not None:
        return apex
    return _apex_plateau_frame([(f, _overhead_reach(pose_by_frame[f])) for f in frames])


def serve_contact_anchor_frame(pose_by_frame, fps, center_frame=None,
                               radius_sec=APEX_SEARCH_RADIUS_SEC):
    """The one function both the live and offline sides call. Overhead apex
    plus a small forward lead onto contact. Frame number, or None if the
    overhead signal is absent (caller falls back to wrist velocity)."""
    apex = find_serve_apex_frame(pose_by_frame, fps, center_frame, radius_sec)
    if apex is None:
        return None
    return apex + round(APEX_TO_CONTACT_LEAD_SEC * (fps or 30.0))


def pose_by_frame_from_frames_list(frames):
    """Adapter: compare_swing's `frames` (list of {'frame', 'landmarks': {name: ...} | None})
    -> {frame_number: landmarks} for the functions above."""
    return {f['frame']: f['landmarks'] for f in frames if f.get('landmarks')}
