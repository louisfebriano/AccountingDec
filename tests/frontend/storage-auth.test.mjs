import test from "node:test";
import assert from "node:assert/strict";

import {
  createManualTransaction,
  loadHistory,
  setHistoryUser,
} from "../../pwa/storage.js";

class MemoryStorage {
  constructor() { this.values = new Map(); }
  getItem(key) { return this.values.get(key) ?? null; }
  setItem(key, value) { this.values.set(key, value); }
  removeItem(key) { this.values.delete(key); }
}

const input = {
  transaction_type: "income",
  date: "2026-08-29",
  total_price: 100000,
  item_name: null,
  quantity: null,
  unit: null,
  note: null,
};

test("cache browser dipisahkan secara ketat berdasarkan user ID", () => {
  const storage = new MemoryStorage();
  setHistoryUser("user-a");
  createManualTransaction(input, { storage, idFactory: () => "a-1" });

  setHistoryUser("user-b");
  assert.deepEqual(loadHistory(storage), []);
  createManualTransaction(input, { storage, idFactory: () => "b-1" });

  setHistoryUser("user-a");
  const userAHistory = loadHistory(storage);
  assert.equal(userAHistory.length, 1);
  assert.equal(userAHistory[0].id, "a-1");
  assert.equal(userAHistory[0].user_id, "user-a");
  assert.notEqual(
    storage.getItem("catatkas.transactions.v2.user-a"),
    storage.getItem("catatkas.transactions.v2.user-b"),
  );
  setHistoryUser(null);
});
