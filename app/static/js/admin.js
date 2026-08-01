/*
File: app/static/js/admin.js
Description: Page-specific behavior for the Rovex Admin Platform dashboard.
The script handles dashboard bootstrap, sandbox query execution, robot sanction
controls, and log streaming while reusing shared session/network helpers.
*/

const ROVEX_ORGANIZATION = 'Rovex Robotics Inc.';
let selectedEngine = 'sql';
let organizationCatalog = [];
let fleetCatalog = [];
const adminSession = window.RovexCommon.ensureSession({
    requiredRole: 'admin',
    redirectPath: '/',
    failureMessage: 'Access Denied: Only Rovex Admins can access the Admin Platform dashboard.',
});
const token = adminSession ? adminSession.token : null;
const userObj = adminSession ? adminSession.user : {};

function handleLogout() {
    window.RovexCommon.logout('/');
}

function openCreateUserModal() {
    document.getElementById('createUserModal').classList.remove('hidden');
    syncCreateUserRoleState();
}

function closeCreateUserModal() {
    document.getElementById('createUserModal').classList.add('hidden');
    document.getElementById('createUserErrorBox').classList.add('hidden');
}

function syncCreateUserRoleState() {
    const roleEl = document.getElementById('createRole');
    const orgEl = document.getElementById('createOrganization');
    if (!roleEl || !orgEl) return;

    const isAdminRole = roleEl.value === 'admin';
    orgEl.readOnly = isAdminRole;
    orgEl.classList.toggle('text-slate-400', isAdminRole);
    orgEl.classList.toggle('bg-slate-950/60', isAdminRole);
    orgEl.classList.toggle('bg-slate-950', !isAdminRole);

    if (isAdminRole) {
        orgEl.value = ROVEX_ORGANIZATION;
    } else if (orgEl.value === ROVEX_ORGANIZATION) {
        orgEl.value = '';
    }
}

function openMetricDetailModal(metricKey) {
    document.getElementById('metricDetailModal').classList.remove('hidden');
    fetchMetricDetail(metricKey);
}

function closeMetricDetailModal() {
    document.getElementById('metricDetailModal').classList.add('hidden');
}

function openCreateRobotModal() {
    document.getElementById('createRobotModal').classList.remove('hidden');
    hydrateRobotOrganizationOptions();
}

function closeCreateRobotModal() {
    document.getElementById('createRobotModal').classList.add('hidden');
    document.getElementById('createRobotErrorBox').classList.add('hidden');
}

function hydrateRobotOrganizationOptions() {
    const organizationSelect = document.getElementById('createRobotOrganization');
    if (!organizationSelect) return;
    organizationSelect.innerHTML = '';
    organizationCatalog.forEach((organization) => {
        organizationSelect.add(new Option(organization.organization, organization.organization));
    });
    syncFleetOptionsForRobotForm();
}

function syncFleetOptionsForRobotForm() {
    const organizationSelect = document.getElementById('createRobotOrganization');
    const fleetSelect = document.getElementById('createRobotFleet');
    if (!organizationSelect || !fleetSelect) return;

    const selectedOrganization = organizationSelect.value;
    const visibleFleets = fleetCatalog.filter((fleet) => fleet.organization === selectedOrganization);
    fleetSelect.innerHTML = '';
    visibleFleets.forEach((fleet) => {
        fleetSelect.add(new Option(`${fleet.fleet_name} (${fleet.fleet_id})`, fleet.fleet_id));
    });
}

function setDbEngine(engine) {
    selectedEngine = engine;
    const btnSql = document.getElementById('btnSql');
    const btnNoSql = document.getElementById('btnNoSql');
    const sqlTemplates = document.querySelectorAll('.sql-template');
    const nosqlTemplates = document.querySelectorAll('.nosql-template');
    const editor = document.getElementById('queryEditor');

    if (engine === 'sql') {
        btnSql.className = 'p-3 rounded-xl border border-indigo-700 bg-indigo-950/20 text-indigo-400 font-bold text-xs flex flex-col items-center justify-center space-y-1 transition';
        btnNoSql.className = 'p-3 rounded-xl border border-slate-800 bg-slate-950 text-slate-500 font-bold text-xs flex flex-col items-center justify-center space-y-1 transition';

        sqlTemplates.forEach((template) => template.classList.remove('hidden'));
        nosqlTemplates.forEach((template) => template.classList.add('hidden'));
        editor.value = 'SELECT * FROM users';
    } else {
        btnNoSql.className = 'p-3 rounded-xl border border-violet-700 bg-violet-950/20 text-violet-400 font-bold text-xs flex flex-col items-center justify-center space-y-1 transition';
        btnSql.className = 'p-3 rounded-xl border border-slate-800 bg-slate-950 text-slate-500 font-bold text-xs flex flex-col items-center justify-center space-y-1 transition';

        nosqlTemplates.forEach((template) => template.classList.remove('hidden'));
        sqlTemplates.forEach((template) => template.classList.add('hidden'));
        editor.value = 'db.robots.find()';
    }
}

