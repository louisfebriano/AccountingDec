import test from "node:test";
import assert from "node:assert/strict";

import { EMPTY_VALUE, presentTransaction } from "../../pwa/formatters.js";
import { RequestGate } from "../../pwa/request-gate.js";
import {
  calculateSummary,
  loadHistory,
  recordSuccessfulResponse,
} from "../../pwa/storage.js";

class MemoryStorage {
  constructor() { this.values = new Map(); }
  getItem(key) { return this.values.get(key) ?? null; }
  setItem(key, value) { this.values.set(key, value); }
  removeItem(key) { this.values.delete(key); }
}

function response(type, price, overrides = {}) {
  return {
    success: true,
    data: {
      item_name: null,
      quantity: null,
      unit: null,
      total_price: price,
      date: "2026-08-22",
      transaction_type: type,
      ...overrides,
    },
  };
}

test("pemasukan, pengeluaran, dan nilai null dipresentasikan dengan benar", () => {
  const income = presentTransaction({ ...response("income", 3000000).data, source: "text" }, "2026-08-22");
  const expense = presentTransaction({ ...response("expense", 250000).data, source: "voice" }, "2026-08-22");
  const unknown = presentTransaction({ ...response("unknown", 500000).data, source: "text" }, "2026-08-22");

  assert.equal(income.type, "Pemasukan");
  assert.equal(income.price, "Rp3.000.000");
  assert.equal(income.item, EMPTY_VALUE);
  assert.equal(income.quantity, EMPTY_VALUE);
  assert.equal(income.unit, EMPTY_VALUE);
  assert.equal(expense.type, "Pengeluaran");
  assert.equal(expense.source, "Suara");
  assert.equal(unknown.type, "Perlu ditinjau");
});

test("transaksi berhasil memperbarui riwayat dan ringkasan lokal", () => {
  const storage = new MemoryStorage();
  recordSuccessfulResponse(response("income", 300000), "text", "pemasukan 300 ribu", { storage });
  recordSuccessfulResponse(response("expense", 100000), "voice", "beli tepung 100 ribu", { storage });
  const history = loadHistory(storage);
  const summary = calculateSummary(history);

  assert.equal(history.length, 2);
  assert.deepEqual(summary, { income: 300000, expense: 100000, balance: 200000 });
  assert.equal(Object.hasOwn(history[0], "raw_output"), false);
  assert.equal(Object.hasOwn(history[0], "audio"), false);
});

test("riwayat AccountingDec lama dimigrasikan ke penyimpanan CatatKas", () => {
  const storage = new MemoryStorage();
  storage.setItem("accountingdec.transactions.v1", JSON.stringify([
    { total_price: 100000, transaction_type: "income" },
  ]));

  const history = loadHistory(storage);

  assert.equal(history.length, 1);
  assert.notEqual(storage.getItem("catatkas.transactions.v1"), null);
  assert.equal(storage.getItem("accountingdec.transactions.v1"), null);
});

test("respons gagal tidak membuat transaksi palsu", () => {
  const storage = new MemoryStorage();
  assert.throws(
    () => recordSuccessfulResponse({ success: false, data: null }, "text", "transfer", { storage }),
    /tidak boleh disimpan/,
  );
  assert.equal(loadHistory(storage).length, 0);
});

test("riwayat dibatasi 50 transaksi", () => {
  const storage = new MemoryStorage();
  for (let index = 0; index < 55; index += 1) {
    recordSuccessfulResponse(response("income", index + 1), "text", `transaksi ${index}`, { storage });
  }
  assert.equal(loadHistory(storage).length, 50);
});

test("request gate mencegah pengiriman ganda", async () => {
  const gate = new RequestGate();
  let release;
  const pending = gate.run(() => new Promise((resolve) => { release = resolve; }));
  const duplicate = await gate.run(async () => "tidak boleh dijalankan");
  assert.equal(duplicate.skipped, true);
  release("selesai");
  assert.equal((await pending).value, "selesai");
});
