#!/usr/bin/env python3
"""
Enhanced Backend Application
Advanced smart meter reading validation with blockchain integration, rate limiting, and forensics
"""

from flask import Flask, request, jsonify, g
from flask_cors import CORS
from utils import verify_signature, validate_reading_payload, is_timestamp_fresh
from init_db import init_db, get_last_seq, store_reading, get_reading_history
from blockchain_integration import BlockchainIntegration
from rate_limiter import RateLimiter
from forensics import ForensicAnalyzer
import requests
import os
import logging
import time
import json
from datetime import datetime, timedelta
from functools import wraps
import threading

# ---------------- CONFIG ----------------
IDS_URL = os.getenv("IDS_URL", "http://127.0.0.1:5100/check")
IDS_TIMEOUT = float(os.getenv("IDS_TIMEOUT", "2.0"))
BLOCKCHAIN_ENABLED = os.getenv("BLOCKCHAIN_ENABLED", "false").lower() == "true"
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
FORENSICS_ENABLED = os.getenv("FORENSICS_ENABLED", "true").lower() == "true"

# Blockchain config
RPC_URL = os.getenv("RPC_URL", "http://localhost:8545")
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
METER_STORE_ADDRESS = os.getenv("METER_STORE_ADDRESS", "")
METER_REGISTRY_ADDRESS = os.getenv("METER_REGISTRY_ADDRESS", "")
CONSENSUS_ADDRESS = os.getenv("CONSENSUS_ADDRESS", "")

# Rate limiting config
RATE_LIMIT_REQUESTS_PER_MINUTE = int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "60"))
RATE_LIMIT_BURST_SIZE = int(os.getenv("RATE_LIMIT_BURST_SIZE", "10"))

# Security config
MAX_TIMESTAMP_DRIFT = int(os.getenv("MAX_TIMESTAMP_DRIFT", "300"))  # 5 minutes
MAX_SEQUENCE_GAP = int(os.getenv("MAX_SEQUENCE_GAP", "100"))
SUSPICIOUS_SCORE_THRESHOLD = float(os.getenv("SUSPICIOUS_SCORE_THRESHOLD", "0.7"))
# ----------------------------------------

app = Flask(__name__)
CORS(app)
init_db()

# Initialize components
blockchain = None
if BLOCKCHAIN_ENABLED and PRIVATE_KEY and METER_STORE_ADDRESS:
    try:
        blockchain = BlockchainIntegration(
            RPC_URL, PRIVATE_KEY, METER_STORE_ADDRESS,
            METER_REGISTRY_ADDRESS, CONSENSUS_ADDRESS
        )
        logging.info("Blockchain integration initialized")
    except Exception as e:
        logging.error(f"Failed to initialize blockchain: {e}")
        blockchain = None

rate_limiter = RateLimiter() if RATE_LIMIT_ENABLED else None
forensics = ForensicAnalyzer() if FORENSICS_ENABLED else None

# Enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    handlers=[
        logging.FileHandler("backend.log"),
        logging.StreamHandler()
    ]
)

# Request tracking
request_stats = {
    "total_requests": 0,
    "successful_requests": 0,
    "failed_requests": 0,
    "suspicious_readings": 0,
    "blockchain_transactions": 0,
    "rate_limited_requests": 0
}

def track_request(func):
    """Decorator to track request statistics"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        request_stats["total_requests"] += 1
        try:
            result = func(*args, **kwargs)
            if result[1] == 200:
                request_stats["successful_requests"] += 1
            else:
                request_stats["failed_requests"] += 1
            return result
        except Exception as e:
            request_stats["failed_requests"] += 1
            raise e
    return wrapper

def rate_limit_check(func):
    """Decorator for rate limiting"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if rate_limiter:
            client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
            if not rate_limiter.is_allowed(client_ip):
                request_stats["rate_limited_requests"] += 1
                return jsonify({
                    "ok": False,
                    "error": "rate-limit-exceeded",
                    "retry_after": rate_limiter.get_retry_after(client_ip)
                }), 429
        return func(*args, **kwargs)
    return wrapper

@app.before_request
def before_request():
    """Log request details"""
    g.start_time = time.time()
    g.request_id = f"{int(time.time()*1000)}_{hash(request.remote_addr)}"

@app.after_request
def after_request(response):
    """Log response details"""
    if hasattr(g, 'start_time'):
        duration = time.time() - g.start_time
        logging.info(f"Request {getattr(g, 'request_id', 'unknown')} completed in {duration:.3f}s")
    return response

