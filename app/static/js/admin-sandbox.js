/*
File: app/static/js/admin-sandbox.js
Description: Page-specific behavior for the dedicated admin sandbox page.
This script loads sandbox catalog metadata, toggles SQL/NoSQL modes, and runs
advanced read-only inspection queries against the backend.
*/

let selectedEngine = 'sql';
const adminSandboxSession = window.RovexCommon.ensureSession({
    requiredRole: 'admin',
    redirectPath: '/',
    failureMessage: 'Access Denied: Only Rovex Admins can access the advanced sandbox page.',
});
const adminSandboxToken = adminSandboxSession ? adminSandboxSession.token : null;
const adminSandboxUser = adminSandboxSession ? adminSandboxSession.user : {};

function setSandboxEngine(engine) {
    selectedEngine = engine;
    const btnSql = document.getElementById('sandboxBtnSql');
    const btnNoSql = document.getElementById('sandboxBtnNoSql');
    const editor = document.getElementById('sandboxQueryEditor');

    if (engine === 'sql') {
        btnSql.className = 'p-3 rounded-xl border border-indigo-700 bg-indigo-950/20 text-indigo-400 font-bold text-xs flex items-center justify-center space-x-2 transition';
        btnNoSql.className = 'p-3 rounded-xl border border-slate-800 bg-slate-950 text-slate-500 font-bold text-xs flex items-center justify-center space-x-2 transition';
        editor.value = 'SHOW TABLES';
    } else {
        btnNoSql.className = 'p-3 rounded-xl border border-violet-700 bg-violet-950/20 text-violet-400 font-bold text-xs flex items-center justify-center space-x-2 transition';
        btnSql.className = 'p-3 rounded-xl border border-slate-800 bg-slate-950 text-slate-500 font-bold text-xs flex items-center justify-center space-x-2 transition';
        editor.value = 'db.listCollections()';
    }
}

function applySandboxTemplate(query, engine) {
    setSandboxEngine(engine);
    document.getElementById('sandboxQueryEditor').value = query;
}

async function fetchSandboxCatalog() {
    try {
        const catalog = await window.RovexCommon.apiRequest('/api/admin/sandbox/catalog', { token: adminSandboxToken });
        document.getElementById('sqlTablesList').innerHTML = catalog.sql_tables.map((table) => `<div class="font-mono-custom text-xs text-slate-300">${table}</div>`).join('') || '<div class="text-slate-500 text-xs">No SQL tables found.</div>';
        document.getElementById('sqlExamplesList').innerHTML = catalog.sql_examples.map((query) => `<button onclick="applySandboxTemplate(${JSON.stringify(query)}, 'sql')" class="w-full text-left p-2.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-lg text-xs font-mono-custom text-indigo-300 transition">${query}</button>`).join('');
        document.getElementById('nosqlCollectionsList').innerHTML = catalog.nosql_collections.map((collection) => `<div class="font-mono-custom text-xs text-slate-300">${collection}</div>`).join('') || '<div class="text-slate-500 text-xs">No NoSQL collections found.</div>';
        document.getElementById('nosqlExamplesList').innerHTML = catalog.nosql_examples.map((query) => `<button onclick="applySandboxTemplate(${JSON.stringify(query)}, 'nosql')" class="w-full text-left p-2.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-lg text-xs font-mono-custom text-violet-300 transition">${query}</button>`).join('');
    } catch (error) {
        console.error('Failed to fetch sandbox catalog', error);
    }
}

async function executeSandboxQuery() {
    const queryBox = document.getElementById('sandboxQueryResult');
    queryBox.innerText = 'Evaluating query in advanced sandbox...';
    const queryString = document.getElementById('sandboxQueryEditor').value;

    try {
        const data = await window.RovexCommon.apiRequest('/api/admin/query', {
            method: 'POST',
            token: adminSandboxToken,
            body: { db_type: selectedEngine, query_string: queryString },
        });
        queryBox.innerText = JSON.stringify(data, null, 2);
    } catch (error) {
        queryBox.innerText = error.message || 'Failed to execute query.';
        console.error(error);
    }
}

window.addEventListener('DOMContentLoaded', async () => {
    if (!adminSandboxSession) return;
    document.getElementById('sandboxUserBadge').innerText = `Admin: ${adminSandboxUser.full_name}`;
    await fetchSandboxCatalog();
});
