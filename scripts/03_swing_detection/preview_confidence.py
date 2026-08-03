import json
import math

def get_lm(landmarks, name):
    for lm in landmarks:
        if lm['name'] == name:
            return lm
    return None

def dist2d(a, b):
    return math.sqrt((a['x']-b['x'])**2 + (a['y']-b['y'])**2)

with open(r'C:\Users\jackp\tennis_app\data\02_pose_extraction\forehand_poses.json') as f:
    pose_data = json.load(f)
with open(r'C:\Users\jackp\tennis_app\data\03_swing_detection\forehand_swings.json') as f:
    swing_data = json.load(f)

index = {fr['frame']: fr['landmarks'] for fr in pose_data['frames'] if fr['landmarks']}

def nearest(idx, target):
    for off in range(9):
        for d in [0, -off, off]:
            if target + d in idx:
                return idx[target + d]
    return None

print(f"{'Swing':>5} | {'PeakFrame':>9} | {'RW.y':>5} | {'RS.y':>5} | {'Overhead':>8} | {'RW_vel':>6} | {'LW_vel':>6}")
print('-' * 65)

for sw in swing_data['swings'][:10]:
    pf = sw['peak_frame']
    lm = nearest(index, pf)
    pm = nearest(index, pf - 3)

    if not lm:
        print(f"{sw['swing_id']:>5} | {pf:>9} | no landmarks")
        continue

    rw = get_lm(lm, 'right_wrist')
    rs = get_lm(lm, 'right_shoulder')
    lw = get_lm(lm, 'left_wrist')
    rw_p = get_lm(pm, 'right_wrist') if pm else None
    lw_p = get_lm(pm, 'left_wrist') if pm else None

    rw_v = round(dist2d(rw, rw_p), 4) if rw and rw_p else 0
    lw_v = round(dist2d(lw, lw_p), 4) if lw and lw_p else 0
    overhead = round(rs['y'] - rw['y'], 3) if rw and rs else 0

    print(f"{sw['swing_id']:>5} | {pf:>9} | {rw['y']:.3f} | {rs['y']:.3f} | {overhead:>+8.3f} | {rw_v:>6.4f} | {lw_v:>6.4f}")
