// Per-tab convenience only: the token survives a reload of this tab, nothing more.
// Storage can be unavailable (private mode, blocked site data), so every access is guarded.

const KEY = "visao.token";

export function loadToken(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function saveToken(token: string | null): void {
  try {
    if (token) sessionStorage.setItem(KEY, token);
    else sessionStorage.removeItem(KEY);
  } catch {
    // Without storage the user simply logs in again after a reload.
  }
}

const PREFIX = "visao.pref.";

export function loadPreference(name: string): string | null {
  try {
    return localStorage.getItem(PREFIX + name);
  } catch {
    return null;
  }
}

export function savePreference(name: string, value: string): void {
  try {
    localStorage.setItem(PREFIX + name, value);
  } catch {
    // Preference just won't persist.
  }
}
