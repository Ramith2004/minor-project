#!/usr/bin/env python3
"""
Advanced Bayesian Model for Smart Meter IDS
Implements multi-feature Bayesian classification with adaptive learning
"""

import json
import time
import math
import statistics
import sqlite3
import os
from typing import Dict, List, Tuple, Any, Optional
from collections import defaultdict, deque
import numpy as np
from dataclasses import dataclass

@dataclass
class MeterProfile:
    """Profile for a specific meter's normal behavior"""
    meter_id: str
    value_stats: Dict[str, float]  # mean, std, min, max
    timing_stats: Dict[str, float]  # mean_interval, std_interval
    sequence_stats: Dict[str, float]  # mean_gap, std_gap
    signature_patterns: Dict[str, int]  # signature characteristics
    anomaly_history: List[float]  # historical anomaly scores
    last_update: float
    sample_count: int

class BayesianModel:
    def __init__(self, db_path: str = "ids_bayesian.db"):
        self.db_path = db_path
        self.meter_profiles: Dict[str, MeterProfile] = {}
        self.global_stats = {
            "total_readings": 0,
            "anomaly_rate": 0.05,  # Expected anomaly rate
            "feature_weights": {
                "value_anomaly": 0.3,
                "timing_anomaly": 0.2,
                "sequence_anomaly": 0.25,
                "signature_anomaly": 0.15,
                "pattern_anomaly": 0.1
            }
        }
        self.feature_history = deque(maxlen=1000)  # Recent feature vectors
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database for storing profiles and statistics"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS meter_profiles (
                    meter_id TEXT PRIMARY KEY,
                    value_mean REAL,
                    value_std REAL,
                    value_min REAL,
                    value_max REAL,
                    timing_mean REAL,
                    timing_std REAL,
                    sequence_mean REAL,
                    sequence_std REAL,
                    signature_patterns TEXT,
                    anomaly_history TEXT,
                    last_update REAL,
                    sample_count INTEGER
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feature_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meter_id TEXT,
                    timestamp REAL,
                    features TEXT,
                    anomaly_score REAL,
                    is_anomaly INTEGER
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS global_stats (
                    key TEXT PRIMARY KEY,
                    value REAL
                )
            """)
    
    def load_meter_profile(self, meter_id: str) -> Optional[MeterProfile]:
        """Load meter profile from database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM meter_profiles WHERE meter_id = ?", (meter_id,)
            )
            row = cursor.fetchone()
            
            if row:
                return MeterProfile(
                    meter_id=row[0],
                    value_stats={
                        "mean": row[1], "std": row[2], "min": row[3], "max": row[4]
                    },
                    timing_stats={
                        "mean": row[5], "std": row[6]
                    },
                    sequence_stats={
                        "mean": row[7], "std": row[8]
                    },
                    signature_patterns=json.loads(row[9]) if row[9] else {},
                    anomaly_history=json.loads(row[10]) if row[10] else [],
                    last_update=row[11],
                    sample_count=row[12]
                )
        return None
    
    def save_meter_profile(self, profile: MeterProfile):
        """Save meter profile to database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO meter_profiles 
                (meter_id, value_mean, value_std, value_min, value_max,
                 timing_mean, timing_std, sequence_mean, sequence_std,
                 signature_patterns, anomaly_history, last_update, sample_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                profile.meter_id,
                profile.value_stats["mean"],
                profile.value_stats["std"],
                profile.value_stats["min"],
                profile.value_stats["max"],
                profile.timing_stats["mean"],
                profile.timing_stats["std"],
                profile.sequence_stats["mean"],
                profile.sequence_stats["std"],
                json.dumps(profile.signature_patterns),
                json.dumps(profile.anomaly_history),
                profile.last_update,
                profile.sample_count
            ))
    
    def extract_features(self, reading: Dict[str, Any], last_reading: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
        """Extract feature vector from reading"""
        features = {}
        
        # Value features
        value = float(reading.get("value", 0))
        features["value"] = value
        features["value_log"] = math.log(max(value, 0.001))  # Log transform
        
        # Timing features
        timestamp = int(reading.get("ts", 0))
        features["timestamp"] = timestamp
        features["hour_of_day"] = time.localtime(timestamp).tm_hour
        features["day_of_week"] = time.localtime(timestamp).tm_wday
        
        if last_reading:
            last_timestamp = int(last_reading.get("ts", 0))
            interval = timestamp - last_timestamp
            features["time_interval"] = interval
            features["time_interval_log"] = math.log(max(interval, 1))
        else:
            features["time_interval"] = 0
            features["time_interval_log"] = 0
        
        # Sequence features
        seq = int(reading.get("seq", 0))
        features["sequence"] = seq
        
        if last_reading:
            last_seq = int(last_reading.get("seq", 0))
            seq_gap = seq - last_seq
            features["sequence_gap"] = seq_gap
            features["sequence_gap_log"] = math.log(max(seq_gap, 1))
        else:
            features["sequence_gap"] = 0
            features["sequence_gap_log"] = 0
        
        # Signature features
        signature = reading.get("signature", "")
        features["signature_length"] = len(signature)
        features["signature_entropy"] = self.calculate_entropy(signature)
        
        # Pattern features
        features["value_change_rate"] = 0
        if last_reading:
            last_value = float(last_reading.get("value", 0))
            if last_value > 0:
                features["value_change_rate"] = (value - last_value) / last_value
        
        return features
    
    def calculate_entropy(self, text: str) -> float:
        """Calculate Shannon entropy of a string"""
        if not text:
            return 0
        
        char_counts = defaultdict(int)
        for char in text:
            char_counts[char] += 1
        
        entropy = 0
        text_len = len(text)
        for count in char_counts.values():
            p = count / text_len
            if p > 0:
                entropy -= p * math.log2(p)
        
        return entropy
    
    def calculate_anomaly_score(self, features: Dict[str, float], meter_id: str) -> Tuple[float, Dict[str, float]]:
        """Calculate Bayesian anomaly score for features"""
        profile = self.load_meter_profile(meter_id)
        
        if not profile or profile.sample_count < 10:
            # Not enough data, use global priors
            return self.calculate_global_anomaly_score(features)
        
        anomaly_scores = {}
        
        # Value anomaly score
        value_score = self.calculate_value_anomaly(features, profile)
        anomaly_scores["value_anomaly"] = value_score
        
        # Timing anomaly score
        timing_score = self.calculate_timing_anomaly(features, profile)
        anomaly_scores["timing_anomaly"] = timing_score
        
        # Sequence anomaly score
        sequence_score = self.calculate_sequence_anomaly(features, profile)
        anomaly_scores["sequence_anomaly"] = sequence_score
        
        # Signature anomaly score
        signature_score = self.calculate_signature_anomaly(features, profile)
        anomaly_scores["signature_anomaly"] = signature_score
        
        # Pattern anomaly score
        pattern_score = self.calculate_pattern_anomaly(features, profile)
        anomaly_scores["pattern_anomaly"] = pattern_score
        
        # Weighted combination
        weights = self.global_stats["feature_weights"]
        total_score = sum(anomaly_scores[feature] * weights[feature] 
                         for feature in weights.keys() 
                         if feature in anomaly_scores)
        
        return total_score, anomaly_scores
    
    def calculate_value_anomaly(self, features: Dict[str, float], profile: MeterProfile) -> float:
        """Calculate value-based anomaly score using Bayesian inference"""
        value = features["value"]
        stats = profile.value_stats
        
        # Calculate z-score
        if stats["std"] > 0:
            z_score = abs(value - stats["mean"]) / stats["std"]
        else:
            z_score = 0
        
        # Bayesian probability of anomaly given z-score
        # Using normal distribution approximation
        anomaly_prob = 2 * (1 - self.normal_cdf(z_score))
        
        return min(anomaly_prob, 1.0)
    
    def calculate_timing_anomaly(self, features: Dict[str, float], profile: MeterProfile) -> float:
        """Calculate timing-based anomaly score"""
        interval = features["time_interval"]
        stats = profile.timing_stats
        
        if interval <= 0 or stats["mean"] <= 0:
            return 0.5  # Neutral score
        
        # Check for unusual timing patterns
        if stats["std"] > 0:
            z_score = abs(interval - stats["mean"]) / stats["std"]
            anomaly_prob = 2 * (1 - self.normal_cdf(z_score))
        else:
            anomaly_prob = 0.1 if interval != stats["mean"] else 0
        
        return min(anomaly_prob, 1.0)
    
    def calculate_sequence_anomaly(self, features: Dict[str, float], profile: MeterProfile) -> float:
        """Calculate sequence-based anomaly score"""
        seq_gap = features["sequence_gap"]
        stats = profile.sequence_stats
        
        if seq_gap <= 0:
            return 0.8  # High anomaly for non-increasing sequences
        
        if stats["std"] > 0:
            z_score = abs(seq_gap - stats["mean"]) / stats["std"]
            anomaly_prob = 2 * (1 - self.normal_cdf(z_score))
        else:
            anomaly_prob = 0.1 if seq_gap != stats["mean"] else 0
        
        return min(anomaly_prob, 1.0)
    
    def calculate_signature_anomaly(self, features: Dict[str, float], profile: MeterProfile) -> float:
        """Calculate signature-based anomaly score"""
        sig_length = features["signature_length"]
        sig_entropy = features["signature_entropy"]
        
        # Check for unusual signature characteristics
        anomaly_score = 0
        
        # Length anomaly
        if sig_length < 130 or sig_length > 132:  # Expected ECDSA signature length
            anomaly_score += 0.3
        
        # Entropy anomaly
        if sig_entropy < 3.0 or sig_entropy > 4.5:  # Expected entropy range
            anomaly_score += 0.2
        
        return min(anomaly_score, 1.0)
    
    def calculate_pattern_anomaly(self, features: Dict[str, float], profile: MeterProfile) -> float:
        """Calculate pattern-based anomaly score"""
        hour = features["hour_of_day"]
        value_change = features["value_change_rate"]
        
        anomaly_score = 0
        
        # Time-based patterns
        if hour < 6 or hour > 22:  # Unusual hours
            anomaly_score += 0.2
        
        # Value change patterns
        if abs(value_change) > 0.5:  # Large value changes
            anomaly_score += 0.3
        
        return min(anomaly_score, 1.0)
    
    def calculate_global_anomaly_score(self, features: Dict[str, float]) -> Tuple[float, Dict[str, float]]:
        """Calculate anomaly score using global statistics when meter profile is unavailable"""
        anomaly_scores = {}
        
        # Simple heuristic-based scoring
        value = features["value"]
        anomaly_scores["value_anomaly"] = 0.1 if value > 1000 or value < 0 else 0
        
        interval = features["time_interval"]
        anomaly_scores["timing_anomaly"] = 0.2 if interval > 300 or interval < 0 else 0
        
        seq_gap = features["sequence_gap"]
        anomaly_scores["sequence_anomaly"] = 0.8 if seq_gap <= 0 else 0.1
        
        sig_length = features["signature_length"]
        anomaly_scores["signature_anomaly"] = 0.3 if sig_length < 130 or sig_length > 132 else 0
        
        anomaly_scores["pattern_anomaly"] = 0.1
        
        # Simple weighted average
        weights = self.global_stats["feature_weights"]
        total_score = sum(anomaly_scores[feature] * weights[feature] 
                         for feature in weights.keys() 
                         if feature in anomaly_scores)
        
        return total_score, anomaly_scores
    
    def normal_cdf(self, x: float) -> float:
        """Approximate cumulative distribution function for standard normal distribution"""
        # Using approximation: 1/2 * (1 + erf(x/sqrt(2)))
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))
    
    def update_profile(self, meter_id: str, features: Dict[str, float], anomaly_score: float):
        """Update meter profile with new data"""
        profile = self.load_meter_profile(meter_id)
        
        if not profile:
            # Create new profile
            profile = MeterProfile(
                meter_id=meter_id,
                value_stats={"mean": 0, "std": 0, "min": 0, "max": 0},
                timing_stats={"mean": 0, "std": 0},
                sequence_stats={"mean": 0, "std": 0},
                signature_patterns={},
                anomaly_history=[],
                last_update=time.time(),
                sample_count=0
            )
        
        # Update statistics using exponential moving average
        alpha = 0.1  # Learning rate
        
        # Value statistics
        value = features["value"]
        profile.value_stats["mean"] = (1 - alpha) * profile.value_stats["mean"] + alpha * value
        profile.value_stats["min"] = min(profile.value_stats["min"], value) if profile.value_stats["min"] != 0 else value
        profile.value_stats["max"] = max(profile.value_stats["max"], value)
        
        # Timing statistics
        interval = features["time_interval"]
        if interval > 0:
            profile.timing_stats["mean"] = (1 - alpha) * profile.timing_stats["mean"] + alpha * interval
        
        # Sequence statistics
        seq_gap = features["sequence_gap"]
        if seq_gap > 0:
            profile.sequence_stats["mean"] = (1 - alpha) * profile.sequence_stats["mean"] + alpha * seq_gap
        
        # Update anomaly history
        profile.anomaly_history.append(anomaly_score)
        if len(profile.anomaly_history) > 100:
            profile.anomaly_history = profile.anomaly_history[-100:]
        
        profile.sample_count += 1
        profile.last_update = time.time()
        
        # Save updated profile
        self.save_meter_profile(profile)
        
        # Store feature history
        self.store_feature_history(meter_id, features, anomaly_score)
    
    def store_feature_history(self, meter_id: str, features: Dict[str, float], anomaly_score: float):
        """Store feature vector in history"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO feature_history 
                (meter_id, timestamp, features, anomaly_score, is_anomaly)
                VALUES (?, ?, ?, ?, ?)
            """, (
                meter_id,
                time.time(),
                json.dumps(features),
                anomaly_score,
                1 if anomaly_score > 0.7 else 0
            ))
    
    def get_anomaly_threshold(self, meter_id: str) -> float:
        """Get adaptive anomaly threshold for meter"""
        profile = self.load_meter_profile(meter_id)
        
        if not profile or len(profile.anomaly_history) < 10:
            return 0.7  # Default threshold
        
        # Calculate adaptive threshold based on historical data
        recent_scores = profile.anomaly_history[-20:]  # Last 20 scores
        mean_score = statistics.mean(recent_scores)
        std_score = statistics.stdev(recent_scores) if len(recent_scores) > 1 else 0
        
        # Threshold = mean + 2*std (covers ~95% of normal data)
        threshold = mean_score + 2 * std_score
        
        return min(max(threshold, 0.3), 0.9)  # Clamp between 0.3 and 0.9
    
    def analyze_reading(self, reading: Dict[str, Any], last_reading: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Main analysis function"""
        meter_id = reading.get("meterID", "unknown")
        
        # Extract features
        features = self.extract_features(reading, last_reading)
        
        # Calculate anomaly score
        anomaly_score, feature_scores = self.calculate_anomaly_score(features, meter_id)
        
        # Get adaptive threshold
        threshold = self.get_anomaly_threshold(meter_id)
        
        # Determine if suspicious
        suspicious = anomaly_score > threshold
        
        # Update profile with new data
        self.update_profile(meter_id, features, anomaly_score)
        
        # Generate reasons
        reasons = []
        if feature_scores["value_anomaly"] > 0.5:
            reasons.append(f"value-anomaly ({feature_scores['value_anomaly']:.3f})")
        if feature_scores["timing_anomaly"] > 0.5:
            reasons.append(f"timing-anomaly ({feature_scores['timing_anomaly']:.3f})")
        if feature_scores["sequence_anomaly"] > 0.5:
            reasons.append(f"sequence-anomaly ({feature_scores['sequence_anomaly']:.3f})")
        if feature_scores["signature_anomaly"] > 0.5:
            reasons.append(f"signature-anomaly ({feature_scores['signature_anomaly']:.3f})")
        if feature_scores["pattern_anomaly"] > 0.5:
            reasons.append(f"pattern-anomaly ({feature_scores['pattern_anomaly']:.3f})")
        
        return {
            "suspicious": suspicious,
            "score": round(anomaly_score, 3),
            "threshold": round(threshold, 3),
            "reasons": reasons,
            "feature_scores": {k: round(v, 3) for k, v in feature_scores.items()},
            "confidence": self.calculate_confidence(meter_id, anomaly_score)
        }
    
    def calculate_confidence(self, meter_id: str, anomaly_score: float) -> float:
        """Calculate confidence in the anomaly detection"""
        profile = self.load_meter_profile(meter_id)
        
        if not profile or profile.sample_count < 20:
            return 0.5  # Low confidence with insufficient data
        
        # Confidence based on sample count and consistency
        sample_confidence = min(profile.sample_count / 100, 1.0)
        
        # Consistency confidence (lower variance in anomaly scores = higher confidence)
        if len(profile.anomaly_history) > 10:
            recent_scores = profile.anomaly_history[-10:]
            variance = statistics.variance(recent_scores) if len(recent_scores) > 1 else 0
            consistency_confidence = max(0, 1 - variance)
        else:
            consistency_confidence = 0.5
        
        return (sample_confidence + consistency_confidence) / 2

# Example usage and testing
if __name__ == "__main__":
    model = BayesianModel()
    
    # Test with sample reading
    test_reading = {
        "meterID": "0x1234567890abcdef",
        "seq": 1,
        "ts": int(time.time()),
        "value": 150.5,
        "signature": "0x1234567890abcdef" * 8
    }
    
    result = model.analyze_reading(test_reading)
    print("Bayesian Analysis Result:")
    print(json.dumps(result, indent=2))