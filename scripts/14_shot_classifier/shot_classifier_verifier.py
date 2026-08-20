"""
Claude-as-teacher verifier for the shot-classifier learning loop. Mirrors
scripts/09_coaching_ai/tip_verifier.py's pattern, with one deliberate
difference: instead of re-describing the same rule-based pose scores back to
Claude as text (which would just be asking it to judge the student's own
evidence), this sends the actual contact-frame image. A real photo is
genuinely independent evidence a vision model can judge on its own, unlike
re-deriving from numbers the student already computed -- more likely to
catch cases where the rule-based scorer got it wrong.

Used during the student's learning phase -- see shot_classifier_training_log.py
for when to stop calling this (once the student's agreement rate is high
enough).
"""
import base64
import json
import os
import re
import sys
import time

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import BACKEND_DIR, DATA_DIR  # noqa: E402

ENV_PATH = os.path.join(BACKEND_DIR, '.env')

COST_LOG_PATH = os.path.join(DATA_DIR, '14_shot_classifier', 'verifier_cost_log.jsonl')

# Rough per-token estimate for a Claude Haiku-tier model (default model=
# switched from Sonnet to Haiku 2026-08-19 to cut real confirmed cost --
# see shot_contact_verifier.py's matching comment) -- NOT pulled from a
# live pricing API, just the widely-published per-million-token rate at
# time of writing ($0.80 in / $4 out). Good enough to see the number move
# as calls accumulate and sanity-check it isn't surprisingly large; check
# console.anthropic.com's actual billed usage for the exact figure rather
# than trusting this constant precisely.
COST_PER_INPUT_TOKEN_USD = 0.8 / 1_000_000
COST_PER_OUTPUT_TOKEN_USD = 4.0 / 1_000_000


def _log_call_cost(input_tokens, output_tokens):
    estimated_cost_usd = round(
        input_tokens * COST_PER_INPUT_TOKEN_USD + output_tokens * COST_PER_OUTPUT_TOKEN_USD, 6)
    record = {
        'timestamp': time.time(),
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'estimated_cost_usd': estimated_cost_usd,
    }
    os.makedirs(os.path.dirname(COST_LOG_PATH), exist_ok=True)
    with open(COST_LOG_PATH, 'a') as f:
        f.write(json.dumps(record) + '\n')
    return estimated_cost_usd


def cost_summary():
    """Total verify_shot() calls + estimated $ spent so far, for
    ml_status_report.py to surface -- the real, running number, not a
    one-time guess."""
    if not os.path.exists(COST_LOG_PATH):
        return {'calls': 0, 'estimated_cost_usd': 0.0}
    calls = 0
    total = 0.0
    with open(COST_LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            calls += 1
            total += rec.get('estimated_cost_usd', 0.0)
    return {'calls': calls, 'estimated_cost_usd': round(total, 4)}


def _load_api_key():
    """Read ANTHROPIC_API_KEY out of backend/.env without adding a
    python-dotenv dependency -- it's a one-line lookup."""
    if os.environ.get('ANTHROPIC_API_KEY'):
        return os.environ['ANTHROPIC_API_KEY']
    if not os.path.exists(ENV_PATH):
        raise RuntimeError(f'.env not found at {ENV_PATH}')
    with open(ENV_PATH) as f:
        for line in f:
            if line.startswith('ANTHROPIC_API_KEY='):
                return line.strip().split('=', 1)[1]
    raise RuntimeError('ANTHROPIC_API_KEY not found in backend/.env')


def _frame_to_base64_jpeg(frame):
    ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise RuntimeError('Failed to encode contact frame as JPEG')
    return base64.b64encode(buf.tobytes()).decode('ascii')


def build_verification_prompt(student_scores, student_pick):
    scores_desc = ', '.join(f'{k}={v:.3f}' for k, v in student_scores.items())
    return f"""This image shows a tennis player at the moment of contact during a swing, captured from match footage.

A rule-based classifier scored this swing against forehand/backhand/serve pose templates and picked "{student_pick}" as the shot type (raw scores: {scores_desc}).

Independently judge from the image alone: is this a forehand, backhand, or serve? Consider racket-arm side, body orientation, arm/racket height relative to the shoulder, and stance.

Respond with ONLY a JSON object, no other text:
{{
  "shot_type": "forehand" | "backhand" | "serve",
  "agrees_with_classifier": true or false,
  "reasoning": "one sentence explaining what in the image supports your judgment, especially if it differs from the classifier's pick"
}}"""


def verify_shot(frame, student_scores, student_pick, model='claude-haiku-4-5-20251001'):
    """
    Calls the Anthropic API (vision) to get Claude's independent shot-type
    judgment from the contact frame image. Returns
    {'shot_type': ..., 'agrees_with_classifier': bool, 'reasoning': str}.

    Requires the `anthropic` package and a valid ANTHROPIC_API_KEY in
    backend/.env.
    """
    import anthropic  # imported lazily so the rest of this module is usable/importable without the dependency installed

    client = anthropic.Anthropic(api_key=_load_api_key())
    image_b64 = _frame_to_base64_jpeg(frame)
    prompt = build_verification_prompt(student_scores, student_pick)

    response = client.messages.create(
        model=model,
        max_tokens=300,
        messages=[{
            'role': 'user',
            'content': [
                {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': image_b64}},
                {'type': 'text', 'text': prompt},
            ],
        }],
    )
    _log_call_cost(response.usage.input_tokens, response.usage.output_tokens)
    text_blocks = [b.text for b in response.content if b.type == 'text']
    if not text_blocks:
        raise ValueError(f'No text block in Claude response (blocks: {[b.type for b in response.content]!r})')
    text = text_blocks[0].strip()

    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise ValueError(f'Could not find JSON in Claude response: {text!r}')
    return json.loads(match.group(0))
