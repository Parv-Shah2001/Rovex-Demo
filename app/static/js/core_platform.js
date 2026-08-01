/*
File: app/static/js/core_platform.js
Description: Page-specific behavior for the Rovex Core Platform dashboard. The
script manages the sticky sidebar shell, live fleet orchestration interactions,
chat command parsing, map rendering, and modal workflows.
*/


const token = window.RovexCommon.getStoredToken();
const userObj = window.RovexCommon.getStoredUser();
const SIDEBAR_COLLAPSE_KEY = 'rovex_core_sidebar_collapsed';
const CORRIDOR_WEIGHT_EDITOR_ROLES = new Set(['admin', 'supervisor', 'sub-supervisor']);

let nodesLayout = {};
let edgesLayout = [];
let canvas, ctx;

const apiRequest = window.RovexCommon.apiRequest;

function setModalVisibility(modalId, isVisible) {
    document.getElementById(modalId).classList.toggle('hidden', !isVisible);
}

function canModifyEdgeWeights() {
    return CORRIDOR_WEIGHT_EDITOR_ROLES.has(userObj.role);
}

function canProvisionHospitalUsers() {
    return userObj.role === 'supervisor';
}

function syncSidebarToggleIcon() {
    const toggleIcon = document.getElementById('sidebarToggleIcon');
    if (!toggleIcon) return;

    const isDesktop = window.innerWidth >= 768;
    const isCollapsed = document.body.classList.contains('sidebar-collapsed');
    const isMobileOpen = document.body.classList.contains('sidebar-mobile-open');

    if (isDesktop) {
        toggleIcon.className = `fa-solid ${isCollapsed ? 'fa-angles-right' : 'fa-angles-left'} text-sm`;
        return;
    }

    toggleIcon.className = `fa-solid ${isMobileOpen ? 'fa-xmark' : 'fa-bars-staggered'} text-sm`;
}

function applySidebarStateFromStorage() {
    if (window.innerWidth < 768) {
        document.body.classList.remove('sidebar-collapsed');
        return;
    }

    const shouldCollapse = localStorage.getItem(SIDEBAR_COLLAPSE_KEY) === 'true';
    document.body.classList.toggle('sidebar-collapsed', shouldCollapse);
}

function closeSidebarOverlay() {
    document.body.classList.remove('sidebar-mobile-open');
    syncSidebarToggleIcon();
}

function toggleSidebar() {
    if (window.innerWidth < 768) {
        document.body.classList.toggle('sidebar-mobile-open');
        syncSidebarToggleIcon();
        return;
    }

    const collapsed = document.body.classList.toggle('sidebar-collapsed');
    localStorage.setItem(SIDEBAR_COLLAPSE_KEY, collapsed ? 'true' : 'false');
    syncSidebarToggleIcon();
}

window.addEventListener('resize', () => {
    if (window.innerWidth >= 768) {
        document.body.classList.remove('sidebar-mobile-open');
        applySidebarStateFromStorage();
    }
    syncSidebarToggleIcon();
});

// On Load
window.addEventListener('DOMContentLoaded', async () => {
    // Check auth
    if (!token || !userObj.username) {
        alert("Session expired. Please log in first.");
        window.location.href = '/';
        return;
    }

    applySidebarStateFromStorage();
    syncSidebarToggleIcon();

    // Fill header and profile card details
    document.getElementById('userName').innerText = userObj.full_name;
    document.getElementById('welcomeName').innerText = userObj.full_name.split(' ')[1] || userObj.full_name;
    document.getElementById('userRoleBadge').innerText = userObj.role.toUpperCase();
    document.getElementById('userInitials').innerText = userObj.full_name.split(' ').map(n => n[0]).join('');
    document.getElementById('sidebarOrganizationLabel').innerText = userObj.organization || 'Hospital Fleet';

    // Hide/Show Admin Dashboard link based on role — only Rovex admins see it
    if (userObj.role === 'admin') {
        document.getElementById('adminPortalBtn').classList.remove('hidden');
    }

    if (canProvisionHospitalUsers()) {
        document.getElementById('supervisorUserAccessBtn').classList.remove('hidden');
        document.getElementById('createUserOrganization').value = userObj.organization;
    }

    document.getElementById('userCreateForm').addEventListener('submit', submitCreateUserForm);

    // Set up Canvas
    canvas = document.getElementById('hospitalCanvas');
    ctx = canvas.getContext('2d');

    // Load data
    await fetchMapLayout();
    await fetchTasks();
    await fetchFleetSummary();
    await fillFormSelectors();
});

