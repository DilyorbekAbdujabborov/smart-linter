/**
 * Shared client-side auth: token storage, refresh-on-401, redirect-to-login.
 * Loaded on every authenticated page (dashboard, process, roster). login.html
 * only needs setTokens(), the rest of the pages need requireAuth+authFetch.
 */
(function (global) {
	function getAccess() {
		return localStorage.getItem('access_token');
	}
	function getRefresh() {
		return localStorage.getItem('refresh_token');
	}
	function setTokens(access, refresh) {
		localStorage.setItem('access_token', access);
		if (refresh) localStorage.setItem('refresh_token', refresh);
	}
	function clearTokens() {
		localStorage.removeItem('access_token');
		localStorage.removeItem('refresh_token');
	}
	function toLogin() {
		clearTokens();
		window.location.href = '/login';
	}

	// Redirects to /login if there's no access token at all. Doesn't check
	// expiry -- an expired-but-present token still lets the page render;
	// the first authFetch call will refresh it or bounce to /login.
	function requireAuth() {
		if (!getAccess()) {
			toLogin();
			return false;
		}
		return true;
	}

	// Coalesce concurrent 401s (e.g. the initial /events fetch and the SSE
	// connection failing around the same time) into a single refresh call.
	let refreshing = null;
	function doRefresh() {
		if (refreshing) return refreshing;
		var rt = getRefresh();
		if (!rt) {
			toLogin();
			return Promise.reject(new Error('no refresh token'));
		}
		refreshing = fetch('/auth/refresh', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ refresh_token: rt }),
		})
			.then(function (resp) {
				if (!resp.ok) throw new Error('refresh failed (HTTP ' + resp.status + ')');
				return resp.json();
			})
			.then(function (data) {
				// Validate the response has the expected fields before
				// clobbering localStorage with undefined values.
				if (!data || !data.access_token) {
					throw new Error('refresh returned no access_token');
				}
				setTokens(data.access_token, data.refresh_token);
				refreshing = null;
				return data.access_token;
			})
			.catch(function (err) {
				refreshing = null;
				console.error('[auth] refresh failed:', err.message);
				toLogin();
				throw err;
			});
		return refreshing;
	}

	// fetch() wrapper that attaches the access token and, on a 401, silently
	// refreshes once and retries before giving up and redirecting to /login.
	function authFetch(url, opts, _retried) {
		opts = opts || {};
		opts.headers = Object.assign({}, opts.headers, {
			Authorization: 'Bearer ' + getAccess(),
		});
		return fetch(url, opts).then(function (resp) {
			if (resp.status === 401 && !_retried) {
				return doRefresh().then(function () {
					return authFetch(url, opts, true);
				});
			}
			if (resp.status === 401) {
				toLogin();
				throw new Error('unauthenticated');
			}
			return resp;
		});
	}

	global.Auth = {
		getAccess: getAccess,
		getRefresh: getRefresh,
		setTokens: setTokens,
		clearTokens: clearTokens,
		toLogin: toLogin,
		requireAuth: requireAuth,
		refresh: doRefresh,
		authFetch: authFetch,
	};
})(window);
