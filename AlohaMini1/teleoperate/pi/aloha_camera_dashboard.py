#!/usr/bin/env python3
"""Optional Raspberry Pi camera dashboard and recorder for AlohaMini1.

Edit CAMERAS for your own /dev/v4l/by-path camera names. Find them with:
  ls -l /dev/v4l/by-path/
"""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

CAMERAS = {
    "right_wrist": "/dev/v4l/by-path/REPLACE_WITH_RIGHT_WRIST_CAMERA",
    "front_post": "/dev/v4l/by-path/REPLACE_WITH_FRONT_POST_CAMERA",
    "chest_lift": "/dev/v4l/by-path/REPLACE_WITH_CHEST_LIFT_CAMERA",
    "left_wrist": "/dev/v4l/by-path/REPLACE_WITH_LEFT_WRIST_CAMERA",
    "back_post": "/dev/v4l/by-path/REPLACE_WITH_BACK_POST_CAMERA",
}

record_lock = threading.Lock()
recording_dir = None
recording_procs = {}

HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Aloha Mini Cameras</title>
<style>
  body { margin: 0; background: #111; color: #eee; font-family: Arial, sans-serif; }
  header { height: 56px; display: flex; align-items: center; gap: 12px; padding: 0 16px; background: #1b1b1b; border-bottom: 1px solid #333; }
  button { padding: 8px 12px; border: 1px solid #555; background: #2b2b2b; color: #eee; cursor: pointer; }
  #status { color: #bbb; }
  .grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; padding: 8px; }
  .cam { background: #050505; border: 1px solid #333; min-height: 220px; position: relative; }
  .cam h2 { position: absolute; left: 8px; top: 6px; margin: 0; font-size: 14px; background: rgba(0,0,0,.55); padding: 4px 7px; }
  .cam img { width: 100%; height: 100%; object-fit: contain; display: block; }
</style>
</head>
<body>
<header>
  <strong>Aloha Mini Cameras</strong>
  <button onclick="startRec()">Start Recording</button>
  <button onclick="stopRec()">Stop Recording</button>
  <span id="status">checking...</span>
</header>
<div class="grid">CAMERA_CARDS</div>
<script>
async function refreshStatus() {
  const r = await fetch('/status');
  const s = await r.json();
  document.getElementById('status').textContent = s.recording ? `recording: ${s.recording_dir}` : 'not recording';
}
async function startRec() { await fetch('/record/start', {method:'POST'}); refreshStatus(); }
async function stopRec() { await fetch('/record/stop', {method:'POST'}); refreshStatus(); }
setInterval(refreshStatus, 1000);
refreshStatus();
</script>
</body>
</html>
"""


def enabled_cameras():
    return {name: device for name, device in CAMERAS.items() if "REPLACE_WITH" not in device}


def camera_cards():
    cards = []
    for name in enabled_cameras():
        cards.append(f'<section class="cam"><h2>{name}</h2><img src="/stream/{name}"></section>')
    return "\n".join(cards) or "<p>No cameras configured. Edit CAMERAS in aloha_camera_dashboard.py.</p>"


def stream_cmd(device, width, height, fps):
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "v4l2", "-framerate", str(fps), "-video_size", f"{width}x{height}", "-i", device, "-q:v", "5", "-f", "mjpeg", "pipe:1"]


def record_cmd(device, width, height, fps, out_path):
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "v4l2", "-framerate", str(fps), "-video_size", f"{width}x{height}", "-i", device, "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(out_path)]


def stop_recording():
    global recording_dir, recording_procs
    with record_lock:
        for proc in recording_procs.values():
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
        for proc in recording_procs.values():
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        recording_procs = {}
        recording_dir = None


def make_handler(args):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *vals):
            return

        def send_json(self, obj, code=200):
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urlparse(self.path).path
            cameras = enabled_cameras()
            if path in ("/", "/index.html"):
                page = HTML.replace("CAMERA_CARDS", camera_cards()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)
                return
            if path == "/status":
                with record_lock:
                    self.send_json({"recording": bool(recording_procs), "recording_dir": str(recording_dir) if recording_dir else None, "cameras": cameras})
                return
            if path.startswith("/stream/"):
                name = path.split("/", 2)[2]
                if name not in cameras:
                    self.send_error(404)
                    return
                self.stream_camera(cameras[name])
                return
            self.send_error(404)

        def do_POST(self):
            global recording_dir, recording_procs
            path = urlparse(self.path).path
            cameras = enabled_cameras()
            if path == "/record/start":
                with record_lock:
                    if recording_procs:
                        self.send_json({"ok": True, "already_recording": True, "dir": str(recording_dir)})
                        return
                    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    recording_dir = Path(args.output_dir).expanduser() / stamp
                    recording_dir.mkdir(parents=True, exist_ok=True)
                    (recording_dir / "metadata.json").write_text(json.dumps({"started_at": stamp, "width": args.width, "height": args.height, "fps": args.fps, "cameras": cameras}, indent=2))
                    for name, device in cameras.items():
                        recording_procs[name] = subprocess.Popen(record_cmd(device, args.width, args.height, args.fps, recording_dir / f"{name}.mp4"))
                    self.send_json({"ok": True, "dir": str(recording_dir)})
                return
            if path == "/record/stop":
                stop_recording()
                self.send_json({"ok": True})
                return
            self.send_error(404)

        def stream_camera(self, device):
            proc = subprocess.Popen(stream_cmd(device, args.width, args.height, args.fps), stdout=subprocess.PIPE)
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            buf = b""
            try:
                while True:
                    chunk = proc.stdout.read(4096)
                    if not chunk:
                        break
                    buf += chunk
                    while True:
                        start = buf.find(b"\xff\xd8")
                        end = buf.find(b"\xff\xd9", start + 2)
                        if start < 0 or end < 0:
                            break
                        jpg = buf[start:end + 2]
                        buf = buf[end + 2:]
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode() + b"\r\n\r\n")
                        self.wfile.write(jpg)
                        self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                if proc.poll() is None:
                    proc.kill()

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9100)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--output-dir", default="~/aloha_recordings")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(args))
    print(f"Aloha camera dashboard listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    finally:
        stop_recording()


if __name__ == "__main__":
    main()
