#!/usr/bin/env python3
"""
Advanced Ensemble Detector for Smart Meter IDS
Combines multiple detection algorithms with voting and confidence mechanisms
"""

import json
import time
import math
import statistics
import sqlite3
import os
from typing import Dict, List, Tuple, Any, Optional, Union
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import Enum
import numpy as np

class DetectorType(Enum):
    BAYESIAN = "bayesian"
    PATTERN = "pattern"
    STATISTICAL = "statistical"
    SIGNATURE = "signature"
    TEMPORAL = "temporal"
    SEQUENCE = "sequence"

@dataclass
class DetectionResult:
    detector_type: DetectorType
    suspicious: bool
    score: float
    confidence: float
    reasons: List[str]
    metadata: Dict[str, Any]
    timestamp: float

@dataclass
class EnsembleResult:
    suspicious: bool
    overall_score: float
    confidence: float
    detector_results: List[DetectionResult]
    consensus_score: float
    voting_result: Dict[str, Any]
    final_reasons: List[str]

class StatisticalDetector:
    """Statistical anomaly detection using z-scores and percentiles"""
    
    def __init__(self):
        self.name = "Statistical Detector"
        self.history = deque(maxlen=1000)
    
    def detect(self, reading: Dict[str, Any], meter_id: str) -> DetectionResult:
        """Detect anomalies using statistical methods"""
        reasons = []
        score = 0.0
        
        # Extract features
        value = float(reading.get("value", 0))
        timestamp = int(reading.get("ts", 0))
        sequence = int(reading.get("seq", 0))
        
        # Value-based detection
        if len(self.history) > 10:
            values = [h["value"] for h in self.history]
            mean_val = statistics.mean(values)
            std_val = statistics.stdev(values) if len(values) > 1 else 0
            
            if std_val > 0:
                z_score = abs(value - mean_val) / std_val
                if z_score > 3:  # 3-sigma rule
                    reasons.append(f"value-outlier (z-score: {z_score:.2f})")
                    score += min(z_score / 3, 1.0) * 0.4
        
        # Timing-based detection
        if len(self.history) > 5:
            timestamps = [h["timestamp"] for h in self.history]
            intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
            
            if intervals:
                mean_interval = statistics.mean(intervals)
                std_interval = statistics.stdev(intervals) if len(intervals) > 1 else 0
                
                if std_interval > 0:
                    current_interval = timestamp - timestamps[-1] if timestamps else 0
                    z_score = abs(current_interval - mean_interval) / std_interval
                    if z_score > 2:
                        reasons.append(f"timing-anomaly (z-score: {z_score:.2f})")
                        score += min(z_score / 2, 1.0) * 0.3
        
        # Sequence-based detection
        if len(self.history) > 0:
            last_seq = self.history[-1]["sequence"]
            seq_gap = sequence - last_seq
            
            if seq_gap <= 0:
                reasons.append("non-increasing-sequence")
                score += 0.8
            elif seq_gap > 10:
                reasons.append(f"large-sequence-gap ({seq_gap})")
                score += min(seq_gap / 20, 1.0) * 0.3
        
        # Update history
        self.history.append({
            "value": value,
            "timestamp": timestamp,
            "sequence": sequence,
            "meter_id": meter_id
        })
        
        suspicious = score > 0.5
        confidence = min(len(self.history) / 50, 1.0)  # Confidence based on history size
        
        return DetectionResult(
            detector_type=DetectorType.STATISTICAL,
            suspicious=suspicious,
            score=min(score, 1.0),
            confidence=confidence,
            reasons=reasons,
            metadata={"history_size": len(self.history)},
            timestamp=time.time()
        )

