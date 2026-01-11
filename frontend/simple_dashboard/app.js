// Configuration
const API_URL = 'http://localhost:8000/api/v1';
const WS_URL = 'ws://localhost:8000/api/v1/events/ws'; // Adjust endpoint if needed

// State
let activeSocket = null;
let currentScanId = null;
let currentProjectId = null; // We need this for the graph
let allScans = []; // cache
let graphNetwork = null; // logic for vis.network

// DOM Elements
const els = {
    btnNewScan: document.getElementById('btn-new-scan'),
    modalNewScan: document.getElementById('modal-new-scan'),
    formScan: document.getElementById('form-scan'),
    closeBtns: document.querySelectorAll('.close-modal'),
    scanList: document.getElementById('scan-list'),
    terminal: document.getElementById('terminal-feed'),
    appStatus: document.getElementById('ws-status'),
    activeCount: document.getElementById('active-scan-count')
};

// Utils
const log = (msg, type = 'system') => {
    const div = document.createElement('div');
    div.className = `log-entry ${type}`;
    const ts = new Date().toISOString().split('T')[1].split('.')[0];
    div.innerHTML = `<span class="ts">[${ts}]</span> ${msg}`;
    els.terminal.appendChild(div);
    els.terminal.scrollTop = els.terminal.scrollHeight;
};

// API
const api = {
    getScans: async () => {
        try {
            const res = await fetch(`${API_URL}/scans/`);
            return await res.json();
        } catch (e) {
            log('Error fetching scans: ' + e.message, 'error');
            return [];
        }
    },
    createScan: async (name, target, instructions) => {
        const res = await fetch(`${API_URL}/scans/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, config: { target, instructions } })
        });
        if (!res.ok) throw new Error('Failed to create scan');
        return await res.json();
    },
    startScan: async (scanId) => {
        await fetch(`${API_URL}/scans/${scanId}/start`, { method: 'POST' });
    },
    getGraph: async (projectId) => {
        const res = await fetch(`${API_URL}/graph/${projectId}`);
        if (!res.ok) return { nodes: [], links: [] };
        return await res.json();
    }
};

// UI Logic
let selectedAgent = 'Manager';

window.selectAgent = (agentName) => {
    selectedAgent = agentName;

    // Update Tree UI
    document.querySelectorAll('.tree-item').forEach(el => {
        el.classList.remove('active');
        if (el.textContent.includes(agentName)) el.classList.add('active');
    });

    // Update Header
    document.querySelector('.section-header h3').innerHTML =
        `<span class="indicator active"></span> LIVE_FEED // ${agentName.toUpperCase()}`;

    // Filter Logs (Mock logic for prototype)
    const logs = document.querySelectorAll('.log-entry');
    logs.forEach(log => {
        const source = log.querySelector('.source')?.textContent || "";
        if (agentName === 'Manager') {
            log.style.display = 'block'; // Manager sees all
        } else {
            // Show only logs from this agent or system logs
            if (source.includes(agentName.toUpperCase()) || source.includes('SYSTEM')) {
                log.style.display = 'block';
            } else {
                log.style.display = 'none';
            }
        }
    });

    // Update Chat Placeholder
    document.getElementById('chat-input').placeholder = `Talk to ${agentName}...`;
};

window.switchTab = (tabName) => {
    // Hide all panes
    document.querySelectorAll('.content-pane').forEach(el => el.style.display = 'none');
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));

    // Show active
    document.getElementById(`pane-${tabName}`).style.display = 'block';

    // Find button (hacky selector)
    const btns = document.querySelectorAll('.tab-btn');
    if (tabName === 'feed') btns[0].classList.add('active');
    if (tabName === 'hive') {
        btns[1].classList.add('active');
        if (currentProjectId) renderHiveGraph(currentProjectId);
    }
};