@app.route("/submitReading", methods=["POST"])
@track_request
@rate_limit_check
def submit_reading():
    """Enhanced reading submission with multi-layer validation"""
    payload = request.get_json(force=True)
    if not payload:
        return jsonify({"ok": False, "error": "empty-payload"}), 400

    # 1) Enhanced payload validation
    is_valid, validation_error = validate_reading_payload(payload)
    if not is_valid:
        logging.warning(f"Invalid payload: {validation_error}")
        return jsonify({"ok": False, "error": "invalid-payload", "detail": validation_error}), 400

    meter = payload.get("meterID")
    seq = int(payload.get("seq", 0))
    timestamp = int(payload.get("ts", 0))
    value = float(payload.get("value", 0))

    # 2) Timestamp validation
    if not is_timestamp_fresh(timestamp, MAX_TIMESTAMP_DRIFT):
        logging.warning(f"Stale timestamp: meter={meter} ts={timestamp}")
        return jsonify({"ok": False, "error": "stale-timestamp"}), 400

    # 3) Signature verification
    signature_valid, recovered_address = verify_signature(payload)
    if not signature_valid:
        logging.warning(f"Invalid signature: meter={meter}")
        return jsonify({"ok": False, "error": "invalid-signature"}), 400

    # 4) Sequence validation
    last_seq = get_last_seq(meter)
    if seq <= last_seq:
        logging.warning(f"Non-increasing sequence: meter={meter} seq={seq} last_seq={last_seq}")
        return jsonify({"ok": False, "error": "non-increasing-seq", "last_seq": last_seq}), 409

    # Check for large sequence gaps
    if seq - last_seq > MAX_SEQUENCE_GAP:
        logging.warning(f"Large sequence gap: meter={meter} gap={seq - last_seq}")
        # Don't reject, but flag as suspicious

    # 5) Enhanced IDS analysis
    suspicious = False
    reasons = []
    score = 0.0
    ids_confidence = 0.0
    
    try:
        ids_payload = {
            "reading": payload,
            "last_seq": last_seq,
            "request_id": getattr(g, 'request_id', 'unknown'),
            "client_ip": request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        }
        
        resp = requests.post(IDS_URL, json=ids_payload, timeout=IDS_TIMEOUT)
        if resp.status_code == 200:
            ids_result = resp.json()
            suspicious = ids_result.get("suspicious", False)
            reasons = ids_result.get("reasons", [])
            score = ids_result.get("score", 0.0)
            ids_confidence = ids_result.get("confidence", 0.0)
            
            if suspicious:
                request_stats["suspicious_readings"] += 1
                logging.warning(f"Suspicious reading: meter={meter} seq={seq} score={score} reasons={reasons}")
        else:
            logging.warning(f"IDS error: {resp.status_code} {resp.text}")
            # Continue without IDS if it's down
    except requests.RequestException as e:
        logging.warning(f"IDS unavailable: {e}")
        # Continue without IDS if it's down

    # 6) Forensic analysis
    forensic_result = None
    if forensics:
        try:
            forensic_result = forensics.analyze_reading(payload, last_seq)
            if forensic_result.get("anomaly_detected", False):
                logging.warning(f"Forensic anomaly: meter={meter} seq={seq}")
                if not suspicious:  # If IDS didn't catch it
                    suspicious = True
                    score = max(score, forensic_result.get("anomaly_score", 0.5))
                    reasons.extend(forensic_result.get("anomaly_reasons", []))
        except Exception as e:
            logging.error(f"Forensic analysis failed: {e}")

    # 7) Store reading with enhanced metadata
    try:
        blockchain_hash = None
        if blockchain and not suspicious:  # Only store non-suspicious readings on blockchain
            try:
                blockchain_hash = blockchain.store_reading_on_chain(
                    meter, seq, timestamp, int(value * 100),  # Convert to integer (wei-like)
                    payload.get("signature", ""), int(score * 1000), reasons
                )
                if blockchain_hash:
                    request_stats["blockchain_transactions"] += 1
                    logging.info(f"Stored on blockchain: {blockchain_hash}")
            except Exception as e:
                logging.error(f"Blockchain storage failed: {e}")
                # Continue without blockchain storage

        store_reading(
            payload, 
            suspicious=suspicious, 
            reasons=reasons, 
            score=score,
            blockchain_hash=blockchain_hash,
            ids_confidence=ids_confidence,
            forensic_result=forensic_result,
            request_id=getattr(g, 'request_id', 'unknown')
        )
        
        logging.info(f"Stored reading: meter={meter} seq={seq} suspicious={suspicious} score={score}")
        
    except Exception as e:
        logging.error(f"Database storage failed: {e}")
        return jsonify({"ok": False, "error": "db-error", "detail": str(e)}), 500

    # 8) Enhanced response
    response_data = {
        "ok": True,
        "stored_seq": seq,
        "suspicious": suspicious,
        "score": round(score, 3),
        "confidence": round(ids_confidence, 3),
        "reasons": reasons,
        "request_id": getattr(g, 'request_id', 'unknown'),
        "processing_time": round(time.time() - g.start_time, 3)
    }
    
    if blockchain_hash:
        response_data["blockchain_hash"] = blockchain_hash
    
    if forensic_result:
        response_data["forensic_analysis"] = forensic_result

    return jsonify(response_data), 200

