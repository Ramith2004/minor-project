#!/usr/bin/env python3
"""
Key Manager - create, list, rotate, and manage per-meter Ethereum-style keys
"""

import os
import json
import time
import argparse
from typing import List, Dict, Optional
from eth_account import Account
from datetime import datetime

SCRIPT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
KEYS_DIR = os.path.join(PROJECT_ROOT, ".keys")
REGISTRY_PATH = os.path.join(KEYS_DIR, "registry.json")

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
    width = 80
    print(f"\n{color}{'=' * width}")
    print(f"{text.center(width)}")
    print(f"{'=' * width}{Colors.END}\n")

def print_box(title: str, content: Dict, color=Colors.GREEN):
    """Print content in a box format"""
    max_key_len = max(len(k) for k in content.keys()) if content else 0
    width = max(60, max_key_len + 40)
    
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

def _ensure_dirs():
    os.makedirs(KEYS_DIR, exist_ok=True)

def _load_registry() -> Dict:
    _ensure_dirs()
    if not os.path.exists(REGISTRY_PATH):
        return {"meters": {}, "created_at": int(time.time())}
    with open(REGISTRY_PATH, "r") as f:
        return json.load(f)

def _save_registry(reg: Dict):
    _ensure_dirs()
    with open(REGISTRY_PATH, "w") as f:
        json.dump(reg, f, indent=2)

def _keyfile_path(meter_id: str) -> str:
    return os.path.join(KEYS_DIR, f"keys_{meter_id}.json")

def generate_keypair(meter_id: str) -> Dict[str, str]:
    acct = Account.create()
    priv = acct.key.hex()
    if not priv.startswith("0x"):
        priv = "0x" + priv
    return {"meter_id": meter_id, "address": acct.address, "private_key": priv}

def save_keypair(k: Dict[str, str]):
    _ensure_dirs()
    path = _keyfile_path(k["meter_id"])
    with open(path, "w") as f:
        json.dump({"address": k["address"], "private_key": k["private_key"]}, f, indent=2)
    # Update registry
    reg = _load_registry()
    reg["meters"][k["meter_id"]] = {
        "address": k["address"],
        "keyfile": os.path.basename(path),
        "created_at": int(time.time()),
        "rotations": 0,
        "active": True
    }
    _save_registry(reg)
    return path

def load_keypair(meter_id: str) -> Optional[Dict[str, str]]:
    path = _keyfile_path(meter_id)
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        data = json.load(f)
    return {"meter_id": meter_id, "address": data["address"], "private_key": data["private_key"]}

def ensure_keys_for(meter_ids: List[str]) -> Dict[str, Dict[str, str]]:
    """Ensure a key exists for each meter ID; return dict of meter_id -> keypair"""
    out = {}
    for mid in meter_ids:
        k = load_keypair(mid)
        if not k:
            k = generate_keypair(mid)
            save_keypair(k)
        out[mid] = k
    return out

def list_meters() -> List[Dict]:
    reg = _load_registry()
    rows = []
    for mid, meta in reg.get("meters", {}).items():
        rows.append({
            "meter_id": mid,
            "address": meta.get("address"),
            "keyfile": meta.get("keyfile"),
            "active": meta.get("active", True),
            "created_at": meta.get("created_at"),
            "rotations": meta.get("rotations", 0)
        })
    rows.sort(key=lambda r: r["meter_id"])
    return rows

def rotate_key(meter_id: str) -> Dict[str, str]:
    """Rotate key for a given meter: generate a new key and replace file; keep registry history."""
    old = load_keypair(meter_id)
    k = generate_keypair(meter_id)
    path = save_keypair(k)

    # Keep a simple archive of old keys
    if old:
        archive_path = os.path.join(KEYS_DIR, f"keys_{meter_id}_{int(time.time())}_old.json")
        with open(archive_path, "w") as f:
            json.dump({"address": old["address"], "private_key": old["private_key"]}, f, indent=2)

    # bump rotations
    reg = _load_registry()
    if meter_id in reg["meters"]:
        reg["meters"][meter_id]["rotations"] = reg["meters"][meter_id].get("rotations", 0) + 1
        _save_registry(reg)

    return {"path": path, "address": k["address"], "old_address": old["address"] if old else None}

def deactivate_meter(meter_id: str) -> bool:
    reg = _load_registry()
    if meter_id in reg["meters"]:
        reg["meters"][meter_id]["active"] = False
        _save_registry(reg)
        return True
    return False

def activate_meter(meter_id: str) -> bool:
    reg = _load_registry()
    if meter_id in reg["meters"]:
        reg["meters"][meter_id]["active"] = True
        _save_registry(reg)
        return True
    return False

def remove_meter(meter_id: str, keep_keyfile: bool = True) -> bool:
    """Remove meter from registry; optionally remove keyfile."""
    reg = _load_registry()
    if meter_id not in reg["meters"]:
        return False
    keyfile = reg["meters"][meter_id].get("keyfile")
    del reg["meters"][meter_id]
    _save_registry(reg)
    if not keep_keyfile and keyfile:
        try:
            os.remove(os.path.join(KEYS_DIR, keyfile))
        except OSError:
            pass
    return True

