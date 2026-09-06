"""Guard rails for the Phase C visual-contact student (contact_evidence.py +
train_contact_frame_model.predict_contact_offset). Mostly that everything
degrades to a no-op cleanly so compare_swing's audioless fallback can never
break a real analysis response."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', '00_utils'))

import contact_evidence  # noqa: E402
import train_contact_frame_model as tcm  # noqa: E402


def _frames(n=12, fps=30):
    """name->dict-landmark frames with a moving right wrist (a speed peak in
    the middle), the shape extract_user_poses() produces."""
    out = []
    for i in range(n):
        x = 0.1 * min(i, n - i)  # rises then falls -> a velocity peak mid-clip
        out.append({'frame': i * 3, 'landmarks': {
            'right_wrist': {'x': x, 'y': 0.5, 'visibility': 0.99},
            'left_wrist': {'x': 0.4, 'y': 0.5, 'visibility': 0.99},
        }})
    return out


def test_wrist_kinematics_empty_on_too_few_frames():
    assert contact_evidence.wrist_kinematics([], 0, 30) == {}
    assert contact_evidence.wrist_kinematics(_frames(3), 1, 30) == {}


def test_wrist_kinematics_shape():
    k = contact_evidence.wrist_kinematics(_frames(14), 7, 30)
    assert set(k) >= {'wrist_speed_at_anchor', 'wrist_decel_offset_f',
                      'wrist_halfspeed_offset_f'}


def test_compute_contact_evidence_none_when_no_detections(monkeypatch):
    monkeypatch.setattr(contact_evidence.rt, 'track_racket_and_ball',
                        lambda *a, **k: ([], 30.0))
    assert contact_evidence.compute_contact_evidence(
        'unused.mp4', _frames(), 30.0, 15, 5) is None


def test_compute_contact_evidence_row_shape(monkeypatch):
    # both ball + racket present near the anchor -> ball_racket_proximity
    dets = [{'frame': f, 'racket_box': [0, 0, 10, 10], 'racket_conf': 0.8,
             'ball_box': [5, 5, 9, 9] if f == 15 else None,
             'ball_conf': 0.7 if f == 15 else None} for f in range(6, 25)]
    monkeypatch.setattr(contact_evidence.rt, 'track_racket_and_ball',
                        lambda *a, **k: (dets, 30.0))
    row = contact_evidence.compute_contact_evidence('unused.mp4', _frames(), 30.0, 15, 5)
    assert set(row) == {'student_frame', 'student_confidence', 'student_method', 'student_meta'}
    assert 'anchor_frame' in row['student_meta']


def test_predict_contact_offset_no_model(monkeypatch, tmp_path):
    monkeypatch.setattr(tcm, 'MODEL_PATH', str(tmp_path / 'nope.pkl'))
    monkeypatch.setattr(tcm, '_model', None)
    monkeypatch.setattr(tcm, '_model_missing_logged', False)
    offset, available = tcm.predict_contact_offset(
        {'student_method': 'ball_racket_proximity', 'student_confidence': 0.7,
         'fps': 30.0, 'student_meta': {}, 'source': 'user_submitted'})
    assert (offset, available) == (0, False)
