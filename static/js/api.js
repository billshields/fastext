const api = (() => {
    const TOKEN_KEY = 'sr_access';
    const REFRESH_KEY = 'sr_refresh';

    function getAccessToken() {
        return localStorage.getItem(TOKEN_KEY);
    }

    function getRefreshToken() {
        return localStorage.getItem(REFRESH_KEY);
    }

    function setTokens(access, refresh) {
        localStorage.setItem(TOKEN_KEY, access);
        localStorage.setItem(REFRESH_KEY, refresh);
    }

    function clearTokens() {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(REFRESH_KEY);
    }

    function isAuthenticated() {
        return !!getAccessToken();
    }

    async function refreshAccessToken() {
        const refresh = getRefreshToken();
        if (!refresh) throw new Error('No refresh token');

        const resp = await fetch('/api/auth/refresh/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh }),
        });

        if (!resp.ok) {
            clearTokens();
            window.location.href = '/';
            throw new Error('Session expired');
        }

        const data = await resp.json();
        setTokens(data.access, data.refresh || refresh);
        return data.access;
    }

    async function request(url, options = {}, auth = true) {
        if (auth) {
            let token = getAccessToken();
            if (!token) {
                window.location.href = '/';
                throw new Error('Not authenticated');
            }
            options.headers = options.headers || {};
            options.headers['Authorization'] = `Bearer ${token}`;
        }

        let resp = await fetch(url, options);

        // Try refreshing token on 401
        if (resp.status === 401 && auth) {
            try {
                const newToken = await refreshAccessToken();
                options.headers['Authorization'] = `Bearer ${newToken}`;
                resp = await fetch(url, options);
            } catch {
                return;
            }
        }

        if (!resp.ok) {
            const errData = await resp.json().catch(() => ({}));
            const err = new Error(errData.detail || JSON.stringify(errData) || resp.statusText);
            err.status = resp.status;
            err.data = errData;
            throw err;
        }

        if (resp.status === 204 || resp.status === 205) return null;
        return resp.json();
    }

    function get(url, auth = true) {
        return request(url, { method: 'GET' }, auth);
    }

    function post(url, body, auth = true) {
        return request(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        }, auth);
    }

    function patch(url, body, auth = true) {
        return request(url, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        }, auth);
    }

    function del(url, auth = true) {
        return request(url, { method: 'DELETE' }, auth);
    }

    function upload(url, formData, auth = true) {
        const options = { method: 'POST', body: formData };
        // Don't set Content-Type -- browser sets it with boundary for FormData
        return request(url, options, auth);
    }

    function beacon(url, data) {
        const token = getAccessToken();
        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
            },
            body: JSON.stringify(data),
            keepalive: true,
        }).catch(() => {});
    }

    function logout() {
        const refresh = getRefreshToken();
        if (refresh) {
            post('/api/auth/logout/', { refresh }).catch(() => {});
        }
        clearTokens();
    }

    function put(url, body, auth = true) {
        return request(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        }, auth);
    }

    return {
        get, post, put, patch, delete: del, upload, beacon,
        setTokens, clearTokens, isAuthenticated, logout,
        getAccessToken,
    };
})();
