"""rotation_range() must ignore the z channel while Z_ROTATION_BLEND == 0.0
(disabled for traj_version 4 -- every trajectory's z is now metric world-derived,
a different scale than the image-z Z_TO_DEG_SCALE was fit to). This pins that the
live body_rotation sub-score is unaffected by the z change."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phase_breakdown as pb  # noqa: E402


def _traj(with_z=True):
    """A short swing where the shoulder line rotates ~40deg through the window."""
    out = []
    for i in range(12):
        ang = math.radians(-20 + i * 4)          # shoulder line sweeps -20 -> +24 deg
        s = math.sin(ang) * 0.2
        lm = {
            'left_shoulder':  {'x': -0.2, 'y': -0.45 - s, 'z': -0.1 if with_z else None},
            'right_shoulder': {'x': 0.2, 'y': -0.45 + s, 'z': 0.3 * math.sin(ang) if with_z else None},
            'left_hip':  {'x': -0.12, 'y': 0.0, 'z': -0.05 if with_z else None},
            'right_hip': {'x': 0.12, 'y': 0.0, 'z': 0.05 if with_z else None},
        }
        out.append({'t': round(-0.4 + i * 0.07, 3), 'landmarks': lm})
    return out


def test_blend_is_disabled():
    assert pb.Z_ROTATION_BLEND == 0.0


def test_rotation_range_ignores_z_when_blend_off():
    with_z = pb.rotation_range(_traj(with_z=True))
    without_z = pb.rotation_range(_traj(with_z=False))
    assert with_z is not None
    assert with_z == without_z
