# generate_keys.py
# Usage: python generate_keys.py
# Generates an ephemeral eth-style keypair and saves to ../.keys/keys.json

import json
import os
from eth_account import Account

def main():
    # create .keys dir relative to project root
    script_dir = os.path.dirname(__file__)
    keys_dir = os.path.abspath(os.path.join(script_dir, "..", ".keys"))
    os.makedirs(keys_dir, exist_ok=True)

    acct = Account.create()  # generates a new private key & address
    priv = acct.key.hex()
    if not priv.startswith("0x"):
        priv = "0x" + priv

    data = {
        "address": acct.address,
        "private_key": priv
    }

    out_path = os.path.join(keys_dir, "keys.json")
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)

    print("Generated address:", data["address"])
    print("Saved key file to:", out_path)
    print("WARNING: This private key is stored in plaintext for dev use only. Do not commit to git.")

if __name__ == "__main__":
    main()
