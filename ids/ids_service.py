#!/usr/bin/env python3
"""
Integrated IDS Microservice for Smart Meter
Combines Bayesian detection with pattern analysis
"""

from flask import Flask, request, jsonify
import json
import time
from typing import Dict, Any, Optional
from datetime import datetime

# Import the sophisticated Bayesian model
from bayesian_model import BayesianModel
# Import pattern analyzer for offline analysis
from pattern_analyzer import PatternAnalyzer

app = Flask(__name__)

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

# Initialize models
bayesian_model = BayesianModel(db_path="ids_bayesian.db")
pattern_analyzer = PatternAnalyzer(db_path="ids_patterns.db")

# Store last readings per meter (for context)
last_readings: Dict[str, Dict[str, Any]] = {}

# Statistics tracking
request_stats = {
    "total_checks": 0,
    "anomalies_detected": 0,
    "false_positives": 0,
    "start_time": time.time()
}

@app.route("/check", methods=["POST"])
def check_reading():
    """
    Main endpoint for real-time anomaly detection
    
    POST /check
    {
        "reading": {
            "meterID": "0x...",
            "seq": 123,
            "ts": 1760088405,
            "value": 12.34,
            "signature": "0x..."
        }
    }
    
    Returns:
    {
        "suspicious": false,
        "score": 0.05,
        "threshold": 0.70,
        "confidence": 0.85,
        "reasons": [],
        "feature_scores": {...},
        "detection_method": "bayesian",
        "timestamp": 1760088405
    }
    """
    try:
        request_stats["total_checks"] += 1
        
        data = request.get_json(force=True)
        reading = data.get("reading", {})
        
        # Log incoming request
        request_data = {
            "Request Number": request_stats["total_checks"],
            "Timestamp": format_timestamp(int(time.time())),
            "Endpoint": "/check",
            "Method": "POST",
            "Client IP": request.remote_addr,
            "─── Reading Data ───": "",
            "Meter ID": reading.get("meterID", "N/A")[:20] + "...",
            "Sequence": reading.get("seq", "N/A"),
            "Value": f"{reading.get('value', 'N/A')} W",
            "Timestamp": format_timestamp(reading.get("ts", 0))
        }
        print_box(f"🔍 IDS Check Request #{request_stats['total_checks']}", request_data, Colors.CYAN)
        
        # Validate required fields
        required_fields = ["meterID", "seq", "ts", "value", "signature"]
        for field in required_fields:
            if field not in reading:
                print_error(f"Missing required field: {field}")
                return jsonify({
                    "error": f"Missing required field: {field}",
                    "suspicious": True,
                    "score": 1.0,
                    "reasons": ["invalid-request"]
                }), 400
        
        meter_id = reading.get("meterID")
        
        # Get last reading for this meter (for context)
        last_reading = last_readings.get(meter_id)
        
        print_info(f"Analyzing reading with Bayesian model...")
        
        # Use Bayesian model for sophisticated detection
        result = bayesian_model.analyze_reading(reading, last_reading)
        
        # Add metadata
        result["detection_method"] = "bayesian"
        result["timestamp"] = int(time.time())
        result["meter_id"] = meter_id
        
        # Update statistics
        if result.get("suspicious", False):
            request_stats["anomalies_detected"] += 1
        
        # Display analysis result
        result_color = Colors.RED if result.get("suspicious") else Colors.GREEN
        status_icon = "🚨 SUSPICIOUS" if result.get("suspicious") else "✓ NORMAL"
        
        analysis_data = {
            "Status": status_icon,
            "Anomaly Score": f"{result.get('score', 0):.4f}",
            "Threshold": f"{result.get('threshold', 0.7):.4f}",
            "Confidence": f"{result.get('confidence', 0):.4f}",
            "Suspicious": "YES" if result.get("suspicious") else "NO",
            "─── Feature Scores ───": "",
        }
        
        # Add feature scores
        feature_scores = result.get("feature_scores", {})
        for feature, score in feature_scores.items():
            analysis_data[f"{feature}"] = f"{score:.4f}"
        
        # Add reasons if any
        if result.get("reasons"):
            analysis_data["─── Anomaly Reasons ───"] = ""
            for i, reason in enumerate(result.get("reasons", []), 1):
                analysis_data[f"Reason {i}"] = reason
        
        print_box(f"📊 Analysis Result #{request_stats['total_checks']}", analysis_data, result_color)
        
        # Print statistics
        anomaly_rate = (request_stats["anomalies_detected"] / request_stats["total_checks"] * 100) if request_stats["total_checks"] > 0 else 0
        uptime = time.time() - request_stats["start_time"]
        
        stats_summary = f"{Colors.BOLD}IDS Stats: {Colors.END}"
        stats_summary += f"{Colors.CYAN}Total Checks: {request_stats['total_checks']}{Colors.END} | "
        stats_summary += f"{Colors.RED}Anomalies: {request_stats['anomalies_detected']}{Colors.END} | "
        stats_summary += f"{Colors.YELLOW}Anomaly Rate: {anomaly_rate:.1f}%{Colors.END} | "
        stats_summary += f"{Colors.BLUE}Uptime: {uptime:.0f}s{Colors.END}"
        
        print(f"\n{stats_summary}")
        print(f"{Colors.CYAN}{'─' * 100}{Colors.END}\n")
        
        # Store this reading as last reading for next time
        last_readings[meter_id] = reading
        
        # Keep only last 1000 meters in memory
        if len(last_readings) > 1000:
            # Remove oldest entry
            oldest_meter = next(iter(last_readings))
            del last_readings[oldest_meter]
        
        return jsonify(result), 200
        
    except Exception as e:
        print_error(f"Processing error: {e}")
        return jsonify({
            "error": str(e),
            "suspicious": True,
            "score": 1.0,
            "reasons": ["processing-error"]
        }), 500