@app.route("/status/<meterID>", methods=["GET"])
@track_request
def status(meterID):
    """Enhanced meter status endpoint"""
    try:
        last_seq = get_last_seq(meterID)
        
        # Get recent reading history
        recent_readings = get_reading_history(meterID, limit=10)
        
        # Calculate statistics
        stats = {
            "meterID": meterID,
            "last_seq": last_seq,
            "total_readings": len(recent_readings),
            "last_update": recent_readings[0].get("ts") if recent_readings else None,
            "recent_suspicious_count": sum(1 for r in recent_readings if r.get("suspicious", False)),
            "average_score": sum(r.get("score", 0) for r in recent_readings) / len(recent_readings) if recent_readings else 0
        }
        
        return jsonify(stats), 200
        
    except Exception as e:
        logging.error(f"Status check failed for {meterID}: {e}")
        return jsonify({"error": "status-check-failed", "detail": str(e)}), 500

@app.route("/forensics/<meterID>", methods=["GET"])
@track_request
def get_forensics(meterID):
    """Get forensic analysis for a meter"""
    if not forensics:
        return jsonify({"error": "forensics-not-enabled"}), 503
    
    try:
        analysis = forensics.get_meter_analysis(meterID)
        return jsonify(analysis), 200
    except Exception as e:
        logging.error(f"Forensics analysis failed for {meterID}: {e}")
        return jsonify({"error": "forensics-failed", "detail": str(e)}), 500

@app.route("/blockchain/verify/<meterID>/<int:sequence>", methods=["POST"])
@track_request
def verify_on_blockchain(meterID, sequence):
    """Verify a reading on blockchain"""
    if not blockchain:
        return jsonify({"error": "blockchain-not-enabled"}), 503
    
    try:
        verified = request.json.get("verified", True)
        tx_hash = blockchain.verify_reading(meterID, sequence, verified)
        
        if tx_hash:
            return jsonify({
                "ok": True,
                "transaction_hash": tx_hash,
                "verified": verified
            }), 200
        else:
            return jsonify({"ok": False, "error": "verification-failed"}), 500
            
    except Exception as e:
        logging.error(f"Blockchain verification failed: {e}")
        return jsonify({"error": "verification-failed", "detail": str(e)}), 500

@app.route("/stats", methods=["GET"])
@track_request
def get_stats():
    """Get system statistics"""
    stats = request_stats.copy()
    
    # Add component status
    stats["components"] = {
        "blockchain": blockchain is not None,
        "rate_limiter": rate_limiter is not None,
        "forensics": forensics is not None,
        "ids": True  # Assume IDS is running if we're running
    }
    
    # Add rate limiter stats if available
    if rate_limiter:
        stats["rate_limiter_stats"] = rate_limiter.get_stats()
    
    return jsonify(stats), 200

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    health_status = {
        "status": "healthy",
        "timestamp": int(time.time()),
        "version": "2.0.0",
        "components": {
            "database": True,
            "ids": True,
            "blockchain": blockchain is not None,
            "rate_limiter": rate_limiter is not None,
            "forensics": forensics is not None
        }
    }
    
    # Check IDS health
    try:
        resp = requests.get(f"{IDS_URL.replace('/check', '/health')}", timeout=1)
        health_status["components"]["ids"] = resp.status_code == 200
    except:
        health_status["components"]["ids"] = False
    
    # Check blockchain health
    if blockchain:
        try:
            health_status["components"]["blockchain"] = blockchain.is_healthy()
        except:
            health_status["components"]["blockchain"] = False
    
    # Overall health
    if not all(health_status["components"].values()):
        health_status["status"] = "degraded"
    
    return jsonify(health_status), 200


