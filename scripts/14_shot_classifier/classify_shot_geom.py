"""
Geometric shot-type classifier -- a decision tree, not three independent
confidence scores.

The reframing (2026-09): forehand vs backhand is a mirror-image distinction --
the only thing separating them is which side of the body the racket contacts on,
and that side is defined by the dominant hand. So:

  1. SERVE gate  -- handedness-independent (overhead reach). Fires first.
  2. FOREHAND vs BACKHAND -- needs handedness. Then it's one geometric test:
     is the dominant hand on its own side of the torso (forehand) or crossed
     over / both-hands-together (backhand)?

The side test is made VIEW-INVARIANT without needing view_direction:
`dot(dominant_wrist - torso_mid, dominant_shoulder - torso_mid)`. A camera
mirror (front vs back view, or a flipped clip) flips BOTH vectors, so the sign
of the dot product is preserved.

All magnitudes are divided by torso length (extract_training_features.torso_scale)
so thresholds hold across phone-selfie and broadcast framing.

Landmark inputs are lists of `{name,x,y,z,visibility}` dicts (what
classify_shot._build_swing_frames produces). MediaPipe image coords: x right,
y DOWN, landmarks anatomically labelled.
"""
import argparse
import math
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '04_clip_extraction'))

from extract_clips import get_lm, visible, dist2d  # noqa: E402
from extract_training_features import torso_scale  # noqa: E402

# ── Tunable thresholds (swept by evaluate_shot_classifiers.py) ────────────────
# Overhead reach = (shoulder.y - wrist.y) / torso, max over the swing window.
# A serve reaches full overhead extension (wrist well above the head); a
# groundstroke's wrist stays near or below the shoulder. Broadcast pose on a
# small player is noisy, so the weak path also requires the elbow above the
# shoulder (a much rarer thing on a groundstroke than a marginal reach value).
# Groundstrokes are ~93% of pipeline swings, so a serve false-positive costs
# more than a missed serve -- keep this conservative (high precision).
SERVE_REACH_STRONG = 0.50   # >= this -> serve
SERVE_REACH_WEAK = 0.35     # >= this AND elbow above shoulder -> serve (weak)
# Both "strong" serve paths floor serve_logit at exactly this value -- used to
# hard-win over the FH/BH side test (see the hard-win check in classify_geom).
# Without it, a big dominant-wrist projection at contact (fh_logit = side*3.0)
# can outvote a correctly-detected serve in the softmax: a real serve with
# strong sustained-overhead evidence (run/frac + above-head) still has SOME
# lateral wrist offset at the marked (downswing) contact frame, and on a
# small/noisy broadcast pose that offset alone can exceed 4.0. The "weak"
# serve paths (serve_logit ~1.5) deliberately stay contestable in the softmax
# below -- that evidence is genuinely less certain and should be allowed to
# lose to a strong FH/BH signal.
SERVE_HARD_WIN_LOGIT = 4.0
# Sustained-overhead serve signal. The contact frame is marked at max wrist
# velocity (extract_clips.py), which for a serve is the DOWNSWING -- the wrist
# is already back near/below the shoulder by then, so contact_reach alone
# misses ~55% of real serves (measured on 84 labelled clips). But across the
# swing window a serve keeps a wrist overhead for a long run of frames (toss
# rise -> hit up), where a groundstroke's follow-through only clips overhead
# for 1-2 frames. Measured separation: fraction of window frames with a wrist
# >0.15 torso above the shoulder -- serve median ~0.42, groundstroke ~0.08;
# longest consecutive run -- serve median ~8, groundstroke p75 ~4.
SUSTAINED_REACH_MIN = 0.15      # a wrist this far above the shoulder counts as "overhead"
SERVE_SUSTAINED_RUN_STRONG = 7  # longest overhead run >= this ...
SERVE_SUSTAINED_FRAC_STRONG = 0.38  # ... OR this fraction of the window overhead ...
SERVE_SUSTAINED_RUN_WEAK = 5    # (weak path) run >= this ...
SERVE_SUSTAINED_FRAC_WEAK = 0.28    # ... OR frac >= this, AND elbow above shoulder ...
# ... AND the wrist reaches this far above the HEAD (nose.y - wrist.y, torso-
# normalised) somewhere in the window. This is the signal that separates a
# serve from a broadcast groundstroke whose noisy follow-through also holds a
# long overhead run: a serve goes to full extension well above the head
# (measured p25 ~0.75), a groundstroke follow-through tops out at chin height
# (measured p75 ~0.46). Without this the sustained gate tanks serve precision
# on the (broadcast) pipeline domain.
SERVE_ABOVE_HEAD_STRONG = 0.60
SERVE_ABOVE_HEAD_WEAK = 0.45
# Two hands this close (as a fraction of torso) at contact = two-handed grip.
# 0.55 was tuned on curated close-up pro clips and misfires on noisy one-handed
# phone forehands (dragging them to backhand); a real two-handed grip sits well
# under 0.40. Swept 0.30/0.35/0.40 against evaluate_shot_classifiers.py.
TWO_HAND_WRIST_SEP = 0.40
# |side projection| below this = contact near the midline = ambiguous FH/BH.
SIDE_AMBIGUOUS = 0.35
# The hitting wrist is often motion-blurred at contact (low MediaPipe
# visibility) on broadcast footage -- but the geometric tests only take a
# sign / a rough height, so a roughly-right position is enough. Accept a
# lower visibility for wrists than the 0.4 default.
WRIST_MIN_VIS = 0.15


