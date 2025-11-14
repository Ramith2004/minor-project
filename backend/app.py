#!/usr/bin/env python3
"""
Enhanced Backend Application
Advanced smart meter reading validation with blockchain integration, rate limiting, forensics, and real-time SSE streaming
"""

from flask import Flask, request, jsonify, g, Response
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
from queue import Queue, Empty
from collections import defaultdict
from flask import stream_with_context
import glob
import click

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
MAX_TIMESTAMP_DRIFT = int(os.getenv("MAX_TIMESTAMP_DRIFT", "300"))
MAX_SEQUENCE_GAP = int(os.getenv("MAX_SEQUENCE_GAP", "100"))
SUSPICIOUS_SCORE_THRESHOLD = float(os.getenv("SUSPICIOUS_SCORE_THRESHOLD", "0.7"))
# ----------------------------------------

app = Flask(__name__)
CORS(app)


# ============ SSE PUB/SUB SYSTEM ============
class SSEPublisher:
    """Thread-safe SSE event publisher"""
    def __init__(self):
        self.subscribers = defaultdict(list)
        self.lock = threading.Lock()
    
    def subscribe(self, stream_name: str) -> Queue:
        q = Queue(maxsize=100)
        with self.lock:
            self.subscribers[stream_name].append(q)
        logging.info(f"New subscriber to stream: {stream_name}")
        return q
    
    def unsubscribe(self, stream_name: str, queue: Queue):
        with self.lock:
            if stream_name in self.subscribers:
                try:
                    self.subscribers[stream_name].remove(queue)
                    logging.info(f"Unsubscribed from stream: {stream_name}")
                except ValueError:
                    pass
    
    def publish(self, stream_name: str, event_type: str, data: dict):
        with self.lock:
            dead_queues = []
            for q in self.subscribers.get(stream_name, []):
                try:
                    q.put_nowait({
                        "event": event_type,
                        "data": data,
                        "timestamp": int(time.time())
                    })
                except:
                    dead_queues.append(q)
            
            for dq in dead_queues:
                try:
                    self.subscribers[stream_name].remove(dq)
                except ValueError:
                    pass
        
        logging.debug(f"Published {event_type} to {stream_name}: {len(self.subscribers.get(stream_name, []))} subscribers")

sse_publisher = SSEPublisher()
# ============================================

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
    format='[%(asctime)s] [%(levelname)s] %(message)s',
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

active_meters = set()

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
                print_warning(f"Rate limit exceeded for IP: {client_ip}")
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

@app.route("/api/stream/readings")
def stream_readings():
    def event_stream():
        q = sse_publisher.subscribe("readings")
        try:
            while True:
                try:
                    event = q.get(timeout=30)
                    yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
                except Empty:
                    # Keep connection alive
                    yield ": keep-alive\n\n"
        finally:
            sse_publisher.unsubscribe("readings", q)
    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")

@app.route("/api/stream/alerts")
def stream_alerts():
    def event_stream():
        q = sse_publisher.subscribe("alerts")
        try:
            while True:
                try:
                    event = q.get(timeout=30)
                    yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
                except Empty:
                    yield ": keep-alive\n\n"
        finally:
            sse_publisher.unsubscribe("alerts", q)
    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")

@app.route("/api/stream/meter/<meterID>")
def stream_meter(meterID):
    stream_name = f"meter_{meterID}"
    def event_stream():
        q = sse_publisher.subscribe(stream_name)
        try:
            while True:
                try:
                    event = q.get(timeout=30)
                    yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
                except Empty:
                    yield ": keep-alive\n\n"
        finally:
            sse_publisher.unsubscribe(stream_name, q)
    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")


@app.route("/stats", methods=["GET"])
def stats():
    """Return summary statistics for dashboard"""
    summary = {
        "total_readings": request_stats.get("total_requests", 0),
        "total_meters": len(active_meters),  # Replace with actual meter count if available
        "total_suspicious": request_stats.get("suspicious_readings", 0),
        "successful_requests": request_stats.get("successful_requests", 0),
        "total_requests": request_stats.get("total_requests", 0),
    }
    return jsonify(summary), 200
