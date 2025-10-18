#!/usr/bin/env python3
"""
Enhanced Smart Meter Simulator
Publishes signed, realistic readings every 2 seconds to MQTT topic 'grid/readings'
Focus: Smart Meter Billing & Fraud Simulation
"""

import os
import json
import time
import math
import random
import paho.mqtt.client as mqtt
from eth_account import Account
from eth_account.messages import encode_defunct

# ---------- Config ----------
SCRIPT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
KEYFILE = os.path.join(PROJECT_ROOT, ".keys", "keys.json")
BROKER = "localhost"
PORT = 1883
TOPIC = "grid/readings"
PUBLISH_INTERVAL = 2  # seconds
# ----------------------------

def load_keys(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Keyfile not found: {path}. Run generate_keys.py first.")
    with open(path, "r") as f:
        return json.load(f)

def canonical_json(obj):
    """Generate canonical JSON for signing"""
    return json.dumps(obj, separators=(",", ":"), sort_keys=True, ensure_ascii=False)

def sign_payload(privkey_hex, payload_text):
    """Ethereum-style signing, returns 0x-prefixed signature"""
    msg = encode_defunct(text=payload_text)
    signed = Account.sign_message(msg, private_key=privkey_hex)
    sig_hex = signed.signature.hex()
    if not sig_hex.startswith("0x"):
        sig_hex = "0x" + sig_hex
    return sig_hex

def generate_reading(hour, base_voltage=230, base_current=5):
    """Generate realistic load curve using sine wave pattern"""
    load_factor = 0.6 + 0.4 * math.sin((hour - 6) / 24 * 2 * math.pi)
    voltage = base_voltage + random.uniform(-3, 3)
    current = base_current * load_factor + random.uniform(-0.3, 0.3)
    power = voltage * current
    return voltage, current, power

def main():
    keys = load_keys(KEYFILE)
    priv = keys["private_key"]
    if not priv.startswith("0x"):
        priv = "0x" + priv
    addr = keys["address"]

    client = mqtt.Client()
    client.connect(BROKER, PORT, 60)

    seq = 0
    energy_kWh = 0.0

    print(f"[INFO] Meter {addr[:10]}... publishing to {BROKER}:{PORT} topic '{TOPIC}'")

    try:
        while True:
            seq += 1
            ts = int(time.time())
            hour = time.localtime(ts).tm_hour

            v, i, p = generate_reading(hour)
            energy_kWh += p * (PUBLISH_INTERVAL / 3600000.0)

            # occasional anomalies
            tamper = random.random() < 0.02
            reverse_flow = random.random() < 0.01
            if random.random() < 0.05:
                energy_kWh = max(0.0, energy_kWh - random.uniform(0.05, 0.5))

            # -------- Flatten payload for signing --------
            flat_payload = {
                "meterID": addr,
                "seq": seq,
                "ts": ts,
                "value": round(p, 2)  # signing only the power
            }
            canonical = canonical_json(flat_payload)
            flat_payload["signature"] = sign_payload(priv, canonical)

            # -------- Full reading for MQTT publish --------
            full_reading = {
                "meterID": addr,
                "seq": seq,
                "ts": ts,
                "reading": {
                    "voltage": round(v, 2),
                    "current": round(i, 2),
                    "power": round(p, 2),
                    "energy_kWh": round(max(0, energy_kWh), 3)
                },
                "status": {
                    "tamper": tamper,
                    "reverse_flow": reverse_flow,
                    "low_voltage": v < 210
                },
                "billing_period": time.strftime("%Y-%m"),
                "value": flat_payload["value"],
                "signature": flat_payload["signature"]
            }

            payload_str = json.dumps(full_reading, separators=(",", ":"), ensure_ascii=False)
            client.publish(TOPIC, payload_str)
            print("[PUB]", json.dumps(full_reading, indent=2))

            time.sleep(PUBLISH_INTERVAL)

    except KeyboardInterrupt:
        print("\n[STOPPED] Meter simulator stopped by user.")

if __name__ == "__main__":
    main()
