"""
Claude-as-teacher verifier for the shot-contact learning loop. Mirrors
scripts/14_shot_classifier/shot_classifier_verifier.py's pattern (send real
image evidence, not a re-description of the student's own numbers), with
two differences:

1. Multiple frames, not one. A single still can't reliably distinguish
   "mid-swing" from "bouncing the ball" or "adjusting the camera" -- motion
   across frames can. Sent as a sequence, in order, in one message.

2. Answers both "is this a real shot" AND "what shot type is it" in the
   same call -- both questions look at the same frames, so one API
   round-trip covers what would otherwise be two separate calls (this
   verifier's job plus scripts/14_shot_classifier/shot_classifier_verifier.py's).
   Callers that only care about one side just ignore the other field.

Used during the student's (verify_shot_contact.py) learning phase -- see
shot_contact_training_log.py for when to stop calling this.
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
        raise RuntimeError('Failed to encode frame as JPEG')
    return base64.b64encode(buf.tobytes()).decode('ascii')


def build_verification_prompt(student_is_shot, student_shot_type=None):
    student_line = (
        f'A separate geometric check estimated this {"IS" if student_is_shot else "may NOT be"} a real racket-to-ball strike in this window.\n'
    )
    type_line = (
        f'If it is a real shot, a rule-based classifier separately guessed "{student_shot_type}" as the shot type.\n'
        if student_shot_type else ''
    )
    return f"""These images are consecutive frames, in chronological order, sampled across a short window of real tennis match footage where a swing-detection algorithm flagged a candidate "shot" based on wrist speed alone.

{student_line}{type_line}
Look across ALL the frames together (not just one) and judge independently:
1. Is there a real racket-to-ball strike visible anywhere across these frames -- an actual swing making contact with the ball? Or is this something else entirely (camera handling/adjusting, bouncing the ball, tossing/catching, walking, standing still, between-point pause)?
2. If it IS a real strike: is it a forehand, backhand, or serve?

Respond with ONLY a JSON object, no other text:
{{
  "is_real_shot": true or false,
  "shot_type": "forehand" | "backhand" | "serve" | null,
  "reasoning": "one or two sentences on what across the frames supports your judgment"
}}"""


def verify_shot_contact(frames, student_is_shot, student_shot_type=None, model='claude-sonnet-5'):
    """
    frames: list of cv2 frames (BGR numpy arrays), in chronological order,
    spanning the candidate window.

    Returns {'is_real_shot': bool, 'shot_type': str|None, 'reasoning': str}.

    Requires the `anthropic` package and a valid ANTHROPIC_API_KEY in
    backend/.env.
    """
    import anthropic  # imported lazily so the rest of this module is usable/importable without the dependency installed

    if not frames:
        raise ValueError('verify_shot_contact() needs at least one frame')

    client = anthropic.Anthropic(api_key=_load_api_key())
    prompt = build_verification_prompt(student_is_shot, student_shot_type)

    content = [
        {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg',
                                      'data': _frame_to_base64_jpeg(f)}}
        for f in frames
    ]
    content.append({'type': 'text', 'text': prompt})

    response = client.messages.create(
        model=model,
        max_tokens=400,
        messages=[{'role': 'user', 'content': content}],
    )
    text_blocks = [b.text for b in response.content if b.type == 'text']
    if not text_blocks:
        raise ValueError(f'No text block in Claude response (blocks: {[b.type for b in response.content]!r})')
    text = text_blocks[0].strip()

    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise ValueError(f'Could not find JSON in Claude response: {text!r}')
    return json.loads(match.group(0))
