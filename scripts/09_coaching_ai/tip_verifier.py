"""
Claude-as-teacher verifier for the tip-selector learning loop.

Given the same deviation stats the student (tip_selector.py) used, asks
Claude to independently pick the true top-N issues from the same candidate
pool. Used during the student's learning phase — see tip_training_log.py for
when to stop calling this (once the student's agreement rate is high enough).

NOTE: this module makes real Anthropic API calls when verify_picks() is
invoked. It is NOT executed as part of building this pipeline — do not call
verify_picks() until the ANTHROPIC_API_KEY in backend/.env has been rotated
(the current one was exposed in chat and needs replacing first).
"""
import json
import os
import re

ENV_PATH = r'C:\Users\jackp\tennis_app\backend\.env'


def _load_api_key():
    """Read ANTHROPIC_API_KEY out of backend/.env without adding a
    python-dotenv dependency — it's a one-line lookup."""
    if os.environ.get('ANTHROPIC_API_KEY'):
        return os.environ['ANTHROPIC_API_KEY']
    if not os.path.exists(ENV_PATH):
        raise RuntimeError(f'.env not found at {ENV_PATH}')
    with open(ENV_PATH) as f:
        for line in f:
            if line.startswith('ANTHROPIC_API_KEY='):
                return line.strip().split('=', 1)[1]
    raise RuntimeError('ANTHROPIC_API_KEY not found in backend/.env')


def build_verification_prompt(shot_type, scored_issues, student_pick_ids, top_n=3):
    """
    scored_issues: full output of tip_selector.score_issues() — every issue
    that triggered, with its signed deviation/magnitude/severity and the
    candidate phrasings for that severity.
    """
    candidates_desc = '\n'.join(
        f'- {i["issue_id"]}: "{i["description"]}" '
        f'(phase={i["phase"]}, deviation={i["deviation"]:+.3f}, severity={i["severity"]})'
        for i in scored_issues
    )
    student_desc = ', '.join(student_pick_ids) if student_pick_ids else '(none triggered)'

    return f"""You are reviewing a tennis coaching tip selector's output for a {shot_type}.

A player's swing was compared against a matched professional's swing. The following technique issues were detected as deviating from the pro (each tied to a specific tracked body landmark and swing phase):

{candidates_desc}

A rule-based selector picked these as the top {top_n} most important issues to show the player: {student_desc}

Independently evaluate: are these genuinely the {top_n} most important issues for the player to work on, ranked by likely impact on their technique? Consider that issues closer to contact usually matter more than backswing/follow-through issues, and larger deviations usually (but not always) matter more than small ones — use your tennis coaching judgment, not just the raw magnitude.

Respond with ONLY a JSON object, no other text:
{{
  "top_picks": ["issue_id_1", "issue_id_2", "issue_id_3"],
  "agrees_with_selector": true or false,
  "reasoning": "one or two sentences explaining your ranking, especially if it differs from the selector's"
}}"""


def verify_picks(shot_type, scored_issues, student_pick_ids, top_n=3, model='claude-sonnet-5'):
    """
    Calls the Anthropic API to get Claude's independent top-N pick.
    Returns {'top_picks': [...], 'agrees_with_selector': bool, 'reasoning': str}.

    Requires the `anthropic` package (pip install anthropic) and a valid,
    rotated ANTHROPIC_API_KEY in backend/.env.
    """
    import anthropic  # imported lazily so the rest of this module is usable/importable without the dependency installed

    client = anthropic.Anthropic(api_key=_load_api_key())
    prompt = build_verification_prompt(shot_type, scored_issues, student_pick_ids, top_n)

    response = client.messages.create(
        model=model,
        max_tokens=500,
        messages=[{'role': 'user', 'content': prompt}],
    )
    text = response.content[0].text.strip()

    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise ValueError(f'Could not find JSON in Claude response: {text!r}')
    return json.loads(match.group(0))


def picks_agree(student_pick_ids, claude_pick_ids):
    """Order-insensitive agreement check between student and Claude picks."""
    return set(student_pick_ids) == set(claude_pick_ids)
