/**
 * Shared fetch wrapper that handles 401 responses globally.
 *
 * When the backend returns 401, the onAuthLost callback fires so
 * the app can redirect to the login screen.
 */

let _onAuthLost = null;

export function setOnAuthLost(callback) {
  _onAuthLost = callback;
}

export async function apiFetch(url, options = {}) {
  const res = await fetch(url, options);

  if (res.status === 401 && _onAuthLost) {
    _onAuthLost();
    throw new Error("Session expired");
  }

  return res;
}
