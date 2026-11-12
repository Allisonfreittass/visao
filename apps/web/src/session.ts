// The token lives in this tab only, unless the owner asks to stay signed in on this device
// (the installed app on a phone, opened from a notification). Storage can be unavailable
// (private mode, blocked site data), so every access is guarded.

const KEY = "visao.token";

export function loadToken(): string | null {
  try {
    return sessionStorage.getItem(KEY) ?? localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function saveToken(token: string | null, remember = false): void {
  try {
    sessionStorage.removeItem(KEY);
    localStorage.removeItem(KEY);
    if (token) (remember ? localStorage : sessionStorage).setItem(KEY, token);
  } catch {
    // Without storage the user simply logs in again after a reload.
  }
}

/** Whether the current token was saved to stay signed in on this device. */
export function tokenRemembered(): boolean {
  try {
    return localStorage.getItem(KEY) !== null;
  } catch {
    return false;
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
