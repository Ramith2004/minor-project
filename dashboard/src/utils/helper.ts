import { format, formatDistanceToNow } from 'date-fns';

export const formatTimestamp = (ts: number): string => {
    return format(new Date(ts * 1000), 'MMM dd, yyyy HH:mm:ss');
};

export const formatRelativeTime = (ts: number): string => {
    return formatDistanceToNow(new Date(ts * 1000), { addSuffix: true });
};

export const formatValue = (value: number, decimals: number = 2): string => {
    return value.toFixed(decimals);
};

export const getSeverityColor = (score: number): string => {
    if (score >= 0.8) return 'text-red-600 bg-red-100';
    if (score >= 0.6) return 'text-orange-600 bg-orange-100';
    if (score >= 0.4) return 'text-yellow-600 bg-yellow-100';
    return 'text-green-600 bg-green-100';
};

export const getSeverityLabel = (score: number): string => {
    if (score >= 0.8) return 'Critical';
    if (score >= 0.6) return 'High';
    if (score >= 0.4) return 'Medium';
    return 'Low';
};