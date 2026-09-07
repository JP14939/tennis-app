"""
Coverage for train_contact_frame_model.py (feature extraction, matrix
shape, outlier drop, end-to-end fit on synthetic rows) and
contact_frame_ml_training_log.py's trust gate.
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '00_utils'))
import train_contact_frame_model as tcm  # noqa: E402
import contact_frame_ml_training_log as ml_log  # noqa: E402


def test_features_full_meta():
    rec = {
        'student_method': 'ball_occlusion_gap(3f)', 'student_confidence': 0.7, 'fps': 30.0,
        'source': 'user_submitted',
        'student_meta': {'n_ball_detections_in_window': 8, 'n_racket_detections_in_window': 12,
                         'n_both_present': 6, 'min_ball_racket_dist': 14.2},
    }
    f = tcm.features_from_record(rec)
    assert f['method_gap'] == 1.0 and f['method_proximity'] == 0.0
    assert f['occlusion_gap_frames'] == 3.0  # parsed from the method string
    assert f['n_both_present'] == 6
    assert f['source_audio_teacher'] == 0.0


def test_features_empty_meta_is_all_none_except_flags():
    f = tcm.features_from_record({})
    assert f['student_confidence'] is None
    assert f['n_ball_detections_in_window'] is None
    # method one-hots still resolve (to 0.0) off an empty method string
    assert f['method_gap'] == 0.0 and f['method_fallback'] == 0.0


def test_features_audio_teacher_source_flag():
    f = tcm.features_from_record({'student_method': 'swing_detector_wrist_peak', 'source': 'audio_teacher'})
    assert f['method_wrist_peak'] == 1.0
    assert f['source_audio_teacher'] == 1.0


def test_to_matrix_shape_and_signed_target():
    rows = [
        {'frame_error': 3, 'student_method': 'ball_racket_proximity', 'student_confidence': 0.5, 'fps': 30, 'student_meta': {}},
        {'frame_error': -2, 'student_method': 'wrist_velocity_fallback', 'student_confidence': 0.3, 'fps': 30, 'student_meta': {}},
    ]
    X, y = tcm._to_matrix(rows)
    assert X.shape == (2, len(tcm.FEATURE_NAMES))
    assert list(y) == [3.0, -2.0]


def test_main_trains_on_synthetic_rows(tmp_path, monkeypatch, capsys):
    log = tmp_path / 'contact_frame_training_log.jsonl'
    rng = random.Random(0)
    with open(log, 'w') as f:
        for _ in range(80):
            gap = rng.randint(2, 5)
            # true offset loosely correlates with gap size + noise
            err = gap - 3 + rng.choice([-1, 0, 0, 1])
            f.write(json.dumps({
                'frame_error': err, 'student_method': f'ball_occlusion_gap({gap}f)',
                'student_confidence': round(rng.uniform(0.4, 0.9), 2), 'fps': 30.0,
                'source': 'user_submitted',
                'student_meta': {'n_ball_detections_in_window': rng.randint(4, 12),
                                 'n_racket_detections_in_window': rng.randint(6, 14),
                                 'n_both_present': rng.randint(2, 8),
                                 'min_ball_racket_dist': round(rng.uniform(5, 40), 1)},
            }) + '\n')
        # a couple of gross outliers to exercise the filter
        for _ in range(3):
            f.write(json.dumps({'frame_error': 200, 'student_method': 'ball_racket_proximity',
                                'student_confidence': 0.5, 'fps': 30.0, 'source': 'user_submitted',
                                'student_meta': {}}) + '\n')
        # an out-of-scope source that must be filtered before the outlier count
        f.write(json.dumps({'frame_error': 1, 'student_method': 'ball_racket_proximity',
                            'student_confidence': 0.5, 'fps': 30.0, 'source': 'manual_review',
                            'student_meta': {}}) + '\n')

    monkeypatch.setattr(tcm, 'LOG_PATH', str(log))
    monkeypatch.setattr(tcm, 'MODEL_PATH', str(tmp_path / 'contact_frame_model.pkl'))
    monkeypatch.setattr(tcm, 'META_PATH', str(tmp_path / 'contact_frame_model_meta.json'))

    tcm.main([])

    assert os.path.exists(tcm.MODEL_PATH)
    meta = json.loads(open(tcm.META_PATH).read())
    assert meta['n_outliers_dropped'] == 3
    assert meta['n_examples'] == 80
    assert 'cv_within_tolerance_after' in meta
    assert meta['feature_names'] == tcm.FEATURE_NAMES


def test_ml_trust_gate(tmp_path, monkeypatch):
    log = tmp_path / 'contact_frame_ml_training_log.jsonl'
    monkeypatch.setattr(ml_log, 'LOG_PATH', str(log))

    assert ml_log.should_trust_student() is False  # no data

    # 60 rows, 58 within tolerance -> > 0.90 and > 50 -> trusted
    for i in range(60):
        ml_err = 0 if i >= 2 else 9
        ml_log.log_example(100 - ml_err, 108, 100, 30.0, source='user_submitted')
    st = ml_log.stats()
    assert st['n'] == 60
    assert st['ml_within_tolerance_rate'] >= 0.9
    assert st['trusted'] is True
