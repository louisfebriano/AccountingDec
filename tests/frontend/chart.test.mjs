import test from "node:test";
import assert from "node:assert/strict";

import {
  aggregateTransactionsByPeriod,
  aggregateWeeklyTransactions,
  describeChartPoint,
  describePeriodInsight,
  getLastSevenDateKeys,
  renderTransactionChart,
} from "../../pwa/chart.js";
import {
  createManualTransaction,
  deleteTransaction,
  updateTransaction,
} from "../../pwa/storage.js";

class MemoryStorage {
  constructor() { this.values = new Map(); }
  getItem(key) { return this.values.get(key) ?? null; }
  setItem(key, value) { this.values.set(key, value); }
  removeItem(key) { this.values.delete(key); }
}

const today = new Date(2026, 7, 22, 12);

class FakeSvgElement {
  constructor(name) {
    this.name = name;
    this.attributes = new Map();
    this.children = [];
    this.listeners = new Map();
    this.style = {};
  }

  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = [...children]; }
  addEventListener(name, listener) { this.listeners.set(name, listener); }
}

test("grafik membentuk tujuh hari termasuk hari ini dan mengisi hari kosong dengan nol", () => {
  assert.deepEqual(getLastSevenDateKeys(today), [
    "2026-08-16", "2026-08-17", "2026-08-18", "2026-08-19",
    "2026-08-20", "2026-08-21", "2026-08-22",
  ]);
  const points = aggregateWeeklyTransactions([
    { date: "2026-08-17", total_price: 100000, transaction_type: "income" },
    { date: "2026-08-17", total_price: 50000, transaction_type: "income" },
    { date: "2026-08-22", total_price: 25000, transaction_type: "expense" },
    { date: "2026-08-22", total_price: 999999, transaction_type: "unknown" },
    { date: "2026-08-15", total_price: 500000, transaction_type: "income" },
  ], today);
  assert.deepEqual(points[0], { date: "2026-08-16", income: 0, expense: 0 });
  assert.deepEqual(points[1], { date: "2026-08-17", income: 150000, expense: 0 });
  assert.deepEqual(points[6], { date: "2026-08-22", income: 0, expense: 25000 });
});

test("setiap titik menyediakan label tanggal, pemasukan, dan pengeluaran", () => {
  const description = describeChartPoint({
    date: "2026-08-22",
    income: 150000,
    expense: 75000,
  });
  assert.match(description.dateLabel, /22 Agustus 2026/i);
  assert.equal(description.incomeLabel, "Rp150.000");
  assert.equal(description.expenseLabel, "Rp75.000");
  assert.match(description.ariaLabel, /Pemasukan Rp150\.000, pengeluaran Rp75\.000/i);
});

test("insight periode diringkas menjadi satu kalimat lengkap", () => {
  const insight = describePeriodInsight("Tahun 2026", {
    income: 6350021,
    expense: 125000,
  });
  assert.deepEqual(insight, {
    state: "positive",
    text: "Tahun 2026 mencatat pemasukan Rp6.350.021 dan pengeluaran Rp125.000, sehingga menghasilkan surplus Rp6.225.021.",
  });
});

test("grafik bulan diringkas per minggu agar seluruh rentang terlihat", () => {
  const chart = aggregateTransactionsByPeriod([
    { date: "2026-08-01", total_price: 100000, transaction_type: "income" },
    { date: "2026-08-22", total_price: 25000, transaction_type: "expense" },
    { date: "2026-09-01", total_price: 999999, transaction_type: "income" },
  ], {
    mode: "month",
    start: "2026-08-01",
    end: "2026-08-31",
    label: "Agustus 2026",
  }, today);

  assert.equal(chart.granularity, "week");
  assert.equal(chart.points.length, 5);
  assert.equal(chart.points[0].date, "2026-08-01");
  assert.equal(chart.points[0].endDate, "2026-08-07");
  assert.equal(chart.points[0].income, 100000);
  assert.equal(chart.points[3].date, "2026-08-22");
  assert.equal(chart.points[3].endDate, "2026-08-28");
  assert.equal(chart.points[3].expense, 25000);
  assert.equal(chart.points.at(-1).endDate, "2026-08-31");
  assert.equal(chart.points.reduce((total, point) => total + point.income, 0), 100000);
});

test("grafik tahun memakai dua belas kelompok bulanan", () => {
  const chart = aggregateTransactionsByPeriod([
    { date: "2026-01-10", total_price: 50000, transaction_type: "expense" },
    { date: "2026-08-22", total_price: 150000, transaction_type: "income" },
  ], {
    mode: "year",
    start: "2026-01-01",
    end: "2026-12-31",
    label: "Tahun 2026",
  }, today);

  assert.equal(chart.granularity, "month");
  assert.equal(chart.points.length, 12);
  assert.equal(chart.points[0].expense, 50000);
  assert.equal(chart.points[7].income, 150000);
  assert.match(chart.points[7].periodLabel, /Agustus 2026/i);
});

