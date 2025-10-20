#!/usr/bin/env python3
"""
Advanced Pattern Analyzer for Smart Meter IDS
Detects complex patterns and behavioral anomalies
"""

import json
import time
import math
import statistics
import sqlite3
import os
from typing import Dict, List, Tuple, Any, Optional, Set
from collections import defaultdict, deque
import numpy as np
from dataclasses import dataclass
from enum import Enum

class PatternType(Enum):
    TEMPORAL = "temporal"
    SEQUENTIAL = "sequential"
    VALUE_BASED = "value_based"
    SIGNATURE_BASED = "signature_based"
    BEHAVIORAL = "behavioral"

@dataclass
class Pattern:
    pattern_type: PatternType
    pattern_id: str
    description: str
    confidence: float
    frequency: int
    last_seen: float
    metadata: Dict[str, Any]

@dataclass
class AnomalyPattern:
    pattern_id: str
    anomaly_type: str
    severity: float
    description: str
    detected_at: float
    evidence: Dict[str, Any]

class PatternAnalyzer:
    def __init__(self, db_path: str = "ids_patterns.db"):
        self.db_path = db_path
        self.patterns: Dict[str, Pattern] = {}
        self.anomaly_patterns: List[AnomalyPattern] = []
        self.meter_behavior: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self.temporal_patterns = defaultdict(list)
        self.sequence_patterns = defaultdict(list)
        self.value_patterns = defaultdict(list)
        self.signature_patterns = defaultdict(list)
        self.init_database()
    
    def init_database(self):
        """Initialize database for pattern storage"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS patterns (
                    pattern_id TEXT PRIMARY KEY,
                    pattern_type TEXT,
                    description TEXT,
                    confidence REAL,
                    frequency INTEGER,
                    last_seen REAL,
                    metadata TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS anomaly_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_id TEXT,
                    anomaly_type TEXT,
                    severity REAL,
                    description TEXT,
                    detected_at REAL,
                    evidence TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS meter_behavior (
                    meter_id TEXT,
                    behavior_type TEXT,
                    data TEXT,
                    last_update REAL,
                    PRIMARY KEY (meter_id, behavior_type)
                )
            """)
    
    def analyze_temporal_patterns(self, readings: List[Dict[str, Any]]) -> List[Pattern]:
        """Analyze temporal patterns in readings"""
        patterns = []
        
        if len(readings) < 10:
            return patterns
        
        # Extract timestamps and values
        timestamps = [r["ts"] for r in readings]
        values = [r["value"] for r in readings]
        
        # Daily patterns
        daily_pattern = self.detect_daily_pattern(timestamps, values)
        if daily_pattern:
            patterns.append(daily_pattern)
        
        # Weekly patterns
        weekly_pattern = self.detect_weekly_pattern(timestamps, values)
        if weekly_pattern:
            patterns.append(weekly_pattern)
        
        # Seasonal patterns
        seasonal_pattern = self.detect_seasonal_pattern(timestamps, values)
        if seasonal_pattern:
            patterns.append(seasonal_pattern)
        
        # Irregular timing patterns
        irregular_pattern = self.detect_irregular_timing(timestamps)
        if irregular_pattern:
            patterns.append(irregular_pattern)
        
        return patterns
    
    def detect_daily_pattern(self, timestamps: List[int], values: List[float]) -> Optional[Pattern]:
        """Detect daily consumption patterns"""
        if len(timestamps) < 24:
            return None
        
        # Group by hour of day
        hourly_values = defaultdict(list)
        for ts, value in zip(timestamps, values):
            hour = time.localtime(ts).tm_hour
            hourly_values[hour].append(value)
        
        # Calculate hourly statistics
        hourly_stats = {}
        for hour in range(24):
            if hour in hourly_values:
                hourly_stats[hour] = {
                    "mean": statistics.mean(hourly_values[hour]),
                    "std": statistics.stdev(hourly_values[hour]) if len(hourly_values[hour]) > 1 else 0,
                    "count": len(hourly_values[hour])
                }
        
        # Detect peak hours
        peak_hours = []
        avg_values = [hourly_stats.get(h, {"mean": 0})["mean"] for h in range(24)]
        overall_mean = statistics.mean(avg_values)
        
        for hour in range(24):
            if hour in hourly_stats and hourly_stats[hour]["mean"] > overall_mean * 1.5:
                peak_hours.append(hour)
        
        if len(peak_hours) > 0:
            return Pattern(
                pattern_type=PatternType.TEMPORAL,
                pattern_id=f"daily_peak_{len(peak_hours)}",
                description=f"Daily peak consumption at hours: {peak_hours}",
                confidence=min(len(peak_hours) / 24, 1.0),
                frequency=len(peak_hours),
                last_seen=time.time(),
                metadata={"peak_hours": peak_hours, "hourly_stats": hourly_stats}
            )
        
        return None
    
    def detect_weekly_pattern(self, timestamps: List[int], values: List[float]) -> Optional[Pattern]:
        """Detect weekly consumption patterns"""
        if len(timestamps) < 7:
            return None
        
        # Group by day of week
        daily_values = defaultdict(list)
        for ts, value in zip(timestamps, values):
            day = time.localtime(ts).tm_wday
            daily_values[day].append(value)
        
        # Calculate daily statistics
        daily_stats = {}
        for day in range(7):
            if day in daily_values:
                daily_stats[day] = {
                    "mean": statistics.mean(daily_values[day]),
                    "std": statistics.stdev(daily_values[day]) if len(daily_values[day]) > 1 else 0,
                    "count": len(daily_values[day])
                }
        
        # Detect weekday vs weekend patterns
        weekday_values = []
        weekend_values = []
        
        for day in range(7):
            if day in daily_stats:
                if day < 5:  # Monday-Friday
                    weekday_values.append(daily_stats[day]["mean"])
                else:  # Saturday-Sunday
                    weekend_values.append(daily_stats[day]["mean"])
        
        if weekday_values and weekend_values:
            weekday_mean = statistics.mean(weekday_values)
            weekend_mean = statistics.mean(weekend_values)
            
            if abs(weekday_mean - weekend_mean) > weekday_mean * 0.2:  # 20% difference
                return Pattern(
                    pattern_type=PatternType.TEMPORAL,
                    pattern_id="weekly_pattern",
                    description=f"Weekday ({weekday_mean:.2f}) vs Weekend ({weekend_mean:.2f}) consumption pattern",
                    confidence=0.8,
                    frequency=2,
                    last_seen=time.time(),
                    metadata={"weekday_mean": weekday_mean, "weekend_mean": weekend_mean}
                )
        
        return None
    
    def detect_seasonal_pattern(self, timestamps: List[int], values: List[float]) -> Optional[Pattern]:
        """Detect seasonal consumption patterns"""
        if len(timestamps) < 30:
            return None
        
        # Group by month
        monthly_values = defaultdict(list)
        for ts, value in zip(timestamps, values):
            month = time.localtime(ts).tm_mon
            monthly_values[month].append(value)
        
        # Calculate monthly statistics
        monthly_stats = {}
        for month in range(1, 13):
            if month in monthly_values:
                monthly_stats[month] = {
                    "mean": statistics.mean(monthly_values[month]),
                    "std": statistics.stdev(monthly_values[month]) if len(monthly_values[month]) > 1 else 0,
                    "count": len(monthly_values[month])
                }
        
        # Detect seasonal variations
        avg_values = [monthly_stats.get(m, {"mean": 0})["mean"] for m in range(1, 13)]
        overall_mean = statistics.mean(avg_values)
        
        # Find months with significant deviation
        seasonal_months = []
        for month in range(1, 13):
            if month in monthly_stats:
                deviation = abs(monthly_stats[month]["mean"] - overall_mean) / overall_mean
                if deviation > 0.3:  # 30% deviation
                    seasonal_months.append(month)
        
        if len(seasonal_months) > 0:
            return Pattern(
                pattern_type=PatternType.TEMPORAL,
                pattern_id="seasonal_pattern",
                description=f"Seasonal consumption variation in months: {seasonal_months}",
                confidence=min(len(seasonal_months) / 12, 1.0),
                frequency=len(seasonal_months),
                last_seen=time.time(),
                metadata={"seasonal_months": seasonal_months, "monthly_stats": monthly_stats}
            )
        
        return None
    
    def detect_irregular_timing(self, timestamps: List[int]) -> Optional[Pattern]:
        """Detect irregular timing patterns"""
        if len(timestamps) < 5:
            return None
        
        # Calculate intervals
        intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
        
        # Calculate statistics
        mean_interval = statistics.mean(intervals)
        std_interval = statistics.stdev(intervals) if len(intervals) > 1 else 0
        
        # Detect irregular patterns
        irregular_count = 0
        for interval in intervals:
            if std_interval > 0:
                z_score = abs(interval - mean_interval) / std_interval
                if z_score > 2:  # More than 2 standard deviations
                    irregular_count += 1
        
        irregularity_ratio = irregular_count / len(intervals)
        
        if irregularity_ratio > 0.3:  # More than 30% irregular
            return Pattern(
                pattern_type=PatternType.TEMPORAL,
                pattern_id="irregular_timing",
                description=f"Irregular timing pattern ({irregularity_ratio:.2%} irregular intervals)",
                confidence=irregularity_ratio,
                frequency=irregular_count,
                last_seen=time.time(),
                metadata={"irregularity_ratio": irregularity_ratio, "intervals": intervals}
            )
        
        return None
    
    def analyze_sequence_patterns(self, readings: List[Dict[str, Any]]) -> List[Pattern]:
        """Analyze sequence number patterns"""
        patterns = []
        
        if len(readings) < 5:
            return patterns
        
        sequences = [r["seq"] for r in readings]
        
        # Sequence gap patterns
        gap_pattern = self.detect_sequence_gaps(sequences)
        if gap_pattern:
            patterns.append(gap_pattern)
        
        # Sequence rollback patterns
        rollback_pattern = self.detect_sequence_rollbacks(sequences)
        if rollback_pattern:
            patterns.append(rollback_pattern)
        
        # Sequence duplication patterns
        duplication_pattern = self.detect_sequence_duplications(sequences)
        if duplication_pattern:
            patterns.append(duplication_pattern)
        
        return patterns
    
    def detect_sequence_gaps(self, sequences: List[int]) -> Optional[Pattern]:
        """Detect unusual sequence gaps"""
        if len(sequences) < 2:
            return None
        
        gaps = [sequences[i+1] - sequences[i] for i in range(len(sequences)-1)]
        
        # Calculate gap statistics
        mean_gap = statistics.mean(gaps)
        std_gap = statistics.stdev(gaps) if len(gaps) > 1 else 0
        
        # Detect large gaps
        large_gaps = [g for g in gaps if g > mean_gap + 2 * std_gap]
        
        if len(large_gaps) > 0:
            return Pattern(
                pattern_type=PatternType.SEQUENTIAL,
                pattern_id="sequence_gaps",
                description=f"Large sequence gaps detected: {large_gaps}",
                confidence=min(len(large_gaps) / len(gaps), 1.0),
                frequency=len(large_gaps),
                last_seen=time.time(),
                metadata={"large_gaps": large_gaps, "mean_gap": mean_gap, "std_gap": std_gap}
            )
        
        return None
    
    def detect_sequence_rollbacks(self, sequences: List[int]) -> Optional[Pattern]:
        """Detect sequence number rollbacks"""
        if len(sequences) < 2:
            return None
        
        rollbacks = []
        for i in range(1, len(sequences)):
            if sequences[i] <= sequences[i-1]:
                rollbacks.append((sequences[i-1], sequences[i]))
        
        if len(rollbacks) > 0:
            return Pattern(
                pattern_type=PatternType.SEQUENTIAL,
                pattern_id="sequence_rollbacks",
                description=f"Sequence rollbacks detected: {rollbacks}",
                confidence=min(len(rollbacks) / len(sequences), 1.0),
                frequency=len(rollbacks),
                last_seen=time.time(),
                metadata={"rollbacks": rollbacks}
            )
        
        return None
    
    def detect_sequence_duplications(self, sequences: List[int]) -> Optional[Pattern]:
        """Detect sequence number duplications"""
        if len(sequences) < 2:
            return None
        
        sequence_counts = defaultdict(int)
        for seq in sequences:
            sequence_counts[seq] += 1
        
        duplications = {seq: count for seq, count in sequence_counts.items() if count > 1}
        
        if len(duplications) > 0:
            return Pattern(
                pattern_type=PatternType.SEQUENTIAL,
                pattern_id="sequence_duplications",
                description=f"Sequence duplications detected: {duplications}",
                confidence=min(len(duplications) / len(sequences), 1.0),
                frequency=sum(duplications.values()) - len(duplications),
                last_seen=time.time(),
                metadata={"duplications": duplications}
            )
        
        return None
    
    def analyze_value_patterns(self, readings: List[Dict[str, Any]]) -> List[Pattern]:
        """Analyze value-based patterns"""
        patterns = []
        
        if len(readings) < 5:
            return patterns
        
        values = [r["value"] for r in readings]
        
        # Sudden changes pattern
        sudden_change_pattern = self.detect_sudden_changes(values)
        if sudden_change_pattern:
            patterns.append(sudden_change_pattern)
        
        # Oscillation pattern
        oscillation_pattern = self.detect_oscillations(values)
        if oscillation_pattern:
            patterns.append(oscillation_pattern)
        
        # Trend pattern
        trend_pattern = self.detect_trends(values)
        if trend_pattern:
            patterns.append(trend_pattern)
        
        return patterns
    
    def detect_sudden_changes(self, values: List[float]) -> Optional[Pattern]:
        """Detect sudden value changes"""
        if len(values) < 3:
            return None
        
        changes = [abs(values[i+1] - values[i]) for i in range(len(values)-1)]
        
        # Calculate change statistics
        mean_change = statistics.mean(changes)
        std_change = statistics.stdev(changes) if len(changes) > 1 else 0
        
        # Detect sudden changes
        sudden_changes = []
        for i, change in enumerate(changes):
            if std_change > 0:
                z_score = change / std_change
                if z_score > 3:  # More than 3 standard deviations
                    sudden_changes.append((i, change, z_score))
        
        if len(sudden_changes) > 0:
            return Pattern(
                pattern_type=PatternType.VALUE_BASED,
                pattern_id="sudden_changes",
                description=f"Sudden value changes detected: {len(sudden_changes)} occurrences",
                confidence=min(len(sudden_changes) / len(changes), 1.0),
                frequency=len(sudden_changes),
                last_seen=time.time(),
                metadata={"sudden_changes": sudden_changes, "mean_change": mean_change, "std_change": std_change}
            )
        
        return None
    
    def detect_oscillations(self, values: List[float]) -> Optional[Pattern]:
        """Detect oscillating value patterns"""
        if len(values) < 6:
            return None
        
        # Calculate second differences to detect oscillations
        first_diffs = [values[i+1] - values[i] for i in range(len(values)-1)]
        second_diffs = [first_diffs[i+1] - first_diffs[i] for i in range(len(first_diffs)-1)]
        
        # Count sign changes in second differences
        sign_changes = 0
        for i in range(1, len(second_diffs)):
            if (second_diffs[i] > 0) != (second_diffs[i-1] > 0):
                sign_changes += 1
        
        oscillation_ratio = sign_changes / len(second_diffs)
        
        if oscillation_ratio > 0.5:  # More than 50% sign changes
            return Pattern(
                pattern_type=PatternType.VALUE_BASED,
                pattern_id="oscillations",
                description=f"Oscillating pattern detected ({oscillation_ratio:.2%} sign changes)",
                confidence=oscillation_ratio,
                frequency=sign_changes,
                last_seen=time.time(),
                metadata={"oscillation_ratio": oscillation_ratio, "sign_changes": sign_changes}
            )
        
        return None
    
    def detect_trends(self, values: List[float]) -> Optional[Pattern]:
        """Detect value trends"""
        if len(values) < 5:
            return None
        
        # Simple linear trend detection
        x = list(range(len(values)))
        n = len(values)
        
        # Calculate slope using least squares
        sum_x = sum(x)
        sum_y = sum(values)
        sum_xy = sum(x[i] * values[i] for i in range(n))
        sum_x2 = sum(x[i] ** 2 for i in range(n))
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
        
        # Calculate correlation coefficient
        mean_x = sum_x / n
        mean_y = sum_y / n
        
        numerator = sum((x[i] - mean_x) * (values[i] - mean_y) for i in range(n))
        denominator_x = sum((x[i] - mean_x) ** 2 for i in range(n))
        denominator_y = sum((values[i] - mean_y) ** 2 for i in range(n))
        
        if denominator_x > 0 and denominator_y > 0:
            correlation = numerator / math.sqrt(denominator_x * denominator_y)
        else:
            correlation = 0
        
        # Determine trend type
        if abs(correlation) > 0.7:  # Strong correlation
            trend_type = "increasing" if slope > 0 else "decreasing"
            return Pattern(
                pattern_type=PatternType.VALUE_BASED,
                pattern_id=f"trend_{trend_type}",
                description=f"Strong {trend_type} trend detected (slope: {slope:.3f}, correlation: {correlation:.3f})",
                confidence=abs(correlation),
                frequency=1,
                last_seen=time.time(),
                metadata={"slope": slope, "correlation": correlation, "trend_type": trend_type}
            )
        
        return None
    
    def analyze_signature_patterns(self, readings: List[Dict[str, Any]]) -> List[Pattern]:
        """Analyze signature-based patterns"""
        patterns = []
        
        if len(readings) < 5:
            return patterns
        
        signatures = [r.get("signature", "") for r in readings]
        
        # Signature length patterns
        length_pattern = self.detect_signature_length_patterns(signatures)
        if length_pattern:
            patterns.append(length_pattern)
        
        # Signature entropy patterns
        entropy_pattern = self.detect_signature_entropy_patterns(signatures)
        if entropy_pattern:
            patterns.append(entropy_pattern)
        
        # Signature reuse patterns
        reuse_pattern = self.detect_signature_reuse(signatures)
        if reuse_pattern:
            patterns.append(reuse_pattern)
        
        return patterns
    
    def detect_signature_length_patterns(self, signatures: List[str]) -> Optional[Pattern]:
        """Detect unusual signature length patterns"""
        if not signatures:
            return None
        
        lengths = [len(sig) for sig in signatures]
        
        # Calculate length statistics
        mean_length = statistics.mean(lengths)
        std_length = statistics.stdev(lengths) if len(lengths) > 1 else 0
        
        # Detect unusual lengths
        unusual_lengths = []
        for i, length in enumerate(lengths):
            if std_length > 0:
                z_score = abs(length - mean_length) / std_length
                if z_score > 2:  # More than 2 standard deviations
                    unusual_lengths.append((i, length, z_score))
        
        if len(unusual_lengths) > 0:
            return Pattern(
                pattern_type=PatternType.SIGNATURE_BASED,
                pattern_id="signature_length_anomaly",
                description=f"Unusual signature lengths detected: {len(unusual_lengths)} occurrences",
                confidence=min(len(unusual_lengths) / len(lengths), 1.0),
                frequency=len(unusual_lengths),
                last_seen=time.time(),
                metadata={"unusual_lengths": unusual_lengths, "mean_length": mean_length, "std_length": std_length}
            )
        
        return None
    
    def detect_signature_entropy_patterns(self, signatures: List[str]) -> Optional[Pattern]:
        """Detect signature entropy patterns"""
        if not signatures:
            return None
        
        entropies = [self.calculate_entropy(sig) for sig in signatures]
        
        # Calculate entropy statistics
        mean_entropy = statistics.mean(entropies)
        std_entropy = statistics.stdev(entropies) if len(entropies) > 1 else 0
        
        # Detect unusual entropies
        unusual_entropies = []
        for i, entropy in enumerate(entropies):
            if std_entropy > 0:
                z_score = abs(entropy - mean_entropy) / std_entropy
                if z_score > 2:  # More than 2 standard deviations
                    unusual_entropies.append((i, entropy, z_score))
        
        if len(unusual_entropies) > 0:
            return Pattern(
                pattern_type=PatternType.SIGNATURE_BASED,
                pattern_id="signature_entropy_anomaly",
                description=f"Unusual signature entropies detected: {len(unusual_entropies)} occurrences",
                confidence=min(len(unusual_entropies) / len(entropies), 1.0),
                frequency=len(unusual_entropies),
                last_seen=time.time(),
                metadata={"unusual_entropies": unusual_entropies, "mean_entropy": mean_entropy, "std_entropy": std_entropy}
            )
        
        return None
    
    def detect_signature_reuse(self, signatures: List[str]) -> Optional[Pattern]:
        """Detect signature reuse patterns"""
        if not signatures:
            return None
        
        signature_counts = defaultdict(int)
        for sig in signatures:
            signature_counts[sig] += 1
        
        reused_signatures = {sig: count for sig, count in signature_counts.items() if count > 1}
        
        if len(reused_signatures) > 0:
            return Pattern(
                pattern_type=PatternType.SIGNATURE_BASED,
                pattern_id="signature_reuse",
                description=f"Signature reuse detected: {len(reused_signatures)} signatures reused",
                confidence=min(len(reused_signatures) / len(signatures), 1.0),
                frequency=sum(reused_signatures.values()) - len(reused_signatures),
                last_seen=time.time(),
                metadata={"reused_signatures": reused_signatures}
            )
        
        return None
    
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
    
    def detect_anomaly_patterns(self, readings: List[Dict[str, Any]]) -> List[AnomalyPattern]:
        """Detect anomaly patterns across all pattern types"""
        anomaly_patterns = []
        
        # Analyze all pattern types
        temporal_patterns = self.analyze_temporal_patterns(readings)
        sequence_patterns = self.analyze_sequence_patterns(readings)
        value_patterns = self.analyze_value_patterns(readings)
        signature_patterns = self.analyze_signature_patterns(readings)
        
        all_patterns = temporal_patterns + sequence_patterns + value_patterns + signature_patterns
        
        # Identify anomaly patterns
        for pattern in all_patterns:
            if pattern.confidence > 0.7:  # High confidence patterns
                anomaly_pattern = AnomalyPattern(
                    pattern_id=pattern.pattern_id,
                    anomaly_type=pattern.pattern_type.value,
                    severity=pattern.confidence,
                    description=pattern.description,
                    detected_at=time.time(),
                    evidence=pattern.metadata
                )
                anomaly_patterns.append(anomaly_pattern)
        
        return anomaly_patterns
    
    def analyze_reading_sequence(self, readings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Main analysis function for a sequence of readings"""
        if not readings:
            return {"patterns": [], "anomaly_patterns": [], "summary": "No readings to analyze"}
        
        # Detect all patterns
        temporal_patterns = self.analyze_temporal_patterns(readings)
        sequence_patterns = self.analyze_sequence_patterns(readings)
        value_patterns = self.analyze_value_patterns(readings)
        signature_patterns = self.analyze_signature_patterns(readings)
        
        all_patterns = temporal_patterns + sequence_patterns + value_patterns + signature_patterns
        
        # Detect anomaly patterns
        anomaly_patterns = self.detect_anomaly_patterns(readings)
        
        # Calculate overall anomaly score
        if anomaly_patterns:
            avg_severity = statistics.mean([ap.severity for ap in anomaly_patterns])
            max_severity = max([ap.severity for ap in anomaly_patterns])
        else:
            avg_severity = 0
            max_severity = 0
        
        # Generate summary
        summary = {
            "total_patterns": len(all_patterns),
            "anomaly_patterns": len(anomaly_patterns),
            "avg_severity": round(avg_severity, 3),
            "max_severity": round(max_severity, 3),
            "pattern_types": {
                "temporal": len(temporal_patterns),
                "sequential": len(sequence_patterns),
                "value_based": len(value_patterns),
                "signature_based": len(signature_patterns)
            }
        }
        
        return {
            "patterns": [{"type": p.pattern_type.value, "id": p.pattern_id, "description": p.description, "confidence": p.confidence} for p in all_patterns],
            "anomaly_patterns": [{"type": ap.anomaly_type, "severity": ap.severity, "description": ap.description} for ap in anomaly_patterns],
            "summary": summary
        }

# Example usage
if __name__ == "__main__":
    analyzer = PatternAnalyzer()
    
    # Test with sample readings
    test_readings = [
        {"meterID": "0x123", "seq": 1, "ts": int(time.time()), "value": 100.0, "signature": "0xabc123"},
        {"meterID": "0x123", "seq": 2, "ts": int(time.time()) + 60, "value": 150.0, "signature": "0xdef456"},
        {"meterID": "0x123", "seq": 3, "ts": int(time.time()) + 120, "value": 200.0, "signature": "0xghi789"},
    ]
    
    result = analyzer.analyze_reading_sequence(test_readings)
    print("Pattern Analysis Result:")
    print(json.dumps(result, indent=2))