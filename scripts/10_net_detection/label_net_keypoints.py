"""
Interactive net-keypoint labeling tool.

Replaces the hard-coded-pixel-dict workflow (build_labels_v3.py) with
click-to-place labeling, so ground truth is a human clicking a zoomed corner
rather than a vision-model estimate. Writes the same JSON schema every
prepare_net_pose_dataset_v*.py already reads
(net_geometry_labels_v*.json), plus a few additive provenance fields.

The 4 keypoints, in placement order:
  1 net_top_left   2 net_top_right   3 left_post_base   4 right_post_base
(matches infer_angle.NET_KEYPOINT_NAMES.)

Controls
  left click     place the active keypoint, auto-advance to the next
  1 2 3 4        jump the active keypoint
  tab            cycle the active keypoint
  backspace      clear the active keypoint (not visible / off-frame -> null)
  r              reset all 4 points on this frame
  e / m / d      set ground-truth confidence easy / medium / hard (default medium)
  c              copy the 4 points from the previous frame (same fixed-mount net)
  p              (re)fill the 4 points from the prefill model
  z              toggle the magnifier (it also auto-flips to the far side of the cursor)
  n  or  enter   save this frame and go to the next
  u              UNUSABLE -- net is there but corners aren't identifiable (occluded, blurred, dark)
  t              PARTIAL  -- net present but a TOP corner is out of frame (can't measure net width)
  0              NO-NET   -- no tennis net visible at all (negative example)
  s              skip -- leave this frame in the todo list, move on
  b              go back to the previous frame
  q  or  esc     save the session and quit

Resumable: frames already present in --out are skipped. Atomic write after
every frame, so a crash never loses more than the frame in progress.

Usage
  python label_net_keypoints.py --frames-dir DIR --out labels.json
  python label_net_keypoints.py --frames-dir DIR --out labels.json --prefill-model RUN_OR_WEIGHTS
  python label_net_keypoints.py --frames-dir DIR --out labels.json --limit 30
"""
import argparse
import datetime as _dt
import glob
import json
import os
import sys

import cv2
import matplotlib
import matplotlib.pyplot as plt

POINTS = ['net_top_left', 'net_top_right', 'left_post_base', 'right_post_base']
POINT_COLORS = {'net_top_left': '#00e5ff', 'net_top_right': '#ffd500',
                'left_post_base': '#ff4d4d', 'right_post_base': '#7cff4d'}
MAG_HALF = 45      # half-width in source px of the magnifier crop
MAG_ZOOM = 6       # magnifier display zoom factor


def _iso_now():
    return _dt.datetime.now().isoformat(timespec='seconds')


def resolve_weights(run_or_path):
    """Accept a bare weights path or a run name under data/10_net_detection/."""
    if run_or_path is None:
        return None
    if os.path.isfile(run_or_path):
        return run_or_path
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.normpath(os.path.join(here, '..', '..', 'data', '10_net_detection',
                                        run_or_path, 'weights', 'best.pt'))
    if os.path.isfile(cand):
        return cand
    raise SystemExit(f'Could not resolve model weights from "{run_or_path}" (tried {cand})')


def load_prefill_model(run_or_path):
    weights = resolve_weights(run_or_path)
    from ultralytics import YOLO
    print(f'Loading prefill model: {weights}', file=sys.stderr)
    return YOLO(weights)


def predict_keypoints(model, img_bgr):
    """Return {name: [x_px, y_px]} for the top detection, or {}."""
    res = model.predict(img_bgr, verbose=False)
    if not res or res[0].keypoints is None or len(res[0].keypoints) == 0:
        return {}
    kxy = res[0].keypoints.xy
    if kxy.shape[1] == 0:
        return {}
    pts = kxy[0].cpu().numpy()
    out = {}
    for i, name in enumerate(POINTS):
        x, y = float(pts[i][0]), float(pts[i][1])
        if x == 0 and y == 0:
            continue
        out[name] = [x, y]
    return out


def load_out(path):
    if not os.path.exists(path):
        return {'_meta': {
            'description': ("Human click-labeled net keypoints, full-frame pixel coords, "
                            "origin top-left. Same schema as net_geometry_labels_v3.json "
                            "plus provenance fields. Frames where the net isn't visible, or "
                            "a corner is occluded/off-frame, are marked unusable rather than guessed."),
            'labeled_by': 'human-click',
        }, 'labels': []}
    with open(path) as f:
        return json.load(f)