test("rentang custom menengah diringkas per minggu tanpa keluar dari bounds", () => {
  const chart = aggregateTransactionsByPeriod([
    { date: "2026-07-01", total_price: 10000, transaction_type: "income" },
    { date: "2026-08-09", total_price: 20000, transaction_type: "expense" },
  ], {
    mode: "custom",
    start: "2026-07-01",
    end: "2026-08-09",
    label: "1 Jul 2026–9 Agu 2026",
  }, today);

  assert.equal(chart.granularity, "week");
  assert.equal(chart.points.length, 6);
  assert.equal(chart.points[0].date, "2026-07-01");
  assert.equal(chart.points.at(-1).endDate, "2026-08-09");
  assert.equal(chart.points[0].income, 10000);
  assert.equal(chart.points.at(-1).expense, 20000);
});

test("hover titik menampilkan garis bantu putus-putus dan hide menghormati pin tooltip", () => {
  const previousDocument = globalThis.document;
  globalThis.document = {
    createElementNS: (_namespace, name) => new FakeSvgElement(name),
  };
  try {
    const svg = new FakeSvgElement("svg");
    let keepPinned = true;
    renderTransactionChart(svg, [{
      date: "2026-08-22",
      endDate: "2026-08-22",
      axisLabel: "22/8",
      income: 150000,
      expense: 75000,
    }], {
      onPointHide: () => !keepPinned,
    });

    const guides = svg.children.filter(
      (element) => element.attributes.get("class") === "chart-hover-guide",
    );
    const zones = svg.children.filter(
      (element) => element.attributes.get("class") === "chart-hover-zone",
    );
    const incomePoint = svg.children.find(
      (element) => element.attributes.get("class")?.includes("chart-income-dot"),
    );
    assert.equal(guides.length, 2);
    assert.equal(zones.length, 1);
    assert.equal(zones[0].attributes.get("fill"), "transparent");
    assert.equal(zones[0].attributes.get("pointer-events"), "all");
    assert.ok(incomePoint);

    zones[0].listeners.get("pointerenter")({ clientX: 120, clientY: 80 });
    assert.equal(guides[0].attributes.get("visibility"), "visible");
    assert.equal(guides[1].attributes.get("visibility"), "hidden");

    incomePoint.listeners.get("pointerenter")();
    assert.ok(guides.every((guide) => guide.attributes.get("visibility") === "visible"));

    incomePoint.listeners.get("pointerleave")();
    assert.ok(guides.every((guide) => guide.attributes.get("visibility") === "visible"));

    keepPinned = false;
    incomePoint.listeners.get("pointerleave")();
    assert.ok(guides.every((guide) => guide.attributes.get("visibility") === "hidden"));
  } finally {
    globalThis.document = previousDocument;
  }
});

test("grafik panjang tetap memakai lebar responsif tanpa min-width horizontal", () => {
  const previousDocument = globalThis.document;
  globalThis.document = {
    createElementNS: (_namespace, name) => new FakeSvgElement(name),
  };
  try {
    const svg = new FakeSvgElement("svg");
    const points = Array.from({ length: 31 }, (_value, index) => ({
      date: `2026-08-${String(index + 1).padStart(2, "0")}`,
      axisLabel: `${index + 1}/8`,
      income: index * 1000,
      expense: index * 500,
    }));
    renderTransactionChart(svg, points);

    assert.equal(svg.attributes.get("viewBox"), "0 0 700 270");
    assert.equal(svg.style.minWidth, undefined);
    const axisLabels = svg.children.filter(
      (element) => element.attributes.get("class") === "chart-axis-label",
    );
    assert.ok(axisLabels.length <= 15);
  } finally {
    globalThis.document = previousDocument;
  }
});

test("hasil CRUD langsung dapat digunakan ulang oleh ringkasan grafik", () => {
  const storage = new MemoryStorage();
  const input = {
    transaction_type: "income",
    date: "2026-08-22",
    total_price: "100000",
    item_name: "",
    quantity: "",
    unit: "",
    note: "",
  };
  const created = createManualTransaction(input, { storage, idFactory: () => "one", now: today });
  assert.equal(aggregateWeeklyTransactions(created.history, today)[6].income, 100000);

  const updated = updateTransaction("one", { ...input, transaction_type: "expense", total_price: "75000" }, { storage, now: today });
  const point = aggregateWeeklyTransactions(updated.history, today)[6];
  assert.deepEqual(point, { date: "2026-08-22", income: 0, expense: 75000 });

  const deleted = deleteTransaction("one", storage);
  assert.deepEqual(aggregateWeeklyTransactions(deleted, today)[6], { date: "2026-08-22", income: 0, expense: 0 });
});