// Logout
function handleLogout() {
    window.RovexCommon.logout('/');
}

// Toggle Recurrence input
function toggleRecurrence() {
    const checked = document.getElementById('isRecurring').checked;
    const target = document.getElementById('recurrenceSelector');
    if (checked) {
        target.classList.remove('hidden');
    } else {
        target.classList.add('hidden');
    }
}

// Modals management
function openScheduleModal() {
    setModalVisibility('scheduleModal', true);
}
function closeScheduleModal() {
    setModalVisibility('scheduleModal', false);
}
function openServiceModal() {
    setModalVisibility('serviceModal', true);
}
function closeServiceModal() {
    setModalVisibility('serviceModal', false);
}
function openWeightModal() {
    const submitBtn = document.getElementById('weightSubmitBtn');
    const rbacWarning = document.getElementById('weightRbacWarning');

    setModalVisibility('weightModal', true);
    submitBtn.disabled = !canModifyEdgeWeights();
    submitBtn.classList.toggle('opacity-50', !canModifyEdgeWeights());
    submitBtn.classList.toggle('cursor-not-allowed', !canModifyEdgeWeights());
    rbacWarning.classList.toggle('hidden', canModifyEdgeWeights());
}
function closeWeightModal() {
    setModalVisibility('weightModal', false);
}
function openUserCreateModal() {
    setModalVisibility('userCreateModal', true);
}
function closeUserCreateModal() {
    setModalVisibility('userCreateModal', false);
    document.getElementById('userCreateErrorBox').classList.add('hidden');
}

async function submitCreateUserForm(event) {
    event.preventDefault();
    const errorBox = document.getElementById('userCreateErrorBox');
    errorBox.classList.add('hidden');

    const payload = {
        full_name: document.getElementById('createUserFullName').value.trim(),
        username: document.getElementById('createUserUsername').value.trim(),
        email: document.getElementById('createUserEmail').value.trim(),
        password: document.getElementById('createUserPassword').value,
        role: document.getElementById('createUserRole').value,
        organization: document.getElementById('createUserOrganization').value.trim(),
    };

    try {
        await apiRequest('/api/users/register', {
            method: 'POST',
            body: payload,
        });
        document.getElementById('userCreateForm').reset();
        document.getElementById('createUserOrganization').value = userObj.organization;
        closeUserCreateModal();
        appendChatBubble('Rovex AI Dispatcher', `Hospital access account <span class="font-bold text-slate-200">${payload.username}</span> was created successfully with role <span class="font-bold text-slate-200">${payload.role}</span> for ${payload.organization}.`, false);
    } catch (error) {
        errorBox.innerText = error.message || 'Failed to create hospital user.';
        errorBox.classList.remove('hidden');
        console.error(error);
    }
}

// Clear Conversation Log
function clearChat() {
    const chatHistory = document.getElementById('chatHistory');
    const welcome = document.getElementById('welcomeContainer');
    chatHistory.innerHTML = '';
    chatHistory.classList.add('hidden');
    welcome.classList.remove('hidden');
}

