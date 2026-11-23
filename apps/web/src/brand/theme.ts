// The look. The brand ("Ciclope Sentinela") shows only the dark theme: FORCED_THEME wins over
// any saved choice. The light theme and the Claro/Escuro/Sistema choice stay in the code,
// hidden, in case they come back. Only appearance lives here.
import { loadPreference, savePreference } from "../session";

export type ThemePreference = "light" | "dark" | "system";
export type Theme = "light" | "dark";

const KEY = "theme";
/** The browser bar and the home-screen splash follow the page's floor (--bg). */
export const THEME_COLOR: Record<Theme, string> = { light: "#F6F4F1", dark: "#09090B" };
/** The theme the brand shows, whatever is saved. null would bring the choice back. */
export const FORCED_THEME: Theme | null = "dark";

export function loadThemePreference(): ThemePreference {
  const saved = loadPreference(KEY);
  return saved === "light" || saved === "dark" || saved === "system" ? saved : "system";
}

export function resolveTheme(preference: ThemePreference, systemDark: boolean): Theme {
  if (FORCED_THEME) return FORCED_THEME;
  if (preference === "system") return systemDark ? "dark" : "light";
  return preference;
}

function systemPrefersDark(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-color-scheme: dark)").matches;
}

/** Sets the theme on <html> (the CSS tokens switch on it) and the browser's bar color. */
export function applyTheme(preference: ThemePreference = loadThemePreference()): Theme {
  const theme = resolveTheme(preference, systemPrefersDark());
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
  document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]').forEach((meta) => {
    meta.content = THEME_COLOR[theme];
    meta.removeAttribute("media");
  });
  return theme;
}

export function saveThemePreference(preference: ThemePreference): Theme {
  savePreference(KEY, preference);
  return applyTheme(preference);
}

/** With "Sistema", the page follows the system when it changes (sunset on a phone, say). */
export function followSystemTheme(): () => void {
  const query = window.matchMedia?.("(prefers-color-scheme: dark)");
  if (!query) return () => undefined;
  const onChange = () => {
    if (loadThemePreference() === "system") applyTheme("system");
  };
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}
