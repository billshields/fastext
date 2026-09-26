const api = (() => {
    const TOKEN_KEY = 'sr_access';
    const REFRESH_KEY = 'sr_refresh';
    // Sent with each request so the server buckets reading stats by the user's local day
    const TIMEZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;

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

    // The access token is short-lived and refreshed on the first 401, so the session
    // lasts as long as the refresh token. Checking its expiry here keeps pages from
    // loading for a session that is already dead and then bouncing back to login.
    function isAuthenticated() {
        const refresh = getRefreshToken();
        if (!getAccessToken() || !refresh) return false;
        try {
            const payload = JSON.parse(atob(refresh.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
            return payload.exp * 1000 > Date.now();
        } catch {
            return false;
        }
    }

    // Refresh tokens are single-use (rotated + blacklisted), so concurrent 401s
    // must share one refresh call or the losers would log the user out
    let refreshInFlight = null;

    function refreshAccessToken() {
        if (!refreshInFlight) {
            refreshInFlight = doRefresh().finally(() => { refreshInFlight = null; });
        }
        return refreshInFlight;
    }

    async function doRefresh() {
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
            options.headers['X-Timezone'] = TIMEZONE;
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
                'X-Timezone': TIMEZONE,
                ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
            },
            body: JSON.stringify(data),
            keepalive: true,
        }).catch(() => {});
    }

    function logout() {
        const refresh = getRefreshToken();
        if (refresh) {
            // keepalive, so revoking the token survives the redirect that follows logout
            beacon('/api/auth/logout/', { refresh });
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
