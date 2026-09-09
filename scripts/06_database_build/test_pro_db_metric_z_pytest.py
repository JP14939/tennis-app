"""Smoke check on the live pro DB once the v4 reslice has run: every
traj_version-4 entry's z is metric world-derived (abs-median in line with x/y,
no image-z-scale outliers). Skips until the DB is v4."""
import json
import os
import statistics

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, '..', '..', 'data', '06_pro_database', 'pro_database.json')


def _load():
    if not os.path.exists(DB_PATH):
        pytest.skip('pro_database.json not present')
    with open(DB_PATH) as f:
        db = json.load(f)
    if db.get('traj_version', 0) < 4:
        pytest.skip(f"pro DB is traj_version {db.get('traj_version')} -- v4 reslice not run yet")
    return db


def test_v4_entries_have_metric_z():
    db = _load()
    v4 = [e for e in db['entries'] if e.get('traj_version', 0) >= 4]
    assert v4, 'no v4 entries'
    checked = 0
    for e in v4[::7]:                                   # sample
        assert 'traj_z_yaw_deg' in e                    # stamped
        zs, xys = [], []
        for p in e['trajectory']:
            for lm in p['landmarks'].values():
                if not lm:
                    continue
                if lm.get('z') is not None:
                    zs.append(abs(lm['z']))
                xys += [abs(lm['x']), abs(lm['y'])]
        if len(zs) < 20:
            continue
        z_med, xy_med = statistics.median(zs), statistics.median(xys)
        assert z_med < 2.5 * xy_med, f"{e['id']}: z abs-median {z_med:.2f} vs x/y {xy_med:.2f}"
        assert max(zs) < 8.0, f"{e['id']}: image-scale z outlier {max(zs):.1f}"
        checked += 1
    assert checked >= 5
