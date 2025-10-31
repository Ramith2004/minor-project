import { useEffect, useState, useCallback, useRef } from 'react';
import type { SSEEvent, Reading, Alert } from '../types';

const SSE_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:5000';

type SSECallback = (event: SSEEvent) => void;

export const useSSE = (endpoint: string, onMessage?: SSECallback) => {
    const [connected, setConnected] = useState(false);
    const [lastEvent, setLastEvent] = useState<SSEEvent | null>(null);
    const [error, setError] = useState<string | null>(null);
    const eventSourceRef = useRef<EventSource | null>(null);

    const connect = useCallback(() => {
        if (eventSourceRef.current) {
            eventSourceRef.current.close();
        }

        const url = `${SSE_BASE_URL}${endpoint}`;
        console.log('Connecting to SSE:', url);

        const eventSource = new EventSource(url);
        eventSourceRef.current = eventSource;

        eventSource.onopen = () => {
            console.log('SSE Connected:', endpoint);
            setConnected(true);
            setError(null);
        };

        eventSource.onerror = (err) => {
            console.error('SSE Error:', err);
            setConnected(false);
            setError('Connection lost');

            // Reconnect after 5 seconds
            setTimeout(() => {
                if (eventSourceRef.current === eventSource) {
                    connect();
                }
            }, 5000);
        };

        // ✅ FIX: Listen for backend's event names
        eventSource.addEventListener('new_reading', (event) => {
            try {
                const data = JSON.parse(event.data);
                const sseEvent: SSEEvent = {
                    event: 'new_reading',
                    data,
                    timestamp: Date.now(),
                };
                setLastEvent(sseEvent);
                onMessage?.(sseEvent);
            } catch (err) {
                console.error('Failed to parse SSE message:', err);
            }
        });

        eventSource.addEventListener('new_alert', (event) => {
            try {
                const data = JSON.parse(event.data);
                const sseEvent: SSEEvent = {
                    event: 'new_alert',
                    data,
                    timestamp: Date.now(),
                };
                setLastEvent(sseEvent);
                onMessage?.(sseEvent);
            } catch (err) {
                console.error('Failed to parse SSE message:', err);
            }
        });

        // Handle generic messages (connection, keepalive)
        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.event === 'connected') {
                    console.log('SSE stream ready:', data.stream);
                }
            } catch (err) {
                // Ignore parse errors for keepalive messages (comments)
            }
        };

        return () => {
            eventSource.close();
        };
    }, [endpoint, onMessage]);

    useEffect(() => {
        const cleanup = connect();
        return cleanup;
    }, [connect]);

    const disconnect = useCallback(() => {
        if (eventSourceRef.current) {
            eventSourceRef.current.close();
            eventSourceRef.current = null;
            setConnected(false);
        }
    }, []);

    return {
        connected,
        lastEvent,
        error,
        disconnect,
        reconnect: connect,
    };
};

// ✅ Specific hooks for different streams
export const useReadingsSSE = (onReading?: (reading: Reading) => void) => {
    return useSSE('/api/stream/readings', (event) => {
        if (event.event === 'new_reading') {
            onReading?.(event.data as Reading);
        }
    });
};

export const useAlertsSSE = (onAlert?: (alert: Alert) => void) => {
    return useSSE('/api/stream/alerts', (event) => {
        if (event.event === 'new_alert') {
            onAlert?.(event.data as Alert);
        }
    });
};

export const useMeterSSE = (
    meterID: string,
    onReading?: (reading: Reading) => void
) => {
    return useSSE(`/api/stream/meter/${meterID}`, (event) => {
        if (event.event === 'new_reading') {
            onReading?.(event.data as Reading);
        }
    });
};