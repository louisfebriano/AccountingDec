import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const app = await readFile(new URL("../../pwa/app.js", import.meta.url), "utf8");
const html = await readFile(new URL("../../pwa/index.html", import.meta.url), "utf8");

test("UI Scan Nota menyediakan kamera, preview, status, dan konfirmasi eksplisit", () => {
  assert.match(html, /id="receipt-tab"[\s\S]*Foto nota/);
  assert.match(html, /id="receipt-file"[\s\S]*accept="image\/jpeg,image\/png,image\/webp"[\s\S]*capture="environment"/);
  assert.match(html, /id="receipt-preview-image"/);
  assert.match(html, /id="receipt-confirm-form"/);
  assert.match(html, /id="receipt-confirm-date"[^>]*required/);
  assert.match(html, /id="receipt-confirm-total"[^>]*required/);
  assert.match(html, /Foto ulang/);
  assert.match(html, /Simpan transaksi/);
});

test("hasil server hanya disimpan di handler konfirmasi", () => {
  const scanHandler = app.match(/elements\.receiptForm\.addEventListener\("submit"[\s\S]*?\n}\);/);
  assert.ok(scanHandler);
  assert.doesNotMatch(scanHandler[0], /createReceiptTransaction/);
  assert.match(app, /receiptConfirmForm\.addEventListener\("submit"[\s\S]*createReceiptTransaction/);
  assert.match(app, /setBusy\(true, "receipt"\)/);
  assert.match(app, /humanizeError\(error, "receipt"\)/);
});

test("OCR raw dan URL preview dibersihkan dari memori antarmuka", () => {
  assert.match(app, /URL\.revokeObjectURL\(receiptPreviewUrl\)/);
  assert.match(app, /releaseProcessedReceiptFile\(\)[\s\S]*selectedReceiptFile = null/);
  assert.match(app, /extractReceipt\(selectedReceiptFile\)[\s\S]*releaseProcessedReceiptFile\(\)/);
  assert.match(app, /receiptOcrText\.textContent = ""/);
  assert.match(app, /resetReceiptSelection\(\)/);
});

test("detail nota dan riwayat menggunakan satu transaksi induk", () => {
  assert.match(app, /Belanja di \$\{transaction\.receipt\.merchant_name\}/);
  assert.match(app, /detailReceiptSection\.hidden = !isReceipt/);
  assert.match(app, /appendReceiptItems\(elements\.detailReceiptItems/);
});
