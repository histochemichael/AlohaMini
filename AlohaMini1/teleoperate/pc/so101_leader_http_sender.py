#!/usr/bin/env python3
"""Stream one SO-101 leader arm on the PC to a follower HTTP agent on the Pi."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

try:
    from lerobot.teleoperators.so_leader.so_leader import SO101Leader
    from lerobot.teleoperators.so_leader.config_so_leader import SO101LeaderConfig
except ModuleNotFoundError:
    from lerobot.teleoperators.so101_leader.so101_leader import SO101Leader
    from lerobot.teleoperators.so101_leader.config_so101_leader import SO101LeaderConfig


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


def post_action(url: str, payload: dict, timeout: float) -> None:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url.rstrip("/") + "/action",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(request, timeout=timeout).read()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PC sender for one SO-101 leader arm")
    parser.add_argument("--leader-port", required=True, help="Windows COM port for this leader arm, e.g. COM5")
    parser.add_argument("--leader-id", required=True, help="LeRobot calibration id for this leader arm")
    parser.add_argument("--robot-url", required=True, help="Pi follower agent URL, e.g. http://PI_IP:9011")
    parser.add_argument("--fps", type=float, default=10, help="Streaming rate; use 10 for bring-up, 30 after stable")
    parser.add_argument("--request-timeout", type=float, default=2.0)
    parser.add_argument("--keep-going", action="store_true", help="Continue after transient HTTP errors")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    leader = SO101Leader(SO101LeaderConfig(port=args.leader_port, id=args.leader_id))
    leader.connect()
    period = 1.0 / args.fps
    leader_start = as_float_dict(leader.get_action())
    print(f"Leader connected on {args.leader_port}; sending to {args.robot_url}", flush=True)

    try:
        while True:
            action = as_float_dict(leader.get_action())
            payload = {"action": action, "leader_start": leader_start}
            try:
                post_action(args.robot_url, payload, args.request_timeout)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                print(f"Follower command failed: {exc}", flush=True)
                if not args.keep_going:
                    raise
            time.sleep(period)
    finally:
        leader.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
