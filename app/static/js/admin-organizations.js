/*
File: app/static/js/admin-organizations.js
Description: Page-specific behavior for the admin organization-management page.
The script loads organization summaries, controller trees, fleet status, and
recent robot/log details for the selected hospital organization.
*/

const adminOrgSession = window.RovexCommon.ensureSession({
    requiredRole: 'admin',
    redirectPath: '/',
    failureMessage: 'Access Denied: Only Rovex Admins can access the organization management page.',
});
const adminOrgToken = adminOrgSession ? adminOrgSession.token : null;
const adminOrgUser = adminOrgSession ? adminOrgSession.user : {};

async function fetchOrganizationOptions() {
    const selectEl = document.getElementById('organizationSelect');
    const organizations = await window.RovexCommon.apiRequest('/api/organizations', { token: adminOrgToken });
    selectEl.innerHTML = '';
    organizations.forEach((organization) => {
        selectEl.add(new Option(organization.organization, organization.organization));
    });
    return organizations;
}

function renderOrganizationProfile(detail) {
    document.getElementById('orgServiceTierBadge').innerText = detail.service_tier;
    const profileCards = [
        ['Organization', detail.organization],
        ['Controller Device', detail.fleet_controller_device],
        ['Contract Owner', detail.contract_owner],
        ['Deployed Since', detail.deployed_since],
        ['Location', `${detail.location.campus}, ${detail.location.city}, ${detail.location.state}`],
        ['Notes', detail.notes],
    ];
    document.getElementById('organizationProfileCards').innerHTML = profileCards.map(([label, value]) => `
        <div class="bg-slate-950/60 border border-slate-800 rounded-xl p-4">
            <span class="block text-[10px] uppercase tracking-wider text-slate-500">${label}</span>
            <span class="text-sm text-slate-200">${value}</span>
        </div>
    `).join('');

    document.getElementById('organizationHistoryTimeline').innerHTML = detail.rovex_history.map((entry) => `
        <div class="border-l border-violet-500/40 pl-3 text-slate-300">${entry}</div>
    `).join('');
}

function renderControllerTree(detail) {
    const tree = detail.controller_tree;
    const groups = [
        ['Supervisors', tree.supervisors],
        ['Sub-Supervisors', tree['sub-supervisors']],
        ['Employees', tree.employees],
    ];
    document.getElementById('organizationTreePanel').innerHTML = groups.map(([label, users]) => `
        <div class="bg-slate-950/60 border border-slate-800 rounded-xl p-4 space-y-2">
            <h3 class="text-sm font-semibold text-white">${label}</h3>
            ${users.length ? users.map((user) => `
                <div class="border border-slate-800 rounded-lg p-3 bg-slate-950/40">
                    <div class="font-semibold text-slate-200">${user.full_name}</div>
                    <div class="text-[10px] text-slate-500 font-mono-custom">${user.username}</div>
                    <div class="text-[11px] text-slate-400">${user.email}</div>
                </div>
            `).join('') : '<div class="text-xs text-slate-500">No users in this controller branch.</div>'}
        </div>
    `).join('');
}

