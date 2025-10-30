#!/usr/bin/env python3
"""
Multi-Meter Simulator - runs many simulated meters concurrently, each with its own key
"""

import os
import json
import time
import math
import random
import signal
import argparse
import threading
from typing import Dict, List, Any, Optional

import paho.mqtt.client as mqtt
from eth_account import Account
from eth_account.messages import encode_defunct

# Local imports
# This file assumes it lives in the `meters/` directory
SCRIPT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
KEYS_DIR = os.path.join(PROJECT_ROOT, ".keys")

# ---------- Utility: canonical JSON ----------
def canonical_json(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True, ensure_ascii=False)

# ---------- Load per-meter key ----------
def load_meter_key(meter_id: str) -> Dict[str, str]:
    keyfile = os.path.join(KEYS_DIR, f"keys_{meter_id}.json")
    if not os.path.exists(keyfile):
        raise FileNotFoundError(f"Keyfile not found for meter {meter_id}: {keyfile}. Use key_manager.py to create it.")
    with open(keyfile, "r") as f:
        return json.load(f)

# ---------- Per-meter simulator ----------
class MeterThread(threading.Thread):
    def __init__(
        self,
        meter_id: str,
        broker: str,
        port: int,
        topic: str,
        interval: float,
        profile: str = "residential",
        stop_event: Optional[threading.Event] = None
    ):
        super().__init__(daemon=True)
        self.meter_id = meter_id
        self.broker = broker
        self.port = port
        self.topic = topic
        self.interval = max(0.5, float(interval))
        self.profile = profile
        self.stop_event = stop_event or threading.Event()

        self.seq = 0
        self.energy_kWh = 0.0
        self.stats = {
            "published": 0,
            "failed": 0,
            "start_time": int(time.time())
        }

        # Key
        self.keys = load_meter_key(meter_id)
        self.priv = self.keys["private_key"]
        if not self.priv.startswith("0x"):
            self.priv = "0x" + self.priv
        self.addr = self.keys["address"]

        # MQTT
        self.client = mqtt.Client(client_id=f"meter_{meter_id}")
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, rc):
        print(f"[{self.meter_id}] MQTT connected rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        print(f"[{self.meter_id}] MQTT disconnected rc={rc}")

    def _gen_reading(self, hour: int) -> Dict[str, float]:
        # Profiles: residential (peaks morning/evening), commercial (business hours), industrial (flatter)
        if self.profile == "commercial":
            # Peak 9-17
            load_factor = 0.25 + 0.75 * (1 if 9 <= hour <= 17 else 0.15 + 0.1 * math.sin(hour / 24 * 2 * math.pi))
            base_voltage = 400.0
            base_current = 15.0
        elif self.profile == "industrial":
            load_factor = 0.7 + 0.2 * math.sin(hour / 24 * 2 * math.pi)
            base_voltage = 690.0
            base_current = 40.0
        else:
            # residential
            peak = 1.0 if (6 <= hour <= 9 or 18 <= hour <= 22) else 0.5
            load_factor = 0.3 + 0.7 * peak + 0.1 * math.sin(hour / 24 * 2 * math.pi)
            base_voltage = 230.0
            base_current = 5.0

        v = base_voltage + random.uniform(-3, 3)
        i = max(0.1, base_current * load_factor + random.uniform(-0.3, 0.3))
        p = v * i
        return {
            "voltage": round(v, 2),
            "current": round(i, 2),
            "power": round(p, 2)
        }

    def _sign_flat(self, flat: Dict[str, Any]) -> str:
        msg = encode_defunct(text=canonical_json(flat))
        signed = Account.sign_message(msg, private_key=self.priv)
        sig_hex = signed.signature.hex()
        if not sig_hex.startswith("0x"):
            sig_hex = "0x" + sig_hex
        return sig_hex

    def run(self):
        try:
            self.client.connect(self.broker, self.port, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"[{self.meter_id}] MQTT connect failed: {e}")
            return

        print(f"[{self.meter_id}] Publishing to {self.broker}:{self.port} topic '{self.topic}' every {self.interval}s (profile={self.profile})")

        try:
            while not self.stop_event.is_set():
                self.seq += 1
                ts = int(time.time())
                hour = time.localtime(ts).tm_hour

                rd = self._gen_reading(hour)
                # Occasionally add simple flags
                status = {
                    "tamper": random.random() < 0.01,
                    "reverse_flow": random.random() < 0.005,
                    "low_voltage": rd["voltage"] < 210 if self.profile == "residential" else False
                }

                self.energy_kWh += rd["power"] * (self.interval / 3600000.0)
                # Flat payload for signing (match backend expectations)
                flat = {
                    "meterID": self.addr,
                    "seq": self.seq,
                    "ts": ts,
                    "value": rd["power"]
                }
                sig = self._sign_flat(flat)

                full = {
                    "meterID": self.addr,
                    "seq": self.seq,
                    "ts": ts,
                    "reading": {
                        "voltage": rd["voltage"],
                        "current": rd["current"],
                        "power": rd["power"],
                        "energy_kWh": round(max(0.0, self.energy_kWh), 3)
                    },
                    "status": status,
                    "billing_period": time.strftime("%Y-%m"),
                    "value": flat["value"],
                    "signature": sig
                }

                try:
                    payload = json.dumps(full, separators=(",", ":"), ensure_ascii=False)
                    rc = self.client.publish(self.topic, payload).rc
                    if rc == mqtt.MQTT_ERR_SUCCESS:
                        self.stats["published"] += 1
                    else:
                        self.stats["failed"] += 1
                        print(f"[{self.meter_id}] Publish failed rc={rc}")
                except Exception as e:
                    self.stats["failed"] += 1
                    print(f"[{self.meter_id}] Publish exception: {e}")

                time.sleep(self.interval)
        except KeyboardInterrupt:
            pass
        finally:
            self.client.loop_stop()
            self.client.disconnect()
            print(f"[{self.meter_id}] Stopped. Stats: {self.stats}")

# ---------- Multi-meter controller ----------
class MultiMeterController:
    def __init__(
        self,
        broker: str = "localhost",
        port: int = 1883,
        topic: str = "grid/readings",
        default_profile: str = "residential",
        count: int = 5,
        interval_min: float = 1.5,
        interval_max: float = 3.0,
        meter_ids: Optional[List[str]] = None
    ):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.default_profile = default_profile
        self.count = count
        self.interval_min = max(0.5, float(interval_min))
        self.interval_max = max(self.interval_min, float(interval_max))
        self.stop_event = threading.Event()
        self.threads: List[MeterThread] = []

        # Determine meters to run
        if meter_ids:
            self.meter_ids = meter_ids
        else:
            # Generate synthetic meter IDs label to correspond to key files keys_<id>.json
            self.meter_ids = [f"meter_{i:03d}" for i in range(count)]

    def start(self):
        print(f"[multi] Starting {len(self.meter_ids)} meters...")
        for mid in self.meter_ids:
            interval = random.uniform(self.interval_min, self.interval_max)
            profile = random.choice(["residential", "commercial", "industrial"]) if self.default_profile == "mixed" else self.default_profile
            t = MeterThread(
                meter_id=mid,
                broker=self.broker,
                port=self.port,
                topic=self.topic,
                interval=interval,
                profile=profile,
                stop_event=self.stop_event
            )
            t.start()
            self.threads.append(t)

        print("[multi] All meters started.")

    def stop(self):
        print("[multi] Stopping meters...")
        self.stop_event.set()
        for t in self.threads:
            t.join(timeout=3)
        print("[multi] Stopped.")

def _install_sig_handlers(ctrl: MultiMeterController):
    def _handler(signum, frame):
        ctrl.stop()
    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)

def main():
    parser = argparse.ArgumentParser(description="Multi-Meter Simulator")
    parser.add_argument("--broker", default="localhost", help="MQTT broker host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--topic", default="grid/readings", help="MQTT topic")
    parser.add_argument("--count", type=int, default=5, help="Number of meters if --meters not provided")
    parser.add_argument("--profile", choices=["residential", "commercial", "industrial", "mixed"], default="mixed", help="Default profile")
    parser.add_argument("--interval-min", type=float, default=1.5, help="Minimum publish interval")
    parser.add_argument("--interval-max", type=float, default=3.0, help="Maximum publish interval")
    parser.add_argument("--meters", help="Comma-separated list of meter IDs (must have keys_<id>.json in .keys)")
    args = parser.parse_args()

    meter_ids = [m.strip() for m in args.meters.split(",")] if args.meters else None
    ctrl = MultiMeterController(
        broker=args.broker,
        port=args.port,
        topic=args.topic,
        default_profile=args.profile,
        count=args.count,
        interval_min=args.interval_min,
        interval_max=args.interval_max,
        meter_ids=meter_ids
    )
    _install_sig_handlers(ctrl)
    ctrl.start()

    # Keep main alive until interrupted
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        ctrl.stop()

if __name__ == "__main__":
    main()