function applyTemplate(query) {
    document.getElementById('queryEditor').value = query;
}

async function fetchDashboardStats() {
    try {
        const stats = await window.RovexCommon.apiRequest('/api/admin/stats', { token });
        document.getElementById('statUsers').innerText = stats.total_users;
        document.getElementById('statOrganizations').innerText = stats.total_organizations;
        document.getElementById('statFleets').innerText = stats.total_fleets;
        document.getElementById('statRobots').innerText = stats.total_robots;
        document.getElementById('statOnlineRobots').innerText = stats.online_robots;
        document.getElementById('statBattery').innerText = stats.average_robot_battery + '%';
        document.getElementById('statPendingTasks').innerText = stats.pending_tasks;
        document.getElementById('statCompletedTasks').innerText = stats.completed_tasks;
        document.getElementById('statUnsanctioned').innerText = stats.un_sanctioned_robots;
    } catch (error) {
        console.error('Stats fetching error', error);
    }
}

async function fetchOrganizationCatalog() {
    try {
        organizationCatalog = await window.RovexCommon.apiRequest('/api/organizations', { token });
    } catch (error) {
        console.error('Organization catalog fetch error', error);
    }
}

async function fetchMetricDetail(metricKey) {
    const titleEl = document.getElementById('metricDetailTitle');
    const descriptionEl = document.getElementById('metricDetailDescription');
    const summaryEl = document.getElementById('metricDetailSummary');
    const contentEl = document.getElementById('metricDetailContent');
    contentEl.innerText = 'Loading metric detail...';
    summaryEl.innerHTML = '';

    try {
        const detail = await window.RovexCommon.apiRequest(`/api/admin/stats/details?metric=${encodeURIComponent(metricKey)}`, { token });
        titleEl.innerText = detail.title;
        descriptionEl.innerText = detail.description;
        const summaryEntries = Object.entries(detail.summary || {});
        summaryEl.innerHTML = summaryEntries.map(([label, value]) => `
            <div class="bg-slate-950/70 rounded-lg border border-slate-800 p-3 text-center">
                <span class="block text-[10px] uppercase tracking-wider text-slate-500">${label.replace(/_/g, ' ')}</span>
                <span class="text-sm font-bold text-white">${value}</span>
            </div>
        `).join('');
        contentEl.innerText = JSON.stringify(detail.items, null, 2);
    } catch (error) {
        titleEl.innerText = 'Metric Detail';
        descriptionEl.innerText = '';
        contentEl.innerText = error.message || 'Failed to load metric detail.';
        console.error(error);
    }
}

async function fetchUsersList() {
    try {
        const users = await window.RovexCommon.apiRequest('/api/users', { token });
        let html = '';
        users.forEach((user) => {
            html += `
            <tr class="border-b border-slate-800 hover:bg-slate-900/20 transition">
                <td class="p-3 font-semibold text-white">${user.full_name}</td>
                <td class="p-3 font-mono text-[11px] text-indigo-300">${user.username}</td>
                <td class="p-3 text-slate-400">${user.organization}</td>
                <td class="p-3">
                    <span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${
                        user.role === 'admin' ? 'bg-rose-500/10 text-rose-400 border border-rose-500/25' :
                        user.role === 'supervisor' ? 'bg-red-500/10 text-red-400 border border-red-500/25' :
                        user.role === 'sub-supervisor' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/25' :
                        'bg-slate-500/10 text-slate-400 border border-slate-500/25'
                    }">
                        ${user.role}
                    </span>
                </td>
            </tr>
            `;
        });
        document.getElementById('usersTableBody').innerHTML = html;
    } catch (error) {
        console.error('Users list fetch error', error);
    }
}

async function fetchFleetsList() {
    try {
        const fleets = await window.RovexCommon.apiRequest('/api/robots/fleets', { token });
        fleetCatalog = fleets;
        let html = '';
        fleets.forEach((fleet) => {
            html += `
            <tr class="border-b border-slate-800 hover:bg-slate-900/20 transition">
                <td class="p-3 font-semibold text-white">${fleet.fleet_name}<span class="text-[9px] font-normal block text-slate-500 font-mono-custom">${fleet.fleet_id}</span></td>
                <td class="p-3 text-slate-400">${fleet.organization}<span class="text-[9px] font-normal block text-slate-500">${fleet.dispatch_zone}</span></td>
                <td class="p-3 text-slate-300">${fleet.total_robot_count}<span class="text-[9px] font-normal block text-slate-500">${fleet.robot_ids.join(', ') || 'No robots assigned'}</span></td>
                <td class="p-3 text-slate-300">${fleet.idle_robot_count}<span class="text-[9px] font-normal block text-slate-500">${fleet.sanctioned_robot_count} sanctioned / ${fleet.unsanctioned_robot_count} unsanctioned</span></td>
            </tr>
            `;
        });
        document.getElementById('fleetsTableBody').innerHTML = html || '<tr><td colspan="4" class="p-4 text-center text-slate-500">No fleets registered.</td></tr>';
    } catch (error) {
        console.error('Fleet list fetch error', error);
    }
}