async function fetchFleetSummary() {
    const fleetPanel = document.getElementById('fleetSummaryPanel');
    if (!fleetPanel) return;

    try {
        const fleets = await apiRequest('/api/robots/fleets');
        if (!fleets.length) {
            fleetPanel.innerHTML = '<div class="text-slate-500">No fleet registry data available.</div>';
            return;
        }

        const totalRobots = fleets.reduce((sum, fleet) => sum + fleet.total_robot_count, 0);
        const totalIdle = fleets.reduce((sum, fleet) => sum + fleet.idle_robot_count, 0);
        const totalUnsanctioned = fleets.reduce((sum, fleet) => sum + fleet.unsanctioned_robot_count, 0);
        const fleetRows = fleets.map((fleet) => `
            <div class="border border-slate-800 rounded-lg p-3 bg-slate-950/40">
                <div class="flex justify-between items-start gap-3">
                    <div>
                        <div class="text-[11px] font-bold text-white">${fleet.fleet_name}</div>
                        <div class="text-[10px] text-slate-500 font-mono-custom">${fleet.fleet_id}</div>
                    </div>
                    <span class="text-[10px] px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">${fleet.total_robot_count} robots</span>
                </div>
                <div class="mt-2 text-[10px] text-slate-400 flex justify-between">
                    <span>Idle ready: <span class="text-emerald-400 font-semibold">${fleet.idle_robot_count}</span></span>
                    <span>Unsanctioned: <span class="text-rose-400 font-semibold">${fleet.unsanctioned_robot_count}</span></span>
                </div>
            </div>
        `).join('');

        fleetPanel.innerHTML = `
            <div class="grid grid-cols-3 gap-2 text-center">
                <div class="bg-slate-950/60 rounded-lg border border-slate-800 p-2">
                    <span class="block text-[9px] uppercase tracking-wider text-slate-500">Fleets</span>
                    <span class="text-sm font-bold text-white">${fleets.length}</span>
                </div>
                <div class="bg-slate-950/60 rounded-lg border border-slate-800 p-2">
                    <span class="block text-[9px] uppercase tracking-wider text-slate-500">Robots</span>
                    <span class="text-sm font-bold text-white">${totalRobots}</span>
                </div>
                <div class="bg-slate-950/60 rounded-lg border border-slate-800 p-2">
                    <span class="block text-[9px] uppercase tracking-wider text-slate-500">Idle Ready</span>
                    <span class="text-sm font-bold text-emerald-400">${totalIdle}</span>
                </div>
            </div>
            <div class="text-[10px] text-slate-500">Unsanctioned robots across this organization: <span class="text-rose-400 font-semibold">${totalUnsanctioned}</span></div>
            <div class="space-y-2">${fleetRows}</div>
        `;
    } catch (error) {
        fleetPanel.innerHTML = '<div class="text-rose-400">Failed to load fleet registry.</div>';
        console.error(error);
    }
}

// Auto fills dropdown options
async function fillFormSelectors() {
    const nodes = Object.keys(nodesLayout);

    const sourceSelect = document.getElementById('sourceNode');
    const targetSelect = document.getElementById('targetNode');
    const weightA = document.getElementById('weightNodeA');
    const weightB = document.getElementById('weightNodeB');

    sourceSelect.innerHTML = '';
    targetSelect.innerHTML = '';
    weightA.innerHTML = '';
    weightB.innerHTML = '';

    nodes.forEach(n => {
        sourceSelect.add(new Option(n, n));
        targetSelect.add(new Option(n, n));
        weightA.add(new Option(n, n));
        weightB.add(new Option(n, n));
    });
    // default offsets
    targetSelect.selectedIndex = 1;
    weightB.selectedIndex = 1;

    // Load robot list options
    try {
        const robots = await apiRequest('/api/robots');
        const rSelect = document.getElementById('assignRobot');
        const sSelect = document.getElementById('serviceRobot');
        rSelect.innerHTML = '<option value="">Auto-assign (Idle with highest battery)</option>';
        sSelect.innerHTML = '';
        robots.forEach(r => {
            if (r.sanctioned && r.status === 'idle') {
                rSelect.add(new Option(`${r.robot_id} (${r.battery}%)`, r.robot_id));
            }
            sSelect.add(new Option(r.robot_id, r.robot_id));
        });
    } catch (err) {
        console.error(err);
    }
}

// Fetch hospital floor map coordinates
async function fetchMapLayout() {
    try {
        const data = await apiRequest('/api/robots/graph/layout');
        nodesLayout = data.nodes;
        edgesLayout = data.edges;
        drawMap();
    } catch (err) {
        console.error(err);
    }
}

