#!/usr/bin/env python3
"""
Integrated IDS Microservice for Smart Meter
Combines Bayesian detection with pattern analysis
"""

from flask import Flask, request, jsonify
import json
import time
from typing import Dict, Any, Optional

# Import the sophisticated Bayesian model
from bayesian_model import BayesianModel
# Import pattern analyzer for offline analysis
from pattern_analyzer import PatternAnalyzer

app = Flask(__name__)

# Initialize models
bayesian_model = BayesianModel(db_path="ids_bayesian.db")
pattern_analyzer = PatternAnalyzer(db_path="ids_patterns.db")

# Store last readings per meter (for context)
last_readings: Dict[str, Dict[str, Any]] = {}

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
        data = request.get_json(force=True)
        reading = data.get("reading", {})
        
        # Validate required fields
        required_fields = ["meterID", "seq", "ts", "value", "signature"]
        for field in required_fields:
            if field not in reading:
                return jsonify({
                    "error": f"Missing required field: {field}",
                    "suspicious": True,
                    "score": 1.0,
                    "reasons": ["invalid-request"]
                }), 400
        
        meter_id = reading.get("meterID")
        
        # Get last reading for this meter (for context)
        last_reading = last_readings.get(meter_id)
        
        # Use Bayesian model for sophisticated detection
        result = bayesian_model.analyze_reading(reading, last_reading)
        
        # Add metadata
        result["detection_method"] = "bayesian"
        result["timestamp"] = int(time.time())
        result["meter_id"] = meter_id
        
        # Store this reading as last reading for next time
        last_readings[meter_id] = reading
        
        # Keep only last 1000 meters in memory
        if len(last_readings) > 1000:
            # Remove oldest entry
            oldest_meter = next(iter(last_readings))
            del last_readings[oldest_meter]
        
        return jsonify(result), 200
        
    except Exception as e:
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
        
        if not readings:
            return jsonify({
                "error": "No readings provided",
                "patterns": [],
                "summary": {}
            }), 400
        
        # Use pattern analyzer for historical analysis
        result = pattern_analyzer.analyze_reading_sequence(readings)
        result["meter_id"] = meter_id
        result["analysis_timestamp"] = int(time.time())
        
        return jsonify(result), 200
        
    except Exception as e:
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
        profile = bayesian_model.load_meter_profile(meter_id)
        
        if not profile:
            return jsonify({
                "error": "Profile not found",
                "meter_id": meter_id,
                "exists": False
            }), 404
        
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
        
        return jsonify({
            "total_meters": total_meters,
            "total_readings": total_readings,
            "anomaly_rate": round(anomaly_rate, 4),
            "cached_last_readings": len(last_readings),
            "timestamp": int(time.time())
        }), 200
        
    except Exception as e:
        return jsonify({
            "error": str(e),
            "timestamp": int(time.time())
        }), 500


@app.route("/", methods=["GET"])
def index():
    """
    API documentation endpoint
    """
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
    print("=" * 60)
    print("Smart Meter IDS Service v2.0")
    print("=" * 60)
    print("\nEndpoints:")
    print("  POST   http://127.0.0.1:5100/check")
    print("  POST   http://127.0.0.1:5100/analyze_patterns")
    print("  GET    http://127.0.0.1:5100/meter_profile/<meter_id>")
    print("  GET    http://127.0.0.1:5100/health")
    print("  GET    http://127.0.0.1:5100/stats")
    print("  GET    http://127.0.0.1:5100/")
    print("\nStarting server...")
    print("=" * 60)
    
    app.run(host="127.0.0.1", port=5100, debug=True)