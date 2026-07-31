/*
File: app/static/js/rovex-common.js
Description: Shared browser utilities for Rovex frontend pages. The helpers centralize
session storage, logout behavior, role-aware redirects, and authenticated fetch logic
so page-specific scripts can stay focused on their own UI responsibilities.
*/

(function bootstrapRovexCommon(window) {
    const TOKEN_STORAGE_KEY = 'rovex_token';
    const USER_STORAGE_KEY = 'rovex_user';

    function getStoredToken() {
        return localStorage.getItem(TOKEN_STORAGE_KEY);
    }

    function getStoredUser() {
        try {
            return JSON.parse(localStorage.getItem(USER_STORAGE_KEY) || '{}');
        } catch (error) {
            console.error('Failed to parse stored Rovex user payload.', error);
            return {};
        }
    }

    function storeSession(token, user) {
        localStorage.setItem(TOKEN_STORAGE_KEY, token);
        localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
    }

    function clearSession() {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        localStorage.removeItem(USER_STORAGE_KEY);
        document.cookie = 'access_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
    }

    function redirectToRoleHome(user) {
        window.location.href = user.role === 'admin' ? '/admin' : '/core';
    }

    function logout(redirectPath = '/') {
        clearSession();
        window.location.href = redirectPath;
    }

    function ensureSession({ requiredRole = null, redirectPath = '/', failureMessage = null } = {}) {
        const token = getStoredToken();
        const user = getStoredUser();

        if (!token || !user.username) {
            if (failureMessage) {
                alert(failureMessage);
            }
            window.location.href = redirectPath;
            return null;
        }

        if (requiredRole && user.role !== requiredRole) {
            if (failureMessage) {
                alert(failureMessage);
            }
            window.location.href = redirectPath;
            return null;
        }

        return { token, user };
    }

    async function apiRequest(
        url,
        {
            method = 'GET',
            body = null,
            headers = {},
            includeAuth = true,
            token = getStoredToken(),
        } = {},
    ) {
        const resolvedHeaders = { ...headers };
        if (body !== null && !resolvedHeaders['Content-Type']) {
            resolvedHeaders['Content-Type'] = 'application/json';
        }
        if (includeAuth && token) {
            resolvedHeaders['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch(url, {
            method,
            headers: resolvedHeaders,
            body: body !== null ? JSON.stringify(body) : undefined,
        });

        const contentType = response.headers.get('content-type') || '';
        const payload = contentType.includes('application/json')
            ? await response.json()
            : await response.text();

        if (!response.ok) {
            const detail = payload?.detail || payload?.message || (typeof payload === 'string' ? payload : 'Request failed.');
            throw new Error(detail);
        }

        return payload;
    }

    window.RovexCommon = {
        TOKEN_STORAGE_KEY,
        USER_STORAGE_KEY,
        apiRequest,
        clearSession,
        ensureSession,
        getStoredToken,
        getStoredUser,
        logout,
        redirectToRoleHome,
        storeSession,
    };
})(window);
