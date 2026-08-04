"""
Build net_geometry_labels_v3.json from this pass's vision-estimated keypoints.

Real-footage frames (mark_vs_silas / nicolas_vs_florian) use one canonical
net position per source video rather than being labeled individually --
both are fixed-mount cameras, so the net's pixel position doesn't move
between swings within the same match. The canonical values were derived by
cropping+zooming the net region on a representative frame from each video
and reading pixel coordinates precisely (see own_footage_frames_v3/_crop_*.jpg),
which is more accurate than eyeballing each full frame individually.

Pro clips are labeled individually since each is a different match/camera.
"""
import glob
import json
import os

FRAMES_DIR = r'C:\Users\jackp\tennis_app\data\10_net_detection\own_footage_frames_v3'
OUT_PATH = r'C:\Users\jackp\tennis_app\data\10_net_detection\net_geometry_labels_v3.json'

MARK_CANON = {
    'net_top_left': [597, 425], 'net_top_right': [1370, 432],
    'left_post_base': [597, 485], 'right_post_base': [1370, 495],
}
NICO_CANON = {
    'net_top_left': [337, 569], 'net_top_right': [1393, 575],
    'left_post_base': [337, 624], 'right_post_base': [1393, 632],
}

# Individually vision-labeled pro clips: frame_file -> keypoints (or None = unusable)
PRO_LABELS = {
    'backhand_swing_0021_conf90.jpg': {'net_top_left': [553, 402], 'net_top_right': [1878, 428], 'left_post_base': [553, 460], 'right_post_base': [1878, 495]},
    'backhand_swing_0022_conf85.jpg': {'net_top_left': [605, 400], 'net_top_right': [1898, 428], 'left_post_base': [605, 460], 'right_post_base': [1898, 493]},
    'backhand_swing_0039_conf85.jpg': {'net_top_left': [590, 345], 'net_top_right': [1618, 345], 'left_post_base': [590, 405], 'right_post_base': [1618, 405]},
    'backhand_swing_0063_conf65.jpg': {'net_top_left': [270, 430], 'net_top_right': [1795, 460], 'left_post_base': [270, 495], 'right_post_base': [1795, 525]},
    'backhand_swing_0074_conf65.jpg': {'net_top_left': [555, 340], 'net_top_right': [1900, 385], 'left_post_base': [555, 400], 'right_post_base': [1900, 445]},
    'backhand_swing_0238_conf90.jpg': {'net_top_left': [400, 478], 'net_top_right': [1580, 485], 'left_post_base': [400, 555], 'right_post_base': [1580, 565]},
    'backhand_swing_0290_conf65.jpg': {'net_top_left': [418, 505], 'net_top_right': [1568, 510], 'left_post_base': [418, 580], 'right_post_base': [1568, 585]},
    'backhand_swing_0293_conf100.jpg': {'net_top_left': [380, 548], 'net_top_right': [1660, 555], 'left_post_base': [380, 618], 'right_post_base': [1660, 625]},
    'backhand_swing_0309_conf90.jpg': {'net_top_left': [145, 405], 'net_top_right': [1785, 435], 'left_post_base': [145, 465], 'right_post_base': [1785, 500]},
    'backhand_swing_0344_conf55.jpg': {'net_top_left': [210, 378], 'net_top_right': [1305, 380], 'left_post_base': [210, 455], 'right_post_base': [1305, 455]},
    'backhand_swing_0354_conf100.jpg': {'net_top_left': [90, 440], 'net_top_right': [1355, 530], 'left_post_base': [90, 505], 'right_post_base': [1355, 595]},
    'backhand_swing_0400_conf90.jpg': {'net_top_left': [598, 505], 'net_top_right': [1750, 540], 'left_post_base': [598, 575], 'right_post_base': [1750, 615]},
    'backhand_swing_0403_conf100.jpg': {'net_top_left': [455, 505], 'net_top_right': [1900, 545], 'left_post_base': [455, 570], 'right_post_base': [1900, 615]},
    'backhand_swing_0433_conf100.jpg': {'net_top_left': [365, 470], 'net_top_right': [1655, 485], 'left_post_base': [365, 535], 'right_post_base': [1655, 555]},
    'backhand_swing_1022_conf100.jpg': {'net_top_left': [60, 1015], 'net_top_right': [1855, 1015], 'left_post_base': None, 'right_post_base': None},
    'backhand_swing_1078_conf80.jpg': {'net_top_left': [40, 895], 'net_top_right': [1885, 895], 'left_post_base': None, 'right_post_base': None},
    'forehand_swing_0011_conf100.jpg': {'net_top_left': [100, 398], 'net_top_right': [1870, 430], 'left_post_base': [100, 455], 'right_post_base': [1870, 495]},
    'forehand_swing_0032_conf75.jpg': {'net_top_left': [395, 455], 'net_top_right': [1735, 510], 'left_post_base': [395, 520], 'right_post_base': [1735, 570]},
    'forehand_swing_0061_conf75.jpg': {'net_top_left': [350, 405], 'net_top_right': [1590, 455], 'left_post_base': [350, 470], 'right_post_base': [1590, 525]},
    'forehand_swing_0093_conf100.jpg': {'net_top_left': [1035, 515], 'net_top_right': [1810, 530], 'left_post_base': [1035, 575], 'right_post_base': [1810, 590]},
    'forehand_swing_0144_conf100.jpg': {'net_top_left': [105, 450], 'net_top_right': [1355, 495], 'left_post_base': [105, 515], 'right_post_base': [1355, 555]},
    'forehand_swing_0160_conf75.jpg': {'net_top_left': [95, 405], 'net_top_right': [1560, 440], 'left_post_base': [95, 460], 'right_post_base': [1560, 505]},
    'forehand_swing_0167_conf100.jpg': {'net_top_left': [145, 390], 'net_top_right': [1440, 415], 'left_post_base': [145, 445], 'right_post_base': [1440, 470]},
    'forehand_swing_0190_conf75.jpg': {'net_top_left': [280, 485], 'net_top_right': [1550, 505], 'left_post_base': [280, 545], 'right_post_base': [1550, 565]},
    'forehand_swing_0252_conf75.jpg': {'net_top_left': [335, 455], 'net_top_right': [1830, 510], 'left_post_base': [335, 510], 'right_post_base': [1830, 570]},
    'forehand_swing_0278_conf100.jpg': {'net_top_left': [430, 470], 'net_top_right': [1490, 485], 'left_post_base': [430, 530], 'right_post_base': [1490, 545]},
    'forehand_swing_0334_conf75.jpg': {'net_top_left': [270, 465], 'net_top_right': [1745, 475], 'left_post_base': [270, 530], 'right_post_base': [1745, 540]},
    'forehand_swing_0356_conf100.jpg': {'net_top_left': [365, 420], 'net_top_right': [1500, 435], 'left_post_base': [365, 470], 'right_post_base': [1500, 490]},
    'forehand_swing_0380_conf75.jpg': {'net_top_left': [400, 505], 'net_top_right': [1660, 530], 'left_post_base': [400, 560], 'right_post_base': [1660, 590]},
    'serve_swing_0038_conf81.jpg': {'net_top_left': [865, 555], 'net_top_right': [1585, 555], 'left_post_base': [865, 600], 'right_post_base': [1585, 600]},
    'serve_swing_0061_conf81.jpg': {'net_top_left': [335, 613], 'net_top_right': [1600, 600], 'left_post_base': [335, 662], 'right_post_base': [1600, 650]},
    'serve_swing_0102_conf73.jpg': {'net_top_left': [400, 595], 'net_top_right': [1560, 585], 'left_post_base': [400, 645], 'right_post_base': [1560, 635]},
    'serve_swing_0103_conf87.jpg': {'net_top_left': [255, 655], 'net_top_right': [1495, 645], 'left_post_base': [255, 700], 'right_post_base': [1495, 690]},
    'serve_swing_0134_conf50.jpg': {'net_top_left': [295, 625], 'net_top_right': [1560, 615], 'left_post_base': [295, 675], 'right_post_base': [1560, 660]},
    'serve_swing_0147_conf56.jpg': {'net_top_left': [345, 610], 'net_top_right': [1615, 620], 'left_post_base': [345, 660], 'right_post_base': [1615, 665]},
    'serve_swing_0168_conf77.jpg': {'net_top_left': [300, 605], 'net_top_right': [1595, 600], 'left_post_base': [300, 655], 'right_post_base': [1595, 650]},
    'serve_swing_0169_conf72.jpg': {'net_top_left': [150, 600], 'net_top_right': [1520, 605], 'left_post_base': [150, 650], 'right_post_base': [1520, 650]},
    'serve_swing_0175_conf89.jpg': {'net_top_left': [95, 585], 'net_top_right': [1425, 585], 'left_post_base': [95, 635], 'right_post_base': [1425, 635]},
    'serve_swing_0195_conf69.jpg': {'net_top_left': [240, 605], 'net_top_right': [1495, 600], 'left_post_base': [240, 655], 'right_post_base': [1495, 650]},
}

