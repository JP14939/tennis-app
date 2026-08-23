"""
Orchestrator for the tip-selector teacher-student loop.

While the student (tip_selector.py) is still learning (agreement rate below
threshold, per tip_training_log.py), every request also calls the Claude
verifier, logs the (features, student_pick, claude_pick, agreed) example, and
returns Claude's picks (the teacher is authoritative during learning). Once
the student is trusted, Claude is skipped and the student's picks are
returned directly — saving API cost.

This is the function ResultsScreen's backend endpoint should eventually call
instead of using tip_selector.py directly.

use_verifier defaults to True here because the *offline* training callers of
this function (run_tip_training.py, train_tip_selector_on_amateur_footage.py)
exist specifically to invoke the real Claude verifier and log agreement
examples -- that's their whole purpose, so this default must stay on for
them. The LIVE per-request callers (compare_swing.py, compare_videos.py) are
a different story: they're invoked synchronously on every real /api/analyse
and /api/compare-videos request, not run as a detached background job the
way this codebase's other teacher-student loops are (shot_contact_training_
log.py, shot_classifier_training_log.py -- both driven from batch/offline
scripts gated behind an explicit RALLYMAX_SKIP_*_VERIFIER opt-out). Those two
live call sites pass use_verifier=False explicitly instead of relying on
this default, so a real user's request never makes a synchronous Claude API
call for a feature HANDOVER.md documents as deferred pending real footage.
"""
import sys

from tip_selector import score_issues, select_top_tips
from tip_training_log import log_example, should_trust_student
from tip_verifier import verify_picks, picks_agree


def get_coaching_tips(user_trajectory, pro_trajectory, shot_type, top_n=3, use_verifier=True):
    scored = score_issues(user_trajectory, pro_trajectory, shot_type)
    student_top = select_top_tips(user_trajectory, pro_trajectory, shot_type, top_n)
    student_pick_ids = [t['issue_id'] for t in student_top if t['issue_id']]

    if not use_verifier or should_trust_student():
        return student_top, {'source': 'student', 'verified': False}

    try:
        claude_result = verify_picks(shot_type, scored, student_pick_ids, top_n)
    except Exception as e:
        print(f'  Verifier call failed ({e}) — falling back to student pick', file=sys.stderr)
        return student_top, {'source': 'student', 'verified': False, 'verifier_error': str(e)}

    claude_pick_ids = claude_result['top_picks']
    agreed = picks_agree(student_pick_ids, claude_pick_ids)
    log_example(shot_type, scored, student_pick_ids, claude_pick_ids, agreed)

    # Resolve Claude's chosen issue_ids back to full tip objects (with text)
    by_id = {s['issue_id']: s for s in scored}
    claude_top = []
    for issue_id in claude_pick_ids:
        item = by_id.get(issue_id)
        if item:
            item = dict(item)
            item['tip_text'] = item['candidate_tips'][0]
            claude_top.append(item)

    if not claude_top:
        claude_top = [{'issue_id': None, 'severity': None,
                        'tip_text': 'Great technique! Your form closely matches the pro.'}]

    return claude_top, {
        'source': 'claude_verified', 'verified': True, 'agreed_with_student': agreed,
        'reasoning': claude_result.get('reasoning'),
    }
