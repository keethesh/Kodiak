export type ScanStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'PAUSED';

export interface ScanJob {
    id: string;
    name: string;
    status: ScanStatus;
    config: Record<string, any>;
    created_at: string;
}

export interface LogMessage {
    scan_id: string;
    level: 'INFO' | 'WARNING' | 'ERROR' | 'DEBUG';
    message: string;
    timestamp: string;
    source: string; // e.g., 'Orchestrator', 'Nmap'
}

export interface WebSocketMessage {
    type: 'log' | 'status_update' | 'finding';
    payload: any;
}
