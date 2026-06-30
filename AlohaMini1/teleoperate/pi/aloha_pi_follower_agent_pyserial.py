#!/usr/bin/env python3
"""Raspberry Pi HTTP receiver for AlohaMini1 base and lift servos using pyserial."""

from __future__ import annotations

import argparse
import json
import math
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import serial

DEFAULT_FRONT_ID = 9
DEFAULT_BACK_LEFT_ID = 8
DEFAULT_BACK_RIGHT_ID = 10
DEFAULT_LIFT_ID = 11


def checksum(data: list[int]) -> int:
    return (~(sum(data) & 0xFF)) & 0xFF


def send_packet(bus: serial.Serial, servo_id: int, instruction: int, params: list[int] | None = None) -> None:
    params = params or []
    body = [servo_id, len(params) + 2, instruction, *params]
    packet = bytes([0xFF, 0xFF, *body, checksum(body)])
    bus.reset_input_buffer()
    bus.write(packet)
    bus.flush()
    time.sleep(0.003)


def drain_response(bus: serial.Serial, timeout: float = 0.025) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if bus.in_waiting:
            bus.read(bus.in_waiting)
        time.sleep(0.001)


def write_byte(bus: serial.Serial, servo_id: int, address: int, value: int) -> None:
    send_packet(bus, servo_id, 0x03, [address & 0xFF, value & 0xFF])
    drain_response(bus)


def write_word(bus: serial.Serial, servo_id: int, address: int, value: int) -> None:
    value &= 0xFFFF
    send_packet(bus, servo_id, 0x03, [address & 0xFF, value & 0xFF, (value >> 8) & 0xFF])
    drain_response(bus)


def encode_speed(speed: int) -> int:
    if abs(speed) > 32767:
        raise ValueError("Speed magnitude must be <= 32767")
    return 32768 + abs(speed) if speed < 0 else speed


def set_velocity_mode(bus: serial.Serial, servo_id: int) -> None:
    # STS3215 velocity-mode register sequence from the working AlohaMini1 controller.
    write_byte(bus, servo_id, 40, 0)
    write_byte(bus, servo_id, 55, 0)
    write_byte(bus, servo_id, 33, 1)
    write_byte(bus, servo_id, 55, 1)
    write_byte(bus, servo_id, 40, 1)


def set_speed(bus: serial.Serial, servo_id: int, speed: int) -> None:
    write_word(bus, servo_id, 46, encode_speed(speed))


def normalize_speeds(speeds: dict[int, int], max_magnitude: int = 32767) -> dict[int, int]:
    largest = max(abs(value) for value in speeds.values())
    if largest <= max_magnitude or largest == 0:
        return speeds
    scale = max_magnitude / largest
    return {servo_id: round(value * scale) for servo_id, value in speeds.items()}


def mix_base_speeds(args, forward_speed: int, turn_speed: int) -> dict[int, int]:
    raw_front = turn_speed
    raw_back_left = (-0.866 * forward_speed) + turn_speed
    raw_back_right = (0.866 * forward_speed) + turn_speed
    return normalize_speeds(
        {
            args.front_id: round(raw_front * args.front_sign),
            args.back_left_id: round(raw_back_left * args.back_left_sign),
            args.back_right_id: round(raw_back_right * args.back_right_sign),
        }
    )


