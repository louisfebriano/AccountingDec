import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../../pwa/sw.js", import.meta.url), "utf8");
const appSource = await readFile(new URL("../../pwa/app.js", import.meta.url), "utf8");
const indexSource = await readFile(new URL("../../pwa/index.html", import.meta.url), "utf8");

test("service worker tidak mengintersep POST, endpoint API, atau audio", () => {
  assert.match(source, /request\.method !== "GET"/);
  assert.match(source, /url\.pathname\.startsWith\("\/extract"\)/);
  assert.match(source, /url\.pathname\.startsWith\("\/auth"\)/);
  assert.match(source, /url\.pathname\.startsWith\("\/transactions"\)/);
  assert.match(source, /url\.pathname\.startsWith\("\/health"\)/);
  assert.match(source, /request\.destination === "audio"/);
});

test("service worker menggunakan cache berversi dan membersihkan cache lama", () => {
  assert.match(source, /catatkas-shell-v23/);
  assert.match(source, /"\/styles\.css\?v=20"/);
  assert.match(source, /"\/filters\.js\?v=16"/);
  assert.match(source, /"\/chart\.js\?v=18"/);
  assert.match(source, /"\/theme\.js\?v=16"/);
  assert.match(source, /caches\.delete/);
  assert.match(source, /request\.mode === "navigate"/);
  assert.match(source, /fetch\(request\)[\s\S]*\.catch\(\(\) => caches\.match\(request\)\)/);
  assert.match(appSource, /updateViaCache:\s*"none"/);
  assert.match(indexSource, /\/styles\.css\?v=20/);
  assert.match(indexSource, /\/app\.js\?v=22/);
});

test("edit dan hapus menampilkan popup hasil aksi", () => {
  assert.match(indexSource, /id="action-popup"/);
  assert.match(indexSource, /aria-live="polite"/);
  assert.match(appSource, /Perubahan transaksi berhasil disimpan\./);
  assert.match(appSource, /Transaksi berhasil dihapus\./);
  assert.match(appSource, /Transaksi nota berhasil disimpan\./);
});

test("ikon mikrofon adalah tombol yang memakai alur recorder utama", () => {
  assert.match(indexSource, /<button class="record-visual" id="record-visual"/);
  assert.match(indexSource, /aria-label="Mulai merekam suara"/);
  assert.match(appSource, /recordVisual\.addEventListener\("click"/);
  assert.match(appSource, /recordingActive[\s\S]*stopButton\.click\(\)/);
  assert.match(appSource, /recordButton\.click\(\)/);
});
