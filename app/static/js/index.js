/*
File: app/static/js/index.js
Description: Page-specific login interactions for the Rovex landing page.
The script uses shared helpers from rovex-common.js to authenticate users,
store browser session state, and redirect them to the correct dashboard.
*/

async function runLogin(username, password) {
    const errorBox = document.getElementById('errorBox');
    errorBox.classList.add('hidden');

    try {
        const data = await window.RovexCommon.apiRequest('/api/users/login', {
            method: 'POST',
            includeAuth: false,
            body: { username, password },
        });

        window.RovexCommon.storeSession(data.access_token, data.user);
        window.RovexCommon.redirectToRoleHome(data.user);
    } catch (error) {
        errorBox.classList.remove('hidden');
        document.getElementById('errorMessage').innerText = error.message || 'Failed to authenticate.';
        console.error(error);
    }
}

async function fillAndLogin(username, password) {
    document.getElementById('username').value = username;
    document.getElementById('password').value = password;
    await runLogin(username, password);
}

window.addEventListener('DOMContentLoaded', () => {
    document.getElementById('loginForm').addEventListener('submit', async (event) => {
        event.preventDefault();
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;
        await runLogin(username, password);
    });
});