@app.route("/analyze_patterns", methods=["POST"])
def analyze_patterns():
    """
    Endpoint for offline pattern analysis (historical data)
    
    POST /analyze_patterns
    {
        "meter_id": "0x...",
        "readings": [
            {"seq": 1, "ts": 123, "value": 100, ...},
            {"seq": 2, "ts": 456, "value": 105, ...},
            ...
        ]
    }
    
    Returns:
    {
        "patterns": [...],
        "summary": {...}
    }
    """
    try:
        data = request.get_json(force=True)
        readings = data.get("readings", [])
        meter_id = data.get("meter_id", "unknown")
        
        pattern_request_data = {
            "Timestamp": format_timestamp(int(time.time())),
            "Endpoint": "/analyze_patterns",
            "Method": "POST",
            "Meter ID": meter_id[:20] + "...",
            "Reading Count": len(readings),
            "Analysis Type": "Historical Pattern Analysis"
        }
        print_box("🔬 Pattern Analysis Request", pattern_request_data, Colors.BLUE)
        
        if not readings:
            print_error("No readings provided")
            return jsonify({
                "error": "No readings provided",
                "patterns": [],
                "summary": {}
            }), 400
        
        print_info(f"Analyzing {len(readings)} readings for patterns...")
        
        # Use pattern analyzer for historical analysis
        result = pattern_analyzer.analyze_reading_sequence(readings)
        result["meter_id"] = meter_id
        result["analysis_timestamp"] = int(time.time())
        
        # Display pattern analysis results
        pattern_data = {
            "Meter ID": meter_id[:20] + "...",
            "Readings Analyzed": len(readings),
            "Patterns Detected": len(result.get("patterns", [])),
            "Analysis Complete": format_timestamp(result["analysis_timestamp"])
        }
        
        # Add summary data
        summary = result.get("summary", {})
        if summary:
            pattern_data["─── Summary ───"] = ""
            for key, value in summary.items():
                pattern_data[key] = str(value)
        
        print_box("📈 Pattern Analysis Results", pattern_data, Colors.GREEN)
        print(f"{Colors.CYAN}{'─' * 100}{Colors.END}\n")
        
        return jsonify(result), 200
        
    except Exception as e:
        print_error(f"Pattern analysis error: {e}")
        return jsonify({
            "error": str(e),
            "patterns": [],
            "summary": {}
        }), 500


