"""
Covers prepare_ball_yolo_dataset.py's split hygiene:
 - the output dir is rebuilt every run (no stale files from a prior, larger run)
 - train/val split is by clip id, not by frame (no near-duplicate leakage)
 - ball_visible:false -> empty label file
No YOLO. Synthetic label log + fake candidate frames in tmp_path.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prepare_ball_yolo_dataset as prep  # noqa: E402


def _write_log(path, rows):
    with open(path, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')


def _row(analysis, frame, visible=True):
    # box moves with the frame so find_fully_static_files doesn't flag the
    # clip as a static decoy
    x = 0.30 + 0.02 * frame
    b = {'x1': x, 'y1': 0.4, 'x2': x + 0.02, 'y2': 0.43}
    return {'file': f'analysis{analysis}_f{frame}_x.jpg', 'bucket': 'near_contact',
            'ball_visible': visible, 'box_norm': b if visible else None}


@pytest.fixture
def _env(tmp_path, monkeypatch):
    frames = tmp_path / 'candidate_frames' / 'near_contact'
    frames.mkdir(parents=True)
    ds = tmp_path / 'ds'
    monkeypatch.setattr(prep, 'FRAMES_DIR', str(tmp_path / 'candidate_frames'))
    monkeypatch.setattr(prep, 'DATASET_DIR', str(ds))
    monkeypatch.setattr(prep, 'MIN_ROWS', 3)
    monkeypatch.setattr(prep, 'VAL_FRAC', 0.34)

    def _make_frames(rows):
        for r in rows:
            (frames / r['file']).write_bytes(b'\xff\xd8\xff\xe0jpegstub')
    return tmp_path, ds, _make_frames


def _split_files(ds):
    tr = set(os.listdir(ds / 'images' / 'train'))
    va = set(os.listdir(ds / 'images' / 'val'))
    return tr, va


def test_clip_level_split_no_frame_leakage(_env, monkeypatch):
    tmp_path, ds, make_frames = _env
    rows = []
    for a in range(1, 7):                      # 6 clips
        for fr in (10, 12, 14, 16):            # 4 near-duplicate frames each
            rows.append(_row(a, fr))
    make_frames(rows)
    log = tmp_path / 'log.jsonl'
    _write_log(log, rows)
    monkeypatch.setattr(sys, 'argv', ['prep', str(log)])
    prep.main()

    tr, va = _split_files(ds)
    assert tr and va
    assert not (tr & va)
    tr_clips = {prep._clip_id(f) for f in tr}
    va_clips = {prep._clip_id(f) for f in va}
    assert not (tr_clips & va_clips)          # the headline guarantee


def test_rerun_with_fewer_rows_leaves_no_stale_files(_env, monkeypatch):
    tmp_path, ds, make_frames = _env
    big = [_row(a, fr) for a in range(1, 9) for fr in (10, 12, 14)]
    make_frames(big)
    log = tmp_path / 'log.jsonl'
    _write_log(log, big)
    monkeypatch.setattr(sys, 'argv', ['prep', str(log)])
    prep.main()
    n_big = sum(len(os.listdir(ds / 'images' / s)) for s in ('train', 'val'))

    small = [_row(a, fr) for a in range(1, 4) for fr in (10, 12)]
    _write_log(log, small)
    prep.main()
    n_small = sum(len(os.listdir(ds / 'images' / s)) for s in ('train', 'val'))
    assert n_small == len(small) < n_big     # no leftovers from the big run


def test_negative_row_gets_empty_label_file(_env, monkeypatch):
    tmp_path, ds, make_frames = _env
    rows = [_row(1, 10), _row(1, 12), _row(2, 10, visible=False),
            _row(3, 10), _row(3, 12), _row(4, 10, visible=False)]
    make_frames(rows)
    log = tmp_path / 'log.jsonl'
    _write_log(log, rows)
    monkeypatch.setattr(sys, 'argv', ['prep', str(log)])
    prep.main()

    for split in ('train', 'val'):
        for lbl in os.listdir(ds / 'labels' / split):
            content = (ds / 'labels' / split / lbl).read_text()
            if 'analysis2' in lbl or 'analysis4' in lbl:
                assert content == ''
            else:
                assert content.startswith('0 ')


def test_rejects_a_tiny_stub_log(_env, monkeypatch):
    tmp_path, ds, make_frames = _env
    monkeypatch.setattr(prep, 'MIN_ROWS', 100)
    rows = [_row(1, 10)]
    make_frames(rows)
    log = tmp_path / 'log.jsonl'
    _write_log(log, rows)
    monkeypatch.setattr(sys, 'argv', ['prep', str(log)])
    with pytest.raises(SystemExit):
        prep.main()