def _xy(lm):
    return (lm['x'], lm['y'])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _side_projection(peak_lm, handedness):
    """Signed, torso-normalised projection of the dominant wrist onto the
    (torso_mid -> dominant_shoulder) axis. >0 = dominant-hand side (forehand),
    <0 = crossed over (backhand). None if the needed landmarks aren't visible.
    View-invariant: a horizontal mirror flips both vectors, sign is kept."""
    rs, ls = get_lm(peak_lm, 'right_shoulder'), get_lm(peak_lm, 'left_shoulder')
    dom_name = 'right_wrist' if handedness == 'right' else 'left_wrist'
    dom_sh = rs if handedness == 'right' else ls
    dom_wr = get_lm(peak_lm, dom_name)
    if not (visible(rs) and visible(ls) and visible(dom_sh) and visible(dom_wr, WRIST_MIN_VIS)):
        return None
    scale = torso_scale(peak_lm)
    if not scale:
        return None
    mid = ((rs['x'] + ls['x']) / 2, (rs['y'] + ls['y']) / 2)
    axis = _sub(_xy(dom_sh), mid)          # spine -> dominant shoulder
    axis_len = math.hypot(*axis)
    if axis_len < 1e-6:
        return None
    wrist_vec = _sub(_xy(dom_wr), mid)
    # projection onto the unit axis, then / torso so it's a "how many torsos
    # out to the dominant side" number.
    return _dot(wrist_vec, (axis[0] / axis_len, axis[1] / axis_len)) / scale


def _overhead_reach(lm):
    """max over both wrists of (shoulder.y - wrist.y)/torso at one frame.
    Positive = a wrist above the shoulder. A serve's contact is at full
    overhead extension (~0.8-1.5); a groundstroke's contact wrist sits at/
    below the shoulder (~ -0.5..+0.2). Both wrists, not just the dominant one,
    so the serve gate works even if handedness is wrong/unknown. None if
    landmarks missing."""
    rs, ls = get_lm(lm, 'right_shoulder'), get_lm(lm, 'left_shoulder')
    scale = torso_scale(lm)
    if not scale:
        return None
    best = None
    for sh, wn in ((rs, 'right_wrist'), (ls, 'left_wrist')):
        w = get_lm(lm, wn)
        if visible(sh) and visible(w, WRIST_MIN_VIS):
            r = (sh['y'] - w['y']) / scale
            if best is None or r > best:
                best = r
    return best


def _sustained_overhead(window_lms):
    """(frac, run) -- fraction of window frames with a wrist > SUSTAINED_REACH_MIN
    torso above the shoulder, and the longest consecutive run of such frames.
    A serve holds a wrist overhead through the toss and hit-up; a groundstroke
    follow-through only clips overhead for a frame or two. None-reach frames
    (landmarks missing) break a run but don't count against the fraction."""
    flags = []
    for lm in (window_lms or []):
        r = _overhead_reach(lm)
        if r is None:
            continue
        flags.append(r > SUSTAINED_REACH_MIN)
    if not flags:
        return 0.0, 0
    best = run = 0
    for f in flags:
        run = run + 1 if f else 0
        best = max(best, run)
    return sum(flags) / len(flags), best