class SignatureDetector:
    """Signature-based anomaly detection"""
    
    def __init__(self):
        self.name = "Signature Detector"
        self.signature_patterns = defaultdict(list)
    
    def detect(self, reading: Dict[str, Any], meter_id: str) -> DetectionResult:
        """Detect signature-based anomalies"""
        reasons = []
        score = 0.0
        
        signature = reading.get("signature", "")
        
        # Length validation
        if len(signature) < 130 or len(signature) > 132:
            reasons.append(f"invalid-signature-length ({len(signature)})")
            score += 0.6
        
        # Format validation
        if not signature.startswith("0x"):
            reasons.append("invalid-signature-format")
            score += 0.5
        
        # Entropy check
        entropy = self.calculate_entropy(signature)
        if entropy < 3.0 or entropy > 4.5:
            reasons.append(f"unusual-signature-entropy ({entropy:.2f})")
            score += 0.3
        
        # Signature reuse detection
        if signature in self.signature_patterns[meter_id]:
            reasons.append("signature-reuse")
            score += 0.7
        
        # Update patterns
        self.signature_patterns[meter_id].append(signature)
        if len(self.signature_patterns[meter_id]) > 100:
            self.signature_patterns[meter_id] = self.signature_patterns[meter_id][-100:]
        
        suspicious = score > 0.4
        confidence = 0.8  # High confidence for signature validation
        
        return DetectionResult(
            detector_type=DetectorType.SIGNATURE,
            suspicious=suspicious,
            score=min(score, 1.0),
            confidence=confidence,
            reasons=reasons,
            metadata={"entropy": entropy, "length": len(signature)},
            timestamp=time.time()
        )
    
    def calculate_entropy(self, text: str) -> float:
        """Calculate Shannon entropy"""
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

class TemporalDetector:
    """Temporal pattern-based anomaly detection"""
    
    def __init__(self):
        self.name = "Temporal Detector"
        self.meter_patterns = defaultdict(lambda: {
            "hourly_values": defaultdict(list),
            "daily_values": defaultdict(list),
            "intervals": deque(maxlen=100)
        })
    
    def detect(self, reading: Dict[str, Any], meter_id: str) -> DetectionResult:
        """Detect temporal anomalies"""
        reasons = []
        score = 0.0
        
        value = float(reading.get("value", 0))
        timestamp = int(reading.get("ts", 0))
        
        # Extract time components
        time_struct = time.localtime(timestamp)
        hour = time_struct.tm_hour
        day = time_struct.tm_wday
        
        patterns = self.meter_patterns[meter_id]
        
        # Hourly pattern analysis
        patterns["hourly_values"][hour].append(value)
        if len(patterns["hourly_values"][hour]) > 50:
            patterns["hourly_values"][hour] = patterns["hourly_values"][hour][-50:]
        
        # Check for unusual hourly values
        if len(patterns["hourly_values"][hour]) > 5:
            hourly_values = patterns["hourly_values"][hour]
            mean_hourly = statistics.mean(hourly_values)
            std_hourly = statistics.stdev(hourly_values) if len(hourly_values) > 1 else 0
            
            if std_hourly > 0:
                z_score = abs(value - mean_hourly) / std_hourly
                if z_score > 2:
                    reasons.append(f"unusual-hourly-value (hour {hour}, z-score: {z_score:.2f})")
                    score += min(z_score / 2, 1.0) * 0.4
        
        # Daily pattern analysis
        patterns["daily_values"][day].append(value)
        if len(patterns["daily_values"][day]) > 50:
            patterns["daily_values"][day] = patterns["daily_values"][day][-50:]
        
        # Check for unusual daily values
        if len(patterns["daily_values"][day]) > 5:
            daily_values = patterns["daily_values"][day]
            mean_daily = statistics.mean(daily_values)
            std_daily = statistics.stdev(daily_values) if len(daily_values) > 1 else 0
            
            if std_daily > 0:
                z_score = abs(value - mean_daily) / std_daily
                if z_score > 2:
                    reasons.append(f"unusual-daily-value (day {day}, z-score: {z_score:.2f})")
                    score += min(z_score / 2, 1.0) * 0.3
        
        # Interval analysis
        if len(patterns["intervals"]) > 0:
            last_timestamp = patterns["intervals"][-1]
            interval = timestamp - last_timestamp
            
            patterns["intervals"].append(timestamp)
            
            # Check for unusual intervals
            if len(patterns["intervals"]) > 5:
                intervals = list(patterns["intervals"])
                interval_diffs = [intervals[i+1] - intervals[i] for i in range(len(intervals)-1)]
                
                if interval_diffs:
                    mean_interval = statistics.mean(interval_diffs)
                    std_interval = statistics.stdev(interval_diffs) if len(interval_diffs) > 1 else 0
                    
                    if std_interval > 0:
                        z_score = abs(interval - mean_interval) / std_interval
                        if z_score > 2:
                            reasons.append(f"unusual-interval (z-score: {z_score:.2f})")
                            score += min(z_score / 2, 1.0) * 0.3
        else:
            patterns["intervals"].append(timestamp)
        
        suspicious = score > 0.5
        confidence = min(len(patterns["intervals"]) / 50, 1.0)
        
        return DetectionResult(
            detector_type=DetectorType.TEMPORAL,
            suspicious=suspicious,
            score=min(score, 1.0),
            confidence=confidence,
            reasons=reasons,
            metadata={"hour": hour, "day": day, "pattern_size": len(patterns["intervals"])},
            timestamp=time.time()
        )

