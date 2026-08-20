"""
Claude-as-teacher ball-position labeler for the fine-tuned ball detector
project (see the approved plan). Structurally mirrors
scripts/10_net_detection/net_presence_verifier.py's single-image pattern
and scripts/16_shot_verification/shot_contact_verifier.py's cost-tracking
pattern.

REVISED 2026-08-20: the original approach here asked Claude to freeform-
locate the ball's pixel box across a full scene, the same way the racket
keypoint model's Claude-vision-estimated coordinates worked. It didn't --
confirmed on 3 real test frames across 3 separate mitigation attempts
(default res, higher res, cropped-to-court), Claude repeatedly drew a
confident box on a bright gap in background foliage instead of the real
ball. A ball is small enough that "roughly right" and "pixel-precise"
aren't the same thing the way they are for a racket or net.

Fixed the same way sample_racket_crops.py always worked: a classical
detector (find_ball_candidates.py, HSV color-threshold + circularity, no
ML) proposes candidate blobs first; Claude only CONFIRMS/REJECTS whether
a small crop around a candidate is really the ball -- a binary judgment,
not a coordinate estimate. verify_ball_candidate_crop() below is that
confirm step; the old verify_ball_position() (freeform, full-scene) is
kept only for reference/comparison, not used by label_ball_frames.py
anymore.
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
COST_LOG_PATH = os.path.join(DATA_DIR, '10b_ball_detection', 'labeler_cost_log.jsonl')

# Same Haiku rates/reasoning as shot_contact_verifier.py's cost constants --
# real, confirmed cheaper tier, not the Sonnet rates from earlier this session.
COST_PER_INPUT_TOKEN_USD = 0.8 / 1_000_000
COST_PER_OUTPUT_TOKEN_USD = 4.0 / 1_000_000


def _log_call_cost(input_tokens, output_tokens):
    estimated_cost_usd = round(
        input_tokens * COST_PER_INPUT_TOKEN_USD + output_tokens * COST_PER_OUTPUT_TOKEN_USD, 6)
    record = {'timestamp': time.time(), 'input_tokens': input_tokens,
              'output_tokens': output_tokens, 'estimated_cost_usd': estimated_cost_usd}
    os.makedirs(os.path.dirname(COST_LOG_PATH), exist_ok=True)
    with open(COST_LOG_PATH, 'a') as f:
        f.write(json.dumps(record) + '\n')
    return estimated_cost_usd


def cost_summary():
    if not os.path.exists(COST_LOG_PATH):
        return {'calls': 0, 'estimated_cost_usd': 0.0}
    calls, total = 0, 0.0
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
    if os.environ.get('ANTHROPIC_API_KEY'):
        return os.environ['ANTHROPIC_API_KEY']
    if not os.path.exists(ENV_PATH):
        raise RuntimeError(f'.env not found at {ENV_PATH}')
    with open(ENV_PATH) as f:
        for line in f:
            if line.startswith('ANTHROPIC_API_KEY='):
                return line.strip().split('=', 1)[1]
    raise RuntimeError('ANTHROPIC_API_KEY not found in backend/.env')


def _image_to_base64_jpeg(image_path):
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f'Could not read image: {image_path}')
    # Downscale before encoding -- but NOT to net_presence_verifier.py's
    # 1024 (that's fine for "is a net somewhere in this photo", but a tennis
    # ball is far smaller, and shrinking a 1920px source down to 1024
    # roughly halves an already-tiny object's pixel footprint again on top
    # of that. Confirmed live: at 1024 Claude confidently returned WRONG
    # boxes (background trees/sky) on 2 of 3 test frames where the ball was
    # genuinely visible elsewhere in frame. 1568 is Claude's own internal
    # long-edge ceiling (larger gets downscaled server-side anyway, so
    # sending more than this wastes tokens without more effective detail).
    h, w = img.shape[:2]
    max_dim = 1568
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise RuntimeError('Failed to encode image as JPEG')
    return base64.b64encode(buf.tobytes()).decode('ascii'), img.shape[1], img.shape[0]


PROMPT = """This is a single frame from real tennis match/practice footage, being labeled to train a tennis-BALL detector.

Look carefully across the WHOLE image (the ball is small and can be anywhere -- near a player, mid-flight, near the net, or off to one side) and judge:
1. Is a tennis ball visible ANYWHERE in this frame -- even partially, blurred, or small? Do not confuse: the sun, a light fixture, a wristband, a hat, a scoreboard logo, or line-marking intersections for a ball.
2. If visible, give a tight bounding box in PIXEL coordinates for the smallest rectangle that fully contains the ball, using this image's actual pixel dimensions (width={width}, height={height}): x1 (left), y1 (top), x2 (right), y2 (bottom).