@app.route("/meter_profile/<meter_id>", methods=["GET"])
def get_meter_profile(meter_id: str):
    """
    Get learned profile for a specific meter
    
    GET /meter_profile/0x123...
    
    Returns:
    {
        "meter_id": "0x...",
        "value_stats": {...},
        "timing_stats": {...},
        "sequence_stats": {...},
        "sample_count": 100,
        "last_update": 1760088405
    }
    """
    try:
        profile_request_data = {
            "Timestamp": format_timestamp(int(time.time())),
            "Endpoint": f"/meter_profile/{meter_id[:20]}...",
            "Method": "GET",
            "Meter ID": meter_id
        }
        print_box("📋 Profile Request", profile_request_data, Colors.CYAN)
        
        profile = bayesian_model.load_meter_profile(meter_id)
        
        if not profile:
            print_warning(f"Profile not found for meter: {meter_id[:20]}...")
            return jsonify({
                "error": "Profile not found",
                "meter_id": meter_id,
                "exists": False
            }), 404
        
        # Display profile information
        profile_data = {
            "Meter ID": meter_id[:20] + "...",
            "Sample Count": profile.sample_count,
            "Last Update": format_timestamp(profile.last_update),
            "Anomaly History Size": len(profile.anomaly_history),
            "Profile Status": "ACTIVE",
            "─── Value Statistics ───": "",
        }
        
        for key, value in profile.value_stats.items():
            profile_data[f"Value {key}"] = f"{value:.2f}" if isinstance(value, float) else str(value)
        
        print_box("👤 Meter Profile", profile_data, Colors.GREEN)
        print(f"{Colors.CYAN}{'─' * 100}{Colors.END}\n")
        
        return jsonify({
            "meter_id": profile.meter_id,
            "value_stats": profile.value_stats,
            "timing_stats": profile.timing_stats,
            "sequence_stats": profile.sequence_stats,
            "sample_count": profile.sample_count,
            "last_update": profile.last_update,
            "anomaly_history_size": len(profile.anomaly_history),
            "exists": True
        }), 200
        
    except Exception as e:
        print_error(f"Profile retrieval error: {e}")
        return jsonify({
            "error": str(e),
            "meter_id": meter_id,
            "exists": False
        }), 500


@app.route("/health", methods=["GET"])
def health_check():
    """
    Health check endpoint
    
    GET /health
    
    Returns:
    {
        "status": "healthy",
        "models_loaded": true,
        "timestamp": 1760088405
    }
    """
    health_data = {
        "Status": "HEALTHY",
        "Models Loaded": "YES",
        "Bayesian Model": "LOADED",
        "Pattern Analyzer": "LOADED",
        "Uptime": f"{time.time() - request_stats['start_time']:.0f}s",
        "Total Checks": request_stats["total_checks"],
        "Timestamp": format_timestamp(int(time.time()))
    }
    print_box("❤️  Health Check", health_data, Colors.GREEN)
    
    return jsonify({
        "status": "healthy",
        "models_loaded": True,
        "bayesian_model": "loaded",
        "pattern_analyzer": "loaded",
        "timestamp": int(time.time())
    }), 200


