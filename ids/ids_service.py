#!/usr/bin/env python3
"""
Simple Bayesian-style IDS microservice for smart meter demo.

POST /check
{
    "reading": {
        "meterID": "0x...",
        "seq": 123,
        "ts": 1760088405,
        "value": 12.34,
        "signature": "0x..."
    },
    "last_seq": 122
}

Returns:
{
    "suspicious": false,
    "score": 0.05,
    "reasons": []
}
"""

from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# ----- simple parameters for naive Bayesian scoring -----
MAX_VALUE_DELTA = 50.0        # large jump in reading is suspicious
MAX_SEQ_GAP = 10              # too many missing readings is suspicious
MAX_TS_DRIFT = 300            # max 5 min drift

@app.route("/check", methods=["POST"])
def check_reading():
    data = request.get_json(force=True)
    reading = data.get("reading", {})
    last_seq = data.get("last_seq", 0)

    reasons = []
    score = 0.0

    # extract values
    try:
        seq = int(reading.get("seq", 0))
        ts = int(reading.get("ts", 0))
        value = float(reading.get("value", 0))
    except Exception:
        return jsonify({"suspicious": True, "score": 1.0, "reasons": ["invalid-types"]})

    # 1) check sequence gap
    seq_gap = seq - last_seq
    if seq_gap <= 0:
        reasons.append(f"non-increasing-seq (gap={seq_gap})")
        score += 0.8  # big suspicious

    elif seq_gap > MAX_SEQ_GAP:
        reasons.append(f"large-seq-gap ({seq_gap})")
        score += 0.5

    # 2) timestamp check
    import time
    now = int(time.time())
    ts_drift = abs(now - ts)
    if ts_drift > MAX_TS_DRIFT:
        reasons.append(f"timestamp-drift ({ts_drift}s)")
        score += 0.5

    # 3) value anomaly (very simple: difference from last seq)
    # For demo, we can just flag very large values (here, > MAX_VALUE_DELTA)
    # In a real naive-Bayes: store prior readings per meter to compute conditional prob
    if abs(value) > MAX_VALUE_DELTA:
        reasons.append(f"abnormal-value ({value})")
        score += 0.5

    # clamp score [0,1]
    score = min(score, 1.0)
    suspicious = score >= 0.7

    return jsonify({
        "suspicious": suspicious,
        "score": round(score, 3),
        "reasons": reasons
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5100, debug=True)
