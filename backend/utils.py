# utils.py
# helpers: canonical JSON and signature verification (eth-account)

import json
from eth_account import Account
from eth_account.messages import encode_defunct

def canonical_json(obj: dict) -> str:
    """
    Create deterministic JSON string for signing/verifying:
    - keys sorted
    - no spaces
    """
    return json.dumps(obj, separators=(",", ":"), sort_keys=True)

def verify_signature(payload: dict) -> bool:
    """
    Expects payload to contain:
      - "signature": hex string (0x...)
      - "meterID": address string (0x...)
    Returns True if signature is valid and recovers meterID.
    """
    sig = payload.get("signature")
    if not sig:
        return False

    # copy payload without signature for canonicalization
    payload_copy = {k: payload[k] for k in payload if k != "signature"}

    canonical = canonical_json(payload_copy)
    message = encode_defunct(text=canonical)

    try:
        # recover address
        recovered = Account.recover_message(message, signature=sig)
        # addresses are case-insensitive; compare lower
        return recovered.lower() == payload.get("meterID", "").lower()
    except Exception as e:
        # verification failed
        return False
