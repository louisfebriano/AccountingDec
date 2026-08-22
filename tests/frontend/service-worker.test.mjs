import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../../pwa/sw.js", import.meta.url), "utf8");

test("service worker tidak mengintersep POST, endpoint API, atau audio", () => {
  assert.match(source, /request\.method !== "GET"/);
  assert.match(source, /url\.pathname === "\/extract"/);
  assert.match(source, /url\.pathname === "\/extract\/audio"/);
  assert.match(source, /request\.destination === "audio"/);
});

test("service worker menggunakan cache berversi dan membersihkan cache lama", () => {
  assert.match(source, /catatkas-shell-v3/);
  assert.match(source, /caches\.delete/);
  assert.match(source, /request\.mode === "navigate"/);
});
