# meter_sim.py
# Usage: python meter_sim.py
# Publishes signed meter readings to MQTT topic "grid/readings" every 2 seconds.

import os
import json
import time
import paho.mqtt.client as mqtt
from eth_account import Account
from eth_account.messages import encode_defunct

# ---------- Config ----------
SCRIPT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
KEYFILE = os.path.join(PROJECT_ROOT, ".keys", "keys.json")
BROKER = "localhost"       # change if broker on different host
BROKER_PORT = 1883
TOPIC = "grid/readings"
PUBLISH_INTERVAL = 2       # seconds
# ----------------------------

def load_keys(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Keyfile not found: {path}. Run generate_keys.py first.")
    with open(path, "r") as f:
        return json.load(f)

def canonical_json(obj):
    # produce canonical JSON for signing: no spaces, sorted keys
    return json.dumps(obj, separators=(",", ":"), sort_keys=True)

def sign_payload(privkey_hex, payload_text):
    # Ethereum-style personal_sign using eth_account
    msg = encode_defunct(text=payload_text)
    signed = Account.sign_message(msg, private_key=privkey_hex)
    return signed.signature.hex()

def main():
    keys = load_keys(KEYFILE)
    priv = keys["private_key"]
    addr = keys["address"]

    client = mqtt.Client()
    try:
        client.connect(BROKER, BROKER_PORT, 60)
    except Exception as e:
        print("Failed to connect to MQTT broker:", e)
        return

    seq = 0
    print("Meter simulator starting. Publishing to", f"{BROKER}:{BROKER_PORT}", "topic", TOPIC)
    try:
        while True:
            seq += 1
            reading = {
                "meterID": addr,
                "seq": seq,
                "ts": int(time.time()),
                # example value; replace with real sim logic if needed
                "value": round(230 + 5 * (0.5 - (time.time() % 1)), 2)
            }
            canonical = canonical_json(reading)
            sig = sign_payload(priv, canonical)
            reading["signature"] = sig

            payload_str = json.dumps(reading, separators=(",", ":"), sort_keys=False)
            client.publish(TOPIC, payload_str)
            print("Published:", payload_str)
            time.sleep(PUBLISH_INTERVAL)

    except KeyboardInterrupt:
        print("\nMeter simulator stopped by user.")

if __name__ == "__main__":
    main()
