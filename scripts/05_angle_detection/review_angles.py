"""
Manual camera-angle review: run infer_camera_angle() over a sample of real
clips, draw the detected net line + the predicted angle / label / confidence
on a representative frame, and write an HTML gallery + a JSON scoresheet for a
human to mark each one correct / off.

There is no labelled ground-truth angle in the repo -- this is the tool for
building an eyeball sense of whether v10 + the new aggregation is sane, and
for capturing a first pass of human judgement.

Usage:
  python review_angles.py --source amateur --n 40
  python review_angles.py --source pro --shot serve --n 30 --seed 7
  python review_angles.py --source both --n 60

Output: data/05_angle_detection/angle_review/<run>/  (index.html, scores.json)
Open index.html, then fill in scores.json's "verdict" / "true_bucket" / "note"
per clip (or just eyeball the gallery).
"""
import argparse
import base64
import json
import os
import random
import sys
import time

import cv2

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from infer_angle import (  # noqa: E402
    infer_camera_angle, angle_label, run_net_keypoint_model, create_landmarker,
    extract_frame,
)

DATA_DIR = os.path.join(SCRIPTS_DIR, '..', 'data')
CLIPS_DIR = os.path.join(DATA_DIR, '04_clips')
PRO_DB = os.path.join(DATA_DIR, '06_pro_database', 'pro_database.json')
OUT_ROOT = os.path.join(DATA_DIR, '05_angle_detection', 'angle_review')

BUCKETS = ['Front view', 'Semi-front', 'Diagonal (ideal)', 'Semi-side', 'Side view']


def _collect_clips(source, shot, n, seed):
    rng = random.Random(seed)
    pool = []

    if source in ('amateur', 'both'):
        adir = os.path.join(CLIPS_DIR, 'amateur')
        if os.path.isdir(adir):
            for fn in os.listdir(adir):
                if fn.endswith('.mp4'):
                    pool.append(('amateur', os.path.join(adir, fn), None))

    if source in ('pro', 'both'):
        with open(PRO_DB) as f:
            entries = json.load(f)['entries']
        for e in entries:
            if shot != 'all' and e['shot_type'] != shot:
                continue
            cp = e.get('clip_path')
            if not cp:
                continue
            full = cp if os.path.isabs(cp) else os.path.join(CLIPS_DIR, cp)
            if os.path.exists(full):
                pool.append(('pro', full, e.get('camera_angle')))

    if source == 'amateur' and shot != 'all':
        print('  (note: --shot is ignored for amateur clips -- they are not shot-typed here)', file=sys.stderr)

    rng.shuffle(pool)
    return pool[:n]


def _filmstrip(path, n=6, strip_w=900):
    """A horizontal tile of n raw frames across the clip -- shows the footage
    and the swing motion without embedding video."""
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release()
        return None
    idxs = [int(total * f) for f in [i / (n - 1) for i in range(n)]]
    tiles = []
    for idx in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, min(idx, total - 1))
        ok, fr = cap.read()
        if ok and fr is not None:
            tiles.append(fr)
    cap.release()
    if not tiles:
        return None
    tw = strip_w // len(tiles)
    th = int(tiles[0].shape[0] * tw / tiles[0].shape[1])
    return cv2.hconcat([cv2.resize(t, (tw, th)) for t in tiles])


