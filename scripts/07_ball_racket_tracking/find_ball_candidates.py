"""
Classical (no ML) tennis-ball candidate proposal via HSV color-thresholding
+ contour/circularity filtering. Built after Claude vision proved unreliable
at freeform-locating the ball's pixel box across a full scene (see the ball
detector project's plan) -- mirrors sample_racket_crops.py's own working
pattern of "run a detector first, only ask Claude to confirm/refine a
crop" instead of asking anything to invent coordinates from scratch.

Real tennis balls are optic yellow/yellow-green -- a genuine, usable color
signal against a green/blue court -- but so are some background elements
(this project's own testing found Claude repeatedly drawn to a bright gap
in tree foliage), so this is candidate PROPOSAL only, ranked by how
ball-like each blob is, not a final answer -- see
ball_presence_verifier.py for the confirm step.
"""
import cv2
import numpy as np

# Optic-yellow/yellow-green tennis ball in HSV (OpenCV's H range 0-179).
HSV_LOWER = np.array([25, 60, 100])
HSV_UPPER = np.array([45, 255, 255])

MIN_AREA = 4      # smaller than this is almost always JPEG/compression noise
MAX_AREA = 3000   # larger than this at these frame resolutions is not a ball-sized blob
MIN_FILL_RATIO = 0.35  # contour area / enclosing-circle area -- filters out non-round blobs


def find_ball_candidates(frame, max_candidates=3):
    """
    Returns up to max_candidates candidate blobs, each
    {'x', 'y', 'radius', 'area', 'fill_ratio'} in the frame's own pixel
    space (x/y are the blob's center), ranked by area * fill_ratio
    descending -- a tight, round, appropriately-sized blob outranks a
    large loose fragment or a tiny noise speck. Empty list if nothing
    plausible is found; this is a proposal, not a guarantee.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, HSV_LOWER, HSV_UPPER)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < MIN_AREA or area > MAX_AREA:
            continue
        (x, y), r = cv2.minEnclosingCircle(c)
        enclosing_area = np.pi * r * r
        if enclosing_area == 0:
            continue
        fill_ratio = area / enclosing_area
        if fill_ratio < MIN_FILL_RATIO:
            continue
        candidates.append({
            'x': round(float(x), 1), 'y': round(float(y), 1), 'radius': round(float(r), 1),
            'area': round(float(area), 1), 'fill_ratio': round(float(fill_ratio), 3),
        })

    candidates.sort(key=lambda c: -(c['area'] * c['fill_ratio']))
    return candidates[:max_candidates]


if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print('Usage: python find_ball_candidates.py <image_path>')
        sys.exit(1)
    img = cv2.imread(path)
    if img is None:
        print(f'Could not read image: {path}')
        sys.exit(1)
    for c in find_ball_candidates(img):
        print(c)
