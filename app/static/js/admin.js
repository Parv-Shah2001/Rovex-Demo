/*
File: app/static/js/admin.js
Description: Page-specific behavior for the Rovex Admin Platform dashboard.
The script handles dashboard bootstrap, sandbox query execution, robot sanction
controls, and log streaming while reusing shared session/network helpers.
*/

let selectedEngine = 'sql';
const ROVEX_ORGANIZATION = 'Rovex Robotics Inc.';
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
        document.getElementById('statRobots').innerText = stats.total_robots;
        document.getElementById('statBattery').innerText = stats.average_robot_battery + '%';
        document.getElementById('statUnsanctioned').innerText = stats.un_sanctioned_robots;
    } catch (error) {
        console.error('Stats fetching error', error);
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

async function fetchRobotsList() {
    try {
        const robots = await window.RovexCommon.apiRequest('/api/robots', { token });
        let html = '';
        robots.forEach((robot) => {
            html += `
            <tr class="border-b border-slate-800 hover:bg-slate-900/20 transition">
                <td class="p-3 font-bold text-white">${robot.robot_id} <span class="text-[9px] font-normal block text-slate-500 font-mono-custom">${robot.serial_number}</span></td>
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
            </tr>
            `;
        });
        document.getElementById('robotsTableBody').innerHTML = html;
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
        await fetchRobotsList();
        await fetchDashboardStats();
        await fetchLogs();
    } catch (error) {
        alert('Error changing sanction: ' + error.message);
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

    document.getElementById('usernameVal').innerText = userObj.full_name;
    document.getElementById('createUserForm').addEventListener('submit', submitCreateUserForm);
    syncCreateUserRoleState();
    await fetchDashboardStats();
    await fetchUsersList();
    await fetchRobotsList();
    await fetchLogs();
});
