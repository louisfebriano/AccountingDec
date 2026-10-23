import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const app = await readFile(new URL("../../pwa/app.js", import.meta.url), "utf8");
const html = await readFile(new URL("../../pwa/index.html", import.meta.url), "utf8");
const storage = await readFile(new URL("../../pwa/storage.js", import.meta.url), "utf8");

test("setiap transaksi melewati dialog konfirmasi editable sebelum disimpan", () => {
  assert.match(html, /id="transaction-confirm-dialog"[^>]*aria-labelledby="transaction-confirm-title"/);
  assert.match(html, /id="transaction-confirm-form"/);
  assert.match(html, /id="transaction-confirm-type"/);
  assert.match(html, /id="transaction-confirm-date"[^>]*required/);
  assert.match(html, /id="transaction-confirm-total-price"[^>]*required/);
  assert.match(html, /id="transaction-confirm-item-name"/);
  assert.match(html, /id="transaction-confirm-quantity"/);
  assert.match(html, /id="transaction-confirm-unit"/);
  assert.match(html, /id="transaction-confirm-note"/);
  assert.match(html, /id="transaction-confirm-category-grid"[^>]*role="group"/);
  assert.match(html, /id="transaction-confirm-custom-category"[^>]*list="category-presets"[^>]*maxlength="50"/);
  assert.match(html, /id="transaction-confirm-cancel-button"/);
  assert.match(html, /id="transaction-confirm-skip-button"/);
  assert.match(html, /<datalist id="category-presets">/);
  // Popup kategori lama tetap ada dan dipakai oleh Scan Nota, yang sudah memiliki
  // editor konfirmasinya sendiri.
  assert.match(html, /id="category-pick-dialog"[^>]*aria-labelledby="category-pick-title"/);
  assert.doesNotMatch(html, /id="manual-category"|id="receipt-confirm-category"/);

  // Chip preset dibangun untuk kedua tempat pemilih kategori.
  assert.match(app, /CATEGORY_PRESETS\.map\(\(preset\)/);
  assert.match(app, /chip\.className = "category-chip"/);

  // Teks, suara, manual, dan edit semuanya membuka dialog konfirmasi.
  assert.match(app, /source: "text"/);
  assert.match(app, /source: "voice"/);
  assert.match(app, /source: editingId \? "edit" : "manual"/);
  assert.match(app, /originalText: response\.input \|\| text/);
  assert.match(app, /originalText: response\.transcript \|\| ""/);

  // Penyimpanan akhir menulis kategori pilihan dialog konfirmasi.
  assert.match(app, /recordSuccessfulResponse\([\s\S]*?\{ category \},\s*\);/);
  assert.match(app, /createManualTransaction\(\{ \.\.\.fields, category \}\)/);
  assert.match(app, /const input = \{ \.\.\.fields, category \};/);
  assert.match(app, /updateTransaction\(pending\.editingId, input\)/);

  // Lewati kategori menyimpan nilai yang dijaga; tombol Simpan mewajibkan pilihan.
  assert.match(app, /confirmCategoryKeep = normalizeCategory\(category\) \?\? UNCATEGORIZED/);
  assert.match(app, /commitConfirmedTransaction\(confirmCategoryKeep\)/);
  assert.match(app, /categoryFromChoice\(confirmCategorySelected, elements\.confirmCategoryCustom\.value\)/);
  assert.match(app, /Pilih satu kategori atau tekan Lewati kategori\./);

  // Scan Nota tetap memakai popup kategori setelah editor barang dikonfirmasi.
  assert.match(app, /askCategory\(\{\s*summary: transactionSummaryText\(\{\s*transaction_type: "expense"/);
  assert.match(app, /categoryFromChoice\(selectedCategory, elements\.categoryPickCustom\.value\)/);
});

test("form manual/edit memiliki pemilih kategori dan nominal terformat", () => {
  // Pemilih kategori berada di form manual/edit, bukan hanya di dialog
  // konfirmasi, sehingga kategori ikut bisa diubah saat mengedit riwayat.
  assert.match(html, /id="manual-form-category-grid"[^>]*role="group"/);
  assert.match(html, /id="manual-form-custom-category"[^>]*list="category-presets"/);
  assert.match(app, /buildManualCategoryPicker\(\)/);
  assert.match(app, /syncManualCategoryPickerSelection\(\)/);
  assert.match(app, /categoryFromChoice\(\s*manualCategorySelected,\s*elements\.manualCategoryCustom\.value,?\s*\)/);
  assert.match(app, /category: formCategory,/);
  // Pemilihan kategori dari form diteruskan ke dialog konfirmasi.
  assert.match(app, /restoreTransactionForm\(pending\.snapshot \|\| \{\}, pending\.editingId\)/);
  assert.match(app, /manualCategoryCustom\.value = snapshot\.category/);
  // Nominal tampil dengan pemisah ribuan titik dan disimpan tanpa separator.
  assert.match(html, /id="transaction-confirm-total-price"[^>]*type="text"[^>]*inputmode="numeric"[^>]*required/);
  assert.match(app, /function formatNumberInput\(value\)/);
  assert.match(app, /total_price: rawDigits\(elements\.confirmTotalPrice\.value\)/);
  assert.match(app, /elements\.confirmTotalPrice\.value = formatNumberInput\(digits\)/);
});

test("riwayat, detail, dan hasil terakhir menampilkan kategori transaksi", () => {
  assert.match(html, /id="detail-category"/);
  assert.match(html, /id="result-category"/);
  assert.match(app, /category\.className = "history-category"/);
  assert.match(app, /category\.textContent = view\.category/);
  assert.match(app, /elements\.detailCategory\.textContent = view\.category/);
  assert.match(app, /elements\.resultCategory\.textContent = view\.category/);
});

test("filter kategori dan ringkasan per kategori mengikuti periode aktif", () => {
  assert.match(html, /id="category-filter"/);
  assert.match(html, /id="category-summary"/);
  assert.match(app, /refreshCategoryFilter\(\)/);
  assert.match(app, /filterTransactionsByCategory\(result\.transactions, category\)/);
  assert.match(app, /renderCategorySummary\(result\.transactions, result\.bounds\.label\)/);
  assert.match(app, /summarizeCategories\(transactions\)/);
  assert.match(app, /elements\.categoryFilter\.value = ""/);
});

test("setiap jalur penyimpanan menulis field kategori", () => {
  assert.match(storage, /category: normalizeCategory\(value\.category\)/);
  assert.match(storage, /category: normalizeCategory\(input\.category\)/);
  assert.match(storage, /normalizeCategory\(options\.category \?\? data\.category\) \?\? UNCATEGORIZED/);
  assert.match(storage, /category: chosenCategory/);
  assert.match(storage, /category: confirmation\.category \|\| UNCATEGORIZED/);
});