// Draw 2D hospital map coordinates to Canvas
function drawMap(highlightPath = []) {
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Bounds for normalizing coordinates (hospital dimensions are roughly 15x15 meters)
    const margin = 50;
    const xMin = -1, xMax = 12, yMin = -1, yMax = 16;
    const scaleX = (canvas.width - 2 * margin) / (xMax - xMin);
    const scaleY = (canvas.height - 2 * margin) / (yMax - yMin);

    const mapX = (x) => margin + (x - xMin) * scaleX;
    const mapY = (y) => canvas.height - margin - (y - yMin) * scaleY; // flip Y for standard screen space

    // 1. Draw connections / corridors (edges)
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 2.5;
    edgesLayout.forEach(edge => {
        const p1 = nodesLayout[edge.from];
        const p2 = nodesLayout[edge.to];
        if (p1 && p2) {
            ctx.beginPath();
            ctx.moveTo(mapX(p1.x), mapY(p1.y));
            ctx.lineTo(mapX(p2.x), mapY(p2.y));
            ctx.stroke();

            // Render weight metric text midway
            ctx.fillStyle = '#64748b';
            ctx.font = '9px Fira Code';
            const midX = (mapX(p1.x) + mapX(p2.x)) / 2;
            const midY = (mapY(p1.y) + mapY(p2.y)) / 2;
            ctx.fillText(edge.weight, midX, midY - 4);
        }
    });

    // 2. Draw active highlighted optimal route line (A* output)
    if (highlightPath.length > 0) {
        ctx.strokeStyle = '#6366f1'; // bright indigo
        ctx.lineWidth = 4;
        ctx.beginPath();
        for (let i = 0; i < highlightPath.length; i++) {
            const p = nodesLayout[highlightPath[i]];
            if (p) {
                if (i === 0) {
                    ctx.moveTo(mapX(p.x), mapY(p.y));
                } else {
                    ctx.lineTo(mapX(p.x), mapY(p.y));
                }
            }
        }
        ctx.stroke();
    }

    // 3. Draw nodes
    for (const [name, coord] of Object.entries(nodesLayout)) {
        const isHighlighted = highlightPath.includes(name);

        // Outer glow
        ctx.beginPath();
        ctx.arc(mapX(coord.x), mapY(coord.y), isHighlighted ? 10 : 6, 0, 2 * Math.PI);
        ctx.fillStyle = isHighlighted ? 'rgba(99, 102, 241, 0.25)' : 'rgba(16, 185, 129, 0.15)';
        ctx.fill();

        // Inner circle
        ctx.beginPath();
        ctx.arc(mapX(coord.x), mapY(coord.y), isHighlighted ? 5 : 4, 0, 2 * Math.PI);
        ctx.fillStyle = isHighlighted ? '#6366f1' : '#10b981';
        ctx.fill();

        // Text labels
        ctx.fillStyle = isHighlighted ? '#ffffff' : '#94a3b8';
        ctx.font = isHighlighted ? 'bold 10px Plus Jakarta Sans' : '9px Plus Jakarta Sans';
        ctx.fillText(name, mapX(coord.x) + 8, mapY(coord.y) + 3);
    }
}

// Fetch user organization scheduled tasks
async function fetchTasks() {
    try {
        const tasks = await apiRequest('/api/tasks');

        // Filter for active (ongoing or pending) tasks
        const activeTasks = tasks.filter(t => t.status === 'ongoing' || t.status === 'pending');
        const taskListEl = document.getElementById('ongoingMissionsList');

        if (activeTasks.length === 0) {
            taskListEl.innerHTML = '<div class="text-center py-4 text-xs text-slate-600">No active tasks.</div>';
            await fetchFleetSummary();
            return;
        }

        let html = '';
        activeTasks.forEach(t => {
            html += `
            <div class="bg-slate-900 border border-slate-800 p-3.5 rounded-xl space-y-2 relative group overflow-hidden">
                <div class="flex justify-between items-start">
                    <div>
                        <span class="text-[10px] font-mono-custom text-slate-500 font-bold uppercase block">${t.id}</span>
                        <span class="text-xs font-bold text-white">${t.source_node} &rarr; ${t.target_node}</span>
                    </div>
                    <span class="text-[9px] font-bold px-2 py-0.5 rounded ${
                        t.status === 'ongoing' ? 'bg-indigo-950 text-indigo-400 border border-indigo-900/30 animate-pulse' : 'bg-slate-800 text-slate-400'
                    }">
                        ${t.status.toUpperCase()}
                    </span>
                </div>

                <div class="flex items-center justify-between text-[10px] text-slate-400 pt-1">
                    <span>Robot: <span class="font-bold text-slate-300 font-mono-custom">${t.robot_id || 'Auto-assigning'}</span></span>
                    <span>ETA: <span class="font-bold text-emerald-400 font-mono-custom">${t.eta_minutes} min</span></span>
                </div>

                <div class="flex space-x-2 pt-1.5 border-t border-slate-950">
                    <button onclick="triggerTransitSimulation('${t.id}')" class="flex-grow text-center py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-[10px] font-bold transition">
                        <i class="fa-solid fa-play mr-1"></i> Simulate Transit Steps
                    </button>
                    <button onclick="cancelTask('${t.id}')" class="px-2 py-1.5 rounded bg-slate-950 hover:bg-rose-950/20 text-slate-500 hover:text-rose-400 border border-slate-800 transition">
                        <i class="fa-solid fa-ban"></i>
                    </button>
                </div>
            </div>
            `;
        });
        taskListEl.innerHTML = html;
        await fetchFleetSummary();
    } catch (err) {
        console.error(err);
    }
}