def _max_above_head(window_lms):
    """Max over the window and both wrists of (nose.y - wrist.y) / torso -- how
    far above the head the wrist gets. A serve's contact/extension is well
    above the head; a groundstroke follow-through tops out around chin height.
    0.0 if the nose or wrists are never usable."""
    best = 0.0
    for lm in (window_lms or []):
        n = get_lm(lm, 'nose')
        scale = torso_scale(lm)
        if not (visible(n) and scale):
            continue
        for wn in ('right_wrist', 'left_wrist'):
            w = get_lm(lm, wn)
            if visible(w, WRIST_MIN_VIS):
                best = max(best, (n['y'] - w['y']) / scale)
    return best


def _serve_evidence(peak_lm, window_lms):
    """(contact_reach, window_max_reach, elbow_elevated, sustained_frac, sustained_run)
    -- overhead reach AT contact, the window max as a weak supporting signal,
    whether either elbow gets above its shoulder anywhere in the window, and
    the sustained-overhead pair (see _sustained_overhead). contact_reach alone
    misses most serves because the marked contact frame is the downswing; the
    sustained pair recovers them without the window-max's follow-through false
    positives."""
    contact_reach = _overhead_reach(peak_lm)
    window_max = contact_reach
    elbow_up = False
    for lm in (window_lms or []):
        r = _overhead_reach(lm)
        if r is not None and (window_max is None or r > window_max):
            window_max = r
        for sh_n, el_n in (('right_shoulder', 'right_elbow'), ('left_shoulder', 'left_elbow')):
            sh, el = get_lm(lm, sh_n), get_lm(lm, el_n)
            if visible(sh) and visible(el) and el['y'] < sh['y']:
                elbow_up = True
    frac, run = _sustained_overhead(window_lms)
    return contact_reach, window_max, elbow_up, frac, run, _max_above_head(window_lms)


def _followthrough_delta(peak_lm, window_lms, handedness):
    """Change in side-projection from contact to the latest follow-through
    frame. Forehand (RH): the wrist keeps sweeping across the body -> delta
    negative. Backhand: keeps going out to the dominant side -> delta positive.
    None if it can't be measured. A weak corroborator, not decisive."""
    if not window_lms:
        return None
    p0 = _side_projection(peak_lm, handedness)
    p1 = _side_projection(window_lms[-1], handedness)
    if p0 is None or p1 is None:
        return None
    return p1 - p0


def _softmax3(a, b, c):
    m = max(a, b, c)
    e = [math.exp(a - m), math.exp(b - m), math.exp(c - m)]
    s = sum(e)
    return [x / s for x in e]