const renderHiveGraph = async (projectId) => {
    if (!projectId) return;

    log('Fetching Hive Mind data...', 'system');
    const data = await api.getGraph(projectId);

    // Transform for VIS.JS if needed?
    // Our API returns { nodes: [{id, label, group}], links: [{source, target}] }
    // Vis expects { nodes: [], edges: [] } with 'from', 'to'

    const nodes = new vis.DataSet(data.nodes.map(n => ({
        id: n.id,
        label: n.label,
        group: n.group,
        value: n.val,
        color: n.group === 'domain' ? '#00ff41' : (n.group === 'finding' ? '#ff3333' : '#0088ff')
    })));

    const edges = new vis.DataSet(data.links.map(l => ({
        from: l.source,
        to: l.target,
        arrows: 'to',
        color: { color: '#444' }
    })));

    const container = document.getElementById('hive-graph');
    const graphData = { nodes, edges };
    const options = {
        nodes: {
            shape: 'dot',
            font: { color: '#ffffff', face: 'monospace' }
        },
        physics: {
            stabilization: false,
            barnesHut: {
                gravitationalConstant: -8000
            }
        },
        interaction: { hover: true, tooltipDelay: 200 }
    };

    if (graphNetwork) {
        graphNetwork.setData(graphData);
    } else {
        graphNetwork = new vis.Network(container, graphData, options);
    }

    log(`Graph rendered: ${nodes.length} nodes, ${edges.length} edges.`, 'system');
};

const renderScans = (scans) => {
    els.scanList.innerHTML = '';
    let runningCount = 0;

    if (scans.length === 0) {
        els.scanList.innerHTML = '<div class="empty-state">No active operations.</div>';
        return;
    }

    scans.forEach(scan => {
        if (scan.status === 'RUNNING') runningCount++;

        const div = document.createElement('div');
        div.className = `scan-item ${scan.status}`;
        div.innerHTML = `
            <div>
                <h4>${scan.name}</h4>
                <p>${scan.config.target || 'No target'}</p>
            </div>
            <div>
                <span class="scan-status">${scan.status}</span>
                ${scan.status === 'CREATED' || scan.status === 'PAUSED' ?
                `<button class="btn secondary small" onclick="startScan('${scan.id}')">START</button>` : ''}
                ${scan.status === 'RUNNING' ?
                `<button class="btn secondary small" onclick="listen('${scan.id}')">MONITOR</button>` : ''}
            </div>
        `;
        els.scanList.appendChild(div);
    });

    els.activeCount.textContent = runningCount;
};

// WebSocket
const connectWS = (scanId) => {
    if (activeSocket) {
        activeSocket.close();
    }

    // Connect to specific scan channel
    // Endpoint config might need adjustment based on backend implementation
    const url = `${WS_URL}/${scanId}`;
    log(`Connecting to Hive Mind uplink: ${scanId}...`);

    activeSocket = new WebSocket(url);

    activeSocket.onopen = () => {
        els.appStatus.textContent = 'CONNECTED';
        els.appStatus.classList.add('connected');
        log('Uplink established.', 'system');
    };

    activeSocket.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        // Handle Event Types
        if (msg.type === 'tool_start') {
            log(`> Executing: ${msg.data.tool}`, 'tool_start');
        } else if (msg.type === 'tool_complete') {
            log(`✓ Completed: ${msg.data.tool}`, 'tool_complete');
            if (msg.data.result.output) {
                log(`  Output: ${msg.data.result.output.substring(0, 100)}...`, 'system');
            }
        } else {
            log(JSON.stringify(msg.data), 'system');
        }
    };

    activeSocket.onclose = () => {
        els.appStatus.textContent = 'DISCONNECTED';
        els.appStatus.classList.remove('connected');
        log('Uplink lost.', 'error');
    };
};

// Actions
window.startScan = async (id) => {
    log(`Initializing sequence for ${id}...`);
    await api.startScan(id);
    refresh();
    listen(id);
};

window.listen = (id) => {
    currentScanId = id;

    // Find project ID
    const scan = allScans.find(s => s.id === id);
    if (scan) {
        currentProjectId = scan.project_id;
        document.querySelector('.section-header h3').innerHTML =
            `<span class="indicator active"></span> OPERATION // ${scan.name.toUpperCase()}`;
    }

    connectWS(id);
};

const refresh = async () => {
    const scans = await api.getScans();
    allScans = scans; // cache
    renderScans(scans);
};

// Init
const init = async () => {
    // Event Listeners
    els.btnNewScan.onclick = () => els.modalNewScan.classList.remove('hidden');
    els.closeBtns.forEach(b => b.onclick = () => els.modalNewScan.classList.add('hidden'));

    els.formScan.onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        try {
            const newScan = await api.createScan(
                fd.get('name'),
                fd.get('target'),
                fd.get('instructions')
            );
            log(`Operation created: ${newScan.name}`);
            els.modalNewScan.classList.add('hidden');
            refresh();
        } catch (err) {
            alert(err.message);
        }
    };

    // Initial Load
    await refresh();
    setInterval(refresh, 5000); // Poll status every 5s
};

init();