// Dispatch scheduler request
document.getElementById('schedulerForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const source_node = document.getElementById('sourceNode').value;
    const target_node = document.getElementById('targetNode').value;
    const robot_id = document.getElementById('assignRobot').value || null;
    const scheduled_time = document.getElementById('scheduledTime').value;
    const is_recurring = document.getElementById('isRecurring').checked;
    const recurrence_interval = is_recurring ? document.getElementById('recurrenceInterval').value : 'none';

    try {
        const task = await apiRequest('/api/tasks', {
            method: 'POST',
            body: { source_node, target_node, robot_id, scheduled_time, is_recurring, recurrence_interval }
        });

        closeScheduleModal();
        await fetchTasks();
        await fillFormSelectors();

        const path = JSON.parse(task.path);
        drawMap(path);
        await triggerPathfinderCalculation(source_node, target_node);

        appendChatBubble('Rovex AI Dispatcher', `Stretcher transport scheduled successfully under ID <span class="font-bold text-slate-200 font-mono-custom">${task.id}</span>. Optimal transit A* path generated: ${path.join(' &rarr; ')}. ETA computed at ${task.eta_minutes} minutes. Click "Simulate Transit Steps" in the sidebar to execute the hardware sequence!`, false);
    } catch (e) {
        alert("Dispatched schedule failed: " + e.message);
        console.error(e);
    }
});

// Maintenance form submission
document.getElementById('serviceForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const robot_id = document.getElementById('serviceRobot').value;
    const issue_description = document.getElementById('issueDescription').value;

    try {
        await apiRequest('/api/tasks/service-request', {
            method: 'POST',
            body: { robot_id, issue_description }
        });

        closeServiceModal();
        alert(`Maintenance request filed for ${robot_id}. This robot is now set to an emergency status 'error' and has been suspended from scheduled duties.`);
        await fillFormSelectors();
        appendChatBubble('Rovex AI Dispatcher', `Emergency Alert! Maintenance request successfully registered for robot <span class="font-bold font-mono-custom text-slate-200">${robot_id}</span>. Reason: "${issue_description}". The robot has been taken offline.`, false);
    } catch (e) {
        alert(e.message);
        console.error(e);
    }
});

// Edge Weight modifying form submission
document.getElementById('weightForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const node_a = document.getElementById('weightNodeA').value;
    const node_b = document.getElementById('weightNodeB').value;
    const weight = parseFloat(document.getElementById('weightVal').value);

    try {
        await apiRequest('/api/robots/graph/edge', {
            method: 'PUT',
            body: { node_a, node_b, weight }
        });

        closeWeightModal();
        await fetchMapLayout();
        appendChatBubble('Rovex AI Dispatcher', `Orchestrator adjusted path weight: Corridor link [${node_a} <-> ${node_b}] has been updated to weight ${weight}. This will dynamically force robots onto lower-weighted paths.`, false);
    } catch (e) {
        alert(e.message);
        console.error(e);
    }
});

// Cancel Task
async function cancelTask(taskId) {
    if (!confirm(`Are you sure you want to cancel transport task ${taskId}?`)) return;
    try {
        await apiRequest(`/api/tasks/${taskId}/cancel`, { method: 'POST' });
        await fetchTasks();
        await fillFormSelectors();
        appendChatBubble('Rovex AI Dispatcher', `Task ${taskId} was cancelled. Associated robot has been freed.`, false);
    } catch (e) {
        console.error(e);
    }
}