class SequenceDetector:
    """Sequence-based anomaly detection"""
    
    def __init__(self):
        self.name = "Sequence Detector"
        self.meter_sequences = defaultdict(lambda: {
            "sequences": deque(maxlen=100),
            "gaps": deque(maxlen=100),
            "last_seq": 0
        })
    
    def detect(self, reading: Dict[str, Any], meter_id: str) -> DetectionResult:
        """Detect sequence-based anomalies"""
        reasons = []
        score = 0.0
        
        sequence = int(reading.get("seq", 0))
        timestamp = int(reading.get("ts", 0))
        
        patterns = self.meter_sequences[meter_id]
        
        # Basic sequence validation
        if sequence <= patterns["last_seq"]:
            reasons.append(f"non-increasing-sequence ({patterns['last_seq']} -> {sequence})")
            score += 0.8
        
        # Gap analysis
        if patterns["last_seq"] > 0:
            gap = sequence - patterns["last_seq"]
            patterns["gaps"].append(gap)
            
            # Check for unusual gaps
            if len(patterns["gaps"]) > 5:
                gaps = list(patterns["gaps"])
                mean_gap = statistics.mean(gaps)
                std_gap = statistics.stdev(gaps) if len(gaps) > 1 else 0
                
                if std_gap > 0:
                    z_score = abs(gap - mean_gap) / std_gap
                    if z_score > 2:
                        reasons.append(f"unusual-sequence-gap ({gap}, z-score: {z_score:.2f})")
                        score += min(z_score / 2, 1.0) * 0.4
        
        # Sequence duplication check
        if sequence in patterns["sequences"]:
            reasons.append(f"sequence-duplication ({sequence})")
            score += 0.6
        
        # Update patterns
        patterns["sequences"].append(sequence)
        patterns["last_seq"] = sequence
        
        suspicious = score > 0.5
        confidence = min(len(patterns["sequences"]) / 50, 1.0)
        
        return DetectionResult(
            detector_type=DetectorType.SEQUENCE,
            suspicious=suspicious,
            score=min(score, 1.0),
            confidence=confidence,
            reasons=reasons,
            metadata={"gap": sequence - patterns["last_seq"] if patterns["last_seq"] > 0 else 0},
            timestamp=time.time()
        )