# Confirmed unusable (no net visible, or too obstructed / corners not identifiable)
UNUSABLE = {
    'backhand_swing_2009_conf100.jpg', 'backhand_swing_2100_conf65.jpg',
    'backhand_swing_3022_conf85.jpg', 'backhand_swing_3035_conf100.jpg',
    'forehand_swing_1049_conf75.jpg', 'forehand_swing_1086_conf75.jpg',
    'forehand_swing_2002_conf50.jpg', 'forehand_swing_2032_conf100.jpg',
    'forehand_swing_0140_conf70.jpg',
    'serve_swing_0053_conf75.jpg', 'serve_swing_0072_conf78.jpg',
    'serve_swing_0086_conf70.jpg', 'serve_swing_0209_conf53.jpg',
    'serve_swing_1034_conf93.jpg', 'serve_swing_1085_conf65.jpg',
}


def main():
    files = sorted(os.path.basename(f) for f in glob.glob(os.path.join(FRAMES_DIR, '*.jpg')) if not f.endswith('_crop.jpg') and '_crop_' not in f)
    labels = []
    for fname in files:
        if fname.startswith('mark_vs_silas'):
            labels.append({'frame_file': fname, 'usable': True, 'keypoints': dict(MARK_CANON)})
        elif fname.startswith('nicolas_vs_florian'):
            labels.append({'frame_file': fname, 'usable': True, 'keypoints': dict(NICO_CANON)})
        elif fname in PRO_LABELS:
            labels.append({'frame_file': fname, 'usable': True, 'keypoints': PRO_LABELS[fname]})
        elif fname in UNUSABLE:
            labels.append({'frame_file': fname, 'usable': False,
                            'keypoints': {'net_top_left': None, 'net_top_right': None, 'left_post_base': None, 'right_post_base': None}})
        else:
            print(f'WARNING: no label decision for {fname}, skipping')

    data = {
        '_meta': {
            'description': 'Second labeling pass (v3) -- vision-labeled net keypoints, full-frame pixel coords, 1920x1080, origin top-left. Real-footage frames (mark_vs_silas/nicolas_vs_florian) use one canonical net position per video (fixed-mount camera).',
            'labeled_by': 'claude-vision-estimate',
            'usable_criteria': "net's top corners clearly visible and identifiable; frames where the net isn't visible at all, or a corner is occluded/off-frame, are marked unusable rather than guessed.",
        },
        'labels': labels,
    }
    with open(OUT_PATH, 'w') as f:
        json.dump(data, f, indent=2)
    n_usable = sum(1 for l in labels if l['usable'])
    print(f'Wrote {len(labels)} labels ({n_usable} usable) to {OUT_PATH}')


if __name__ == '__main__':
    main()