function renderFleetPanel(detail) {
    document.getElementById('organizationFleetsPanel').innerHTML = detail.fleets.map((fleet) => `
        <div class="bg-slate-950/60 border border-slate-800 rounded-xl p-4 space-y-4">
            <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
                <div>
                    <h3 class="text-sm font-semibold text-white">${fleet.fleet_name}</h3>
                    <div class="text-[10px] text-slate-500 font-mono-custom">${fleet.fleet_id} · ${fleet.fleet_type}</div>
                    <p class="text-[11px] text-slate-400 mt-1">${fleet.dispatch_zone}</p>
                </div>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-2 text-center text-xs">
                    <div class="bg-slate-900/70 rounded-lg p-2 border border-slate-800"><span class="block text-[10px] text-slate-500">Robots</span><span class="font-bold text-white">${fleet.total_robot_count}</span></div>
                    <div class="bg-slate-900/70 rounded-lg p-2 border border-slate-800"><span class="block text-[10px] text-slate-500">Active</span><span class="font-bold text-indigo-300">${fleet.active_robot_count}</span></div>
                    <div class="bg-slate-900/70 rounded-lg p-2 border border-slate-800"><span class="block text-[10px] text-slate-500">Idle Ready</span><span class="font-bold text-emerald-300">${fleet.idle_robot_count}</span></div>
                    <div class="bg-slate-900/70 rounded-lg p-2 border border-slate-800"><span class="block text-[10px] text-slate-500">Unsanctioned</span><span class="font-bold text-rose-300">${fleet.unsanctioned_robot_count}</span></div>
                </div>
            </div>
            <div class="space-y-3">
                ${fleet.robots.map((robot) => `
                    <div class="border border-slate-800 rounded-lg p-4 bg-slate-900/50 space-y-3">
                        <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
                            <div>
                                <div class="font-semibold text-white">${robot.robot_id}</div>
                                <div class="text-[10px] text-slate-500 font-mono-custom">${robot.serial_number}</div>
                            </div>
                            <div class="flex gap-2 flex-wrap text-[10px]">
                                <span class="px-2 py-1 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">${robot.status}</span>
                                <span class="px-2 py-1 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">${robot.battery}%</span>
                                <span class="px-2 py-1 rounded ${robot.sanctioned ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20' : 'bg-rose-500/10 text-rose-300 border border-rose-500/20'}">${robot.sanctioned ? 'sanctioned' : 'unsanctioned'}</span>
                            </div>
                        </div>
                        <div class="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs text-slate-400">
                            <div><span class="block text-[10px] uppercase tracking-wider text-slate-500">Location</span>${robot.location} (${robot.x_m}, ${robot.y_m})</div>
                            <div><span class="block text-[10px] uppercase tracking-wider text-slate-500">Task</span>${robot.assigned_task_id || 'No active task'}</div>
                            <div><span class="block text-[10px] uppercase tracking-wider text-slate-500">Last Problem</span>${robot.last_problem}</div>
                        </div>
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                            <div class="bg-black/40 border border-slate-800 rounded-lg p-3">
                                <div class="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Recent Alert Log</div>
                                <div class="space-y-1 text-slate-300">${robot.recent_notification_messages.length ? robot.recent_notification_messages.map((entry) => `<div>${entry}</div>`).join('') : '<div class="text-slate-500">No recent alerts.</div>'}</div>
                            </div>
                            <div class="bg-black/40 border border-slate-800 rounded-lg p-3">
                                <div class="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Recent Telemetry</div>
                                <div class="space-y-1 text-slate-300 font-mono-custom">${robot.recent_telemetry_timestamps.length ? robot.recent_telemetry_timestamps.map((entry) => `<div>${entry}</div>`).join('') : '<div class="text-slate-500">No recent telemetry.</div>'}</div>
                            </div>
                        </div>
                    </div>
                `).join('') || '<div class="text-xs text-slate-500">No robots assigned to this fleet.</div>'}
            </div>
        </div>
    `).join('');
}

async function loadOrganizationDetail(organizationName) {
    const detail = await window.RovexCommon.apiRequest(`/api/organizations/${encodeURIComponent(organizationName)}`, { token: adminOrgToken });
    renderOrganizationProfile(detail);
    renderControllerTree(detail);
    renderFleetPanel(detail);
}

window.addEventListener('DOMContentLoaded', async () => {
    if (!adminOrgSession) return;
    document.getElementById('usernameBadge').innerText = `Admin: ${adminOrgUser.full_name}`;
    const organizations = await fetchOrganizationOptions();
    if (organizations.length) {
        await loadOrganizationDetail(organizations[0].organization);
    }
    document.getElementById('organizationSelect').addEventListener('change', async (event) => {
        await loadOrganizationDetail(event.target.value);
    });
});