def print_table(rows: List[Dict]):
    if not rows:
        print_warning("No meters found in registry.")
        return
    
    print_banner("REGISTERED METERS OVERVIEW", Colors.CYAN)
    
    headers = ["Meter ID", "Address", "Status", "Created", "Rotations"]
    widths = [15, 42, 10, 20, 10]
    
    # Print header
    header_line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(f"{Colors.BOLD}{header_line}{Colors.END}")
    print("─" * len(header_line))
    
    # Print rows
    for r in rows:
        status = f"{Colors.GREEN}ACTIVE{Colors.END}" if r['active'] else f"{Colors.RED}INACTIVE{Colors.END}"
        created = format_timestamp(r['created_at']) if r['created_at'] else "N/A"
        
        row_data = [
            r['meter_id'].ljust(widths[0]),
            r['address'][:40].ljust(widths[1]),
            status,
            created.ljust(widths[2]),
            str(r['rotations']).ljust(widths[3])
        ]
        print("  ".join(row_data))
    
    print(f"\n{Colors.BOLD}Total Meters: {len(rows)}{Colors.END}")
    active_count = sum(1 for r in rows if r['active'])
    print(f"{Colors.GREEN}Active: {active_count}{Colors.END} | {Colors.RED}Inactive: {len(rows) - active_count}{Colors.END}\n")

def main():
    parser = argparse.ArgumentParser(description="Key Manager for multi-meter simulation")
    sub = parser.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", help="Initialize keys for a list of meter IDs")
    p_init.add_argument("--meters", required=True, help="Comma-separated meter IDs")

    p_new = sub.add_parser("new", help="Create a new key for a meter")
    p_new.add_argument("--meter", required=True, help="Meter ID")

    p_list = sub.add_parser("list", help="List all meters/keys")

    p_rotate = sub.add_parser("rotate", help="Rotate key for a meter")
    p_rotate.add_argument("--meter", required=True, help="Meter ID")

    p_deact = sub.add_parser("deactivate", help="Deactivate a meter in registry")
    p_deact.add_argument("--meter", required=True)

    p_act = sub.add_parser("activate", help="Activate a meter in registry")
    p_act.add_argument("--meter", required=True)

    p_rm = sub.add_parser("remove", help="Remove meter from registry (optionally delete keyfile)")
    p_rm.add_argument("--meter", required=True)
    p_rm.add_argument("--delete-keyfile", action="store_true")

    args = parser.parse_args()

    if args.cmd == "init":
        print_banner("INITIALIZING METER KEYS", Colors.CYAN)
        meter_ids = [m.strip() for m in args.meters.split(",") if m.strip()]
        print_info(f"Processing {len(meter_ids)} meter(s)...")
        
        created = ensure_keys_for(meter_ids)
        
        print_success(f"Successfully initialized {len(created)} meters")
        print()
        
        for mid, k in created.items():
            print_box(f"Meter: {mid}", {
                "Address": k['address'],
                "Private Key": k['private_key'][:20] + "..." + k['private_key'][-10:],
                "Keyfile": _keyfile_path(mid),
                "Status": "ACTIVE"
            }, Colors.GREEN)
        return

    if args.cmd == "new":
        print_banner("GENERATING NEW KEY", Colors.CYAN)
        print_info(f"Creating keypair for meter: {args.meter}")
        
        k = generate_keypair(args.meter)
        path = save_keypair(k)
        
        print_success("Key generation successful!")
        print_box(f"Meter: {args.meter}", {
            "Ethereum Address": k['address'],
            "Private Key": k['private_key'][:20] + "..." + k['private_key'][-10:],
            "Full Private Key": k['private_key'],
            "Keyfile Location": path,
            "Status": "ACTIVE",
            "Created": format_timestamp(int(time.time()))
        }, Colors.GREEN)
        return

    if args.cmd == "list":
        rows = list_meters()
        print_table(rows)
        return

    if args.cmd == "rotate":
        print_banner("KEY ROTATION", Colors.YELLOW)
        print_info(f"Rotating key for meter: {args.meter}")
        
        out = rotate_key(args.meter)
        
        print_success("Key rotation successful!")
        print_box(f"Meter: {args.meter}", {
            "Old Address": out.get('old_address', 'N/A'),
            "New Address": out['address'],
            "Keyfile": out['path'],
            "Archive": f"Old key archived with timestamp"
        }, Colors.YELLOW)
        return

    if args.cmd == "deactivate":
        print_banner("DEACTIVATING METER", Colors.YELLOW)
        ok = deactivate_meter(args.meter)
        if ok:
            print_success(f"Meter '{args.meter}' deactivated successfully")
        else:
            print_error(f"Meter '{args.meter}' not found in registry")
        return

    if args.cmd == "activate":
        print_banner("ACTIVATING METER", Colors.GREEN)
        ok = activate_meter(args.meter)
        if ok:
            print_success(f"Meter '{args.meter}' activated successfully")
        else:
            print_error(f"Meter '{args.meter}' not found in registry")
        return

    if args.cmd == "remove":
        print_banner("REMOVING METER", Colors.RED)
        action = "and deleting keyfile" if args.delete_keyfile else "but keeping keyfile"
        print_info(f"Removing meter '{args.meter}' from registry {action}")
        
        ok = remove_meter(args.meter, keep_keyfile=not args.delete_keyfile)
        if ok:
            print_success(f"Meter '{args.meter}' removed successfully")
        else:
            print_error(f"Meter '{args.meter}' not found in registry")
        return

    parser.print_help()

if __name__ == "__main__":
    main()