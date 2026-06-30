#!/usr/bin/env python3
"""PC remote operator for AlohaMini1 base, lift, and steering.

Keyboard/pedal keys control base forward/backward and lift. Steering can come from
an Android/iOS browser gyro page, face tracking, or be disabled.
"""

from __future__ import annotations

import argparse
import json
import math
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pynput import keyboard


HTML_PAGE = """<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Aloha Mini Remote Control</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 24px; line-height: 1.35; }
    #camera { display: CAM_DISPLAY; width: 100%; max-width: 960px; background: #111; border: 1px solid #ccc; }
    button, select { font-size: 18px; padding: 10px 12px; margin: 4px 4px 4px 0; }
    .value { font-family: ui-monospace, Consolas, monospace; font-size: 18px; }
  </style>
</head>
<body>
  <h1>Aloha Mini Remote Control</h1>
  <img id="camera" src="CAMERA_URL" alt="Camera feed">
  <button id="start">Enable motion</button>
  <button id="zeroButton">Re-zero</button>
  <p>Status: <span id="status">idle</span></p>
  <p>Secure context: <span class="value" id="secure">?</span></p>
  <p>Events seen: <span class="value" id="events">0</span></p>
  <p>Posts sent: <span class="value" id="posts">0</span></p>
  <p>Steering axis:
    <select id="axis">
      <option value="gamma">gamma / roll</option>
      <option value="alpha" selected>alpha / yaw</option>
      <option value="beta">beta / pitch</option>
    </select>
  </p>
  <p>Zero value: <span class="value" id="zero">?</span></p>
  <p>Alpha: <span class="value" id="alpha">?</span></p>
  <p>Beta: <span class="value" id="beta">?</span></p>
  <p>Gamma: <span class="value" id="gamma">?</span></p>
  <p>Relative axis: <span class="value" id="relative">?</span></p>
  <p>Steer: <span class="value" id="steer">?</span></p>
  <script>
    const statusEl = document.getElementById("status");
    const secureEl = document.getElementById("secure");
    const eventsEl = document.getElementById("events");
    const postsEl = document.getElementById("posts");
    const axisEl = document.getElementById("axis");
    const zeroEl = document.getElementById("zero");
    const alphaEl = document.getElementById("alpha");
    const betaEl = document.getElementById("beta");
    const gammaEl = document.getElementById("gamma");
    const relativeEl = document.getElementById("relative");
    const steerEl = document.getElementById("steer");

    secureEl.textContent = window.isSecureContext ? "yes" : "no";
    let zeroValue = null;
    let lastSent = 0;
    let eventCount = 0;
    let postCount = 0;
    let listenerAttached = false;

    function setStatus(text) { statusEl.textContent = text; }
    function numberOrNull(value) { return Number.isFinite(value) ? value : null; }
    function format(value) { return Number.isFinite(value) ? value.toFixed(2) : "null"; }
    function angleDelta(value, zero) {
      let delta = value - zero;
      while (delta > 180) delta -= 360;
      while (delta < -180) delta += 360;
      return delta;
    }
    function selectedAxisValue(event) {
      if (axisEl.value === "alpha") return event.alpha;
      if (axisEl.value === "beta") return event.beta;
      return event.gamma;
    }
    function send(payload) {
      fetch("/gyro", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
        keepalive: true
      }).then(() => {
        postCount += 1;
        postsEl.textContent = String(postCount);
      }).catch(() => setStatus("events firing, but phone cannot POST to PC"));
    }
    function onOrientation(event) {
      eventCount += 1;
      eventsEl.textContent = String(eventCount);
      const alpha = numberOrNull(event.alpha);
      const beta = numberOrNull(event.beta);
      const gamma = numberOrNull(event.gamma);
      alphaEl.textContent = format(alpha);
      betaEl.textContent = format(beta);
      gammaEl.textContent = format(gamma);
      const axisValue = selectedAxisValue(event);
      if (!Number.isFinite(axisValue)) {
        setStatus("events firing, selected axis is null");
        return;
      }
      if (zeroValue === null) {
        zeroValue = axisValue;
        zeroEl.textContent = zeroValue.toFixed(2);
      }
      const relativeAxis = axisEl.value === "alpha" ? angleDelta(axisValue, zeroValue) : axisValue - zeroValue;
      relativeEl.textContent = relativeAxis.toFixed(2);
      const maxAngle = 60;
      const deadzone = 20;
      let steer = 0;
      const magnitude = Math.abs(relativeAxis);
      if (magnitude > deadzone) {
        steer = Math.sign(relativeAxis) * Math.min(1, (magnitude - deadzone) / (maxAngle - deadzone));
      }
      steerEl.textContent = steer.toFixed(3);
      setStatus("streaming to PC operator");
      const now = performance.now();
      if (now - lastSent > 40) {
        lastSent = now;
        send({axis: axisEl.value, alpha, beta, gamma, relative_axis: relativeAxis, steer, timestamp_ms: Date.now()});
      }
    }
    async function start() {
      if (typeof DeviceOrientationEvent === "undefined") {
        setStatus("DeviceOrientationEvent is not available in this browser");
        return;
      }
      if (typeof DeviceOrientationEvent.requestPermission === "function") {
        const response = await DeviceOrientationEvent.requestPermission();
        if (response !== "granted") {
          setStatus("permission denied");
          return;
        }
      }
      zeroValue = null;
      if (!listenerAttached) {
        window.addEventListener("deviceorientation", onOrientation);
        listenerAttached = true;
      }
      setStatus("listener attached; waiting for events");
    }
    axisEl.addEventListener("change", () => { zeroValue = null; zeroEl.textContent = "?"; relativeEl.textContent = "?"; setStatus("axis changed; re-zero on next event"); });
    document.getElementById("zeroButton").addEventListener("click", () => { zeroValue = null; zeroEl.textContent = "?"; relativeEl.textContent = "?"; setStatus("re-zero on next event"); });
    document.getElementById("start").addEventListener("click", start);
  </script>
</body>
</html>
"""