# ========== DASHBOARD ENDPOINTS ==========

@app.route("/api/dashboard/readings", methods=["GET"])
@track_request
def get_readings():
    """Get paginated readings with filters"""
    from init_db import list_readings
    
    meterID = request.args.get("meterID")
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    ts_from = request.args.get("ts_from", type=int)
    ts_to = request.args.get("ts_to", type=int)
    
    try:
        readings = list_readings(meterID, limit, offset, ts_from, ts_to)
        return jsonify({
            "ok": True,
            "readings": readings,
            "count": len(readings),
            "offset": offset,
            "limit": limit
        }), 200
    except Exception as e:
        logging.error(f"Failed to get readings: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/dashboard/alerts", methods=["GET"])
@track_request
def get_alerts():
    """Get suspicious readings (alerts)"""
    from init_db import list_alerts
    
    meterID = request.args.get("meterID")
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    min_score = float(request.args.get("min_score", 0.0))
    ts_from = request.args.get("ts_from", type=int)
    ts_to = request.args.get("ts_to", type=int)
    
    try:
        alerts = list_alerts(limit, offset, meterID, min_score, ts_from, ts_to)
        return jsonify({
            "ok": True,
            "alerts": alerts,
            "count": len(alerts),
            "offset": offset,
            "limit": limit
        }), 200
    except Exception as e:
        logging.error(f"Failed to get alerts: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/dashboard/meters", methods=["GET"])
@track_request
def get_meters():
    """Get all meters with summary statistics"""
    from init_db import list_meters
    
    try:
        meters = list_meters()
        return jsonify({
            "ok": True,
            "meters": meters,
            "count": len(meters)
        }), 200
    except Exception as e:
        logging.error(f"Failed to get meters: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/dashboard/meters/<meterID>", methods=["GET"])
@track_request
def get_meter_detail(meterID):
    """Get detailed meter information"""
    from init_db import get_meter_details, get_reading_history
    
    try:
        details = get_meter_details(meterID)
        if not details:
            return jsonify({"ok": False, "error": "meter-not-found"}), 404
        
        # Add recent readings
        recent = get_reading_history(meterID, limit=20)
        details["recent_readings"] = recent
        
        return jsonify({
            "ok": True,
            "meter": details
        }), 200
    except Exception as e:
        logging.error(f"Failed to get meter details: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/dashboard/latest", methods=["GET"])
@track_request
def get_latest():
    """Get latest readings across all meters"""
    from init_db import get_latest_readings
    
    limit = int(request.args.get("limit", 20))
    
    try:
        readings = get_latest_readings(limit)
        return jsonify({
            "ok": True,
            "readings": readings,
            "count": len(readings)
        }), 200
    except Exception as e:
        logging.error(f"Failed to get latest readings: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/dashboard/summary", methods=["GET"])
@track_request
def get_summary():
    """Get dashboard summary statistics"""
    from init_db import list_meters, list_alerts
    import sqlite3
    
    try:
        # Get overall stats
        with sqlite3.connect(init_db.DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM readings")
            total_readings = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM readings WHERE suspicious=1")
            total_suspicious = c.fetchone()[0]
            
            c.execute("SELECT COUNT(DISTINCT meterID) FROM readings")
            total_meters = c.fetchone()[0]
            
            c.execute("SELECT AVG(score) FROM readings WHERE suspicious=1")
            avg_suspicious_score = c.fetchone()[0] or 0
        
        # Get recent alerts
        recent_alerts = list_alerts(limit=5)
        
        return jsonify({
            "ok": True,
            "summary": {
                "total_readings": total_readings,
                "total_suspicious": total_suspicious,
                "total_meters": total_meters,
                "suspicious_percentage": round((total_suspicious / total_readings * 100) if total_readings > 0 else 0, 2),
                "avg_suspicious_score": round(avg_suspicious_score, 3),
                "recent_alerts": recent_alerts,
                **request_stats
            }
        }), 200
    except Exception as e:
        logging.error(f"Failed to get summary: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "endpoint-not-found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logging.error(f"Internal server error: {error}")
    return jsonify({"error": "internal-server-error"}), 500

if __name__ == "__main__":
    logging.info("Starting enhanced backend server...")
    logging.info(f"Blockchain enabled: {BLOCKCHAIN_ENABLED}")
    logging.info(f"Rate limiting enabled: {RATE_LIMIT_ENABLED}")
    logging.info(f"Forensics enabled: {FORENSICS_ENABLED}")
    
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)