@app.route("/submitReading", methods=["POST"])
@track_request
@rate_limit_check
def submit_reading():
    """Enhanced reading submission with multi-layer validation and SSE notifications"""
    payload = request.get_json(force=True)
    if not payload:
        print_error("Empty payload received")
        return jsonify({"ok": False, "error": "empty-payload"}), 400
    
    meter = payload.get("meterID")
    active_meters.add(meter)

    # Display incoming request
    request_data = {
        "Request Number": request_stats["total_requests"],
        "Request ID": getattr(g, 'request_id', 'unknown'),
        "Timestamp": format_timestamp(int(time.time())),
        "Client IP": request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr),
        "─── Reading Data ───": "",
        "Meter ID": payload.get("meterID", "N/A")[:20] + "...",
        "Sequence": payload.get("seq", "N/A"),
        "Value": f"{payload.get('value', 'N/A')} W",
        "Timestamp": format_timestamp(payload.get("ts", 0)),
        "Signature": (payload.get("signature", "")[:20] + "...") if payload.get("signature") else "N/A"
    }
    print_box(f"📥 Incoming Reading #{request_stats['total_requests']}", request_data, Colors.CYAN)

    # 1) Enhanced payload validation
    is_valid, validation_error = validate_reading_payload(payload)
    if not is_valid:
        print_error(f"Invalid payload: {validation_error}")
        return jsonify({"ok": False, "error": "invalid-payload", "detail": validation_error}), 400

    meter = payload.get("meterID")
    seq = int(payload.get("seq", 0))
    timestamp = int(payload.get("ts", 0))
    value = float(payload.get("value", 0))

    # 2) Timestamp validation
    if not is_timestamp_fresh(timestamp, MAX_TIMESTAMP_DRIFT):
        print_error(f"Stale timestamp detected: {format_timestamp(timestamp)}")
        return jsonify({"ok": False, "error": "stale-timestamp"}), 400

    print_success("✓ Timestamp validation passed")

    # 3) Signature verification
    signature_valid, recovered_address = verify_signature(payload)
    if not signature_valid:
        print_error("✗ Signature verification failed")
        return jsonify({"ok": False, "error": "invalid-signature"}), 400

    print_success(f"✓ Signature verified (recovered: {recovered_address[:10]}...)")

    # 4) Sequence validation
    last_seq = get_last_seq(meter)
    if seq <= last_seq:
        print_error(f"Non-increasing sequence: {seq} <= {last_seq}")
        return jsonify({"ok": False, "error": "non-increasing-seq", "last_seq": last_seq}), 409

    if seq - last_seq > MAX_SEQUENCE_GAP:
        print_warning(f"⚠ Large sequence gap detected: {seq - last_seq}")

    print_success(f"✓ Sequence validation passed (gap: {seq - last_seq})")

    # 5) Enhanced IDS analysis
    print_info("Forwarding to IDS for analysis...")
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
            
            ids_result_data = {
                "IDS Status": "🚨 SUSPICIOUS" if suspicious else "✓ NORMAL",
                "Anomaly Score": f"{score:.4f}",
                "Confidence": f"{ids_confidence:.4f}",
                "Response Time": f"{resp.elapsed.total_seconds():.3f}s"
            }
            
            if reasons:
                ids_result_data["─── Reasons ───"] = ""
                for i, reason in enumerate(reasons, 1):
                    ids_result_data[f"Reason {i}"] = reason
            
            result_color = Colors.RED if suspicious else Colors.GREEN
            print_box("🔍 IDS Analysis Result", ids_result_data, result_color)
            
            if suspicious:
                request_stats["suspicious_readings"] += 1
        else:
            print_warning(f"IDS error: {resp.status_code}")
    except requests.RequestException as e:
        print_warning(f"IDS unavailable: {e}")

    # 6) Forensic analysis
    forensic_result = None
    if forensics:
        try:
            print_info("Running forensic analysis...")
            forensic_result = forensics.analyze_reading(payload, last_seq)
            if forensic_result.get("anomaly_detected", False):
                print_warning("⚠ Forensic anomaly detected")
                if not suspicious:
                    suspicious = True
                    score = max(score, forensic_result.get("anomaly_score", 0.5))
                    reasons.extend(forensic_result.get("anomaly_reasons", []))
        except Exception as e:
            print_error(f"Forensic analysis failed: {e}")

    # 7) Store reading with enhanced metadata
    try:
        blockchain_hash = None
        if blockchain and not suspicious:
            try:
                print_info("Storing on blockchain...")
                blockchain_hash = blockchain.store_reading_on_chain(
                    meter, seq, timestamp, int(value * 100),
                    payload.get("signature", ""), int(score * 1000), reasons
                )
                if blockchain_hash:
                    request_stats["blockchain_transactions"] += 1
                    print_success(f"✓ Stored on blockchain: {blockchain_hash[:20]}...")
            except Exception as e:
                print_error(f"Blockchain storage failed: {e}")

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
        
        print_success(f"✓ Reading stored in database")
        
    except Exception as e:
        print_error(f"Database storage failed: {e}")
        return jsonify({"ok": False, "error": "db-error", "detail": str(e)}), 500

    # 8) Enhanced response
    processing_time = time.time() - g.start_time
    response_data = {
        "ok": True,
        "stored_seq": seq,
        "suspicious": suspicious,
        "score": round(score, 3),
        "confidence": round(ids_confidence, 3),
        "reasons": reasons,
        "request_id": getattr(g, 'request_id', 'unknown'),
        "processing_time": round(processing_time, 3)
    }
    
    if blockchain_hash:
        response_data["blockchain_hash"] = blockchain_hash
    
    if forensic_result:
        response_data["forensic_analysis"] = forensic_result

    # Display final result
    final_result = {
        "Status": "🚨 SUSPICIOUS" if suspicious else "✓ ACCEPTED",
        "Stored Sequence": seq,
        "Anomaly Score": f"{score:.3f}",
        "Confidence": f"{ids_confidence:.3f}",
        "Processing Time": f"{processing_time:.3f}s",
        "Request ID": getattr(g, 'request_id', 'unknown')
    }
    
    if blockchain_hash:
        final_result["Blockchain Hash"] = blockchain_hash[:30] + "..."
    
    if reasons:
        final_result["─── Alert Reasons ───"] = ""
        for i, reason in enumerate(reasons, 1):
            final_result[f"Reason {i}"] = reason
    
    result_color = Colors.RED if suspicious else Colors.GREEN
    print_box(f"📤 Final Result #{request_stats['total_requests']}", final_result, result_color)

    # Print statistics
    success_rate = (request_stats["successful_requests"] / request_stats["total_requests"] * 100) if request_stats["total_requests"] > 0 else 0
    suspicious_rate = (request_stats["suspicious_readings"] / request_stats["total_requests"] * 100) if request_stats["total_requests"] > 0 else 0
    
    stats_summary = f"{Colors.BOLD}Backend Stats: {Colors.END}"
    stats_summary += f"{Colors.CYAN}Total: {request_stats['total_requests']}{Colors.END} | "
    stats_summary += f"{Colors.GREEN}Success: {request_stats['successful_requests']}{Colors.END} | "
    stats_summary += f"{Colors.RED}Suspicious: {request_stats['suspicious_readings']}{Colors.END} | "
    stats_summary += f"{Colors.YELLOW}Success Rate: {success_rate:.1f}%{Colors.END} | "
    stats_summary += f"{Colors.HEADER}Anomaly Rate: {suspicious_rate:.1f}%{Colors.END}"
    
    if blockchain:
        stats_summary += f" | {Colors.BLUE}BC Tx: {request_stats['blockchain_transactions']}{Colors.END}"
    
    print(f"\n{stats_summary}")
    print(f"{Colors.CYAN}{'─' * 100}{Colors.END}\n")

    # ====== SSE NOTIFICATIONS ======
    reading_event = {
        "meterID": meter,
        "meterName": get_meter_name(meter),
        "seq": seq,
        "ts": timestamp,
        "value": value,
        "suspicious": suspicious,
        "score": score,
        "reasons": reasons,
        "blockchain_hash": blockchain_hash
    }
    
    sse_publisher.publish("readings", "new_reading", reading_event)
    sse_publisher.publish(f"meter_{meter}", "new_reading", reading_event)
    
    if suspicious:
        alert_event = reading_event.copy()
        alert_event["meterName"] = get_meter_name(meter)
        sse_publisher.publish("alerts", "new_alert", alert_event)
    # ===============================

    return jsonify(response_data), 200

