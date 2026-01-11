import { useEffect, useRef, useState } from 'react';
import { WebSocketMessage } from '@/types';

interface UseWebSocketOptions {
    scanId: string;
    onMessage?: (msg: WebSocketMessage) => void;
    enabled?: boolean;
}

export function useWebSocket({ scanId, onMessage, enabled = true }: UseWebSocketOptions) {
    // Use env var or default to localhost:8000
    const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/api/v1';

    const ws = useRef<WebSocket | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!enabled || !scanId) return;

        const url = `${WS_URL}/ws/${scanId}`;
        console.log('Connecting to WebSocket:', url);

        try {
            ws.current = new WebSocket(url);

            ws.current.onopen = () => {
                console.log('WebSocket Connected');
                setIsConnected(true);
                setError(null);
            };

            ws.current.onclose = () => {
                console.log('WebSocket Disconnected');
                setIsConnected(false);
            };

            ws.current.onerror = (event) => {
                console.error('WebSocket Error:', event);
                setError('Connection failed');
            };

            ws.current.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (onMessage) {
                        onMessage(data);
                    }
                } catch (e) {
                    console.error('Failed to parse WS message:', event.data);
                }
            };
        } catch (e: any) {
            setError(e.message);
        }

        return () => {
            if (ws.current) {
                ws.current.close();
            }
        };
    }, [scanId, enabled, WS_URL]);

    const sendMessage = (msg: any) => {
        if (ws.current && isConnected) {
            ws.current.send(JSON.stringify(msg));
        }
    };

    return { isConnected, error, sendMessage };
}