def write_out(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def load_frame_sources(frames_dir):
    """Optional {frame_file: source_video} map from a sibling frame_manifest.json."""
    man = os.path.join(frames_dir, 'frame_manifest.json')
    if not os.path.exists(man):
        man = os.path.join(os.path.dirname(frames_dir.rstrip('/\\')), 'frame_manifest.json')
    if not os.path.exists(man):
        return {}
    try:
        with open(man) as f:
            rows = json.load(f)
        return {r['frame_file']: r.get('source_video') for r in rows}
    except Exception:
        return {}


class Labeler:
    def __init__(self, frames, frames_dir, out_path, out_data, model, model_name, sources):
        self.frames = frames
        self.frames_dir = frames_dir
        self.out_path = out_path
        self.out_data = out_data
        self.model = model
        self.model_name = model_name
        self.sources = sources
        self.idx = 0
        self.done_files = {r['frame_file'] for r in out_data['labels']}
        # carry-forward: most test frames come in runs from one fixed-mount
        # video where the net doesn't move -- reuse the last human labels for
        # the same source video instead of re-clicking an identical net.
        self.prev_kp = None
        self.prev_video = None
        self.prev_conf = 'medium'
        for r in out_data['labels']:                      # seed from an existing session
            if r.get('usable') and all(r['keypoints'].get(p) for p in POINTS):
                self.prev_kp = {p: list(r['keypoints'][p]) for p in POINTS}
                self.prev_video = self._video_key(r['frame_file'])
                self.prev_conf = r.get('gt_confidence', 'medium')

        self.fig, self.ax = plt.subplots(figsize=(15, 8.5))
        self.fig.subplots_adjust(left=0.03, right=0.99, top=0.93, bottom=0.03)
        self.mag_ax = self.fig.add_axes([0.80, 0.55, 0.18, 0.40], zorder=10)
        self.mag_ax.set_xticks([]); self.mag_ax.set_yticks([])
        self.mag_on = True
        self._mag_rect_right = [0.80, 0.55, 0.18, 0.40]
        self._mag_rect_left = [0.02, 0.55, 0.18, 0.40]
        self.fig.canvas.mpl_connect('button_press_event', self.on_click)
        self.fig.canvas.mpl_connect('key_press_event', self.on_key)
        self.fig.canvas.mpl_connect('motion_notify_event', self.on_move)

        self._img_rgb = None
        self._load_current()

    # ---- frame state ----
    def _cur_file(self):
        return os.path.basename(self.frames[self.idx])

    def _video_key(self, fname):
        """Group frames by source video so the net can be carried forward."""
        v = self.sources.get(fname) if hasattr(self, 'sources') else None
        if v:
            return v
        import re
        return re.sub(r'_(swing_\d+|\d{2,})\.(jpg|png)$', '', fname, flags=re.I)

    def _advance_to_unlabeled(self, step=1):
        while 0 <= self.idx < len(self.frames):
            if self._cur_file() not in self.done_files:
                return True
            self.idx += step
        return False

    def _load_current(self):
        if not (0 <= self.idx < len(self.frames)):
            print('\nAll frames handled. Saving and closing.')
            plt.close(self.fig)
            return
        path = self.frames[self.idx]
        img = cv2.imread(path)
        if img is None:
            print(f'  cannot read {path} -- skipping', file=sys.stderr)
            self.idx += 1
            self._load_current()
            return
        self.h, self.w = img.shape[:2]
        self._img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        self.kp = {p: None for p in POINTS}
        self.active = 0
        self.confidence = 'medium'
        self.status = ''
        same_video = self.prev_kp is not None and self._video_key(self._cur_file()) == self.prev_video
        if same_video:
            # fixed-mount: carry the last human labels forward. Nudge only if the
            # net actually looks different, then n. Press m to drop to model prefill.
            self.kp = {p: list(self.prev_kp[p]) for p in POINTS}
            self.confidence = self.prev_conf
            self.status = 'carried from previous frame (same video) -- adjust or n'
        elif self.model is not None:
            for name, xy in predict_keypoints(self.model, img).items():
                self.kp[name] = [round(xy[0], 1), round(xy[1], 1)]
        self._redraw()

    # ---- drawing ----
    def _redraw(self):
        self.ax.clear()
        self.ax.imshow(self._img_rgb)
        self.ax.set_xticks([]); self.ax.set_yticks([])
        for i, p in enumerate(POINTS):
            xy = self.kp[p]
            if xy is None:
                continue
            marker = 'o' if i != self.active else 'D'
            self.ax.plot(xy[0], xy[1], marker=marker, ms=11, mfc='none',
                         mec=POINT_COLORS[p], mew=2.5)
            self.ax.annotate(str(i + 1), (xy[0], xy[1]), textcoords='offset points',
                             xytext=(8, 8), color=POINT_COLORS[p], fontsize=11, weight='bold')
        # draw the net quad if all top corners present
        tl, tr = self.kp['net_top_left'], self.kp['net_top_right']
        bl, br = self.kp['left_post_base'], self.kp['right_post_base']
        if tl and tr:
            self.ax.plot([tl[0], tr[0]], [tl[1], tr[1]], '-', color='w', lw=1, alpha=0.6)
        if tl and bl:
            self.ax.plot([tl[0], bl[0]], [tl[1], bl[1]], '-', color='w', lw=1, alpha=0.4)
        if tr and br:
            self.ax.plot([tr[0], br[0]], [tr[1], br[1]], '-', color='w', lw=1, alpha=0.4)

        n_done = len(self.done_files)
        active_name = POINTS[self.active]
        self.fig.suptitle(
            f'[{n_done + 1}] {self._cur_file()}   |   placing: {self.active + 1} {active_name}   '
            f'|   conf: {self.confidence}   {self.status}\n'
            f'click=place  1-4=pick pt  bksp=clear  r=reset  c=copy prev  p=model prefill  z=magnifier  '
            f'e/m/d=conf  n=save+next  u=unusable  t=partial(corner off-frame)  0=no-net  s=skip  b=back  q=quit',
            fontsize=10)
        self.fig.canvas.draw_idle()

    def on_move(self, event):
        if not self.mag_on or event.inaxes != self.ax or event.xdata is None:
            return
        # keep the magnifier on the opposite side from the cursor so it never
        # sits on top of the corner you're trying to click
        want = self._mag_rect_left if (event.xdata / self.w) > 0.52 else self._mag_rect_right
        if list(self.mag_ax.get_position().bounds) != want:
            self.mag_ax.set_position(want)
        cx, cy = int(event.xdata), int(event.ydata)
        x0, x1 = max(0, cx - MAG_HALF), min(self.w, cx + MAG_HALF)
        y0, y1 = max(0, cy - MAG_HALF), min(self.h, cy + MAG_HALF)
        crop = self._img_rgb[y0:y1, x0:x1]
        if crop.size == 0:
            return
        self.mag_ax.clear()
        self.mag_ax.imshow(crop, extent=[x0, x1, y1, y0], interpolation='nearest')
        self.mag_ax.plot([cx], [cy], '+', color='magenta', ms=14, mew=1.5)
        for p in POINTS:
            xy = self.kp[p]
            if xy and x0 <= xy[0] <= x1 and y0 <= xy[1] <= y1:
                self.mag_ax.plot(xy[0], xy[1], 'o', ms=10, mfc='none',
                                 mec=POINT_COLORS[p], mew=2)
        self.mag_ax.set_xlim(x0, x1); self.mag_ax.set_ylim(y1, y0)
        self.mag_ax.set_xticks([]); self.mag_ax.set_yticks([])
        self.fig.canvas.draw_idle()

    def on_click(self, event):
        if event.inaxes != self.ax or event.xdata is None:
            return
        self.kp[POINTS[self.active]] = [round(float(event.xdata), 1), round(float(event.ydata), 1)]
        self.active = (self.active + 1) % 4
        self._redraw()

    # ---- record building ----
    def _record(self, usable, no_net=False, partial=False):
        kp_out = {p: (self.kp[p] if self.kp[p] is not None else None) for p in POINTS}
        if not usable:
            kp_out = {p: None for p in POINTS}
        return {
            'frame_file': self._cur_file(),
            'usable': bool(usable),
            'no_net': bool(no_net),
            'partial_net': bool(partial),
            'keypoints': kp_out,
            'labeled_by': 'human-click',
            'labeled_at': _iso_now(),
            'prefill_model': self.model_name,
            'source_video': self.sources.get(self._cur_file()),
            'img_w': self.w, 'img_h': self.h,
            'gt_confidence': self.confidence,
        }

    def _commit(self, rec):
        fname = rec['frame_file']
        self.out_data['labels'] = [r for r in self.out_data['labels'] if r['frame_file'] != fname]
        self.out_data['labels'].append(rec)
        self.out_data['_meta']['updated_at'] = _iso_now()
        write_out(self.out_path, self.out_data)
        self.done_files.add(fname)
        if rec['usable'] and all(rec['keypoints'].get(p) for p in POINTS):
            self.prev_kp = {p: list(rec['keypoints'][p]) for p in POINTS}
            self.prev_video = self._video_key(fname)
            self.prev_conf = rec['gt_confidence']

    def _save_and_next(self, usable, no_net=False, partial=False):
        if usable:
            missing = [p for p in ('net_top_left', 'net_top_right') if self.kp[p] is None]
            if missing:
                self.status = f'!! need {", ".join(missing)} (or press u / t / 0)'
                self._redraw()
                return
        self._commit(self._record(usable, no_net, partial))
        self.idx += 1
        self._load_current()

    def on_key(self, event):
        k = event.key
        if k in ('n', 'enter'):
            self._save_and_next(usable=True)
        elif k == 'u':
            self._save_and_next(usable=False)
        elif k == 't':
            self._save_and_next(usable=False, partial=True)
        elif k == '0':
            self._save_and_next(usable=False, no_net=True)
        elif k == 's':
            self.idx += 1
            self._load_current()
        elif k == 'b':
            self.idx = max(0, self.idx - 1)
            # allow re-labeling: drop it from done so _load_current shows it
            f = self._cur_file()
            self.out_data['labels'] = [r for r in self.out_data['labels'] if r['frame_file'] != f]
            self.done_files.discard(f)
            write_out(self.out_path, self.out_data)
            self._load_current()
        elif k in ('q', 'escape'):
            plt.close(self.fig)
        elif k in ('1', '2', '3', '4'):
            self.active = int(k) - 1
            self._redraw()
        elif k == 'tab':
            self.active = (self.active + 1) % 4
            self._redraw()
        elif k == 'backspace':
            self.kp[POINTS[self.active]] = None
            self._redraw()
        elif k == 'r':
            self.kp = {p: None for p in POINTS}
            self.active = 0
            self._redraw()
        elif k == 'z':
            self.mag_on = not self.mag_on
            self.mag_ax.set_visible(self.mag_on)
            self.status = 'magnifier ' + ('on' if self.mag_on else 'off')
            self._redraw()
        elif k == 'c':
            if self.prev_kp is not None:
                self.kp = {p: list(self.prev_kp[p]) for p in POINTS}
                self.status = 'copied previous frame'
            self._redraw()
        elif k == 'p':
            if self.model is not None:
                path = self.frames[self.idx]
                self.kp = {p: None for p in POINTS}
                for name, xy in predict_keypoints(self.model, cv2.imread(path)).items():
                    self.kp[name] = [round(xy[0], 1), round(xy[1], 1)]
                self.status = 'model prefill'
            self._redraw()
        elif k in ('e', 'm', 'd'):
            self.confidence = {'e': 'easy', 'm': 'medium', 'd': 'hard'}[k]
            self._redraw()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frames-dir', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--prefill-model', default=None,
                    help='run name under data/10_net_detection/ or a bare best.pt path')
    ap.add_argument('--limit', type=int, default=None)
    args = ap.parse_args()

    frames = sorted(glob.glob(os.path.join(args.frames_dir, '*.jpg')) +
                    glob.glob(os.path.join(args.frames_dir, '*.png')))
    if not frames:
        raise SystemExit(f'No .jpg/.png frames in {args.frames_dir}')

    out_data = load_out(args.out)
    done = {r['frame_file'] for r in out_data['labels']}
    todo = [f for f in frames if os.path.basename(f) not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f'{len(frames)} frames in dir, {len(done)} already labeled, {len(todo)} to do this session.')
    if not todo:
        print('Nothing to label. Done.')
        return

    model = load_prefill_model(args.prefill_model) if args.prefill_model else None

    try:
        matplotlib.use('TkAgg')
    except Exception:
        pass

    lab = Labeler(todo, args.frames_dir, args.out, out_data, model,
                  args.prefill_model, load_frame_sources(args.frames_dir))
    plt.show()

    n = len(out_data['labels'])
    usable = sum(1 for r in out_data['labels'] if r['usable'])
    print(f'\nSession over. {args.out} now has {n} labels ({usable} usable).')


if __name__ == '__main__':
    main()
