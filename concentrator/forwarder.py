#!/usr/bin/env python3
"""
MQTT to Backend Forwarder
Subscribes to MQTT broker and forwards meter readings to backend API
"""

import json
import time
from datetime import datetime
import paho.mqtt.client as mqtt
import requests

# Configuration
BROKER = "localhost"
BROKER_PORT = 1883
TOPIC = "grid/readings"
BACKEND_URL = "http://127.0.0.1:5000/submitReading"

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
        # Handle long values
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

# Statistics tracking
stats = {
    "total_received": 0,
    "total_forwarded": 0,
    "total_failed": 0,
    "start_time": time.time()
}

def on_connect(client, userdata, flags, rc):
    """MQTT connection callback"""
    print_banner("MQTT TO BACKEND FORWARDER", Colors.CYAN)
    
    if rc == 0:
        print_success(f"Connected to MQTT broker at {BROKER}:{BROKER_PORT}")
        client.subscribe(TOPIC)
        print_success(f"Subscribed to topic: {TOPIC}")
        
        config_data = {
            "MQTT Broker": f"{BROKER}:{BROKER_PORT}",
            "MQTT Topic": TOPIC,
            "Backend URL": BACKEND_URL,
            "Status": "ACTIVE",
            "Started At": format_timestamp(int(stats["start_time"]))
        }
        print_box("Forwarder Configuration", config_data, Colors.BLUE)
        
        print_info("Waiting for meter readings...")
        print(f"{Colors.CYAN}{'─' * 100}{Colors.END}\n")
    else:
        print_error(f"Failed to connect to MQTT broker (code: {rc})")

def on_disconnect(client, userdata, rc):
    """MQTT disconnection callback"""
    if rc != 0:
        print_warning(f"Unexpected disconnection from MQTT broker (code: {rc})")