class RobotState:
    def __init__(self, bus: serial.Serial, args):
        self.bus = bus
        self.args = args
        self.timeout = args.timeout
        self.lock = threading.Lock()
        self.last_command = 0.0
        self.last_base_speeds: dict[int, int] | None = None
        self.last_lift_speed: int | None = None
        self.command_count = 0
        self.last_error = ""
        self.running = True

    @property
    def base_ids(self) -> tuple[int, int, int]:
        return (self.args.front_id, self.args.back_left_id, self.args.back_right_id)

    def apply(self, base_forward: int, base_turn: int, lift: int) -> None:
        base_speeds = mix_base_speeds(self.args, base_forward, base_turn)
        with self.lock:
            if base_speeds != self.last_base_speeds:
                for servo_id in self.base_ids:
                    set_speed(self.bus, servo_id, base_speeds[servo_id])
                self.last_base_speeds = base_speeds
            if lift != self.last_lift_speed:
                set_speed(self.bus, self.args.lift_id, lift)
                self.last_lift_speed = lift
            self.last_command = time.monotonic()
            self.command_count += 1
            self.last_error = ""

    def stop(self) -> None:
        with self.lock:
            for servo_id in self.base_ids:
                set_speed(self.bus, servo_id, 0)
            set_speed(self.bus, self.args.lift_id, 0)
            self.last_base_speeds = {servo_id: 0 for servo_id in self.base_ids}
            self.last_lift_speed = 0

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            age = time.monotonic() - self.last_command if self.last_command else math.inf
            return {
                "ok": not self.last_error,
                "command_count": self.command_count,
                "last_command_age": None if math.isinf(age) else round(age, 3),
                "timeout": self.timeout,
                "base_speeds": self.last_base_speeds,
                "lift_speed": self.last_lift_speed,
                "last_error": self.last_error,
                "servo_ids": {"front": self.args.front_id, "back_left": self.args.back_left_id, "back_right": self.args.back_right_id, "lift": self.args.lift_id},
            }

    def watchdog_loop(self) -> None:
        while self.running:
            age = time.monotonic() - self.last_command if self.last_command else math.inf
            if age > self.timeout:
                try:
                    self.stop()
                except Exception as exc:
                    with self.lock:
                        self.last_error = str(exc)
            time.sleep(0.05)


def make_handler(robot: RobotState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def write_json(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/status":
                self.write_json(200, robot.snapshot())
                return
            self.send_error(404)

        def do_POST(self):
            if self.path == "/stop":
                try:
                    robot.stop()
                    self.write_json(200, {"ok": True, "stopped": True})
                except Exception as exc:
                    self.write_json(500, {"ok": False, "error": str(exc)})
                return
            if self.path != "/command":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                robot.apply(int(payload.get("base_forward", 0)), int(payload.get("base_turn", 0)), int(payload.get("lift", 0)))
                self.write_json(200, {"ok": True})
            except Exception as exc:
                with robot.lock:
                    robot.last_error = str(exc)
                try:
                    robot.stop()
                finally:
                    self.write_json(400, {"ok": False, "error": str(exc)})

    return Handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aloha Mini Raspberry Pi base/lift follower agent using pyserial")
    parser.add_argument("--servo-port", default="/dev/ttyACM0", help="Servo bus path; prefer /dev/serial/by-id/... on the Pi")
    parser.add_argument("--baud", type=int, default=1_000_000)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--front-id", type=int, default=DEFAULT_FRONT_ID)
    parser.add_argument("--back-left-id", type=int, default=DEFAULT_BACK_LEFT_ID)
    parser.add_argument("--back-right-id", type=int, default=DEFAULT_BACK_RIGHT_ID)
    parser.add_argument("--lift-id", type=int, default=DEFAULT_LIFT_ID)
    parser.add_argument("--front-sign", type=int, choices=[-1, 1], default=1)
    parser.add_argument("--back-left-sign", type=int, choices=[-1, 1], default=-1)
    parser.add_argument("--back-right-sign", type=int, choices=[-1, 1], default=-1)
    parser.add_argument("--timeout", type=float, default=0.35)
    parser.add_argument("--setup-velocity-mode", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    bus = serial.Serial(args.servo_port, args.baud, timeout=0.1, write_timeout=0.1)
    time.sleep(0.15)
    try:
        if args.setup_velocity_mode:
            for servo_id in (args.front_id, args.back_left_id, args.back_right_id, args.lift_id):
                print(f"Setting ID {servo_id} to velocity mode...", flush=True)
                set_velocity_mode(bus, servo_id)
        robot = RobotState(bus, args)
        robot.stop()
        threading.Thread(target=robot.watchdog_loop, daemon=True).start()
        server = ThreadingHTTPServer((args.host, args.port), make_handler(robot))
        print(f"Aloha Pi base/lift agent listening on http://{args.host}:{args.port}", flush=True)
        print(f"Servo bus: {args.servo_port} at {args.baud}", flush=True)
        print("POST /command with base_forward, base_turn, lift. Ctrl+C to stop.", flush=True)
        try:
            server.serve_forever()
        finally:
            robot.running = False
            robot.stop()
            server.server_close()
            print("Stopped all servos.", flush=True)
        return 0
    finally:
        bus.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