// Trigger step transit simulation (calls POST /api/tasks/{task_id}/execute)
async function triggerTransitSimulation(taskId) {
    appendChatBubble('Rovex AI Dispatcher', `Starting real-time physical transit simulation for Task ${taskId}...`, false);
    try {
        const task = await apiRequest(`/api/tasks/${taskId}/execute`, { method: 'POST' });
        const path = JSON.parse(task.path);

        // Simulate visual step progress
        let stepIdx = 0;
        const interval = setInterval(() => {
            if (stepIdx < path.length) {
                const activeNodes = path.slice(0, stepIdx + 1);
                drawMap(activeNodes);
                stepIdx++;
            } else {
                clearInterval(interval);
                fetchTasks();
                fillFormSelectors();
                drawMap(path);
                appendChatBubble('Rovex AI Dispatcher', `Simulation Completed! Task ${taskId} successfully finished. Robot arrived at destination node <span class="font-bold text-white">${path[path.length - 1]}</span> and is now idling. Check Admin Logs for detailed logs.`, false);
            }
        }, 1000);
    } catch (e) {
        alert("Transit simulation failed: " + e.message);
        console.error(e);
    }
}

// Run Path Finder Calculation Details visually
async function triggerPathfinderCalculation(start_node, goal_node) {
    try {
        const data = await apiRequest('/api/robots/path-planning', {
            method: 'POST',
            body: { start_node, goal_node }
        });

        document.getElementById('patherStatus').innerText = "Path solved successfully!";
        document.getElementById('patherDist').innerText = data.total_distance_meters + 'm';
        document.getElementById('patherCost').innerText = data.total_cost;
        document.getElementById('patherSteps').innerText = data.steps_taken;

        document.getElementById('pathDisplay').innerHTML = data.path.join(' &rarr; ');

        let hConsole = '';
        data.algorithm_steps.forEach((step, idx) => {
            hConsole += `[Step ${idx+1}] Node: ${step.current_node.padEnd(16)} | g(n)=${step.g_score.toFixed(1).padEnd(5)} | h(n)=${step.heuristic.toFixed(1).padEnd(5)} | f(n)=${step.f_score.toFixed(1).padEnd(5)}\n`;
        });
        document.getElementById('heuristicConsole').innerText = hConsole;

        drawMap(data.path);
    } catch (err) {
        console.error(err);
    }
}

// Gemini AI Assistant Chat Box Logic
document.getElementById('chatForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = document.getElementById('chatInput');
    const prompt = input.value.trim();
    if (!prompt) return;

    input.value = '';
    await executeAssistantCommand(prompt);
});

// Trigger prompt via bubble click
async function useQuickPrompt(text) {
    await executeAssistantCommand(text);
}

// Parse user chat commands
async function executeAssistantCommand(prompt) {
    // Hide welcome screen if showing
    document.getElementById('welcomeContainer').classList.add('hidden');
    const history = document.getElementById('chatHistory');
    history.classList.remove('hidden');

    // 1. User message bubble
    appendChatBubble('Staff', prompt, true);

    const prompt_lower = prompt.toLowerCase();

    // Simple natural language commands parser
    if (prompt_lower.includes('schedule from') || prompt_lower.includes('dispatch from') || prompt_lower.includes('schedule a transport')) {
        // regex try: schedule from [NodeA] to [NodeB]
        const regex = /(?:schedule|dispatch)(?:\s+a)?(?:\s+transport)?\s+from\s+([a-zA-Z0-9\s]+?)\s+to\s+([a-zA-Z0-9\s]+)/i;
        const match = prompt.match(regex);
        if (match) {
            const start = match[1].trim();
            const end = match[2].trim();

            // Verify if starting/ending nodes are real in our graph
            const validNodes = Object.keys(nodesLayout);
            const realStart = validNodes.find(n => n.toLowerCase() === start.toLowerCase());
            const realEnd = validNodes.find(n => n.toLowerCase() === end.toLowerCase());

            if (realStart && realEnd) {
                appendChatBubble('Rovex AI Assistant', `Processing task dispatch from ${realStart} to ${realEnd}... Calling REST scheduler...`, false);
                // Trigger actual schedule dispatch API
                await triggerTaskDispatchAPI(realStart, realEnd);
            } else {
                appendChatBubble('Rovex AI Assistant', `Sorry, could not verify the nodes. Real nodes available: ${validNodes.join(', ')}`, false);
            }
        } else {
            appendChatBubble('Rovex AI Assistant', "To schedule, please specify clearly: 'schedule from Reception to Pharmacy' or select the 'Interactive Scheduler' above.", false);
        }
    } 
    else if (prompt_lower.includes('robots') || prompt_lower.includes('list active') || prompt_lower.includes('show robots')) {
        appendChatBubble('Rovex AI Assistant', "Scanning PyMongo database for live robot bios...", false);
        await triggerListRobotsAPI();
    } 
    else if (prompt_lower.includes('divert') || prompt_lower.includes('congestion') || prompt_lower.includes('weight')) {
        appendChatBubble('Rovex AI Assistant', "Routing configuration requested. You can adjust link priority weights by clicking the 'Update' button beside 'Corridor Traffic Priority' in the sidebar or calling PUT /api/robots/graph/edge.", false);
    }
    else {
        // Default chatbot response
        appendChatBubble('Rovex AI Assistant', "I can parse commands to perform live backend database modifications. Try asking:<br><br>&bull; <strong>'schedule from Reception to ICU'</strong> (runs A* route & logs SQL task)<br>&bull; <strong>'list active robots'</strong> (queries PyMongo collection)<br>&bull; <strong>'divert traffic'</strong> (explains corridor weights)<br><br>Or type any standard questions to chat!", false);
    }
}

