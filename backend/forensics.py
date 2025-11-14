#!/usr/bin/env python3
"""
Forensic Analysis Module
Advanced forensic analysis for detecting sophisticated attacks and anomalies
"""

import json
import time
import sqlite3
import os
import logging
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict, deque
from dataclasses import dataclass
import statistics
import threading
from datetime import datetime, timedelta

@dataclass
class ForensicEvidence:
    """Forensic evidence structure"""
    evidence_type: str
    severity: float
    description: str
    timestamp: float
    metadata: Dict[str, Any]
    confidence: float

@dataclass
class AttackPattern:
    """Attack pattern structure"""
    pattern_id: str
    pattern_type: str
    description: str
    frequency: int
    first_seen: float
    last_seen: float
    severity: float
    evidence: List[ForensicEvidence]

class ForensicAnalyzer:
    def __init__(self, db_path: str = "forensics.db"):
        self.db_path = db_path
        self.evidence_history: deque = deque(maxlen=10000)
        self.attack_patterns: Dict[str, AttackPattern] = {}
        self.meter_profiles: Dict[str, Dict[str, Any]] = defaultdict(dict)
        
        # Analysis threads
        self.analysis_thread = threading.Thread(target=self._analysis_loop, daemon=True)
        self.analysis_thread.start()
        
        # Initialize database
        self.init_database()
        
        logging.info("Forensic analyzer initialized")
    
    def init_database(self):
        """Initialize forensic database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS forensic_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meter_id TEXT,
                    evidence_type TEXT,
                    severity REAL,
                    description TEXT,
                    timestamp REAL,
                    metadata TEXT,
                    confidence REAL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS attack_patterns (
                    pattern_id TEXT PRIMARY KEY,
                    pattern_type TEXT,
                    description TEXT,
                    frequency INTEGER,
                    first_seen REAL,
                    last_seen REAL,
                    severity REAL,
                    evidence_count INTEGER
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS meter_forensics (
                    meter_id TEXT PRIMARY KEY,
                    total_readings INTEGER,
                    suspicious_readings INTEGER,
                    attack_patterns TEXT,
                    last_analysis REAL,
                    risk_score REAL
                )
            """)
    
    def analyze_reading(self, reading: Dict[str, Any], last_seq: int) -> Dict[str, Any]:
        """Analyze a single reading for forensic evidence"""
        meter_id = reading.get("meterID", "unknown")
        sequence = int(reading.get("seq", 0))
        timestamp = int(reading.get("ts", 0))
        value = float(reading.get("value", 0))
        signature = reading.get("signature", "")
        
        evidence_list = []
        anomaly_score = 0.0
        
        # 1. Sequence Analysis
        seq_evidence = self._analyze_sequence_patterns(meter_id, sequence, last_seq)
        if seq_evidence:
            evidence_list.extend(seq_evidence)
            anomaly_score += sum(e.severity for e in seq_evidence)
        
        # 2. Timing Analysis
        timing_evidence = self._analyze_timing_patterns(meter_id, timestamp)
        if timing_evidence:
            evidence_list.extend(timing_evidence)
            anomaly_score += sum(e.severity for e in timing_evidence)
        
        # 3. Value Analysis
        value_evidence = self._analyze_value_patterns(meter_id, value)
        if value_evidence:
            evidence_list.extend(value_evidence)
            anomaly_score += sum(e.severity for e in value_evidence)
        
        # 4. Signature Analysis
        sig_evidence = self._analyze_signature_patterns(meter_id, signature)
        if sig_evidence:
            evidence_list.extend(sig_evidence)
            anomaly_score += sum(e.severity for e in sig_evidence)
        
        # 5. Cross-Meter Analysis
        cross_evidence = self._analyze_cross_meter_patterns(meter_id, reading)
        if cross_evidence:
            evidence_list.extend(cross_evidence)
            anomaly_score += sum(e.severity for e in cross_evidence)
        
        # Store evidence
        for evidence in evidence_list:
            self._store_evidence(meter_id, evidence)
        
        # Update meter profile
        self._update_meter_profile(meter_id, reading, evidence_list)
        
        # Detect attack patterns
        attack_patterns = self._detect_attack_patterns(meter_id, evidence_list)
        
        return {
            "anomaly_detected": anomaly_score > 0.5,
            "anomaly_score": min(anomaly_score, 1.0),
            "anomaly_reasons": [e.description for e in evidence_list],
            "evidence_count": len(evidence_list),
            "attack_patterns": [p.pattern_id for p in attack_patterns],
            "risk_level": self._calculate_risk_level(anomaly_score, attack_patterns)
        }
    
    def _analyze_sequence_patterns(self, meter_id: str, sequence: int, last_seq: int) -> List[ForensicEvidence]:
        """Analyze sequence number patterns"""
        evidence = []
        
        if sequence <= last_seq:
            evidence.append(ForensicEvidence(
                evidence_type="sequence_rollback",
                severity=0.9,
                description=f"Sequence rollback detected: {last_seq} -> {sequence}",
                timestamp=time.time(),
                metadata={"last_seq": last_seq, "current_seq": sequence},
                confidence=1.0
            ))
        
        gap = sequence - last_seq
        if gap > 100:
            evidence.append(ForensicEvidence(
                evidence_type="large_sequence_gap",
                severity=0.6,
                description=f"Large sequence gap detected: {gap}",
                timestamp=time.time(),
                metadata={"gap": gap, "last_seq": last_seq},
                confidence=0.8
            ))
        
        # Check for sequence patterns
        if meter_id in self.meter_profiles:
            profile = self.meter_profiles[meter_id]
            if "sequence_history" in profile:
                seq_history = profile["sequence_history"]
                if len(seq_history) > 5:
                    # Check for arithmetic progression
                    diffs = [seq_history[i+1] - seq_history[i] for i in range(len(seq_history)-1)]
                    if len(set(diffs)) == 1 and diffs[0] != 1:
                        evidence.append(ForensicEvidence(
                            evidence_type="non_standard_sequence_pattern",
                            severity=0.4,
                            description=f"Non-standard sequence pattern: step size {diffs[0]}",
                            timestamp=time.time(),
                            metadata={"step_size": diffs[0], "pattern_length": len(seq_history)},
                            confidence=0.7
                        ))
        
        return evidence
    
    def _analyze_timing_patterns(self, meter_id: str, timestamp: int) -> List[ForensicEvidence]:
        """Analyze timing patterns"""
        evidence = []
        current_time = time.time()
        
        # Check timestamp freshness
        time_diff = abs(current_time - timestamp)
        if time_diff > 300:  # 5 minutes
            evidence.append(ForensicEvidence(
                evidence_type="stale_timestamp",
                severity=0.5,
                description=f"Stale timestamp: {time_diff}s old",
                timestamp=current_time,
                metadata={"time_diff": time_diff, "timestamp": timestamp},
                confidence=0.9
            ))
        
        # Check timing patterns
        if meter_id in self.meter_profiles:
            profile = self.meter_profiles[meter_id]
            if "timing_history" in profile:
                timing_history = profile["timing_history"]
                if len(timing_history) > 3:
                    intervals = [timing_history[i+1] - timing_history[i] for i in range(len(timing_history)-1)]
                    
                    # Check for regular intervals (possible automation)
                    if len(set(intervals)) == 1 and intervals[0] > 0:
                        evidence.append(ForensicEvidence(
                            evidence_type="regular_timing_pattern",
                            severity=0.3,
                            description=f"Regular timing pattern: {intervals[0]}s intervals",
                            timestamp=current_time,
                            metadata={"interval": intervals[0], "pattern_length": len(intervals)},
                            confidence=0.6
                        ))
        
        return evidence
    
    def _analyze_value_patterns(self, meter_id: str, value: float) -> List[ForensicEvidence]:
        """Analyze value patterns"""
        evidence = []
        
        # Check for extreme values
        if value < 0:
            evidence.append(ForensicEvidence(
                evidence_type="negative_value",
                severity=0.8,
                description=f"Negative value detected: {value}",
                timestamp=time.time(),
                metadata={"value": value},
                confidence=1.0
            ))
        
        if value > 10000:  # Unrealistic high value
            evidence.append(ForensicEvidence(
                evidence_type="extreme_value",
                severity=0.7,
                description=f"Extreme value detected: {value}",
                timestamp=time.time(),
                metadata={"value": value},
                confidence=0.8
            ))
        
        # Check value patterns
        if meter_id in self.meter_profiles:
            profile = self.meter_profiles[meter_id]
            if "value_history" in profile:
                value_history = profile["value_history"]
                if len(value_history) > 5:
                    # Check for sudden changes
                    recent_values = list(value_history)[-5:]  # Convert deque to list for slicing
                    if len(recent_values) > 1:
                        changes = [abs(recent_values[i+1] - recent_values[i]) for i in range(len(recent_values)-1)]
                        avg_change = statistics.mean(changes)
                        
                        if abs(value - recent_values[-1]) > avg_change * 3:
                            evidence.append(ForensicEvidence(
                                evidence_type="sudden_value_change",
                                severity=0.6,
                                description=f"Sudden value change: {abs(value - recent_values[-1])}",
                                timestamp=time.time(),
                                metadata={"change": abs(value - recent_values[-1]), "avg_change": avg_change},
                                confidence=0.7
                            ))
        
        return evidence
    
    def _analyze_signature_patterns(self, meter_id: str, signature: str) -> List[ForensicEvidence]:
        """Analyze signature patterns"""
        evidence = []
        
        # Check signature format
        if not signature.startswith("0x"):
            evidence.append(ForensicEvidence(
                evidence_type="invalid_signature_format",
                severity=0.8,
                description="Invalid signature format",
                timestamp=time.time(),
                metadata={"signature": signature[:20] + "..."},
                confidence=1.0
            ))
        
        # Check signature length
        if len(signature) < 130 or len(signature) > 132:
            evidence.append(ForensicEvidence(
                evidence_type="invalid_signature_length",
                severity=0.7,
                description=f"Invalid signature length: {len(signature)}",
                timestamp=time.time(),
                metadata={"length": len(signature)},
                confidence=0.9
            ))
        
        # Check signature reuse
        if meter_id in self.meter_profiles:
            profile = self.meter_profiles[meter_id]
            if "signature_history" in profile:
                if signature in profile["signature_history"]:
                    evidence.append(ForensicEvidence(
                        evidence_type="signature_reuse",
                        severity=0.9,
                        description="Signature reuse detected",
                        timestamp=time.time(),
                        metadata={"signature": signature[:20] + "..."},
                        confidence=1.0
                    ))
        
        return evidence
    
    def _analyze_cross_meter_patterns(self, meter_id: str, reading: Dict[str, Any]) -> List[ForensicEvidence]:
        """Analyze patterns across multiple meters"""
        evidence = []
        
        # Check for coordinated attacks
        current_time = time.time()
        recent_readings = self._get_recent_readings(60)  # Last minute
        
        # Look for similar patterns across meters
        similar_readings = []
        for other_reading in recent_readings:
            if other_reading["meterID"] != meter_id:
                # Check for similar values
                if abs(float(other_reading["value"]) - float(reading["value"])) < 0.1:
                    similar_readings.append(other_reading)
        
        if len(similar_readings) > 2:
            evidence.append(ForensicEvidence(
                evidence_type="coordinated_attack",
                severity=0.8,
                description=f"Coordinated attack detected: {len(similar_readings)} similar readings",
                timestamp=current_time,
                metadata={"similar_count": len(similar_readings), "meters": [r["meterID"] for r in similar_readings]},
                confidence=0.7
            ))
        
        return evidence
    
    def _analyze_timing_patterns(self, meter_id: str, timestamp: int) -> List[ForensicEvidence]:
        """Analyze timing patterns"""
        evidence = []
        current_time = time.time()
        
        # Check timestamp freshness
        time_diff = abs(current_time - timestamp)
        if time_diff > 300:  # 5 minutes
            evidence.append(ForensicEvidence(
                evidence_type="stale_timestamp",
                severity=0.5,
                description=f"Stale timestamp: {time_diff}s old",
                timestamp=current_time,
                metadata={"time_diff": time_diff, "timestamp": timestamp},
                confidence=0.9
            ))
        
        # Check timing patterns
        if meter_id in self.meter_profiles:
            profile = self.meter_profiles[meter_id]
            if "timing_history" in profile:
                timing_history = profile["timing_history"]
                if len(timing_history) > 3:
                    timing_list = list(timing_history)  # Convert deque to list
                    intervals = [timing_list[i+1] - timing_list[i] for i in range(len(timing_list)-1)]
                    
                    # Check for regular intervals (possible automation)
                    if len(set(intervals)) == 1 and intervals[0] > 0:
                        evidence.append(ForensicEvidence(
                            evidence_type="regular_timing_pattern",
                            severity=0.3,
                            description=f"Regular timing pattern: {intervals[0]}s intervals",
                            timestamp=current_time,
                            metadata={"interval": intervals[0], "pattern_length": len(intervals)},
                            confidence=0.6
                        ))
        
        return evidence
    
    def _detect_attack_patterns(self, meter_id: str, evidence_list: List[ForensicEvidence]) -> List[AttackPattern]:
        """Detect attack patterns from evidence"""
        patterns = []
        
        # Group evidence by type
        evidence_by_type = defaultdict(list)
        for evidence in evidence_list:
            evidence_by_type[evidence.evidence_type].append(evidence)
        
        # Detect replay attack pattern
        if "signature_reuse" in evidence_by_type and "sequence_rollback" in evidence_by_type:
            pattern_id = f"replay_attack_{meter_id}_{int(time.time())}"
            patterns.append(AttackPattern(
                pattern_id=pattern_id,
                pattern_type="replay_attack",
                description="Replay attack pattern detected",
                frequency=1,
                first_seen=time.time(),
                last_seen=time.time(),
                severity=0.9,
                evidence=evidence_list
            ))
        
        # Detect timing attack pattern
        if "regular_timing_pattern" in evidence_by_type and len(evidence_by_type["regular_timing_pattern"]) > 3:
            pattern_id = f"timing_attack_{meter_id}_{int(time.time())}"
            patterns.append(AttackPattern(
                pattern_id=pattern_id,
                pattern_type="timing_attack",
                description="Automated timing attack pattern",
                frequency=len(evidence_by_type["regular_timing_pattern"]),
                first_seen=time.time(),
                last_seen=time.time(),
                severity=0.6,
                evidence=evidence_by_type["regular_timing_pattern"]
            ))
        
        return patterns
    
    def _calculate_risk_level(self, anomaly_score: float, attack_patterns: List[AttackPattern]) -> str:
        """Calculate risk level"""
        if anomaly_score > 0.8 or any(p.severity > 0.8 for p in attack_patterns):
            return "HIGH"
        elif anomaly_score > 0.5 or any(p.severity > 0.5 for p in attack_patterns):
            return "MEDIUM"
        elif anomaly_score > 0.2 or any(p.severity > 0.2 for p in attack_patterns):
            return "LOW"
        else:
            return "NORMAL"
    
    def _store_evidence(self, meter_id: str, evidence: ForensicEvidence):
        """Store forensic evidence"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO forensic_evidence 
                (meter_id, evidence_type, severity, description, timestamp, metadata, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                meter_id,
                evidence.evidence_type,
                evidence.severity,
                evidence.description,
                evidence.timestamp,
                json.dumps(evidence.metadata),
                evidence.confidence
            ))
        
        self.evidence_history.append(evidence)
    
    def _update_meter_profile(self, meter_id: str, reading: Dict[str, Any], evidence_list: List[ForensicEvidence]):
        """Update meter profile with new data"""
        if meter_id not in self.meter_profiles:
            self.meter_profiles[meter_id] = {
                "sequence_history": deque(maxlen=100),
                "timing_history": deque(maxlen=100),
                "value_history": deque(maxlen=100),
                "signature_history": deque(maxlen=100),
                "evidence_count": 0,
                "last_update": time.time()
            }
        
        profile = self.meter_profiles[meter_id]
        
        # Update histories
        profile["sequence_history"].append(int(reading.get("seq", 0)))
        profile["timing_history"].append(int(reading.get("ts", 0)))
        profile["value_history"].append(float(reading.get("value", 0)))
        profile["signature_history"].append(reading.get("signature", ""))
        
        # Update evidence count
        profile["evidence_count"] += len(evidence_list)
        profile["last_update"] = time.time()
    
    def _get_recent_readings(self, seconds: int) -> List[Dict[str, Any]]:
        """Get recent readings from database"""
        # This would typically query the main database
        # For now, return empty list
        return []
    
    def get_meter_analysis(self, meter_id: str) -> Dict[str, Any]:
        """Get comprehensive forensic analysis for a meter"""
        with sqlite3.connect(self.db_path) as conn:
            # Get evidence for meter
            cursor = conn.execute("""
                SELECT evidence_type, severity, description, timestamp, metadata, confidence
                FROM forensic_evidence 
                WHERE meter_id = ? 
                ORDER BY timestamp DESC 
                LIMIT 100
            """, (meter_id,))
            
            evidence = []
            for row in cursor.fetchall():
                evidence.append({
                    "type": row[0],
                    "severity": row[1],
                    "description": row[2],
                    "timestamp": row[3],
                    "metadata": json.loads(row[4]) if row[4] else {},
                    "confidence": row[5]
                })
            
            # Get meter profile
            profile = self.meter_profiles.get(meter_id, {})
            
            # Calculate statistics
            total_evidence = len(evidence)
            high_severity_evidence = sum(1 for e in evidence if e["severity"] > 0.7)
            recent_evidence = sum(1 for e in evidence if time.time() - e["timestamp"] < 3600)
            
            return {
                "meter_id": meter_id,
                "total_evidence": total_evidence,
                "high_severity_evidence": high_severity_evidence,
                "recent_evidence": recent_evidence,
                "evidence": evidence,
                "profile": {
                    "sequence_count": len(profile.get("sequence_history", [])),
                    "timing_count": len(profile.get("timing_history", [])),
                    "value_count": len(profile.get("value_history", [])),
                    "signature_count": len(profile.get("signature_history", [])),
                    "evidence_count": profile.get("evidence_count", 0),
                    "last_update": profile.get("last_update", 0)
                },
                "risk_assessment": self._assess_meter_risk(meter_id, evidence)
            }
    
    def _assess_meter_risk(self, meter_id: str, evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Assess risk level for a meter"""
        if not evidence:
            return {"risk_level": "NORMAL", "risk_score": 0.0}
        
        # Calculate risk score
        risk_score = sum(e["severity"] for e in evidence) / len(evidence)
        
        # Determine risk level
        if risk_score > 0.7:
            risk_level = "HIGH"
        elif risk_score > 0.4:
            risk_level = "MEDIUM"
        elif risk_score > 0.1:
            risk_level = "LOW"
        else:
            risk_level = "NORMAL"
        
        return {
            "risk_level": risk_level,
            "risk_score": round(risk_score, 3),
            "evidence_types": list(set(e["type"] for e in evidence)),
            "recommendations": self._get_risk_recommendations(risk_level, evidence)
        }
    
    def _get_risk_recommendations(self, risk_level: str, evidence: List[Dict[str, Any]]) -> List[str]:
        """Get risk mitigation recommendations"""
        recommendations = []
        
        if risk_level == "HIGH":
            recommendations.extend([
                "Immediate investigation required",
                "Consider suspending meter",
                "Implement additional monitoring",
                "Review recent readings manually"
            ])
        elif risk_level == "MEDIUM":
            recommendations.extend([
                "Increase monitoring frequency",
                "Review meter configuration",
                "Check for system anomalies"
            ])
        elif risk_level == "LOW":
            recommendations.extend([
                "Continue normal monitoring",
                "Review evidence periodically"
            ])
        
        return recommendations
    
    def _analysis_loop(self):
        """Background analysis loop"""
        while True:
            try:
                time.sleep(60)  # Run every minute
                self._perform_background_analysis()
            except Exception as e:
                logging.error(f"Background analysis error: {e}")
    
    def _perform_background_analysis(self):
        """Perform background forensic analysis"""
        # Analyze patterns across all meters
        # Detect coordinated attacks
        # Update risk assessments
        pass
    
    def get_system_forensics(self) -> Dict[str, Any]:
        """Get system-wide forensic analysis"""
        with sqlite3.connect(self.db_path) as conn:
            # Get system statistics
            cursor = conn.execute("""
                SELECT COUNT(*) as total_evidence,
                       COUNT(DISTINCT meter_id) as affected_meters,
                       AVG(severity) as avg_severity
                FROM forensic_evidence
            """)
            
            stats = cursor.fetchone()
            
            # Get top evidence types
            cursor = conn.execute("""
                SELECT evidence_type, COUNT(*) as count, AVG(severity) as avg_severity
                FROM forensic_evidence
                GROUP BY evidence_type
                ORDER BY count DESC
                LIMIT 10
            """)
            
            top_evidence = []
            for row in cursor.fetchall():
                top_evidence.append({
                    "type": row[0],
                    "count": row[1],
                    "avg_severity": round(row[2], 3)
                })
            
            return {
                "total_evidence": stats[0],
                "affected_meters": stats[1],
                "average_severity": round(stats[2], 3),
                "top_evidence_types": top_evidence,
                "active_meters": len(self.meter_profiles),
                "analysis_timestamp": time.time()
            }