async function fetchRobotsList() {
    try {
        const robots = await window.RovexCommon.apiRequest('/api/robots', { token });
        let html = '';
        robots.forEach((robot) => {
            html += `
            <tr class="border-b border-slate-800 hover:bg-slate-900/20 transition">
                <td class="p-3 font-bold text-white">${robot.robot_id} <span class="text-[9px] font-normal block text-slate-500 font-mono-custom">${robot.serial_number}</span></td>
                <td class="p-3 text-slate-400">${robot.fleet_id}</td>
                <td class="p-3 text-slate-400">${robot.organization}</td>
                <td class="p-3 text-slate-400">${robot.location}</td>
                <td class="p-3 font-semibold ${robot.battery > 50 ? 'text-emerald-400' : robot.battery > 20 ? 'text-amber-400' : 'text-rose-400'}">${robot.battery}%</td>
                <td class="p-3">
                    <span class="px-2 py-0.5 rounded text-[10px] font-bold ${
                        robot.status === 'idle' ? 'bg-slate-800 text-slate-300' :
                        robot.status === 'transit' ? 'bg-indigo-950 text-indigo-400 border border-indigo-900/40' :
                        robot.status === 'charging' ? 'bg-emerald-950 text-emerald-400 border border-emerald-900/40' :
                        'bg-rose-950 text-rose-400 border border-rose-900/40'
                    }">
                        ${robot.status.toUpperCase()}
                    </span>
                </td>
                <td class="p-3">
                    <button onclick="toggleRobotSanction('${robot.robot_id}', ${robot.sanctioned})" class="px-2.5 py-1 rounded text-[10px] font-bold transition ${
                        robot.sanctioned ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/25 hover:bg-rose-500/10 hover:text-rose-400 hover:border-rose-500/25' :
                        'bg-rose-500/10 text-rose-400 border border-rose-500/25 hover:bg-emerald-500/10 hover:text-emerald-400 hover:border-emerald-500/25'
                    }">
                        ${robot.sanctioned ? 'Sanctioned' : 'Banned'}
                    </button>
                </td>
                <td class="p-3">
                    <button onclick="removeRobot('${robot.robot_id}')" class="px-2.5 py-1 rounded text-[10px] font-bold bg-slate-950 text-rose-400 border border-rose-500/25 hover:bg-rose-950/20 transition">
                        <i class="fa-solid fa-trash-can mr-1"></i> Remove
                    </button>
                </td>
            </tr>
            `;
        });
        document.getElementById('robotsTableBody').innerHTML = html || '<tr><td colspan="8" class="p-4 text-center text-slate-500">No robots registered.</td></tr>';
    } catch (error) {
        console.error('Robots list fetch error', error);
    }
}

async function toggleRobotSanction(robotId, currentSanction) {
    try {
        await window.RovexCommon.apiRequest(`/api/robots/${robotId}/sanction`, {
            method: 'PUT',
            token,
            body: { sanctioned: !currentSanction },
        });
        await fetchFleetsList();
        await fetchRobotsList();
        await fetchDashboardStats();
        await fetchLogs();
    } catch (error) {
        alert('Error changing sanction: ' + error.message);
        console.error(error);
    }
}

async function removeRobot(robotId) {
    if (!confirm(`Remove robot ${robotId} from the registry?`)) return;
    try {
        await window.RovexCommon.apiRequest(`/api/robots/${robotId}`, {
            method: 'DELETE',
            token,
        });
        await fetchFleetsList();
        await fetchRobotsList();
        await fetchDashboardStats();
    } catch (error) {
        alert('Error removing robot: ' + error.message);
        console.error(error);
    }
}

