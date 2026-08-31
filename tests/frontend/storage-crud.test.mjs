import test from "node:test";
import assert from "node:assert/strict";

import {
  HISTORY_KEY,
  calculateSummary,
  createManualTransaction,
  createReceiptTransaction,
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

test("satu nota dikonfirmasi sebagai satu transaksi dengan banyak rincian", () => {
  const storage = new MemoryStorage();
  const response = {
    success: true,
    source: "receipt",
    ocr_text: "RAW OCR TIDAK DISIMPAN",
    raw_output: "RAW MODEL TIDAK DISIMPAN",
    extraction_method: "llama_soft_prompt_receipt",
    validation: { status: "valid", warnings: [] },
    image: "FOTO TIDAK DISIMPAN",
    data: {
      item_name: null,
      quantity: null,
      unit: null,
      total_price: 80000,
      date: "2026-08-26",
      transaction_type: "expense",
      receipt: {
        merchant_name: "Toko Makmur",
        receipt_number: "INV-001",
        subtotal: 70000,
        discount: 5000,
        tax: 10000,
        service_charge: 5000,
        total: 80000,
        warnings: ["transien"],
        items: [
          { item_name: "Minyak", quantity: 2, unit: "liter", unit_price: 20000, line_total: 40000, confidence: 0.91 },
          { item_name: "Beras", quantity: 2, unit: "kg", unit_price: 15000, line_total: 30000, confidence: 0.93 },
        ],
      },
    },
  };

  assert.equal(loadHistory(storage).length, 0, "hasil OCR belum tersimpan sebelum konfirmasi");
  const saved = createReceiptTransaction(response, {
    items: [
      { item_name: "Minyak Goreng", quantity: 2, unit: "liter", unit_price: 21000, line_total: 42000 },
      { item_name: "Beras", quantity: 2, unit: "kg", unit_price: 16000, line_total: 32000 },
    ],
  }, {
    storage,
    idFactory: () => "receipt-1",
    now: new Date(2026, 7, 30, 10, 0, 0),
  });

  assert.equal(saved.history.length, 1);
  assert.equal(saved.record.source, "receipt");
  assert.equal(saved.record.transaction_type, "expense");
  assert.equal(saved.record.date, "2026-08-30");
  assert.equal(saved.record.total_price, 74000);
  assert.equal(saved.record.receipt.total, 74000);
  assert.equal(saved.record.receipt.items.length, 2);
  assert.equal(saved.record.receipt.items[0].item_name, "Minyak Goreng");
  assert.deepEqual(calculateSummary(saved.history), { income: 0, expense: 74000, balance: -74000 });

  const serialized = storage.getItem(HISTORY_KEY);
  assert.doesNotMatch(serialized, /RAW OCR|RAW MODEL|FOTO TIDAK|ocr_text|raw_output|image|warnings|transien|INV-001|subtotal|discount|tax|service_charge|receipt_number/);
});

test("edit transaksi induk mempertahankan rincian nota", () => {
  const storage = new MemoryStorage();
  const response = {
    success: true,
    source: "receipt",
    data: {
      total_price: 50000,
      date: "2026-08-26",
      receipt: {
        merchant_name: "Warung Ibu",
        total: 50000,
        items: [{ item_name: "Telur", quantity: 2, unit: "kg", line_total: 50000 }],
      },
    },
  };
  createReceiptTransaction(response, {
    date: "2026-08-26",
    items: [{ item_name: "Telur", quantity: 2, unit: "kg", unit_price: 25000, line_total: 50000 }],
  }, {
    storage,
    idFactory: () => "receipt-edit",
  });
  const updated = updateTransaction("receipt-edit", manualInput({
    transaction_type: "expense",
    date: "2026-08-27",
    total_price: 55000,
  }), { storage });

  assert.equal(updated.record.receipt.merchant_name, "Warung Ibu");
  assert.equal(updated.record.receipt.items[0].item_name, "Telur");
});