class GyroState:
    def __init__(self):
        self.lock = threading.Lock()
        self.steer = 0.0
        self.relative_axis = 0.0
        self.axis = "?"
        self.last_update = 0.0

    def update(self, steer, relative_axis, axis):
        with self.lock:
            self.steer = steer
            self.relative_axis = relative_axis
            self.axis = axis
            self.last_update = time.monotonic()

    def snapshot(self):
        with self.lock:
            return self.steer, self.relative_axis, self.axis, self.last_update


class FaceSteerState:
    def __init__(self, camera, deadband, max_yaw, smoothing, mirror, preview):
        self.camera = camera
        self.deadband = deadband
        self.max_yaw = max_yaw
        self.smoothing = smoothing
        self.mirror = mirror
        self.preview = preview
        self.lock = threading.Lock()
        self.steer = 0.0
        self.yaw = 0.0
        self.tracked = False
        self.last_update = 0.0
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def snapshot(self):
        with self.lock:
            return self.steer, self.yaw, self.tracked, self.last_update

    def _set(self, steer, yaw, tracked):
        with self.lock:
            self.steer = steer
            self.yaw = yaw
            self.tracked = tracked
            self.last_update = time.monotonic()

    def _yaw_to_steer(self, yaw):
        if abs(yaw) <= self.deadband:
            return 0.0
        sign = 1.0 if yaw > 0 else -1.0
        scaled = (abs(yaw) - self.deadband) / max(1e-6, self.max_yaw - self.deadband)
        return sign * clamp(scaled, 0.0, 1.0)

    def _rotation_matrix_to_yaw(self, rotation_matrix):
        sy = math.sqrt(rotation_matrix[0, 0] ** 2 + rotation_matrix[1, 0] ** 2)
        return math.degrees(math.atan2(-rotation_matrix[2, 0], sy))

    def _run(self):
        import cv2
        import mediapipe as mp
        import numpy as np

        face_points = [1, 152, 33, 263, 61, 291]
        model_points = np.array(
            [(0.0, 0.0, 0.0), (0.0, -63.6, -12.5), (-43.3, 32.7, -26.0), (43.3, 32.7, -26.0), (-28.9, -28.9, -24.1), (28.9, -28.9, -24.1)],
            dtype=np.float64,
        )
        cap = cv2.VideoCapture(self.camera, cv2.CAP_DSHOW)
        if not cap.isOpened():
            print(f"Could not open face camera {self.camera}", file=sys.stderr, flush=True)
            return
        face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6,
        )
        smoothed = 0.0
        while not self.stop_event.is_set():
            ok, frame = cap.read()
            if not ok:
                self._set(0.0, 0.0, False)
                time.sleep(0.05)
                continue
            if self.mirror:
                frame = cv2.flip(frame, 1)
            height, width = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(rgb)
            if not results.multi_face_landmarks:
                smoothed = 0.0
                self._set(0.0, 0.0, False)
                continue
            landmarks = results.multi_face_landmarks[0].landmark
            image_points = np.array([(landmarks[i].x * width, landmarks[i].y * height) for i in face_points], dtype=np.float64)
            camera_matrix = np.array([[width, 0, width / 2], [0, width, height / 2], [0, 0, 1]], dtype=np.float64)
            success, rotation_vec, _ = cv2.solvePnP(model_points, image_points, camera_matrix, np.zeros((4, 1), dtype=np.float64), flags=cv2.SOLVEPNP_ITERATIVE)
            if not success:
                smoothed = 0.0
                self._set(0.0, 0.0, False)
                continue
            rotation_matrix, _ = cv2.Rodrigues(rotation_vec)
            yaw = self._rotation_matrix_to_yaw(rotation_matrix)
            raw_steer = self._yaw_to_steer(yaw)
            alpha = clamp(self.smoothing, 0.0, 1.0)
            smoothed = (1.0 - alpha) * smoothed + alpha * raw_steer
            self._set(smoothed, yaw, True)
            if self.preview:
                cv2.putText(frame, f"Yaw: {yaw:+.1f}  Steer: {smoothed:+.2f}", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
                cv2.imshow("Face steering preview", frame)
                if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                    self.stop_event.set()
        face_mesh.close()
        cap.release()


def clamp(value, low, high):
    return max(low, min(high, value))


def key_name(key):
    if isinstance(key, keyboard.Key):
        return key.name
    if isinstance(key, keyboard.KeyCode):
        return key.char.lower() if key.char else str(key.vk)
    return str(key).lower()


def normalize_key(name):
    return name.strip().lower().replace("key.", "")


def guess_local_ip():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return "PC_IP"


def post_json(url, payload, timeout=0.2):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def make_handler(state, camera_url):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def do_GET(self):
            if self.path not in ("/", "/index.html"):
                self.send_error(404)
                return
            page = HTML_PAGE.replace("CAMERA_URL", camera_url or "")
            page = page.replace("CAM_DISPLAY", "block" if camera_url else "none")
            body = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/gyro":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                steer = clamp(float(payload.get("steer", 0.0)), -1.0, 1.0)
                relative_axis = float(payload.get("relative_axis", 0.0))
                axis = str(payload.get("axis", "?"))
            except (TypeError, ValueError, json.JSONDecodeError):
                self.send_error(400)
                return
            state.update(steer, relative_axis, axis)
            self.send_response(204)
            self.end_headers()

    return Handler


def run(args):
    base_forward_key = normalize_key(args.base_forward_key)
    base_backward_key = normalize_key(args.base_backward_key)
    lift_up_key = normalize_key(args.lift_up_key)
    lift_down_key = normalize_key(args.lift_down_key)
    robot_url = f"http://{args.robot_host}:{args.robot_port}"
    state = GyroState()
    face_state = None
    if args.steering_mode == "face":
        face_state = FaceSteerState(args.face_camera, args.face_deadband, args.face_max_yaw, args.face_smoothing, args.face_mirror, args.face_preview)
        face_state.start()
    pressed = set()
    key_lock = threading.Lock()
    stop_event = threading.Event()

    def on_press(key):
        name = normalize_key(key_name(key))
        with key_lock:
            pressed.add(name)
        if args.debug_keys:
            print(f"key down: {name}", flush=True)

    def on_release(key):
        name = normalize_key(key_name(key))
        with key_lock:
            pressed.discard(name)
        if args.debug_keys:
            print(f"key up: {name}", flush=True)
        if key == keyboard.Key.esc:
            stop_event.set()
            return False

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    server = ThreadingHTTPServer((args.host, args.web_port), make_handler(state, args.camera_url))
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    pc_hint = args.phone_host_hint or args.pc_host_hint or guess_local_ip()
    print(f"Phone control page: http://{pc_hint}:{args.web_port}")
    print(f"Robot agent: {robot_url}")
    print(f"Base pedals: {base_forward_key}=forward, {base_backward_key}=backward, speed={args.base_speed}")
    print(f"Lift pedals: {lift_up_key}=up, {lift_down_key}=down, speed={args.lift_speed}")
    print("Press Esc or Ctrl+C to stop.")
    smoothed_steer = 0.0
    last_payload = None
    last_printed = None

    try:
        while not stop_event.is_set():
            with key_lock:
                base_forward = base_forward_key in pressed
                base_backward = base_backward_key in pressed
                lift_up = lift_up_key in pressed
                lift_down = lift_down_key in pressed
            forward_speed = args.base_speed if base_forward and not base_backward else -args.base_speed if base_backward and not base_forward else 0
            lift_speed = args.lift_speed * args.lift_sign if lift_up and not lift_down else -args.lift_speed * args.lift_sign if lift_down and not lift_up else 0
            if args.steering_mode == "gyro":
                steer, relative_axis, axis, last_update = state.snapshot()
                age = time.monotonic() - last_update if last_update else math.inf
                if age > args.gyro_timeout:
                    steer = 0.0
                if args.invert_turn:
                    steer = -steer
                smoothed_steer = args.smoothing * smoothed_steer + (1.0 - args.smoothing) * steer
            elif args.steering_mode == "face":
                steer, relative_axis, tracked, last_update = face_state.snapshot()
                axis = "face"
                age = time.monotonic() - last_update if last_update else math.inf
                if not tracked or age > args.face_timeout:
                    steer = 0.0
                if args.invert_turn:
                    steer = -steer
                smoothed_steer = steer
            else:
                relative_axis, axis, age = 0.0, "none", 0.0
                smoothed_steer = 0.0
            turn_speed = round(smoothed_steer * args.turn_speed)
            payload = {"base_forward": forward_speed, "base_turn": turn_speed, "lift": lift_speed}
            if payload != last_payload or args.stream_commands:
                try:
                    if not args.dry_run:
                        post_json(f"{robot_url}/command", payload, timeout=args.request_timeout)
                    last_payload = payload
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    print(f"Robot command failed: {exc}", file=sys.stderr, flush=True)
            printable = (forward_speed, lift_speed, axis, round(smoothed_steer, 3), turn_speed, age <= args.gyro_timeout)
            if printable != last_printed:
                live = "live" if age <= args.gyro_timeout else "timeout"
                print("base={:+5d} lift={:+5d} axis={} {} steer={:+.3f} turn={:+5d}".format(forward_speed, lift_speed, axis, live, smoothed_steer, turn_speed), flush=True)
                last_printed = printable
            time.sleep(args.interval)
    finally:
        stop_event.set()
        try:
            post_json(f"{robot_url}/stop", {}, timeout=args.request_timeout)
        except Exception:
            pass
        if face_state:
            face_state.stop()
        listener.stop()
        server.shutdown()
        server.server_close()
        print("Remote robot stop sent.")


def build_parser():
    parser = argparse.ArgumentParser(description="PC remote operator for Aloha Mini Pi follower agent")
    parser.add_argument("--robot-host", required=True, help="Raspberry Pi IP address")
    parser.add_argument("--robot-port", type=int, default=9000)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--web-port", type=int, default=8765)
    parser.add_argument("--pc-host-hint", default="", help="PC Wi-Fi IPv4 address to print for phone browser")
    parser.add_argument("--phone-host-hint", default="")
    parser.add_argument("--camera-url", default="")
    parser.add_argument("--base-forward-key", default="d")
    parser.add_argument("--base-backward-key", default="f")
    parser.add_argument("--lift-up-key", default="a")
    parser.add_argument("--lift-down-key", default="s")
    parser.add_argument("--base-speed", type=int, default=3000)
    parser.add_argument("--lift-speed", type=int, default=1000)
    parser.add_argument("--lift-sign", type=int, default=1)
    parser.add_argument("--turn-speed", type=int, default=600)
    parser.add_argument("--invert-turn", action="store_true")
    parser.add_argument("--gyro-timeout", type=float, default=0.35)
    parser.add_argument("--steering-mode", choices=["gyro", "face", "none"], default="gyro")
    parser.add_argument("--face-camera", type=int, default=0)
    parser.add_argument("--face-deadband", type=float, default=8.0)
    parser.add_argument("--face-max-yaw", type=float, default=35.0)
    parser.add_argument("--face-smoothing", type=float, default=0.2)
    parser.add_argument("--face-timeout", type=float, default=0.35)
    parser.add_argument("--face-mirror", action="store_true", default=True)
    parser.add_argument("--face-preview", action="store_true")
    parser.add_argument("--interval", type=float, default=0.05)
    parser.add_argument("--smoothing", type=float, default=0.75)
    parser.add_argument("--request-timeout", type=float, default=0.2)
    parser.add_argument("--stream-commands", action="store_true", default=True)
    parser.add_argument("--debug-keys", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main():
    args = build_parser().parse_args()
    args.smoothing = clamp(args.smoothing, 0.0, 0.98)
    run(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
