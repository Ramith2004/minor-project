#!/usr/bin/env python3
"""
Pattern Analyzer for Smart Meter IDS - OFFLINE ANALYSIS ONLY
Detects temporal patterns and trends for reporting and insights
(Not used for real-time detection - bayesian_model.py handles that)
"""

import json
import time
import math
import statistics
import sqlite3
from typing import Dict, List, Tuple, Any, Optional
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum

class PatternType(Enum):
    TEMPORAL = "temporal"
    TREND = "trend"

@dataclass
class Pattern:
    pattern_type: PatternType
    pattern_id: str
    description: str
    confidence: float
    frequency: int
    last_seen: float
    metadata: Dict[str, Any]

class PatternAnalyzer:
    """
    Offline pattern analyzer for historical data analysis
    Use for: Reports, insights, long-term trend detection
    Do NOT use for: Real-time anomaly detection (use bayesian_model.py)
    """
    
    def __init__(self, db_path: str = "ids_patterns.db"):
        self.db_path = db_path
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
    
    # ==================== UNIQUE ALGORITHMS (KEEP) ====================
    
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
        overall_mean = statistics.mean(avg_values) if avg_values else 0
        
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
        overall_mean = statistics.mean(avg_values) if avg_values else 0
        
        # Find months with significant deviation
        seasonal_months = []
        for month in range(1, 13):
            if month in monthly_stats and overall_mean > 0:
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
        
        oscillation_ratio = sign_changes / len(second_diffs) if second_diffs else 0
        
        if oscillation_ratio > 0.5:  # More than 50% sign changes
            return Pattern(
                pattern_type=PatternType.TREND,
                pattern_id="oscillations",
                description=f"Oscillating pattern detected ({oscillation_ratio:.2%} sign changes)",
                confidence=oscillation_ratio,
                frequency=sign_changes,
                last_seen=time.time(),
                metadata={"oscillation_ratio": oscillation_ratio, "sign_changes": sign_changes}
            )
        
        return None
    
    def detect_trends(self, values: List[float]) -> Optional[Pattern]:
        """Detect value trends using linear regression"""
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
        
        if n * sum_x2 - sum_x ** 2 == 0:
            return None
        
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
                pattern_type=PatternType.TREND,
                pattern_id=f"trend_{trend_type}",
                description=f"Strong {trend_type} trend detected (slope: {slope:.3f}, correlation: {correlation:.3f})",
                confidence=abs(correlation),
                frequency=1,
                last_seen=time.time(),
                metadata={"slope": slope, "correlation": correlation, "trend_type": trend_type}
            )
        
        return None
    
    # ==================== MAIN ANALYSIS FUNCTION ====================
    
    def analyze_reading_sequence(self, readings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Main analysis function for historical data
        Use this for generating reports and insights
        """
        if not readings:
            return {"patterns": [], "summary": "No readings to analyze"}
        
        # Extract data
        timestamps = [r["ts"] for r in readings]
        values = [r["value"] for r in readings]
        
        patterns = []
        
        # Detect temporal patterns
        daily_pattern = self.detect_daily_pattern(timestamps, values)
        if daily_pattern:
            patterns.append(daily_pattern)
        
        weekly_pattern = self.detect_weekly_pattern(timestamps, values)
        if weekly_pattern:
            patterns.append(weekly_pattern)
        
        seasonal_pattern = self.detect_seasonal_pattern(timestamps, values)
        if seasonal_pattern:
            patterns.append(seasonal_pattern)
        
        # Detect trend patterns
        trend_pattern = self.detect_trends(values)
        if trend_pattern:
            patterns.append(trend_pattern)
        
        oscillation_pattern = self.detect_oscillations(values)
        if oscillation_pattern:
            patterns.append(oscillation_pattern)
        
        # Generate summary
        summary = {
            "total_patterns": len(patterns),
            "pattern_types": {
                "temporal": len([p for p in patterns if p.pattern_type == PatternType.TEMPORAL]),
                "trend": len([p for p in patterns if p.pattern_type == PatternType.TREND])
            },
            "readings_analyzed": len(readings)
        }
        
        return {
            "patterns": [
                {
                    "type": p.pattern_type.value,
                    "id": p.pattern_id,
                    "description": p.description,
                    "confidence": p.confidence
                } for p in patterns
            ],
            "summary": summary
        }

# Example usage
if __name__ == "__main__":
    analyzer = PatternAnalyzer()
    
    # Test with sample readings
    test_readings = []
    base_time = int(time.time())
    
    # Generate 48 hours of data
    for i in range(48):
        test_readings.append({
            "meterID": "0x123",
            "seq": i + 1,
            "ts": base_time + (i * 3600),  # Every hour
            "value": 100.0 + (i % 24) * 5,  # Daily pattern
            "signature": "0xabc123"
        })
    
    result = analyzer.analyze_reading_sequence(test_readings)
    print("Pattern Analysis Result:")
    print(json.dumps(result, indent=2))