@app.route("/status/<meterID>", methods=["GET"])
@track_request
def status(meterID):
    """Enhanced meter status endpoint"""
    try:
        status_request = {
            "Endpoint": f"/status/{meterID[:20]}...",
            "Method": "GET",
            "Timestamp": format_timestamp(int(time.time()))
        }
        print_box("📊 Status Request", status_request, Colors.CYAN)
        
        last_seq = get_last_seq(meterID)
        recent_readings = get_reading_history(meterID, limit=10)
        
        stats = {
            "meterID": meterID,
            "last_seq": last_seq,
            "total_readings": len(recent_readings),
            "last_update": recent_readings[0].get("ts") if recent_readings else None,
            "recent_suspicious_count": sum(1 for r in recent_readings if r.get("suspicious", False)),
            "average_score": sum(r.get("score", 0) for r in recent_readings) / len(recent_readings) if recent_readings else 0
        }
        
        status_data = {
            "Meter ID": meterID[:20] + "...",
            "Last Sequence": last_seq,
            "Total Readings": len(recent_readings),
            "Recent Suspicious": sum(1 for r in recent_readings if r.get("suspicious", False)),
            "Average Score": f"{stats['average_score']:.3f}",
            "Last Update": format_timestamp(stats['last_update']) if stats['last_update'] else "Never"
        }
        print_box("📈 Meter Status", status_data, Colors.GREEN)
        
        return jsonify(stats), 200
        
    except Exception as e:
        print_error(f"Status check failed: {e}")
        return jsonify({"error": "status-check-failed", "detail": str(e)}), 500

