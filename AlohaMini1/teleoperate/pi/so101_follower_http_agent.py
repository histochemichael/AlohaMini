#!/usr/bin/env python3
"""Raspberry Pi HTTP receiver for one SO-101 follower arm."""

from __future__ import annotations

import argparse
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from lerobot.robots.so_follower.so_follower import SO101Follower
    from lerobot.robots.so_follower.config_so_follower import SO101FollowerConfig
except ModuleNotFoundError:
    from lerobot.robots.so101_follower.so101_follower import SO101Follower
    from lerobot.robots.so101_follower.config_so101_follower import SO101FollowerConfig


def as_float_dict(values):
    out = {}
    for key, value in values.items():
        try:
            out[key] = float(value)
        except Exception:
            try:
                out[key] = float(value.item())
            except Exception:
                pass
    return out


def make_follower(port, robot_id, max_relative_target):
    try:
        cfg = SO101FollowerConfig(port=port, id=robot_id, max_relative_target=max_relative_target)
    except TypeError:
        cfg = SO101FollowerConfig(port=port, id=robot_id)
    return SO101Follower(cfg)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HTTP receiver for one SO-101 follower arm on the Pi")
    parser.add_argument("--follower-port", required=True, help="Pi serial path for follower arm; prefer /dev/serial/by-id/...")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, required=True, help="HTTP port for this follower arm, e.g. 9011")
    parser.add_argument("--robot-id", default="so101_follower_remote", help="LeRobot follower calibration id")
    parser.add_argument("--max-relative-target", type=float, default=10, help="Passed to LeRobot follower config when supported")
    parser.add_argument("--activation-threshold", type=float, default=0.0, help="Ignore commands until leader moves this far from startup pose")
    parser.add_argument("--no-relative-to-start-pose", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser


args = build_parser().parse_args()
logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(message)s")

robot = make_follower(args.follower_port, args.robot_id, args.max_relative_target)
robot.connect()
robot_start = as_float_dict(robot.get_observation())
last_action_time = None
last_error = None
command_count = 0
lock = threading.Lock()

logging.info("Follower connected on %s; HTTP listening on %s:%s", args.follower_port, args.host, args.port)


def build_action(payload):
    leader_action = as_float_dict(payload.get("action", {}))
    leader_start = as_float_dict(payload.get("leader_start", {}))
    if not leader_action:
        return None
    if args.activation_threshold > 0 and leader_start:
        moved = max((abs(leader_action.get(k, v) - v) for k, v in leader_start.items()), default=0.0)
        if moved < args.activation_threshold:
            return None
    if args.no_relative_to_start_pose or not leader_start:
        return leader_action
    action = {}
    for key, leader_value in leader_action.items():
        if key in robot_start and key in leader_start:
            action[key] = robot_start[key] + (leader_value - leader_start[key])
    return action


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *vals):
        return

    def _send(self, code, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path != "/status":
            self._send(404, {"ok": False, "error": "not found"})
            return
        with lock:
            self._send(200, {"ok": True, "follower_port": args.follower_port, "command_count": command_count, "last_action_time": last_action_time, "last_error": last_error})

    def do_POST(self):
        global last_action_time, last_error, command_count
        if self.path != "/action":
            self._send(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            action = build_action(payload)
            if action:
                robot.send_action(action)
                with lock:
                    command_count += 1
                    last_action_time = time.time()
                    last_error = None
            self._send(200, {"ok": True, "sent": bool(action)})
        except Exception as exc:
            with lock:
                last_error = repr(exc)
            logging.exception("action failed")
            self._send(500, {"ok": False, "error": repr(exc)})


try:
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
finally:
    robot.disconnect()