Respond with ONLY a JSON object, no other text:
{{
  "ball_visible": true or false,
  "box": {{"x1": <int>, "y1": <int>, "x2": <int>, "y2": <int>}} or null,
  "reasoning": "one short sentence"
}}"""


def verify_ball_position(image_path, model='claude-haiku-4-5-20251001'):
    """
    Returns {'ball_visible': bool, 'box': {'x1','y1','x2','y2'} or None,
    'reasoning': str, 'image_width': int, 'image_height': int}. Box
    coordinates are in the (possibly downscaled) encoded image's own
    pixel space -- image_width/image_height are returned alongside so
    callers can normalize to [0,1] correctly regardless of downscaling.

    Requires the `anthropic` package and a valid ANTHROPIC_API_KEY in
    backend/.env.
    """
    import anthropic  # imported lazily, same reasoning as the other verifiers

    client = anthropic.Anthropic(api_key=_load_api_key())
    b64, width, height = _image_to_base64_jpeg(image_path)
    content = [
        {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': b64}},
        {'type': 'text', 'text': PROMPT.format(width=width, height=height)},
    ]

    response = client.messages.create(
        model=model,
        max_tokens=250,
        messages=[{'role': 'user', 'content': content}],
    )
    _log_call_cost(response.usage.input_tokens, response.usage.output_tokens)

    text_blocks = [b.text for b in response.content if b.type == 'text']
    if not text_blocks:
        raise ValueError(f'No text block in Claude response (blocks: {[b.type for b in response.content]!r})')
    text = text_blocks[0].strip()

    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise ValueError(f'Could not find JSON in Claude response: {text!r}')
    result = json.loads(match.group(0))
    result['image_width'] = width
    result['image_height'] = height
    return result


# Extra margin around a classical candidate's enclosing box so a slightly
# off-center detection still shows the real ball fully within the crop --
# same idea as sample_racket_crops.py's PADDING_FRAC, tuned larger here
# since ball candidates are tiny (a few px radius) and a fixed-fraction pad
# alone would still crop to just a few pixels total.
CROP_PADDING_PX = 30

CROP_CONFIRM_PROMPT = """This is a small cropped region from a tennis video frame, centered on a candidate spot a classical color detector flagged as POSSIBLY a tennis ball.

Judge only: is there a real tennis ball visible in this crop (anywhere within it, not necessarily dead-center)? Common false positives from this detector: gaps of bright sky between leaves, sun glare, white court lines, a wristband, or a light-colored logo -- answer false for any of those.

Respond with ONLY a JSON object, no other text:
{
  "is_ball": true or false,
  "reasoning": "one short sentence"
}"""


def _crop_around_candidate(frame, candidate, pad_px=CROP_PADDING_PX):
    h, w = frame.shape[:2]
    x, y, r = candidate['x'], candidate['y'], candidate['radius']
    x1 = max(0, int(x - r - pad_px))
    y1 = max(0, int(y - r - pad_px))
    x2 = min(w, int(x + r + pad_px))
    y2 = min(h, int(y + r + pad_px))
    return frame[y1:y2, x1:x2]


def verify_ball_candidate_crop(frame, candidate, model='claude-haiku-4-5-20251001'):
    """
    Crops tightly around a single classical-detector candidate (see
    find_ball_candidates.py) and asks Claude a binary confirm/reject
    question -- NOT a coordinate estimate, the crop's already-known
    candidate position (reprojected to full-frame coords by the caller)
    IS the label if confirmed. This is the fix for verify_ball_position()'s
    freeform-localization failure -- see this module's docstring.

    Returns {'is_ball': bool, 'reasoning': str}.
    """
    import anthropic

    crop = _crop_around_candidate(frame, candidate)
    if crop.size == 0 or crop.shape[0] < 5 or crop.shape[1] < 5:
        return {'is_ball': False, 'reasoning': 'crop too small/empty to judge'}

    # Crops are tiny (a few dozen px) -- upscale generously so Claude isn't
    # squinting at a handful of pixels, same reasoning as sample_racket_
    # crops.py padding the box before this project ever needed a confirm step.
    ch, cw = crop.shape[:2]
    upscale = max(1.0, 300 / max(ch, cw))
    if upscale > 1.0:
        crop = cv2.resize(crop, (int(cw * upscale), int(ch * upscale)), interpolation=cv2.INTER_CUBIC)

    ok, buf = cv2.imencode('.jpg', crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise RuntimeError('Failed to encode crop as JPEG')
    b64 = base64.b64encode(buf.tobytes()).decode('ascii')

    client = anthropic.Anthropic(api_key=_load_api_key())
    content = [
        {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': b64}},
        {'type': 'text', 'text': CROP_CONFIRM_PROMPT},
    ]
    response = client.messages.create(model=model, max_tokens=150, messages=[{'role': 'user', 'content': content}])
    _log_call_cost(response.usage.input_tokens, response.usage.output_tokens)

    text_blocks = [b.text for b in response.content if b.type == 'text']
    if not text_blocks:
        raise ValueError(f'No text block in Claude response (blocks: {[b.type for b in response.content]!r})')
    match = re.search(r'\{.*\}', text_blocks[0].strip(), re.DOTALL)
    if not match:
        raise ValueError(f'Could not find JSON in Claude response: {text_blocks[0]!r}')
    return json.loads(match.group(0))
