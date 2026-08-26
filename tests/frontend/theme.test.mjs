import test from "node:test";
import assert from "node:assert/strict";

import {
  THEME_KEY,
  applyTheme,
  loadTheme,
  nextTheme,
  resolveTheme,
  saveTheme,
} from "../../pwa/theme.js";

class MemoryStorage {
  constructor() { this.values = new Map(); }
  getItem(key) { return this.values.get(key) ?? null; }
  setItem(key, value) { this.values.set(key, value); }
}

test("tema tersimpan diprioritaskan dan preferensi perangkat menjadi fallback", () => {
  assert.equal(resolveTheme("light", true), "light");
  assert.equal(resolveTheme("dark", false), "dark");
  assert.equal(resolveTheme(null, true), "dark");
  assert.equal(resolveTheme("invalid", false), "light");

  const storage = new MemoryStorage();
  assert.equal(loadTheme(storage, { matches: true }), "dark");
  storage.setItem(THEME_KEY, "light");
  assert.equal(loadTheme(storage, { matches: true }), "light");
});

test("toggle tema menerapkan atribut, meta color, dan menyimpan pilihan", () => {
  const storage = new MemoryStorage();
  const root = { dataset: {}, style: {} };
  const meta = {
    value: null,
    setAttribute(name, value) { if (name === "content") this.value = value; },
  };

  assert.equal(nextTheme("light"), "dark");
  assert.equal(applyTheme("dark", root, meta), "dark");
  assert.equal(root.dataset.theme, "dark");
  assert.equal(root.style.colorScheme, "dark");
  assert.equal(meta.value, "#004146");
  assert.equal(saveTheme("dark", storage), "dark");
  assert.equal(storage.getItem(THEME_KEY), "dark");
});