def on_message(client, userdata, msg):
    """MQTT message callback"""
    try:
        stats["total_received"] += 1
        
        # Parse MQTT payload
        payload = json.loads(msg.payload.decode())
        
        # Display received reading
        received_data = {
            "Message Number": stats["total_received"],
            "Received At": format_timestamp(int(time.time())),
            "Topic": msg.topic,
            "─── MQTT Payload ───": "",
            "Meter ID": payload.get("meterID", "N/A"),
            "Sequence": payload.get("seq", "N/A"),
            "Timestamp": format_timestamp(payload.get("ts", 0)),
            "Power Value": f"{payload.get('value', 0)} W",
            "Signature": (payload.get("signature", "")[:30] + "..." + payload.get("signature", "")[-30:]) if payload.get("signature") else "N/A"
        }
        print_box(f"📥 Received Reading #{stats['total_received']}", received_data, Colors.CYAN)

        # Flatten payload for backend
        simplified_payload = {
            "meterID": payload.get("meterID"),
            "seq": payload.get("seq"),
            "ts": payload.get("ts"),
            "value": payload.get("value"),
            "signature": payload.get("signature")
        }

        print_info(f"Forwarding to backend: {BACKEND_URL}")
        
        # Forward to backend
        res = requests.post(BACKEND_URL, json=simplified_payload, timeout=5)
        
        # Display backend response
        if res.status_code == 200:
            stats["total_forwarded"] += 1
            
            try:
                response_data = res.json()
            except:
                response_data = {"raw_response": res.text}
            
            backend_data = {
                "Status Code": f"{res.status_code} OK",
                "Response Time": f"{res.elapsed.total_seconds():.3f}s",
                "─── Backend Response ───": "",
            }
            
            # Add response data
            if isinstance(response_data, dict):
                for key, value in response_data.items():
                    backend_data[key] = value
            else:
                backend_data["Response"] = str(response_data)
            
            print_box(f"📤 Backend Response #{stats['total_forwarded']}", backend_data, Colors.GREEN)
            print_success(f"Successfully forwarded reading #{stats['total_received']} to backend")
            
        else:
            stats["total_failed"] += 1
            error_data = {
                "Status Code": f"{res.status_code} ERROR",
                "Response Time": f"{res.elapsed.total_seconds():.3f}s",
                "Error Message": res.text[:200] if res.text else "No error message"
            }
            print_box(f"❌ Backend Error #{stats['total_failed']}", error_data, Colors.RED)
            print_error(f"Failed to forward reading #{stats['total_received']} (HTTP {res.status_code})")

        # Print statistics
        success_rate = (stats["total_forwarded"] / stats["total_received"] * 100) if stats["total_received"] > 0 else 0
        uptime = time.time() - stats["start_time"]
        
        stats_summary = f"{Colors.BOLD}Stats: {Colors.END}"
        stats_summary += f"{Colors.CYAN}Received: {stats['total_received']}{Colors.END} | "
        stats_summary += f"{Colors.GREEN}Forwarded: {stats['total_forwarded']}{Colors.END} | "
        stats_summary += f"{Colors.RED}Failed: {stats['total_failed']}{Colors.END} | "
        stats_summary += f"{Colors.YELLOW}Success Rate: {success_rate:.1f}%{Colors.END} | "
        stats_summary += f"{Colors.BLUE}Uptime: {uptime:.0f}s{Colors.END}"
        
        print(f"\n{stats_summary}")
        print(f"{Colors.CYAN}{'─' * 100}{Colors.END}\n")

    except json.JSONDecodeError as e:
        stats["total_failed"] += 1
        print_error(f"Failed to parse MQTT message: {e}")
        print(f"Raw payload: {msg.payload.decode()}\n")
        
    except requests.exceptions.RequestException as e:
        stats["total_failed"] += 1
        print_error(f"Failed to forward to backend: {e}")
        error_data = {
            "Error Type": type(e).__name__,
            "Error Message": str(e),
            "Backend URL": BACKEND_URL
        }
        print_box("❌ Network Error", error_data, Colors.RED)
        print(f"{Colors.CYAN}{'─' * 100}{Colors.END}\n")
        
    except Exception as e:
        stats["total_failed"] += 1
        print_error(f"Unexpected error processing message: {e}")
        print(f"{Colors.CYAN}{'─' * 100}{Colors.END}\n")

def print_shutdown_stats():
    """Print final statistics on shutdown"""
    print_banner("FORWARDER SHUTDOWN - FINAL STATISTICS", Colors.YELLOW)
    
    uptime = time.time() - stats["start_time"]
    success_rate = (stats["total_forwarded"] / stats["total_received"] * 100) if stats["total_received"] > 0 else 0
    
    final_stats = {
        "Total Uptime": f"{uptime:.0f} seconds ({uptime/60:.1f} minutes)",
        "Total Messages Received": stats["total_received"],
        "Successfully Forwarded": f"{stats['total_forwarded']} ({success_rate:.1f}%)",
        "Failed Forwards": f"{stats['total_failed']} ({100-success_rate:.1f}%)",
        "Average Rate": f"{stats['total_received']/(uptime/60):.2f} msg/min" if uptime > 0 else "N/A",
        "MQTT Broker": f"{BROKER}:{BROKER_PORT}",
        "Backend URL": BACKEND_URL,
        "Shutdown Time": format_timestamp(int(time.time()))
    }
    
    print_box("Final Statistics", final_stats, Colors.YELLOW)

def main():
    """Main forwarder loop"""
    # Create MQTT client
    client = mqtt.Client(client_id="grid_forwarder", callback_api_version=mqtt.CallbackAPIVersion.VERSION1)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    try:
        print_info(f"Connecting to MQTT broker at {BROKER}:{BROKER_PORT}...")
        client.connect(BROKER, BROKER_PORT, 60)
        client.loop_forever()
    except KeyboardInterrupt:
        print_warning("\nShutdown requested by user...")
    except Exception as e:
        print_error(f"Fatal error: {e}")
    finally:
        client.disconnect()
        print_shutdown_stats()

if __name__ == "__main__":
    main()