def classify_geom(peak_lm, prev_lm, window_lms, handedness='right'):
    """Returns {shot_type, scores:{forehand,backhand,serve}, confidence, reason}.
    shot_type is None only if there's not enough pose to decide anything."""
    reasons = []
    (contact_reach, window_reach, elbow_up, sustained_frac, sustained_run,
     above_head) = _serve_evidence(peak_lm, window_lms)

    # ── serve gate ── the reach AT CONTACT is decisive when it's there, but the
    # marked contact frame is the downswing on a serve so it usually isn't.
    # Fall back to the sustained-overhead signal (a wrist held overhead for a
    # long run of window frames), which a groundstroke follow-through doesn't
    # produce.
    serve_logit = -4.0
    if contact_reach is not None and contact_reach >= SERVE_REACH_STRONG:
        serve_logit = 4.0 + (contact_reach - SERVE_REACH_STRONG) * 4
        reasons.append(f'contact reach {contact_reach:.2f}>=strong')
    elif ((sustained_run >= SERVE_SUSTAINED_RUN_STRONG or sustained_frac >= SERVE_SUSTAINED_FRAC_STRONG)
          and above_head >= SERVE_ABOVE_HEAD_STRONG):
        serve_logit = 4.0
        reasons.append(f'sustained overhead run {sustained_run} frac {sustained_frac:.2f} above-head {above_head:.2f}')
    elif contact_reach is not None and contact_reach >= SERVE_REACH_WEAK and elbow_up:
        serve_logit = 1.5 + (contact_reach - SERVE_REACH_WEAK) * 3
        reasons.append(f'contact reach {contact_reach:.2f}+elbow')
    elif (elbow_up and above_head >= SERVE_ABOVE_HEAD_WEAK
          and (sustained_run >= SERVE_SUSTAINED_RUN_WEAK or sustained_frac >= SERVE_SUSTAINED_FRAC_WEAK)):
        serve_logit = 1.5
        reasons.append(f'sustained overhead run {sustained_run} frac {sustained_frac:.2f} above-head {above_head:.2f}+elbow')

    # ── serve hard-win ── strong serve evidence (either strong path above)
    # wins outright, before the FH/BH side test even runs -- see
    # SERVE_HARD_WIN_LOGIT's comment for why the softmax alone isn't safe here.
    if serve_logit >= SERVE_HARD_WIN_LOGIT:
        return {'shot_type': 'serve', 'scores': {'serve': 0.92, 'forehand': 0.04, 'backhand': 0.04},
                'confidence': 0.75, 'reason': '; '.join(reasons) or 'strong serve evidence'}

    side = _side_projection(peak_lm, handedness)
    if side is None:
        # no usable FH/BH geometry -- only a serve call is possible
        if serve_logit > 1.0:
            return {'shot_type': 'serve', 'scores': {'serve': 0.9, 'forehand': 0.05, 'backhand': 0.05},
                    'confidence': 0.6, 'reason': '; '.join(reasons) or 'serve reach, no FH/BH geometry'}
        return {'shot_type': None, 'scores': {'forehand': 1 / 3, 'backhand': 1 / 3, 'serve': 1 / 3},
                'confidence': 0.0, 'reason': 'insufficient landmarks'}

    # ── two-handed grip override ──
    rw, lw = get_lm(peak_lm, 'right_wrist'), get_lm(peak_lm, 'left_wrist')
    scale = torso_scale(peak_lm) or 1.0
    two_handed = (visible(rw) and visible(lw)
                  and abs(rw['x'] - lw['x']) / scale < TWO_HAND_WRIST_SEP)

    # ── forehand vs backhand ──
    fh_logit = side * 3.0
    bh_logit = -side * 3.0
    reasons.append(f'side {side:+.2f}')
    if two_handed:
        bh_logit += 2.5
        reasons.append('wrists together (two-handed)')
    ft = _followthrough_delta(peak_lm, window_lms, handedness)
    if ft is not None:
        fh_logit += -ft * 1.5
        bh_logit += ft * 1.5
        reasons.append(f'followthrough {ft:+.2f}')

    fh_p, bh_p, sv_p = _softmax3(fh_logit, bh_logit, serve_logit)
    scores = {'forehand': round(fh_p, 3), 'backhand': round(bh_p, 3), 'serve': round(sv_p, 3)}
    shot = max(scores, key=scores.get)

    # confidence: how decisive the winning margin is, damped near the midline
    top2 = sorted(scores.values(), reverse=True)[:2]
    margin = top2[0] - top2[1]
    conf = margin
    if shot in ('forehand', 'backhand') and abs(side) < SIDE_AMBIGUOUS and not two_handed:
        # Near the midline the dot-product side test is unreliable (a one-handed
        # backhand contacts near the body's centreline). The follow-through
        # direction is then the real signal: if it's present and sweeps the way
        # the winner implies, keep a modest confidence so a trajectory-off caller
        # (phone footage, GEOM_CONF_MIN_NOTRAJ) can still use the call. Otherwise
        # it's a genuine coin-flip -> damp below any floor so it reaches Claude.
        ft_agrees = ft is not None and (
            (shot == 'backhand' and ft > 0.03) or (shot == 'forehand' and ft < -0.03))
        if ft_agrees:
            conf = min(conf, 0.30)
            reasons.append('near midline, follow-through-backed')
        else:
            conf = min(conf, 0.12)
            reasons.append('near midline -> low confidence')
    return {'shot_type': shot, 'scores': scores, 'confidence': round(conf, 3),
            'reason': '; '.join(reasons)}


# ── CLI (manual check) ───────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('video')
    ap.add_argument('contact_time', type=float)
    ap.add_argument('--handedness', choices=['right', 'left'], default='right')
    args = ap.parse_args()
    from classify_shot import _build_swing_frames
    peak_lm, prev_lm, window_lms, _fps = _build_swing_frames(args.video, args.contact_time, None)
    import json
    print(json.dumps(classify_geom(peak_lm, prev_lm, window_lms, args.handedness), indent=2))


if __name__ == '__main__':
    main()
