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

SCRIPT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
KEYS_DIR = os.path.join(PROJECT_ROOT, ".keys")
REGISTRY_PATH = os.path.join(KEYS_DIR, "registry.json")

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

    return {"path": path, "address": k["address"]}

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
        print("No meters found.")
        return
    headers = ["meter_id", "address", "keyfile", "active", "created_at", "rotations"]
    widths = [max(len(str(x[h])) for x in rows + [{h: h}]) for h in headers]
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    for r in rows:
        print("  ".join(str(r[h]).ljust(w) for h, w in zip(headers, widths)))

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
        meter_ids = [m.strip() for m in args.meters.split(",") if m.strip()]
        created = ensure_keys_for(meter_ids)
        print(f"Initialized/ensured {len(created)} meters.")
        for mid, k in created.items():
            print(f"- {mid}: {k['address']}")
        return

    if args.cmd == "new":
        k = generate_keypair(args.meter)
        path = save_keypair(k)
        print(f"Created key for {args.meter}: {k['address']}")
        print(f"Saved to: {path}")
        return

    if args.cmd == "list":
        rows = list_meters()
        print_table(rows)
        return

    if args.cmd == "rotate":
        out = rotate_key(args.meter)
        print(f"Rotated key for {args.meter}: new address {out['address']}")
        print(f"Saved to: {out['path']}")
        return

    if args.cmd == "deactivate":
        ok = deactivate_meter(args.meter)
        print("Deactivated." if ok else "Meter not found.")
        return

    if args.cmd == "activate":
        ok = activate_meter(args.meter)
        print("Activated." if ok else "Meter not found.")
        return

    if args.cmd == "remove":
        ok = remove_meter(args.meter, keep_keyfile=not args.delete_keyfile)
        print("Removed." if ok else "Meter not found.")
        return

    parser.print_help()

if __name__ == "__main__":
    main()