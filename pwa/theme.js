export const THEME_KEY = "catatkas.theme.v1";

// Default selalu terang agar tampilan pertama konsisten di semua perangkat.
// Pilihan pengguna yang sudah tersimpan tetap dihormati.
export function resolveTheme(storedTheme) {
  return storedTheme === "dark" ? "dark" : "light";
}

export function nextTheme(currentTheme) {
  return currentTheme === "dark" ? "light" : "dark";
}

export function loadTheme(storage = localStorage) {
  try {
    return resolveTheme(storage.getItem(THEME_KEY));
  } catch {
    return "light";
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