// Call the list robots API for chatbot interface
async function triggerListRobotsAPI() {
    try {
        const robots = await apiRequest('/api/robots');
        let responseHtml = '<strong>PyMongo Records found (' + robots.length + '):</strong><ul class="list-disc pl-5 mt-2 space-y-2">';
        robots.forEach(r => {
            responseHtml += `
            <li>
                <span class="font-bold text-white">${r.robot_id}</span> (${r.serial_number})<br>
                Status: <span class="text-indigo-400 font-semibold">${r.status}</span> | Location: ${r.location} | Battery: <span class="text-emerald-400">${r.battery}%</span> | Sanctioned: ${r.sanctioned}
            </li>
            `;
        });
        responseHtml += '</ul>';
        appendChatBubble('Rovex AI Assistant', responseHtml, false);
    } catch (err) {
        appendChatBubble('Rovex AI Assistant', "Error connecting to PyMongo robots database.", false);
    }
}

// Dispatch scheduler request from Chat Commands
async function triggerTaskDispatchAPI(source_node, target_node) {
    try {
        const task = await apiRequest('/api/tasks', {
            method: 'POST',
            body: { source_node, target_node, robot_id: null, scheduled_time: 'now', is_recurring: false, recurrence_interval: 'none' }
        });

        await fetchTasks();
        await fillFormSelectors();

        const path = JSON.parse(task.path);
        drawMap(path);
        await triggerPathfinderCalculation(source_node, target_node);

        appendChatBubble('Rovex AI Assistant', `<strong>SUCCESS: Stretcher Robot Dispatched!</strong><br><br>Task ID: <span class="font-mono-custom text-white font-bold">${task.id}</span><br>Route: ${path.join(' &rarr; ')}<br>Assigned Robot: ${task.robot_id || 'Waiting in Queue'}<br>ETA: ${task.eta_minutes} minutes.<br><br>Click <strong>'Simulate Transit Steps'</strong> on the sidebar task card to initiate execution!`, false);
    } catch (e) {
        appendChatBubble('Rovex AI Assistant', `Failed to schedule: ${e.message}`, false);
        console.error(e);
    }
}

// Helper to append bubble
function appendChatBubble(sender, text, isUser) {
    const history = document.getElementById('chatHistory');

    const outerDiv = document.createElement('div');
    outerDiv.className = isUser ? "flex justify-end" : "flex justify-start";

    const innerDiv = document.createElement('div');
    innerDiv.className = isUser 
        ? "max-w-[80%] bg-slate-900 border border-slate-800 p-4 rounded-2xl rounded-tr-none text-xs text-slate-300 select-text" 
        : "max-w-[80%] bg-indigo-950/20 border border-indigo-900/30 p-4 rounded-2xl rounded-tl-none text-xs text-slate-300 select-text";

    innerDiv.innerHTML = `
        <span class="block text-[10px] uppercase tracking-wider font-bold ${isUser ? 'text-indigo-400' : 'text-purple-400'} mb-1">${sender}</span>
        <p class="leading-relaxed whitespace-pre-wrap">${text}</p>
    `;
    outerDiv.appendChild(innerDiv);
    history.appendChild(outerDiv);

    // Auto scroll to bottom
    history.scrollTop = history.scrollHeight;
}