@app.route("/stats", methods=["GET"])
def get_stats():
    """
    Get overall system statistics
    
    GET /stats
    
    Returns:
    {
        "total_meters": 100,
        "total_readings": 5000,
        "anomaly_rate": 0.05,
        "timestamp": 1760088405
    }
    """
    try:
        # Count total meters in database
        import sqlite3
        with sqlite3.connect(bayesian_model.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM meter_profiles")
            total_meters = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM feature_history")
            total_readings = cursor.fetchone()[0]
            
            cursor = conn.execute(
                "SELECT AVG(is_anomaly) FROM feature_history WHERE timestamp > ?",
                (time.time() - 86400,)  # Last 24 hours
            )
            result = cursor.fetchone()
            anomaly_rate = result[0] if result[0] else 0.0
        
        stats_data = {
            "Total Meters": total_meters,
            "Total Readings": total_readings,
            "Anomaly Rate (24h)": f"{anomaly_rate * 100:.2f}%",
            "Cached Readings": len(last_readings),
            "Total API Checks": request_stats["total_checks"],
            "Anomalies Detected": request_stats["anomalies_detected"],
            "System Uptime": f"{time.time() - request_stats['start_time']:.0f}s",
            "Timestamp": format_timestamp(int(time.time()))
        }
        print_box("📊 System Statistics", stats_data, Colors.BLUE)
        
        return jsonify({
            "total_meters": total_meters,
            "total_readings": total_readings,
            "anomaly_rate": round(anomaly_rate, 4),
            "cached_last_readings": len(last_readings),
            "timestamp": int(time.time())
        }), 200
        
    except Exception as e:
        print_error(f"Stats retrieval error: {e}")
        return jsonify({
            "error": str(e),
            "timestamp": int(time.time())
        }), 500


@app.route("/", methods=["GET"])
def index():
    """
    API documentation endpoint
    """
    doc_data = {
        "Service": "Smart Meter IDS",
        "Version": "2.0",
        "Description": "Integrated Intrusion Detection System",
        "Detection Method": "Bayesian Inference + Pattern Analysis",
        "Status": "RUNNING"
    }
    print_box("📖 API Documentation Request", doc_data, Colors.CYAN)
    
    return jsonify({
        "service": "Smart Meter IDS",
        "version": "2.0",
        "description": "Integrated Intrusion Detection System using Bayesian inference",
        "endpoints": {
            "POST /check": "Real-time anomaly detection for single reading",
            "POST /analyze_patterns": "Offline pattern analysis for historical data",
            "GET /meter_profile/<meter_id>": "Get learned profile for specific meter",
            "GET /health": "Health check",
            "GET /stats": "System statistics",
            "GET /": "This documentation"
        },
        "algorithms": {
            "real_time_detection": [
                "Z-Score Normalization",
                "Normal CDF",
                "Exponential Moving Average (EMA)",
                "Weighted Bayesian Fusion",
                "Adaptive Thresholding"
            ],
            "offline_analysis": [
                "Temporal Pattern Detection",
                "Trend Analysis (Linear Regression)",
                "Oscillation Detection"
            ]
        }
    }), 200


if __name__ == "__main__":
    print_banner("SMART METER INTRUSION DETECTION SYSTEM", Colors.CYAN)
    
    service_config = {
        "Service Name": "IDS Microservice",
        "Version": "2.0",
        "Host": "127.0.0.1",
        "Port": "5100",
        "Detection Model": "Bayesian Inference",
        "Pattern Analysis": "Enabled",
        "Database": "SQLite (ids_bayesian.db, ids_patterns.db)",
        "Status": "INITIALIZING"
    }
    print_box("Service Configuration", service_config, Colors.BLUE)
    
    print_info("Loading Bayesian model...")
    print_success("Bayesian model loaded successfully")
    
    print_info("Loading Pattern analyzer...")
    print_success("Pattern analyzer loaded successfully")
    
    endpoints_info = {
        "Real-time Check": "POST   http://127.0.0.1:5100/check",
        "Pattern Analysis": "POST   http://127.0.0.1:5100/analyze_patterns",
        "Meter Profile": "GET    http://127.0.0.1:5100/meter_profile/<meter_id>",
        "Health Check": "GET    http://127.0.0.1:5100/health",
        "Statistics": "GET    http://127.0.0.1:5100/stats",
        "Documentation": "GET    http://127.0.0.1:5100/"
    }
    print_box("Available Endpoints", endpoints_info, Colors.GREEN)
    
    print_success("IDS Service is ready to accept requests!")
    print(f"{Colors.CYAN}{'─' * 100}{Colors.END}\n")
    
    app.run(host="127.0.0.1", port=5100, debug=False)