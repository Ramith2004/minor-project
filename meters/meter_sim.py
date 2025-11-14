#!/usr/bin/env python3
"""
Enhanced Smart Meter Simulator
Advanced meter simulation with multiple profiles, realistic anomalies, and sophisticated behavior
"""

import os
import json
import time
import math
import random
import threading
import argparse
from typing import Dict, List, Any, Optional
import paho.mqtt.client as mqtt
from eth_account import Account
from eth_account.messages import encode_defunct
from dataclasses import dataclass
from enum import Enum

class MeterType(Enum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    INDUSTRIAL = "industrial"

class AnomalyType(Enum):
    TAMPER = "tamper"
    REVERSE_FLOW = "reverse_flow"
    LOW_VOLTAGE = "low_voltage"
    HIGH_VOLTAGE = "high_voltage"
    EQUIPMENT_FAILURE = "equipment_failure"
    NETWORK_ISSUE = "network_issue"
    CALIBRATION_DRIFT = "calibration_drift"

# ANSI color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

def print_banner(text: str, color=Colors.CYAN):
    """Print a stylized banner"""
    width = 100
    print(f"\n{color}{'=' * width}")
    print(f"{text.center(width)}")
    print(f"{'=' * width}{Colors.END}\n")

def print_box(title: str, content: Dict, color=Colors.GREEN):
    """Print content in a box format"""
    max_key_len = max(len(str(k)) for k in content.keys()) if content else 0
    width = max(80, max_key_len + 50)
    
    print(f"\n{color}┌{'─' * (width - 2)}┐")
    print(f"│ {Colors.BOLD}{title}{Colors.END}{color}{' ' * (width - len(title) - 3)}│")
    print(f"├{'─' * (width - 2)}┤")
    
    for key, value in content.items():
        key_str = f"{key}:".ljust(max_key_len + 2)
        value_str = str(value)
        # Handle long values (like signatures)
        if len(value_str) > width - max_key_len - 8:
            value_str = value_str[:width - max_key_len - 11] + "..."
        print(f"│ {Colors.BOLD}{key_str}{Colors.END}{color} {value_str}{' ' * (width - len(key_str) - len(value_str) - 3)}│")
    
    print(f"└{'─' * (width - 2)}┘{Colors.END}\n")

def print_success(message: str):
    print(f"{Colors.GREEN}✓ {message}{Colors.END}")

def print_info(message: str):
    print(f"{Colors.CYAN}ℹ {message}{Colors.END}")

def print_warning(message: str):
    print(f"{Colors.YELLOW}⚠ {message}{Colors.END}")

def print_error(message: str):
    print(f"{Colors.RED}✗ {message}{Colors.END}")

@dataclass
class MeterProfile:
    """Meter profile configuration"""
    meter_type: MeterType
    base_voltage: float
    base_current: float
    consumption_pattern: str
    anomaly_rate: float
    network_reliability: float
    calibration_drift_rate: float

@dataclass
class AnomalyEvent:
    """Anomaly event structure"""
    anomaly_type: AnomalyType
    severity: float
    duration: int
    start_time: float
    description: str

class EnhancedMeterSimulator:
    def __init__(self, meter_id: str, meter_type: MeterType = MeterType.RESIDENTIAL):
        self.meter_alias = meter_id
        
        # Load keys first to get the real Ethereum address
        self.keys = self._load_keys()
        
        # IMPORTANT: Use the Ethereum address as the actual meter ID
        self.meter_id = self.keys["address"]
        
        self.meter_type = meter_type
        self.profile = self._create_profile(meter_type)
        
        # State variables
        self.sequence = 0
        self.energy_kWh = 0.0
        self.running = False
        
        # Anomaly tracking
        self.active_anomalies: List[AnomalyEvent] = []
        self.anomaly_history: List[AnomalyEvent] = []
        
        # Calibration drift
        self.calibration_offset = 0.0
        
        # Network simulation
        self.network_delays = []
        self.packet_loss_rate = 0.0
        
        # MQTT client
        self.client = mqtt.Client(client_id=f"meter_{meter_id}", callback_api_version=mqtt.CallbackAPIVersion.VERSION1)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        
        # Configuration
        self.broker = "localhost"
        self.port = 1883
        self.topic = "grid/readings"
        self.publish_interval = 2.0
        
        # Statistics
        self.stats = {
            "total_readings": 0,
            "successful_transmissions": 0,
            "failed_transmissions": 0,
            "anomalies_detected": 0,
            "network_issues": 0
        }
    
    def _create_profile(self, meter_type: MeterType) -> MeterProfile:
        """Create meter profile based on type"""
        profiles = {
            MeterType.RESIDENTIAL: MeterProfile(
                meter_type=MeterType.RESIDENTIAL,
                base_voltage=230.0,
                base_current=5.0,
                consumption_pattern="daily_cycle",
                anomaly_rate=0.02,
                network_reliability=0.95,
                calibration_drift_rate=0.001
            ),
            MeterType.COMMERCIAL: MeterProfile(
                meter_type=MeterType.COMMERCIAL,
                base_voltage=400.0,
                base_current=15.0,
                consumption_pattern="business_hours",
                anomaly_rate=0.01,
                network_reliability=0.98,
                calibration_drift_rate=0.0005
            ),
            MeterType.INDUSTRIAL: MeterProfile(
                meter_type=MeterType.INDUSTRIAL,
                base_voltage=1000.0,
                base_current=50.0,
                consumption_pattern="continuous",
                anomaly_rate=0.005,
                network_reliability=0.99,
                calibration_drift_rate=0.0002
            )
        }
        return profiles[meter_type]
    
    def _load_keys(self) -> Dict[str, str]:
        """Load meter keys"""
        script_dir = os.path.dirname(__file__)
        project_root = os.path.abspath(os.path.join(script_dir, ".."))
        # Use the alias (meter1, meter2, etc.) to load the keyfile
        keyfile = os.path.join(project_root, ".keys", f"keys_{self.meter_alias}.json")
        
        if not os.path.exists(keyfile):
            raise FileNotFoundError(f"Keyfile not found: {keyfile}")
        
        with open(keyfile, "r") as f:
            return json.load(f)
    
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            print_success(f"[{self.meter_alias}] Connected to MQTT broker at {self.broker}:{self.port}")
        else:
            print_error(f"[{self.meter_alias}] Failed to connect to MQTT broker: {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback"""
        if rc != 0:
            print_warning(f"[{self.meter_alias}] Unexpected disconnection from MQTT broker (code: {rc})")
    
    def _generate_realistic_reading(self) -> Dict[str, float]:
        """Generate realistic meter reading based on profile"""
        current_time = time.time()
        hour = time.localtime(current_time).tm_hour
        day_of_week = time.localtime(current_time).tm_wday
        
        # Base consumption pattern
        if self.profile.consumption_pattern == "daily_cycle":
            # Residential: peak in morning and evening
            if 6 <= hour <= 9 or 18 <= hour <= 22:
                load_factor = 0.8 + 0.2 * random.random()
            else:
                load_factor = 0.3 + 0.4 * random.random()
        elif self.profile.consumption_pattern == "business_hours":
            # Commercial: peak during business hours
            if 9 <= hour <= 17 and day_of_week < 5:
                load_factor = 0.9 + 0.1 * random.random()
            else:
                load_factor = 0.2 + 0.3 * random.random()
        else:  # continuous
            # Industrial: relatively constant with some variation
            load_factor = 0.7 + 0.3 * random.random()
        
        # Generate electrical values
        voltage = self.profile.base_voltage + random.uniform(-2, 2)
        current = self.profile.base_current * load_factor + random.uniform(-0.2, 0.2)
        power = voltage * current
        
        # Apply calibration drift
        power *= (1 + self.calibration_offset)
        
        return {
            "voltage": round(voltage, 2),
            "current": round(current, 2),
            "power": round(power, 2)
        }
    
    def _check_for_anomalies(self) -> List[AnomalyEvent]:
        """Check for and generate anomalies"""
        new_anomalies = []
        
        # Check if new anomaly should occur
        if random.random() < self.profile.anomaly_rate:
            anomaly_type = random.choice(list(AnomalyType))
            
            # Create anomaly event
            anomaly = AnomalyEvent(
                anomaly_type=anomaly_type,
                severity=random.uniform(0.1, 1.0),
                duration=random.randint(30, 300),  # 30 seconds to 5 minutes
                start_time=time.time(),
                description=f"{anomaly_type.value} anomaly detected"
            )
            
            new_anomalies.append(anomaly)
            self.active_anomalies.append(anomaly)
            self.anomaly_history.append(anomaly)
            self.stats["anomalies_detected"] += 1
        
        return new_anomalies
    
    def _apply_anomalies(self, reading: Dict[str, float]) -> Dict[str, Any]:
        """Apply active anomalies to reading"""
        status = {
            "tamper": False,
            "reverse_flow": False,
            "low_voltage": False,
            "high_voltage": False,
            "equipment_failure": False,
            "network_issue": False,
            "calibration_drift": abs(self.calibration_offset) > 0.01
        }
        
        # Apply active anomalies
        for anomaly in self.active_anomalies[:]:  # Copy list to avoid modification during iteration
            if time.time() - anomaly.start_time > anomaly.duration:
                # Anomaly expired
                self.active_anomalies.remove(anomaly)
                continue
            
            if anomaly.anomaly_type == AnomalyType.TAMPER:
                status["tamper"] = True
                reading["power"] *= random.uniform(0.5, 1.5)
            
            elif anomaly.anomaly_type == AnomalyType.REVERSE_FLOW:
                status["reverse_flow"] = True
                reading["power"] *= -1
            
            elif anomaly.anomaly_type == AnomalyType.LOW_VOLTAGE:
                status["low_voltage"] = True
                reading["voltage"] *= random.uniform(0.7, 0.9)
            
            elif anomaly.anomaly_type == AnomalyType.HIGH_VOLTAGE:
                status["high_voltage"] = True
                reading["voltage"] *= random.uniform(1.1, 1.3)
            
            elif anomaly.anomaly_type == AnomalyType.EQUIPMENT_FAILURE:
                status["equipment_failure"] = True
                reading["power"] *= random.uniform(0.1, 0.5)
            
            elif anomaly.anomaly_type == AnomalyType.NETWORK_ISSUE:
                status["network_issue"] = True
                self.packet_loss_rate = anomaly.severity
            
            elif anomaly.anomaly_type == AnomalyType.CALIBRATION_DRIFT:
                drift_amount = anomaly.severity * random.uniform(-0.1, 0.1)
                self.calibration_offset += drift_amount
        
        return status
    
    def _simulate_network_conditions(self) -> bool:
        """Simulate network conditions"""
        # Simulate packet loss
        if random.random() < self.packet_loss_rate:
            self.stats["network_issues"] += 1
            return False
        
        # Simulate network delay
        if self.network_delays:
            delay = random.choice(self.network_delays)
            time.sleep(delay)
        
        return True
    
    def _sign_payload(self, payload: Dict[str, Any]) -> str:
        """Sign payload using Ethereum-style signing"""
        try:
            priv_key = self.keys["private_key"]
            if not priv_key.startswith("0x"):
                priv_key = "0x" + priv_key
            
            # Create canonical JSON
            canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
            
            # Sign message
            msg = encode_defunct(text=canonical)
            signed = Account.sign_message(msg, private_key=priv_key)
            sig_hex = signed.signature.hex()
            
            if not sig_hex.startswith("0x"):
                sig_hex = "0x" + sig_hex
            
            return sig_hex
            
        except Exception as e:
            print_error(f"[{self.meter_alias}] Signature error: {e}")
            return "0x" + "0" * 130  # Fallback signature
    
    def _publish_reading(self, reading_data: Dict[str, Any]) -> bool:
        """Publish reading to MQTT"""
        try:
            # Simulate network conditions
            if not self._simulate_network_conditions():
                return False
            
            # Create payload that matches backend expectations
            payload = {
                "meterID": self.meter_id,
                "seq": self.sequence,
                "ts": int(time.time()),
                "value": reading_data["power"],
                "signature": reading_data["signature"]
            }
            
            # Publish to MQTT
            payload_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
            result = self.client.publish(self.topic, payload_str)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.stats["successful_transmissions"] += 1
                return True
            else:
                self.stats["failed_transmissions"] += 1
                return False
                
        except Exception as e:
            print_error(f"[{self.meter_alias}] Publish error: {e}")
            self.stats["failed_transmissions"] += 1
            return False
    
    def _update_calibration_drift(self):
        """Update calibration drift"""
        drift_change = random.uniform(-self.profile.calibration_drift_rate, self.profile.calibration_drift_rate)
        self.calibration_offset += drift_change
        
        # Limit drift to reasonable range
        self.calibration_offset = max(-0.05, min(0.05, self.calibration_offset))
    
    def _print_reading_details(self, reading: Dict[str, Any], signing_payload: Dict[str, Any]):
        """Print detailed reading information"""
        # Determine if there are any active anomalies
        has_anomalies = any(reading["status"].values())
        box_color = Colors.YELLOW if has_anomalies else Colors.GREEN
        
        # Prepare display data
        display_data = {
            "Meter ID": self.meter_id,
            "Meter Alias": self.meter_alias,
            "Meter Type": self.meter_type.value.upper(),
            "Sequence": self.sequence,
            "Timestamp": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(signing_payload["ts"])),
            "─── Electrical Readings ───": "",
            "Voltage": f"{reading['voltage']} V",
            "Current": f"{reading['current']} A",
            "Power": f"{reading['power']} W",
            "Total Energy": f"{reading['energy_kWh']} kWh",
            "─── Status Flags ───": "",
            "Tamper": "⚠ YES" if reading["status"]["tamper"] else "✓ NO",
            "Reverse Flow": "⚠ YES" if reading["status"]["reverse_flow"] else "✓ NO",
            "Low Voltage": "⚠ YES" if reading["status"]["low_voltage"] else "✓ NO",
            "High Voltage": "⚠ YES" if reading["status"]["high_voltage"] else "✓ NO",
            "Equipment Failure": "⚠ YES" if reading["status"]["equipment_failure"] else "✓ NO",
            "Network Issue": "⚠ YES" if reading["status"]["network_issue"] else "✓ NO",
            "Calibration Drift": "⚠ YES" if reading["status"]["calibration_drift"] else "✓ NO",
            "─── Security ───": "",
            "Signature": reading["signature"][:20] + "..." + reading["signature"][-20:],
            "Full Signature": reading["signature"]
        }
        
        print_box(f"Reading #{self.sequence}", display_data, box_color)
        
        # Print MQTT payload that was sent
        mqtt_payload = {
            "meterID": signing_payload["meterID"],
            "seq": signing_payload["seq"],
            "ts": signing_payload["ts"],
            "value": signing_payload["value"],
            "signature": reading["signature"][:30] + "..." + reading["signature"][-30:]
        }
        
        print(f"{Colors.CYAN}Published MQTT Payload:{Colors.END}")
        print(f"{Colors.BOLD}{json.dumps(mqtt_payload, indent=2)}{Colors.END}\n")
    
    def start(self):
        """Start meter simulation"""
        print_banner(f"SMART METER SIMULATION - {self.meter_type.value.upper()}", Colors.CYAN)
        
        # Print meter configuration
        config_data = {
            "Meter Alias": self.meter_alias,
            "Meter ID (Address)": self.meter_id,
            "Meter Type": self.meter_type.value.upper(),
            "Base Voltage": f"{self.profile.base_voltage} V",
            "Base Current": f"{self.profile.base_current} A",
            "Consumption Pattern": self.profile.consumption_pattern,
            "Anomaly Rate": f"{self.profile.anomaly_rate * 100:.1f}%",
            "Network Reliability": f"{self.profile.network_reliability * 100:.1f}%",
            "MQTT Broker": f"{self.broker}:{self.port}",
            "MQTT Topic": self.topic,
            "Publish Interval": f"{self.publish_interval} seconds"
        }
        print_box("Meter Configuration", config_data, Colors.BLUE)
        
        # Connect to MQTT broker
        try:
            print_info(f"Connecting to MQTT broker at {self.broker}:{self.port}...")
            self.client.connect(self.broker, self.port, 60)
            self.client.loop_start()
            time.sleep(1)  # Give connection time to establish
        except Exception as e:
            print_error(f"Failed to connect to broker: {e}")
            return
        
        self.running = True
        
        try:
            while self.running:
                self.sequence += 1
                
                # Generate reading
                reading = self._generate_realistic_reading()
                
                # Check for anomalies
                new_anomalies = self._check_for_anomalies()
                
                # Apply anomalies
                status = self._apply_anomalies(reading)
                
                # Update calibration drift
                self._update_calibration_drift()
                
                # Create signing payload
                signing_payload = {
                    "meterID": self.meter_id,
                    "seq": self.sequence,
                    "ts": int(time.time()),
                    "value": reading["power"]
                }
                
                # Sign payload
                signature = self._sign_payload(signing_payload)
                
                # Add signature and status to reading
                reading["signature"] = signature
                reading["status"] = status
                
                # Update energy total
                self.energy_kWh += reading["power"] * (self.publish_interval / 3600000.0)
                reading["energy_kWh"] = round(max(0, self.energy_kWh), 3)
                
                # Print detailed reading
                self._print_reading_details(reading, signing_payload)
                
                # Publish reading
                success = self._publish_reading(reading)
                
                if success:
                    print_success(f"Reading #{self.sequence} successfully published to MQTT")
                else:
                    print_error(f"Failed to publish reading #{self.sequence}")
                
                # Log anomalies
                for anomaly in new_anomalies:
                    print_warning(f"New anomaly detected: {anomaly.description} (severity: {anomaly.severity:.2f})")
                
                self.stats["total_readings"] += 1
                
                print(f"{Colors.CYAN}{'─' * 100}{Colors.END}\n")
                
                # Sleep until next reading
                time.sleep(self.publish_interval)
                
        except KeyboardInterrupt:
            print_warning(f"\nStopping meter simulation...")
        finally:
            self.stop()
    
    def stop(self):
        """Stop meter simulation"""
        self.running = False
        self.client.loop_stop()
        self.client.disconnect()
        
        # Print final statistics
        print_banner("SIMULATION COMPLETE - FINAL STATISTICS", Colors.YELLOW)
        
        stats_data = {
            "Meter ID": self.meter_id,
            "Meter Type": self.meter_type.value.upper(),
            "Total Readings": self.stats['total_readings'],
            "Successful Transmissions": f"{self.stats['successful_transmissions']} ({self.stats['successful_transmissions']/max(1,self.stats['total_readings'])*100:.1f}%)",
            "Failed Transmissions": f"{self.stats['failed_transmissions']} ({self.stats['failed_transmissions']/max(1,self.stats['total_readings'])*100:.1f}%)",
            "Anomalies Detected": self.stats['anomalies_detected'],
            "Network Issues": self.stats['network_issues'],
            "Total Energy Consumed": f"{self.energy_kWh:.3f} kWh",
            "Final Calibration Offset": f"{self.calibration_offset:.4f}",
            "Active Anomalies at End": len(self.active_anomalies)
        }
        
        print_box("Final Statistics", stats_data, Colors.YELLOW)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get meter statistics"""
        return {
            "meter_id": self.meter_id,
            "meter_type": self.meter_type.value,
            "sequence": self.sequence,
            "energy_kWh": self.energy_kWh,
            "calibration_offset": self.calibration_offset,
            "active_anomalies": len(self.active_anomalies),
            "stats": self.stats.copy()
        }

def main():
    parser = argparse.ArgumentParser(description="Enhanced Smart Meter Simulator")
    parser.add_argument("--meter-id", required=True, help="Meter ID")
    parser.add_argument("--meter-type", choices=["residential", "commercial", "industrial"], 
                       default="residential", help="Meter type")
    parser.add_argument("--broker", default="localhost", help="MQTT broker host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--topic", default="grid/readings", help="MQTT topic")
    parser.add_argument("--interval", type=float, default=2.0, help="Publish interval in seconds")
    
    args = parser.parse_args()
    
    # Create meter simulator
    meter_type = MeterType(args.meter_type)
    simulator = EnhancedMeterSimulator(args.meter_id, meter_type)
    
    # Configure simulator
    simulator.broker = args.broker
    simulator.port = args.port
    simulator.topic = args.topic
    simulator.publish_interval = args.interval
    
    # Start simulation
    simulator.start()

if __name__ == "__main__":
    main()