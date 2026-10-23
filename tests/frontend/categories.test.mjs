import test from "node:test";
import assert from "node:assert/strict";

import {
  CATEGORY_ICONS,
  CATEGORY_MAX_LENGTH,
  CATEGORY_PRESETS,
  UNCATEGORIZED,
  categoryFromChoice,
  categoryIcon,
  categoryLabel,
  categoryPresentation,
  normalizeCategory,
} from "../../pwa/categories.js";

test("preset kategori UMKM unik, berbatas, dan memiliki kategori default", () => {
  assert.equal(new Set(CATEGORY_PRESETS).size, CATEGORY_PRESETS.length);
  assert.equal(CATEGORY_PRESETS[0], UNCATEGORIZED);
  assert.ok(CATEGORY_PRESETS.includes("Bahan baku"));
  assert.ok(CATEGORY_PRESETS.includes("Operasional"));
  assert.ok(CATEGORY_PRESETS.includes("Penjualan"));
  assert.ok(CATEGORY_PRESETS.includes("Gaji karyawan"));
  CATEGORY_PRESETS.forEach((preset) => {
    assert.ok(preset.length <= CATEGORY_MAX_LENGTH);
    assert.equal(preset, preset.trim());
  });
});

test("kategori dinormalisasi dari preset, teks kustom, dan nilai kosong", () => {
  assert.equal(normalizeCategory("  bahan baku "), "Bahan baku");
  assert.equal(normalizeCategory("OPERASIONAL"), "Operasional");
  assert.equal(normalizeCategory("Bekal anak sekolah"), "Bekal anak sekolah");
  assert.equal(normalizeCategory("  Bekal anak sekolah  "), "Bekal anak sekolah");
  assert.equal(normalizeCategory(""), null);
  assert.equal(normalizeCategory("   "), null);
  assert.equal(normalizeCategory(null), null);
  assert.equal(normalizeCategory(undefined), null);
});

test("kategori dipotong pada batas kolom database", () => {
  assert.equal(normalizeCategory("x".repeat(80)).length, CATEGORY_MAX_LENGTH);
});

test("label kosong selalu tampil sebagai kategori belum dipilih", () => {
  assert.equal(categoryLabel(null), UNCATEGORIZED);
  assert.equal(categoryLabel("   "), UNCATEGORIZED);
  assert.equal(categoryLabel("Sewa"), "Sewa");
});

test("pilihan popup: teks kustom mengalahkan chip dan nilai kosong menjadi null", () => {
  assert.equal(categoryFromChoice("Bahan baku", " Gas LPG "), "Gas LPG");
  assert.equal(categoryFromChoice("Bahan baku", ""), "Bahan baku");
  assert.equal(categoryFromChoice("Bahan baku", null), "Bahan baku");
  assert.equal(categoryFromChoice(null, "Operasional"), "Operasional");
  assert.equal(categoryFromChoice(null, "  "), null);
  assert.equal(categoryFromChoice(undefined, undefined), null);
  assert.equal(categoryFromChoice("bahan baku", ""), "Bahan baku");
  assert.equal(categoryFromChoice(null, UNCATEGORIZED), UNCATEGORIZED);
});

test("semua preset memiliki logo dan logo-nya unik", () => {
  assert.equal(CATEGORY_PRESETS.length, Object.keys(CATEGORY_ICONS).length);
  assert.equal(CATEGORY_ICONS[UNCATEGORIZED], "🏷️");
  assert.equal(CATEGORY_ICONS["Penjualan"], "🛒");
  assert.equal(CATEGORY_ICONS["Bahan baku"], "📦");
  const icons = Object.values(CATEGORY_ICONS);
  assert.equal(new Set(icons).size, icons.length);
  icons.forEach((icon) => assert.ok(icon.length >= 1));
});

test("logo hanya untuk preset; kategori kustom tidak berlogo", () => {
  assert.equal(categoryIcon("bahan baku"), "📦");
  assert.equal(categoryIcon("OPERASIONAL"), "⚙️");
  assert.equal(categoryIcon(null), "🏷️");
  assert.equal(categoryIcon("Bekal anak sekolah"), "");
  assert.equal(categoryIcon("Gas LPG"), "");
});

test("presentasi kategori = logo + nama; nilai kustom tanpa logo", () => {
  assert.equal(categoryPresentation("Bahan baku"), "📦 Bahan baku");
  assert.equal(categoryPresentation(null), "🏷️ Belum dikategorikan");
  assert.equal(categoryPresentation("Bekal anak sekolah"), "Bekal anak sekolah");
});
