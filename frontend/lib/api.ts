const API_BASE = process.env.NEXT_PUBLIC_WS_URL?.replace('ws://', 'http://').replace('wss://', 'https://') || 'http://localhost:8000/api/v1';

export async function startScan(scanId: string) {
    const res = await fetch(`${API_BASE}/scans/${scanId}/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) throw new Error('Failed to start scan');
    return res.json();
}

export async function stopScan(scanId: string) {
    const res = await fetch(`${API_BASE}/scans/${scanId}/stop`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) throw new Error('Failed to stop scan');
    return res.json();
}

export async function createScan(name: string, target: string, instructions: string = "") {
    const res = await fetch(`${API_BASE}/scans/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name,
            config: {
                target,
                instructions
            }
        })
    });
    if (!res.ok) throw new Error('Failed to create scan');
    return res.json();
}
