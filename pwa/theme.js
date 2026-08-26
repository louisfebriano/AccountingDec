export const THEME_KEY = "catatkas.theme.v1";

export function resolveTheme(storedTheme, prefersDark = false) {
  if (["light", "dark"].includes(storedTheme)) return storedTheme;
  return prefersDark ? "dark" : "light";
}

export function nextTheme(currentTheme) {
  return currentTheme === "dark" ? "light" : "dark";
}

export function loadTheme(storage = localStorage, mediaQuery = matchMedia("(prefers-color-scheme: dark)")) {
  try {
    return resolveTheme(storage.getItem(THEME_KEY), mediaQuery.matches);
  } catch {
    return resolveTheme(null, mediaQuery.matches);
  }
}

export function applyTheme(theme, root = document.documentElement, meta = document.querySelector('meta[name="theme-color"]')) {
  const resolved = resolveTheme(theme);
  root.dataset.theme = resolved;
  root.style.colorScheme = resolved;
  if (meta) meta.setAttribute("content", resolved === "dark" ? "#004146" : "#EFF5F9");
  return resolved;
}

export function saveTheme(theme, storage = localStorage) {
  const resolved = resolveTheme(theme);
  storage.setItem(THEME_KEY, resolved);
  return resolved;
}