class EnsembleDetector:
    """Main ensemble detector that combines multiple detection algorithms"""
    
    def __init__(self, db_path: str = "ids_ensemble.db"):
        self.db_path = db_path
        self.detectors = {
            DetectorType.STATISTICAL: StatisticalDetector(),
            DetectorType.SIGNATURE: SignatureDetector(),
            DetectorType.TEMPORAL: TemporalDetector(),
            DetectorType.SEQUENCE: SequenceDetector(),
        }
        
        # Voting weights (can be adjusted based on performance)
        self.detector_weights = {
            DetectorType.STATISTICAL: 0.25,
            DetectorType.SIGNATURE: 0.3,
            DetectorType.TEMPORAL: 0.25,
            DetectorType.SEQUENCE: 0.2,
        }
        
        # Confidence thresholds
        self.confidence_threshold = 0.6
        self.score_threshold = 0.5
        
        self.init_database()
    
    def init_database(self):
        """Initialize database for storing ensemble results"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ensemble_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meter_id TEXT,
                    timestamp REAL,
                    suspicious INTEGER,
                    overall_score REAL,
                    confidence REAL,
                    consensus_score REAL,
                    detector_results TEXT,
                    voting_result TEXT,
                    final_reasons TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS detector_performance (
                    detector_type TEXT,
                    total_detections INTEGER,
                    correct_detections INTEGER,
                    false_positives INTEGER,
                    false_negatives INTEGER,
                    last_update REAL,
                    PRIMARY KEY (detector_type)
                )
            """)
    
    def weighted_voting(self, results: List[DetectionResult]) -> Dict[str, Any]:
        """Perform weighted voting on detector results"""
        suspicious_votes = 0
        total_weight = 0
        weighted_score = 0
        
        for result in results:
            weight = self.detector_weights[result.detector_type]
            total_weight += weight
            
            if result.suspicious:
                suspicious_votes += weight
            
            weighted_score += result.score * weight
        
        # Normalize scores
        if total_weight > 0:
            suspicious_ratio = suspicious_votes / total_weight
            avg_score = weighted_score / total_weight
        else:
            suspicious_ratio = 0
            avg_score = 0
        
        return {
            "suspicious_votes": suspicious_votes,
            "total_weight": total_weight,
            "suspicious_ratio": suspicious_ratio,
            "weighted_score": avg_score,
            "consensus": suspicious_ratio > 0.5
        }
    
    def confidence_weighted_voting(self, results: List[DetectionResult]) -> Dict[str, Any]:
        """Perform confidence-weighted voting"""
        suspicious_votes = 0
        total_confidence = 0
        weighted_score = 0
        
        for result in results:
            confidence_weight = result.confidence
            total_confidence += confidence_weight
            
            if result.suspicious:
                suspicious_votes += confidence_weight
            
            weighted_score += result.score * confidence_weight
        
        # Normalize scores
        if total_confidence > 0:
            suspicious_ratio = suspicious_votes / total_confidence
            avg_score = weighted_score / total_confidence
        else:
            suspicious_ratio = 0
            avg_score = 0
        
        return {
            "suspicious_votes": suspicious_votes,
            "total_confidence": total_confidence,
            "suspicious_ratio": suspicious_ratio,
            "weighted_score": avg_score,
            "consensus": suspicious_ratio > 0.5
        }
    
    def majority_voting(self, results: List[DetectionResult]) -> Dict[str, Any]:
        """Perform simple majority voting"""
        suspicious_count = sum(1 for r in results if r.suspicious)
        total_count = len(results)
        
        suspicious_ratio = suspicious_count / total_count if total_count > 0 else 0
        avg_score = statistics.mean([r.score for r in results]) if results else 0
        
        return {
            "suspicious_count": suspicious_count,
            "total_count": total_count,
            "suspicious_ratio": suspicious_ratio,
            "weighted_score": avg_score,
            "consensus": suspicious_ratio > 0.5
        }
    
    def calculate_consensus_score(self, results: List[DetectionResult]) -> float:
        """Calculate consensus score based on agreement between detectors"""
        if not results:
            return 0.0
        
        # Calculate agreement score
        suspicious_count = sum(1 for r in results if r.suspicious)
        total_count = len(results)
        
        # Agreement ratio (how many detectors agree)
        agreement_ratio = max(suspicious_count, total_count - suspicious_count) / total_count
        
        # Confidence-weighted agreement
        avg_confidence = statistics.mean([r.confidence for r in results])
        
        # Score-weighted agreement
        avg_score = statistics.mean([r.score for r in results])
        
        # Combine factors
        consensus_score = (agreement_ratio * 0.4 + avg_confidence * 0.3 + avg_score * 0.3)
        
        return consensus_score
    
    def detect_anomaly(self, reading: Dict[str, Any], meter_id: str) -> EnsembleResult:
        """Main detection function using ensemble methods"""
        detector_results = []
        
        # Run all detectors
        for detector_type, detector in self.detectors.items():
            try:
                result = detector.detect(reading, meter_id)
                detector_results.append(result)
            except Exception as e:
                print(f"Error in {detector_type.value} detector: {e}")
                # Create a neutral result for failed detectors
                detector_results.append(DetectionResult(
                    detector_type=detector_type,
                    suspicious=False,
                    score=0.0,
                    confidence=0.0,
                    reasons=[f"detector-error: {str(e)}"],
                    metadata={},
                    timestamp=time.time()
                ))
        
        # Perform different voting methods
        weighted_vote = self.weighted_voting(detector_results)
        confidence_vote = self.confidence_weighted_voting(detector_results)
        majority_vote = self.majority_voting(detector_results)
        
        # Calculate consensus score
        consensus_score = self.calculate_consensus_score(detector_results)
        
        # Determine final decision
        # Use weighted voting as primary method
        suspicious = weighted_vote["consensus"]
        overall_score = weighted_vote["weighted_score"]
        
        # Calculate overall confidence
        avg_confidence = statistics.mean([r.confidence for r in detector_results])
        
        # Collect all reasons
        all_reasons = []
        for result in detector_results:
            all_reasons.extend(result.reasons)
        
        # Remove duplicates while preserving order
        final_reasons = list(dict.fromkeys(all_reasons))
        
        # Create ensemble result
        ensemble_result = EnsembleResult(
            suspicious=suspicious,
            overall_score=overall_score,
            confidence=avg_confidence,
            detector_results=detector_results,
            consensus_score=consensus_score,
            voting_result={
                "weighted": weighted_vote,
                "confidence": confidence_vote,
                "majority": majority_vote
            },
            final_reasons=final_reasons
        )
        
        # Store result in database
        self.store_result(meter_id, ensemble_result)
        
        return ensemble_result
    
    def store_result(self, meter_id: str, result: EnsembleResult):
        """Store ensemble result in database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO ensemble_results 
                (meter_id, timestamp, suspicious, overall_score, confidence, 
                 consensus_score, detector_results, voting_result, final_reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                meter_id,
                time.time(),
                1 if result.suspicious else 0,
                result.overall_score,
                result.confidence,
                result.consensus_score,
                json.dumps([{
                    "type": r.detector_type.value,
                    "suspicious": r.suspicious,
                    "score": r.score,
                    "confidence": r.confidence,
                    "reasons": r.reasons
                } for r in result.detector_results]),
                json.dumps(result.voting_result),
                json.dumps(result.final_reasons)
            ))
    
    def get_detector_performance(self) -> Dict[str, Any]:
        """Get performance statistics for each detector"""
        performance = {}
        
        with sqlite3.connect(self.db_path) as conn:
            for detector_type in DetectorType:
                cursor = conn.execute(
                    "SELECT * FROM detector_performance WHERE detector_type = ?",
                    (detector_type.value,)
                )
                row = cursor.fetchone()
                
                if row:
                    total = row[1]
                    correct = row[2]
                    fp = row[3]
                    fn = row[4]
                    
                    precision = correct / (correct + fp) if (correct + fp) > 0 else 0
                    recall = correct / (correct + fn) if (correct + fn) > 0 else 0
                    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
                    
                    performance[detector_type.value] = {
                        "total_detections": total,
                        "correct_detections": correct,
                        "false_positives": fp,
                        "false_negatives": fn,
                        "precision": precision,
                        "recall": recall,
                        "f1_score": f1_score
                    }
                else:
                    performance[detector_type.value] = {
                        "total_detections": 0,
                        "correct_detections": 0,
                        "false_positives": 0,
                        "false_negatives": 0,
                        "precision": 0,
                        "recall": 0,
                        "f1_score": 0
                    }
        
        return performance
    
    def update_detector_weights(self, performance: Dict[str, Any]):
        """Update detector weights based on performance"""
        # Simple weight adjustment based on F1 score
        total_f1 = sum(perf["f1_score"] for perf in performance.values())
        
        if total_f1 > 0:
            for detector_type in DetectorType:
                f1_score = performance[detector_type.value]["f1_score"]
                new_weight = f1_score / total_f1
                self.detector_weights[detector_type] = new_weight
    
    def analyze_reading(self, reading: Dict[str, Any], meter_id: str = None) -> Dict[str, Any]:
        """Main analysis function compatible with existing IDS interface"""
        if not meter_id:
            meter_id = reading.get("meterID", "unknown")
        
        # Run ensemble detection
        result = self.detect_anomaly(reading, meter_id)
        
        # Format result for compatibility
        return {
            "suspicious": result.suspicious,
            "score": round(result.overall_score, 3),
            "confidence": round(result.confidence, 3),
            "consensus_score": round(result.consensus_score, 3),
            "reasons": result.final_reasons,
            "detector_results": {
                r.detector_type.value: {
                    "suspicious": r.suspicious,
                    "score": round(r.score, 3),
                    "confidence": round(r.confidence, 3),
                    "reasons": r.reasons
                } for r in result.detector_results
            },
            "voting_summary": {
                "weighted_consensus": result.voting_result["weighted"]["consensus"],
                "confidence_consensus": result.voting_result["confidence"]["consensus"],
                "majority_consensus": result.voting_result["majority"]["consensus"]
            }
        }

# Example usage
if __name__ == "__main__":
    ensemble = EnsembleDetector()
    
    # Test with sample reading
    test_reading = {
        "meterID": "0x1234567890abcdef",
        "seq": 1,
        "ts": int(time.time()),
        "value": 150.5,
        "signature": "0x1234567890abcdef" * 8
    }
    
    result = ensemble.analyze_reading(test_reading)
    print("Ensemble Detection Result:")
    print(json.dumps(result, indent=2))
    
    # Get performance statistics
    performance = ensemble.get_detector_performance()
    print("\nDetector Performance:")
    print(json.dumps(performance, indent=2))