// The look: three themes, switched at once in Ajustes › Aparência (DESIGN.md §2). Papel is the
// default. Only appearance lives here; the colors are in tokens.css, keyed by data-theme on <html>.
import { loadPreference, savePreference } from "../session";

export type Theme = "papel" | "tinta" | "rotulo";

export const THEMES: { value: Theme; label: string }[] = [
  { value: "papel", label: "Papel" },
  { value: "tinta", label: "Tinta" },
  { value: "rotulo", label: "Rótulo" },
];

const KEY = "theme";
export const DEFAULT_THEME: Theme = "papel";
/** The browser bar and the home-screen splash follow the page's floor (--bg). */
export const THEME_COLOR: Record<Theme, string> = { papel: "#F6F4EF", tinta: "#101214", rotulo: "#F3E9D2" };

/** The saved theme. Choices saved before the three themes ("light", "dark") carry over. */
export function parseTheme(saved: string | null): Theme {
  if (saved === "papel" || saved === "tinta" || saved === "rotulo") return saved;
  if (saved === "dark") return "tinta";
  return DEFAULT_THEME;
}

export function loadTheme(): Theme {
  return parseTheme(loadPreference(KEY));
}

/** Sets the theme on <html> (the CSS tokens switch on it) and the browser's bar color. */
export function applyTheme(theme: Theme = loadTheme()): Theme {
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.style.colorScheme = theme === "tinta" ? "dark" : "light";
  document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]').forEach((meta) => {
    meta.content = THEME_COLOR[theme];
    meta.removeAttribute("media");
  });
  return theme;
}

export function saveTheme(theme: Theme): Theme {
  savePreference(KEY, theme);
  return applyTheme(theme);
}