async function submitCreateRobotForm(event) {
    event.preventDefault();
    const errorBox = document.getElementById('createRobotErrorBox');
    errorBox.classList.add('hidden');
    const payload = {
        robot_id: document.getElementById('createRobotId').value.trim(),
        serial_number: document.getElementById('createRobotSerial').value.trim(),
        organization: document.getElementById('createRobotOrganization').value,
        fleet_id: document.getElementById('createRobotFleet').value,
        battery: Number(document.getElementById('createRobotBattery').value),
        status: document.getElementById('createRobotStatus').value,
        sanctioned: document.getElementById('createRobotSanctioned').checked,
        location: document.getElementById('createRobotLocation').value.trim(),
        x_m: Number(document.getElementById('createRobotX').value),
        y_m: Number(document.getElementById('createRobotY').value),
        last_serviced: document.getElementById('createRobotServiced').value.trim(),
        last_problem: document.getElementById('createRobotProblem').value.trim(),
    };

    try {
        await window.RovexCommon.apiRequest('/api/robots', {
            method: 'POST',
            token,
            body: payload,
        });
        document.getElementById('createRobotForm').reset();
        hydrateRobotOrganizationOptions();
        closeCreateRobotModal();
        await fetchFleetsList();
        await fetchRobotsList();
        await fetchDashboardStats();
        alert(`Robot '${payload.robot_id}' added successfully.`);
    } catch (error) {
        errorBox.innerText = error.message || 'Failed to add robot.';
        errorBox.classList.remove('hidden');
        console.error(error);
    }
}

async function fetchLogs() {
    try {
        const data = await window.RovexCommon.apiRequest('/api/notifications/logs?lines=100', { token });
        const consoleEl = document.getElementById('logConsole');
        consoleEl.innerText = data.logs;
        consoleEl.scrollTop = consoleEl.scrollHeight;
    } catch (error) {
        console.error('Logs fetching error', error);
    }
}

async function executeQuery() {
    const queryBox = document.getElementById('queryResult');
    queryBox.innerText = 'Evaluating query in database secure sandbox...';
    const query_string = document.getElementById('queryEditor').value;

    try {
        const data = await window.RovexCommon.apiRequest('/api/admin/query', {
            method: 'POST',
            token,
            body: { db_type: selectedEngine, query_string },
        });
        queryBox.innerHTML = syntaxHighlight(JSON.stringify(data.data, null, 2));
        await fetchUsersList();
        await fetchFleetsList();
        await fetchRobotsList();
        await fetchDashboardStats();
    } catch (error) {
        queryBox.innerHTML = `<span class="text-rose-400">Error: ${error.message || 'Failed to parse query.'}</span>`;
        console.error(error);
    }
}

async function submitCreateUserForm(event) {
    event.preventDefault();
    const errorBox = document.getElementById('createUserErrorBox');
    errorBox.classList.add('hidden');

    const payload = {
        full_name: document.getElementById('createFullName').value.trim(),
        username: document.getElementById('createUsername').value.trim(),
        email: document.getElementById('createEmail').value.trim(),
        password: document.getElementById('createPassword').value,
        role: document.getElementById('createRole').value,
        organization: document.getElementById('createOrganization').value.trim(),
    };

    try {
        await window.RovexCommon.apiRequest('/api/users/register', {
            method: 'POST',
            token,
            body: payload,
        });
        document.getElementById('createUserForm').reset();
        syncCreateUserRoleState();
        closeCreateUserModal();
        await fetchUsersList();
        await fetchDashboardStats();
        alert(`User '${payload.username}' created successfully.`);
    } catch (error) {
        errorBox.innerText = error.message || 'Failed to create user.';
        errorBox.classList.remove('hidden');
        console.error(error);
    }
}

function syntaxHighlight(json) {
    if (!json) return '';
    const escaped = json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return escaped.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g, function (match) {
        let cls = 'text-amber-300';
        if (/^"/.test(match)) {
            cls = /:$/.test(match) ? 'text-indigo-400 font-semibold' : 'text-emerald-400';
        } else if (/true|false/.test(match)) {
            cls = 'text-orange-400';
        } else if (/null/.test(match)) {
            cls = 'text-slate-500';
        }
        return '<span class="' + cls + '">' + match + '</span>';
    });
}

window.addEventListener('DOMContentLoaded', async () => {
    if (!adminSession) {
        return;
    }

    const usernameEl = document.getElementById('usernameVal');
    if (usernameEl) {
        usernameEl.innerText = userObj.full_name;
    }

    if (document.getElementById('createUserForm')) {
        document.getElementById('createUserForm').addEventListener('submit', submitCreateUserForm);
        syncCreateUserRoleState();
    }
    if (document.getElementById('createRobotForm')) {
        document.getElementById('createRobotForm').addEventListener('submit', submitCreateRobotForm);
    }

    await fetchOrganizationCatalog();
    await fetchFleetsList();

    if (document.getElementById('createRobotOrganization')) {
        hydrateRobotOrganizationOptions();
    }
    if (document.getElementById('statUsers')) {
        await fetchDashboardStats();
    }
    if (document.getElementById('usersTableBody')) {
        await fetchUsersList();
    }
    if (document.getElementById('robotsTableBody')) {
        await fetchRobotsList();
    }
    if (document.getElementById('logConsole')) {
        await fetchLogs();
    }
});