# ... (rest of the endpoints remain the same, but add similar print_box formatting)

def get_meter_name(meter_id: str) -> str:
    """Get a readable meter name from meter ID"""
    import hashlib
    meter_hash = int(hashlib.md5(meter_id.encode()).hexdigest()[:8], 16)
    meter_num = (meter_hash % 1000) + 1
    return f"Meter {meter_num}"

@app.cli.command("reset-db")
def reset_db():
    """Delete all .db files in the project."""
    db_files = glob.glob("**/*.db", recursive=True)
    for f in db_files:
        try:
            os.remove(f)
            print(f"Deleted: {f}")
        except Exception as e:
            print(f"Failed to delete {f}: {e}")
    print("All .db files deleted.")

if __name__ == "__main__":
    print_banner("SMART METER BACKEND SERVER", Colors.CYAN)
    
    server_config = {
        "Service Name": "Backend API Server",
        "Version": "2.0.0",
        "Host": "127.0.0.1",
        "Port": "5000",
        "Threading": "Enabled",
        "─── Features ───": "",
        "IDS Integration": f"✓ {IDS_URL}",
        "Blockchain": "✓ Enabled" if BLOCKCHAIN_ENABLED else "✗ Disabled",
        "Rate Limiting": "✓ Enabled" if RATE_LIMIT_ENABLED else "✗ Disabled",
        "Forensics": "✓ Enabled" if FORENSICS_ENABLED else "✗ Disabled",
        "SSE Streaming": "✓ Enabled",
        "─── Security ───": "",
        "Max Timestamp Drift": f"{MAX_TIMESTAMP_DRIFT}s",
        "Max Sequence Gap": MAX_SEQUENCE_GAP,
        "Suspicious Threshold": SUSPICIOUS_SCORE_THRESHOLD
    }
    print_box("Server Configuration", server_config, Colors.BLUE)
    
    print_info("Initializing database...")
    init_db()
    print_success("✓ Database initialized")
    
    if blockchain:
        print_success("✓ Blockchain integration active")
    
    if rate_limiter:
        print_success(f"✓ Rate limiting active ({RATE_LIMIT_REQUESTS_PER_MINUTE} req/min)")
    
    if forensics:
        print_success("✓ Forensic analysis active")
    
    endpoints_info = {
        "Submit Reading": "POST   http://127.0.0.1:5000/submitReading",
        "Meter Status": "GET    http://127.0.0.1:5000/status/<meterID>",
        "Forensics": "GET    http://127.0.0.1:5000/forensics/<meterID>",
        "Blockchain Verify": "POST   http://127.0.0.1:5000/blockchain/verify/<meterID>/<seq>",
        "Statistics": "GET    http://127.0.0.1:5000/stats",
        "Health Check": "GET    http://127.0.0.1:5000/health",
        "─── SSE Streams ───": "",
        "All Readings": "GET    http://127.0.0.1:5000/api/stream/readings",
        "Alerts Only": "GET    http://127.0.0.1:5000/api/stream/alerts",
        "Meter Specific": "GET    http://127.0.0.1:5000/api/stream/meter/<meterID>"
    }
    print_box("Available Endpoints", endpoints_info, Colors.GREEN)
    
    print_success("Backend server is ready to accept requests!")
    print(f"{Colors.CYAN}{'─' * 100}{Colors.END}\n")
    
    logging.info("Starting enhanced backend server with SSE support...")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)