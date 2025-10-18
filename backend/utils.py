# backend/utils.py
"""
Helpers: canonical JSON, signature verification, payload validation, timestamp check, IDS call.
Uses eth-account for Ethereum-style message signing.
"""
import json
import time
import logging
import os
from typing import Tuple, Dict, Any, Optional

import requests
from eth_account import Account
from eth_account.messages import encode_defunct

logger = logging.getLogger(__name__)

# Config
DEFAULT_MAX_TS_AGE = int(os.getenv("MAX_TIMESTAMP_AGE", "300"))  # seconds (5 minutes)
IDS_URL = os.getenv("IDS_URL", "http://127.0.0.1:5100/check")
IDS_TIMEOUT = float(os.getenv("IDS_TIMEOUT", "0.5"))  # seconds

def canonical_json(obj: dict) -> str:
    """
    Produce deterministic JSON text for signing / verification:
      - keys sorted
      - no spaces
      - stable ordering of nested dicts (via sort_keys=True)
    """
    return json.dumps(obj, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def _payload_for_signing(payload: dict) -> dict:
    """Return a shallow copy of payload excluding 'signature' for canonicalization"""
    return {k: payload[k] for k in payload if k != "signature"}


def verify_signature(payload: dict) -> Tuple[bool, Optional[str]]:
    """
    Verify Ethereum-style signature.

    Returns (ok, recovered_address or None)
    - payload must contain 'signature' and 'meterID' (address)
    - signature must be hex string (0x...)
    """
    sig = payload.get("signature")
    meter = payload.get("meterID", "")

    if not sig or not meter:
        logger.debug("verify_signature: missing signature or meterID")
        return False, None

    try:
        payload_copy = _payload_for_signing(payload)
        canonical = canonical_json(payload_copy)
        message = encode_defunct(text=canonical)
        recovered = Account.recover_message(message, signature=sig)
        # compare lowercase checksum-insensitive
        if recovered.lower() == meter.lower():
            return True, recovered
        else:
            logger.debug("verify_signature: recovered != meter (recovered=%s, claimed=%s)", recovered, meter)
            return False, recovered
    except Exception as e:
        logger.exception("verify_signature: exception during verification: %s", e)
        return False, None


def validate_reading_payload(payload: dict) -> Tuple[bool, str]:
    """
    Basic payload validation - types and presence.
    Returns (ok, reason_message)
    Expected fields:
      - meterID (str)
      - seq (int)
      - ts (int)
      - value (int/float)
      - signature (hex str)
    """
    if not isinstance(payload, dict):
        return False, "payload-not-dict"

    required = ("meterID", "seq", "ts", "value", "signature")
    for k in required:
        if k not in payload:
            return False, f"missing-{k}"

    # types
    try:
        seq = int(payload["seq"])
    except Exception:
        return False, "invalid-seq"

    try:
        ts = int(payload["ts"])
    except Exception:
        return False, "invalid-ts"

    try:
        # allow float or int
        float(payload["value"])
    except Exception:
        return False, "invalid-value"

    # signature basic check
    sig = payload.get("signature")
    if not isinstance(sig, str) or not sig.startswith("0x"):
        return False, "invalid-signature-format"

    return True, "ok"


def is_timestamp_fresh(ts: int, max_age_seconds: int = DEFAULT_MAX_TS_AGE) -> bool:
    """
    Check whether reading timestamp is not too old (or far in future).
    Accept if now - ts <= max_age_seconds and ts not far in future (>60s)
    """
    now = int(time.time())
    if ts < now - max_age_seconds:
        return False
    if ts > now + 60:
        # future timestamp beyond tolerance
        return False
    return True


def call_ids(payload: dict, last_seq: int) -> Dict[str, Any]:
    """
    Call external IDS microservice (synchronous, lightweight).
    The IDS should accept JSON with payload and last_seq (for context).
    Returns IDS response dict: expected keys {suspicious, score, reasons}
    On any error, returns a conservative default (low suspicion).
    """
    data = {
        "reading": payload,
        "last_seq": last_seq
    }
    try:
        resp = requests.post(IDS_URL, json=data, timeout=IDS_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        else:
            logger.warning("IDS returned non-200: %s %s", resp.status_code, resp.text)
            return {"suspicious": False, "score": 0.0, "reasons": ["ids-unavailable-non200"]}
    except requests.RequestException as e:
        logger.warning("IDS call failed: %s", e)
        return {"suspicious": False, "score": 0.0, "reasons": ["ids-unavailable-exception"]}
