import test from "node:test";
import assert from "node:assert/strict";

import { filterTransactionsByPeriod, getPeriodBounds } from "../../pwa/filters.js";

const today = new Date(2026, 7, 22, 12);
const history = [
  { id: "a", date: "2026-08-16" },
  { id: "b", date: "2026-08-17" },
  { id: "c", date: "2026-08-22" },
  { id: "d", date: "2026-08-23" },
  { id: "e", date: "2026-07-31" },
  { id: "f", date: "2025-08-22" },
];

test("filter minggu memakai Senin–Minggu kalender lokal", () => {
  const result = filterTransactionsByPeriod(history, { mode: "week", weekDate: "2026-08-22" }, today);
  assert.equal(result.bounds.start, "2026-08-17");
  assert.equal(result.bounds.end, "2026-08-23");
  assert.deepEqual(result.transactions.map((item) => item.id), ["b", "c", "d"]);
});

test("filter bulan dan tahun memilih periode yang tepat", () => {
  const month = filterTransactionsByPeriod(history, { mode: "month", month: "2026-08" }, today);
  assert.deepEqual(month.transactions.map((item) => item.id), ["a", "b", "c", "d"]);
  const year = filterTransactionsByPeriod(history, { mode: "year", year: "2026" }, today);
  assert.deepEqual(year.transactions.map((item) => item.id), ["a", "b", "c", "d", "e"]);
});

test("filter custom date inklusif dan menolak rentang terbalik", () => {
  const custom = filterTransactionsByPeriod(history, {
    mode: "custom",
    startDate: "2026-08-16",
    endDate: "2026-08-22",
  }, today);
  assert.deepEqual(custom.transactions.map((item) => item.id), ["a", "b", "c"]);
  assert.throws(
    () => getPeriodBounds({ mode: "custom", startDate: "2026-08-22", endDate: "2026-08-16" }, today),
    /tidak boleh melewati/,
  );
});

test("filter semua tidak mengubah urutan atau data", () => {
  const result = filterTransactionsByPeriod(history, { mode: "all" }, today);
  assert.deepEqual(result.transactions, history);
  assert.notEqual(result.transactions, history);
});
