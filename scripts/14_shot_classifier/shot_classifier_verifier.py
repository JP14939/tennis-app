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

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '00_utils'))
from paths import BACKEND_DIR  # noqa: E402

ENV_PATH = os.path.join(BACKEND_DIR, '.env')


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


def verify_shot(frame, student_scores, student_pick, model='claude-sonnet-5'):
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
    text_blocks = [b.text for b in response.content if b.type == 'text']
    if not text_blocks:
        raise ValueError(f'No text block in Claude response (blocks: {[b.type for b in response.content]!r})')
    text = text_blocks[0].strip()

    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise ValueError(f'Could not find JSON in Claude response: {text!r}')
    return json.loads(match.group(0))
