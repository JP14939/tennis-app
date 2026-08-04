"""
Persistent camera-calibration inference process.

Unlike every other script in this pipeline (spawned fresh per request by the
Node backend), this one is meant to stay running: it loads the net-keypoint
YOLO model once at startup and keeps it resident in memory, so repeated live
calibration checks (as a player positions their camera, roughly every 1.5s
from the frontend) only pay for decode + one forward pass, not a fresh model
load every time.

Usage:
  python calibration_server.py [port]   # default port 5055

POST /check with raw JPEG bytes as the body -> JSON matching
check_camera_setup.py's shape (see infer_angle.check_camera_setup_frame).
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '05_angle_detection'))
from infer_angle import check_camera_setup_frame, _get_net_kp_model  # noqa: E402

DEFAULT_PORT = 5055


class CalibrationHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Default logging writes to stderr per-request -- fine, but keep it
        # short since this fires every ~1.5s while a player is positioning.
        sys.stderr.write(f'[calibration_server] {fmt % args}\n')

    def do_POST(self):
        if self.path != '/check':
            self.send_response(404)
            self.end_headers()
            return

        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            arr = np.frombuffer(body, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError('Could not decode image')

            result = check_camera_setup_frame(frame)
            payload = json.dumps(result).encode('utf-8')

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as e:
            payload = json.dumps({
                'ok': False, 'angle': None, 'confidence': 0.0,
                'height_ratio': None, 'elevation_status': 'unknown',
                'message': str(e),
            }).encode('utf-8')
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)


class SingleInstanceServer(ThreadingHTTPServer):
    # HTTPServer defaults allow_reuse_address = True, which on this platform
    # let multiple instances all appear to bind the same port simultaneously
    # (observed directly: 5 leaked processes all showing LISTENING on 5055
    # after rapid nodemon restarts raced the Node-side "already running"
    # check). Disabling it makes a genuine port conflict fail loudly and
    # immediately instead of silently leaking a duplicate model-holding process.
    allow_reuse_address = False


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT

    print('[calibration_server] loading net-keypoint model...', flush=True)
    _get_net_kp_model()  # warm the model once at startup, not on first request
    print(f'[calibration_server] model loaded, listening on 127.0.0.1:{port}', flush=True)

    try:
        server = SingleInstanceServer(('127.0.0.1', port), CalibrationHandler)
    except OSError as e:
        print(f'[calibration_server] port {port} already in use, exiting: {e}', flush=True)
        sys.exit(1)
    server.serve_forever()


if __name__ == '__main__':
    main()
