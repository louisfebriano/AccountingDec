import test from "node:test";
import assert from "node:assert/strict";

import {
  HISTORY_KEY,
  createManualTransaction,
  deleteTransaction,
  loadHistory,
  recordSuccessfulResponse,
  updateTransaction,
} from "../../pwa/storage.js";
import { presentTransactionDetail } from "../../pwa/formatters.js";

class MemoryStorage {
  constructor() { this.values = new Map(); }
  getItem(key) { return this.values.get(key) ?? null; }
  setItem(key, value) { this.values.set(key, value); }
  removeItem(key) { this.values.delete(key); }
}

const manualInput = (overrides = {}) => ({
  transaction_type: "income",
  date: "2026-08-22",
  total_price: "250000",
  item_name: "",
  quantity: "",
  unit: "",
  note: "",
  ...overrides,
});

test("CRUD manual membuat, mengedit, dan menghapus transaksi dengan ID stabil", () => {
  const storage = new MemoryStorage();
  const created = createManualTransaction(manualInput(), {
    storage,
    now: new Date("2026-08-22T10:00:00+07:00"),
    idFactory: () => "manual-1",
  });
  assert.equal(created.record.id, "manual-1");
  assert.equal(created.record.source, "manual");
  assert.equal(created.record.item_name, null);
  assert.equal(created.record.quantity, null);
  assert.equal(created.record.unit, null);
  assert.equal(created.record.note, null);

  const updated = updateTransaction("manual-1", manualInput({
    transaction_type: "expense",
    total_price: "300000",
    item_name: "Tepung",
  }), { storage, now: new Date("2026-08-22T11:00:00+07:00") });
  assert.equal(updated.record.id, "manual-1");
  assert.equal(updated.record.source, "manual");
  assert.equal(updated.record.transaction_type, "expense");
  assert.equal(updated.record.total_price, 300000);

  const remaining = deleteTransaction("manual-1", storage);
  assert.deepEqual(remaining, []);
  assert.deepEqual(loadHistory(storage), []);
});

test("form manual menolak nominal dan quantity yang tidak positif", () => {
  const storage = new MemoryStorage();
  assert.throws(
    () => createManualTransaction(manualInput({ total_price: "0" }), { storage }),
    /Nominal harus berupa angka positif/,
  );
  assert.throws(
    () => createManualTransaction(manualInput({ quantity: "-2" }), { storage }),
    /Quantity harus berupa angka positif/,
  );
  assert.throws(
    () => createManualTransaction(manualInput({ transaction_type: "unknown" }), { storage }),
    /pemasukan atau pengeluaran/,
  );
});

test("transkrip raw dan teks normalisasi suara disimpan terpisah tanpa audio atau raw output", () => {
  const storage = new MemoryStorage();
  const response = {
    success: true,
    transcript: "beli tepung dua karung total dua ratus ribu",
    normalized_text: "beli tepung 2 karung total 200000",
    raw_output: "rahasia model",
    audio: "binary-audio",
    data: {
      item_name: "Tepung",
      quantity: 2,
      unit: "karung",
      total_price: 200000,
      date: "2026-08-22",
      transaction_type: "expense",
      raw_output: "jangan simpan",
    },
  };
  const saved = recordSuccessfulResponse(response, "voice", response.transcript, {
    storage,
    idFactory: () => "voice-1",
  });
  assert.equal(saved.record.transcript, response.transcript);
  assert.equal(saved.record.normalized_text, response.normalized_text);
  assert.equal(saved.record.original_text, null);

  const serialized = storage.getItem(HISTORY_KEY);
  assert.doesNotMatch(serialized, /raw_output|binary-audio|rahasia model/);
  const detail = presentTransactionDetail(saved.record, "2026-08-22");
  assert.equal(detail.originalLabel, "Transkrip asli");
  assert.equal(detail.originalText, response.transcript);
  assert.equal(detail.normalizedText, response.normalized_text);
});

test("input teks tetap disebut input asli dan data lama tanpa field baru tetap terbaca", () => {
  const storage = new MemoryStorage();
  storage.setItem(HISTORY_KEY, JSON.stringify([{
    id: "legacy-1",
    source: "text",
    original_text: "jual bakmi 2 porsi 40 ribu",
    total_price: 40000,
    date: "2026-08-22",
    transaction_type: "income",
    raw_output: "hapus saat migrasi",
    audio: "jangan disimpan",
  }]));
  const record = loadHistory(storage)[0];
  const detail = presentTransactionDetail(record, "2026-08-22");
  assert.equal(record.id, "legacy-1");
  assert.equal(record.transcript, null);
  assert.equal(record.normalized_text, null);
  assert.equal(detail.originalLabel, "Input asli");
  assert.equal(detail.originalText, "jual bakmi 2 porsi 40 ribu");
  assert.doesNotMatch(storage.getItem(HISTORY_KEY), /raw_output|audio|hapus saat migrasi/);
});
