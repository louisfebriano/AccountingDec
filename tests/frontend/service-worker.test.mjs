import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../../pwa/sw.js", import.meta.url), "utf8");
const appSource = await readFile(new URL("../../pwa/app.js", import.meta.url), "utf8");
const indexSource = await readFile(new URL("../../pwa/index.html", import.meta.url), "utf8");

test("service worker tidak mengintersep POST, endpoint API, atau audio", () => {
  assert.match(source, /request\.method !== "GET"/);
  assert.match(source, /url\.pathname === "\/extract"/);
  assert.match(source, /url\.pathname === "\/extract\/audio"/);
  assert.match(source, /request\.destination === "audio"/);
});

test("service worker menggunakan cache berversi dan membersihkan cache lama", () => {
  assert.match(source, /catatkas-shell-v15/);
  assert.match(source, /"\/styles\.css\?v=15"/);
  assert.match(source, /"\/filters\.js\?v=15"/);
  assert.match(source, /"\/chart\.js\?v=15"/);
  assert.match(source, /"\/theme\.js\?v=15"/);
  assert.match(source, /caches\.delete/);
  assert.match(source, /request\.mode === "navigate"/);
  assert.match(source, /fetch\(request\)[\s\S]*\.catch\(\(\) => caches\.match\(request\)\)/);
  assert.match(appSource, /updateViaCache:\s*"none"/);
  assert.match(indexSource, /\/styles\.css\?v=15/);
  assert.match(indexSource, /\/app\.js\?v=15/);
});

test("ikon mikrofon adalah tombol yang memakai alur recorder utama", () => {
  assert.match(indexSource, /<button class="record-visual" id="record-visual"/);
  assert.match(indexSource, /aria-label="Mulai merekam suara"/);
  assert.match(appSource, /recordVisual\.addEventListener\("click"/);
  assert.match(appSource, /recordingActive[\s\S]*stopButton\.click\(\)/);
  assert.match(appSource, /recordButton\.click\(\)/);
});
