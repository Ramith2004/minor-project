export interface Reading {
    meterID: string;
    meterName?: string;
    seq: number;
    ts: number;
    value: number;
    raw?: string;
    blockchain_hash?: string;
    suspicious: boolean;  // ✅ Changed from number to boolean
    score: number;
    reasons?: string[];
    received_at: number;
}

export interface Alert {
    meterID: string;
    meterName?: string;
    seq: number;
    ts: number;
    value: number;
    blockchain_hash?: string;
    score: number;
    reasons: string[];
    received_at: number;
}

export interface Meter {
    last_update?: number;
    recent_suspicious_count: number;
    average_score: any;
    meterID: string;
    total_readings: number;
    suspicious_count: number;
    last_seq: number;
    last_ts?: number;
    avg_score: number;
}

export interface MeterDetails extends Meter {
    last_update?: number;
    average_score: number;
    recent_readings: Reading[];
}

export interface DashboardSummary {
    total_readings: number;
    total_suspicious: number;
    total_meters: number;
    suspicious_percentage: number;
    avg_suspicious_score: number;
    recent_alerts: Alert[];
    total_requests: number;
    successful_requests: number;
    failed_requests: number;
    suspicious_readings: number;
    blockchain_transactions: number;
    rate_limited_requests: number;
}

export interface SystemStats {
    total_requests: number;
    successful_requests: number;
    failed_requests: number;
    suspicious_readings: number;
    blockchain_transactions: number;
    rate_limited_requests: number;
    components: {
        blockchain: boolean;
        rate_limiter: boolean;
        forensics: boolean;
        ids: boolean;
        sse: boolean;
    };
    rate_limiter_stats?: {
        active_limiters: number;
        total_blocked: number;
    };
}

export interface HealthStatus {
    status: 'healthy' | 'degraded' | 'unhealthy';
    timestamp: number;
    version: string;
    components: {
        database: boolean;
        ids: boolean;
        blockchain: boolean;
        rate_limiter: boolean;
        forensics: boolean;
        sse: boolean;
    };
}

export interface SSEEvent {
    event: string;
    data: Reading | Alert;
    timestamp: number;
}

export interface ForensicAnalysis {
    meterID: string;
    analysis_timestamp: number;
    anomalies_detected: number;
    risk_level: 'low' | 'medium' | 'high' | 'critical';
    findings: string[];
}

export interface LogEntry {
    timestamp: number;
    level: string;
    message: string;
    request_id?: string;
}