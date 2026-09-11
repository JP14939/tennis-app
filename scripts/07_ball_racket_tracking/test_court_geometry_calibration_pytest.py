"""
Synthetic-camera validation for ball_speed._solve_camera_geometry -- the
court-geometry self-calibration (v3): solves for camera focal length,
height, pitch, and camera-to-baseline distance from the sidelines'
vanishing-point row, the net's row/width, and the near baseline's row, using
only the court's fixed dimensions (NET_WIDTH_M, BASELINE_TO_NET_M) -- no
assumed distance or height anywhere.

This is the primary correctness gate for that solver: there is no real
ground-truth video to check final speed numbers against, so recovering
known synthetic (f, H, pitch, d_baseline) tuples exactly is the only
evidence of correctness available this session. Do not weaken these
tolerances to make a change pass -- a wrong-but-close-enough answer here is
exactly the failure mode this feature is designed to avoid (see ball_speed.py
module docstring, v3, on the first vanishing-point approach that turned out
to be mathematically degenerate).
"""
import itertools
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ball_speed  # noqa: E402
from ball_speed import _solve_camera_geometry  # noqa: E402


def _forward_project(f, h_cam, theta_deg, d_baseline, frame_height_px):
    """
    The same exact pinhole geometry _solve_camera_geometry is built on
    (see its docstring), used here in the FORWARD direction: given true
    camera parameters, compute the (vp_y, net_y, net_width_px, baseline_y)
    pixel measurements a real detector would have produced.
    """
    theta = np.radians(theta_deg)
    cy = frame_height_px / 2.0

    def yc(d):
        return h_cam * np.cos(theta) - d * np.sin(theta)

    def zc(d):
        return h_cam * np.sin(theta) + d * np.cos(theta)

    vp_y = cy - f * np.tan(theta)
    d_net = d_baseline + ball_speed.BASELINE_TO_NET_M
    net_y = cy + f * yc(d_net) / zc(d_net)
    net_width_px = f * ball_speed.NET_WIDTH_M / zc(d_net)
    baseline_y = cy + f * yc(d_baseline) / zc(d_baseline)
    return vp_y, net_y, net_width_px, baseline_y


# Realistic phone-holding ranges: focal length in pixels for typical phone
# video resolutions/fields of view, height in metres, pitch in degrees,
# camera-to-baseline distance in metres (someone standing right at the
# fence up to a few metres back).
F_VALUES = [1000.0, 1400.0, 2000.0, 3000.0]
H_VALUES = [1.0, 1.3, 1.6, 1.8]
THETA_DEG_VALUES = [1.0, 5.0, 12.0, 20.0, 25.0]
D_BASELINE_VALUES = [0.3, 1.0, 2.0, 3.0]
FRAME_HEIGHT_PX = 1080.0


@pytest.mark.parametrize('f,h_cam,theta_deg,d_baseline',
                        list(itertools.product(F_VALUES, H_VALUES, THETA_DEG_VALUES, D_BASELINE_VALUES)))
def test_solver_recovers_synthetic_ground_truth(f, h_cam, theta_deg, d_baseline):
    vp_y, net_y, net_width_px, baseline_y = _forward_project(
        f, h_cam, theta_deg, d_baseline, FRAME_HEIGHT_PX)

    result = _solve_camera_geometry(vp_y, net_y, net_width_px, baseline_y, FRAME_HEIGHT_PX / 2.0)

    assert result is not None, (
        f'solver returned None for f={f} H={h_cam} theta={theta_deg} d_baseline={d_baseline}')
    rf, rh, rtheta, rd1 = result
    assert abs(rf - f) / f < 1e-6
    assert abs(rh - h_cam) / h_cam < 1e-6
    assert abs(rtheta - theta_deg) < 1e-6
    assert abs(rd1 - d_baseline) / d_baseline < 1e-6


def test_solver_none_on_bad_row_ordering():
    # vp_y must be < net_y < baseline_y (horizon above net above baseline,
    # closer-to-camera objects lower in frame) -- anything else is not a
    # real behind-the-baseline geometry.
    assert _solve_camera_geometry(500.0, 400.0, 100.0, 900.0, 540.0) is None  # net above horizon
    assert _solve_camera_geometry(200.0, 900.0, 100.0, 850.0, 540.0) is None  # baseline above net


def test_solver_none_when_lines_parallel_no_theta_root():
    # A vp_y implying theta≈0 with row measurements inconsistent with any
    # real pitch in the searched range should fail to find a sign change and
    # return None rather than extrapolate wildly.
    result = _solve_camera_geometry(vp_y_px=539.9, net_y_px=540.0, net_width_px=100.0,
                                    baseline_y_px=540.1, cy_px=540.0)
    assert result is None


def test_solver_none_when_recovered_height_implausible():
    # Fabricate self-consistent measurements for a camera height WAY outside
    # any real phone-holding range (e.g. 20m up, a drone/broadcast shot) --
    # the plausibility clamp should reject it rather than return a "valid"
    # but nonsensical calibration.
    vp_y, net_y, net_width_px, baseline_y = _forward_project(
        f=1400.0, h_cam=20.0, theta_deg=12.0, d_baseline=1.0, frame_height_px=FRAME_HEIGHT_PX)
    result = _solve_camera_geometry(vp_y, net_y, net_width_px, baseline_y, FRAME_HEIGHT_PX / 2.0)
    assert result is None
