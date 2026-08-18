"""
Claude-as-teacher net-presence verifier. Structurally mirrors
scripts/16_shot_verification/shot_contact_verifier.py's pattern (real image
evidence, one API round-trip, JSON out) with two differences suited to this
use case rather than shot verification:

1. Single image, not a multi-frame sequence -- these are static sourced
   photos (see source_net_negatives.py), not a video window where motion
   across frames matters.

2. Asks for presence + a one-line reason only, not pixel coordinates -- an
   LLM guessing exact keypoint pixel positions from a description is
   unreliable; that's what the existing manual/geometric labeling tools
   (sample_frames_for_labeling_v3.py etc.) are for. This is a sanity/labeling
   gate for "is there a tennis net in this image at all," used to build
   negative training examples (see prepare_net_pose_dataset_v4.py) for the
   net-keypoint model, which was proven this session to have never seen a
   real negative and false-positive on 100% of tested non-tennis images.
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
    # Downscale before encoding -- these are full-res sourced photos (some
    # multi-MB) and we only need enough resolution for Claude to judge
    # "is there a net," not pixel-perfect detail. Keeps requests small/cheap.
    h, w = img.shape[:2]
    max_dim = 1024
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise RuntimeError('Failed to encode image as JPEG')
    return base64.b64encode(buf.tobytes()).decode('ascii')


PROMPT = """This is a single photo sourced for a "does this image contain a tennis net" labeling task.

Look at the whole image and judge:
1. Is there a TENNIS net visible anywhere in this image -- the net specifically used to divide a tennis court (a taut white-banded net between two posts at roughly waist height, on a marked tennis court)? Answer false for any other kind of net (volleyball, badminton, soccer goal, fishing, chain-link fence, hairnet, etc.) and false for tennis-adjacent scenes with no net actually visible (an empty tennis court with no net strung, a tennis racket/ball with no net in frame).
2. Briefly say what net-like or misleading structures (if any) are visible, since this is being used to build a "hard negative" training set for a tennis-net detector that keeps confusing other horizontal lines/nets for a tennis net.

Respond with ONLY a JSON object, no other text:
{
  "has_tennis_net": true or false,
  "reasoning": "one sentence"
}"""


def verify_net_presence(image_path, model='claude-sonnet-5'):
    """
    Returns {'has_tennis_net': bool, 'reasoning': str}.

    Requires the `anthropic` package and a valid ANTHROPIC_API_KEY in
    backend/.env.
    """
    import anthropic  # imported lazily, same reasoning as shot_contact_verifier.py

    client = anthropic.Anthropic(api_key=_load_api_key())
    content = [
        {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg',
                                      'data': _image_to_base64_jpeg(image_path)}},
        {'type': 'text', 'text': PROMPT},
    ]

    response = client.messages.create(
        model=model,
        max_tokens=200,
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
