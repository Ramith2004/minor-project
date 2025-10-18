from flask import Flask, request, jsonify
from utils import verify_signature
from init_db import init_db, get_last_seq, store_reading
import requests
import os
import logging

# ---------------- CONFIG ----------------
IDS_URL = "http://127.0.0.1:5100/check"  # your running IDS
IDS_TIMEOUT = 2.0  # seconds
# ----------------------------------------

app = Flask(__name__)
init_db()

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s')

@app.route("/submitReading", methods=["POST"])
def submit_reading():
    payload = request.get_json(force=True)
    if not payload:
        return jsonify({"ok": False, "error": "empty-payload"}), 400

    # 1) verify signature
    if not verify_signature(payload):
        return jsonify({"ok": False, "error": "invalid-signature"}), 400

    meter = payload.get("meterID")
    seq = int(payload.get("seq", 0))
    last_seq = get_last_seq(meter)

    # 2) replay/seq check
    if seq <= last_seq:
        return jsonify({"ok": False, "error": "non-increasing-seq", "last_seq": last_seq}), 409

    # 3) call IDS
    suspicious = False
    reasons = []
    score = 0.0
    try:
        resp = requests.post(IDS_URL, json={"reading": payload, "last_seq": last_seq}, timeout=IDS_TIMEOUT)
        if resp.status_code == 200:
            ids_result = resp.json()
            suspicious = ids_result.get("suspicious", False)
            reasons = ids_result.get("reasons", [])
            score = ids_result.get("score", 0.0)
            if suspicious:
                logging.warning(f"Suspicious reading detected: meter={meter} seq={seq} score={score} reasons={reasons}")
        else:
            logging.warning(f"IDS returned non-200: {resp.status_code} {resp.text}")
    except requests.RequestException as e:
        logging.warning(f"IDS call failed: {e}")

    # 4) store reading anyway, but can add a 'quarantine' flag in DB if suspicious
    try:
        store_reading(payload, suspicious=suspicious, reasons=reasons, score=score)
        logging.info(f"Stored reading: meter={meter} seq={seq} suspicious={suspicious}")
    except Exception as e:
        return jsonify({"ok": False, "error": "db-error", "detail": str(e)}), 500

    return jsonify({
        "ok": True,
        "stored_seq": seq,
        "suspicious": suspicious,
        "score": score,
        "reasons": reasons
    }), 200

@app.route("/status/<meterID>", methods=["GET"])
def status(meterID):
    last = get_last_seq(meterID)
    return jsonify({"meterID": meterID, "last_seq": last})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