def _draw(frame, kp, angle, conf, debug):
    h, w = frame.shape[:2]
    if w > 960:  # keep the gallery / embedded HTML a sane size
        frame = cv2.resize(frame, (960, int(h * 960 / w)))
        h, w = frame.shape[:2]
    out = frame.copy()

    def px(pt):
        return int(pt[0] * w), int(pt[1] * h)

    if 'net_top_left' in kp and 'net_top_right' in kp:
        a, b = px(kp['net_top_left']), px(kp['net_top_right'])
        cv2.line(out, a, b, (0, 255, 0), 3)
        for p in (a, b):
            cv2.circle(out, p, 7, (0, 200, 255), -1)
    else:
        cv2.putText(out, 'NO NET KEYPOINTS on this frame', (20, h - 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

    lbl = angle_label(angle)
    lines = [
        f'angle: {angle}  ->  {lbl}' if angle is not None else 'angle: NONE',
        f'confidence: {conf}',
    ]
    if isinstance(debug, dict):
        lines.append(f"method: {debug.get('net_detection_method')}  "
                     f"kp_frames: {debug.get('net_keypoint_frames')}")
        if 'per_frame_angles' in debug:
            lines.append(f"per-frame: {debug['per_frame_angles']}  spread {debug.get('angle_spread')}")
    elif isinstance(debug, str):
        lines.append(debug[:80])

    y = 34
    for ln in lines:
        cv2.putText(out, ln, (18, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4)
        cv2.putText(out, ln, (18, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)
        y += 30
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', choices=['amateur', 'pro', 'both'], default='amateur')
    ap.add_argument('--shot', choices=['forehand', 'backhand', 'serve', 'all'], default='all')
    ap.add_argument('--n', type=int, default=40)
    ap.add_argument('--seed', type=int, default=0)
    args = ap.parse_args()

    clips = _collect_clips(args.source, args.shot, args.n, args.seed)
    if not clips:
        raise SystemExit('no clips matched')

    run = f"{args.source}_{args.shot}_{time.strftime('%Y%m%d_%H%M%S')}"
    out_dir = os.path.join(OUT_ROOT, run)
    os.makedirs(out_dir, exist_ok=True)

    lm = create_landmarker()
    rows = []
    for i, (src, path, stored_angle) in enumerate(clips):
        try:
            angle, conf, debug = infer_camera_angle(path, landmarker=lm)
        except Exception as e:  # noqa: BLE001
            angle, conf, debug = None, 0.0, f'ERROR: {e}'

        cap = cv2.VideoCapture(path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        try:
            frame = extract_frame(path, total // 2)
        except Exception:
            frame = None

        img_name = f'{i:03d}_{src}.jpg'
        strip_name = f'{i:03d}_{src}_strip.jpg'
        if frame is not None:
            kp = run_net_keypoint_model(frame)
            cv2.imwrite(os.path.join(out_dir, img_name),
                        _draw(frame, kp, angle, conf, debug))
        else:
            img_name = None
        strip = _filmstrip(path)
        if strip is not None:
            cv2.imwrite(os.path.join(out_dir, strip_name), strip,
                        [cv2.IMWRITE_JPEG_QUALITY, 70])
        else:
            strip_name = None

        rows.append({
            'i': i, 'source': src, 'clip': os.path.relpath(path, CLIPS_DIR),
            'clip_abs': path,
            'image': img_name,
            'strip': strip_name,
            'pred_angle': angle, 'pred_label': angle_label(angle),
            'confidence': conf,
            'method': debug.get('net_detection_method') if isinstance(debug, dict) else str(debug),
            'stored_pro_angle': stored_angle,
            'verdict': '',          # human: 'ok' | 'off' | 'bad-net'
            'true_bucket': '',       # human: one of BUCKETS, if verdict != ok
            'note': '',
        })
        print(f'  {i+1}/{len(clips)}  {src:<8} angle={angle} conf={conf}', flush=True)

    lm.close()

    with open(os.path.join(out_dir, 'scores.json'), 'w') as f:
        json.dump({'run': run, 'buckets': BUCKETS, 'rows': rows}, f, indent=1)

    _write_html(out_dir, run, rows, 'index_linked.html', embed=False)
    _write_html(out_dir, run, rows, 'index.html', embed=True)  # self-contained, portable
    size_mb = os.path.getsize(os.path.join(out_dir, 'index.html')) / 1e6
    print(f'\n{len(rows)} clips -> {out_dir}')
    print(f'open {os.path.join(out_dir, "index.html")}  (self-contained, {size_mb:.1f} MB)')
    if size_mb > 20:
        print('  (large -- use index_linked.html locally, or lower --n, for a lighter file)')
    print(f'or  {os.path.join(out_dir, "index_linked.html")}  (references clips in place, local only)')


def _write_html(out_dir, run, rows, fname='index.html', embed=False):
    def _src(name):
        p = os.path.join(out_dir, name)
        if embed:
            with open(p, 'rb') as fh:
                return 'data:image/jpeg;base64,' + base64.b64encode(fh.read()).decode()
        return name

    cards = []
    for r in rows:
        img = (f'<img src="{_src(r["image"])}" style="width:100%;border-radius:6px">'
               if r['image'] else '<div>(no frame)</div>')
        strip = (f'<img src="{_src(r["strip"])}" style="width:100%;border-radius:6px">'
                 if r.get('strip') else '')
        rel_clip = os.path.relpath(r['clip_abs'], out_dir).replace(os.sep, '/')

        stored = f' &nbsp; stored-pro: {r["stored_pro_angle"]}' if r['stored_pro_angle'] is not None else ''
        cards.append(f"""
        <div style="border:1px solid #ccc;border-radius:8px;padding:10px;background:#fff">
          {img}
          <div style="font:11px system-ui;color:#999;margin:2px 0 6px">detected net (green) + corners (orange) + prediction</div>
          {strip}
          <div style="font:11px system-ui;color:#999;margin-top:2px">the clip, {6} frames start→end &nbsp;·&nbsp; <a href="{rel_clip}">open full clip</a></div>
          <div style="font:13px system-ui;margin-top:6px">
            <b>#{r['i']} · {r['source']}</b> &nbsp; <span style="color:#555">{r['clip']}</span><br>
            <b style="font-size:15px">{r['pred_angle']}° → {r['pred_label']}</b> &nbsp; conf {r['confidence']}{stored}<br>
            <span style="color:#777">{r['method']}</span>
          </div>
        </div>""")

    html = f"""<!doctype html><meta charset=utf-8><title>angle review · {run}</title>
    <body style="margin:20px;background:#f4f4f4;font:14px system-ui">
    <h2>Camera-angle review — {run}</h2>
    <p>{len(rows)} clips. Top image: a mid-clip frame with the detected net top cord
    (green) + corners (orange) and the predicted angle / label / confidence. Below it:
    a 6-frame start→end filmstrip of the actual clip (and a link to the full video,
    which opens when this file sits next to the clips). Eyeball whether the call
    matches the footage; record verdicts in <code>scores.json</code>.</p>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(440px,1fr));gap:14px">
    {''.join(cards)}
    </div></body>"""
    with open(os.path.join(out_dir, fname), 'w', encoding='utf-8') as f:
        f.write(html)


if __name__ == '__main__':
    main()
