import axios from 'axios';
import type {
    Reading,
    Alert,
    Meter,
    MeterDetails,
    DashboardSummary,
    SystemStats,
    HealthStatus,
    ForensicAnalysis
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:5000';

const apiClient = axios.create({
    baseURL: API_BASE_URL,
    timeout: 10000,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Response interceptor for error handling
apiClient.interceptors.response.use(
    (response) => response,
    (error) => {
        console.error('API Error:', error.response?.data || error.message);
        return Promise.reject(error);
    }
);

export const api = {
    // ========== DASHBOARD ENDPOINTS ==========

    // Dashboard Summary
    getSummary: async (): Promise<DashboardSummary> => {
        const { data } = await apiClient.get('/api/dashboard/summary');
        return data.summary;
    },

    // Meters
    getMeters: async (): Promise<Meter[]> => {
        const { data } = await apiClient.get('/api/dashboard/meters');
        return data.meters;
    },

    getMeterDetails: async (meterID: string): Promise<MeterDetails> => {
        const { data } = await apiClient.get(`/api/dashboard/meters/${meterID}`);
        return data.meter;
    },

    // Readings
    getReadings: async (params?: {
        meterID?: string;
        limit?: number;
        offset?: number;
        ts_from?: number;
        ts_to?: number;
    }): Promise<Reading[]> => {
        const { data } = await apiClient.get('/api/dashboard/readings', { params });
        return data.readings;
    },

    getLatestReadings: async (limit: number = 20): Promise<Reading[]> => {
        const { data } = await apiClient.get('/api/dashboard/latest', {
            params: { limit },
        });
        return data.readings;
    },

    // Alerts
    getAlerts: async (params?: {
        meterID?: string;
        min_score?: number;
        limit?: number;
        offset?: number;
        ts_from?: number;
        ts_to?: number;
    }): Promise<Alert[]> => {
        const { data } = await apiClient.get('/api/dashboard/alerts', { params });
        return data.alerts;
    },

    // ========== SYSTEM ENDPOINTS ==========

    // System Statistics
    getStats: async (): Promise<SystemStats> => {
        const { data } = await apiClient.get('/stats');
        return data;
    },

    // Health Check
    getHealth: async (): Promise<HealthStatus> => {
        const { data } = await apiClient.get('/health');
        return data;
    },

    // Meter Status (single meter)
    getMeterStatus: async (meterID: string) => {
        const { data } = await apiClient.get(`/status/${meterID}`);
        return data;
    },

    // Forensic Analysis
    getForensics: async (meterID: string): Promise<ForensicAnalysis> => {
        const { data } = await apiClient.get(`/forensics/${meterID}`);
        return data;
    },

    // Blockchain Verification
    verifyOnBlockchain: async (meterID: string, sequence: number, verified: boolean = true) => {
        const { data } = await apiClient.post(`/blockchain/verify/${meterID}/${sequence}`, {
            verified,
        });
        return data;
    },
};

export default apiClient;