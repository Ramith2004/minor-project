# app.py
from flask import Flask, request, jsonify
from utils import verify_signature
from init_db import init_db, get_last_seq, store_reading
import os

app = Flask(__name__)
init_db()  # ensure DB exists

@app.route("/submitReading", methods=["POST"])
def submit_reading():
    payload = request.get_json(force=True)
    if not payload:
        return jsonify({"ok": False, "error": "empty-payload"}), 400

    # 1) verify signature
    sig_ok = verify_signature(payload)
    if not sig_ok:
        return jsonify({"ok": False, "error": "invalid-signature"}), 400

    meter = payload.get("meterID")
    seq = int(payload.get("seq", 0))

    # 2) replay/seq check
    last_seq = get_last_seq(meter)
    if seq <= last_seq:
        # suspicious replay or duplicate
        return jsonify({"ok": False, "error": "non-increasing-seq", "last_seq": last_seq}), 409

    # 3) store reading
    try:
        store_reading(payload)
    except Exception as e:
        return jsonify({"ok": False, "error": "db-error", "detail": str(e)}), 500

    return jsonify({"ok": True, "stored_seq": seq}), 200

@app.route("/status/<meterID>", methods=["GET"])
def status(meterID):
    last = get_last_seq(meterID)
    return jsonify({"meterID": meterID, "last_seq": last})

if __name__ == "__main__":
    # run dev server
    app.run(host="127.0.0.1", port=5000, debug=True)
