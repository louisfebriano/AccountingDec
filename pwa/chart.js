import { formatCompactRupiah, formatRupiah } from "./formatters.js?v=16";
import { localDateKey } from "./filters.js?v=16";

const SVG_NS = "http://www.w3.org/2000/svg";
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function parseDateKey(value) {
  if (!DATE_PATTERN.test(String(value || ""))) return null;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(year, month - 1, day, 12);
  if (parsed.getFullYear() !== year || parsed.getMonth() !== month - 1 || parsed.getDate() !== day) {
    return null;
  }
  return parsed;
}

function addDays(value, days) {
  const result = new Date(value);
  result.setDate(result.getDate() + days);
  return result;
}

function addMonths(value, months) {
  return new Date(value.getFullYear(), value.getMonth() + months, 1, 12);
}

function shortDate(value) {
  return new Intl.DateTimeFormat("id-ID", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(value);
}

function fullDate(value) {
  return new Intl.DateTimeFormat("id-ID", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(value);
}

function monthLabel(value) {
  return new Intl.DateTimeFormat("id-ID", { month: "long", year: "numeric" }).format(value);
}

function rangeLabel(start, end) {
  return localDateKey(start) === localDateKey(end)
    ? fullDate(start)
    : `${shortDate(start)}–${shortDate(end)}`;
}

function countDays(start, end) {
  const startUtc = Date.UTC(start.getFullYear(), start.getMonth(), start.getDate());
  const endUtc = Date.UTC(end.getFullYear(), end.getMonth(), end.getDate());
  return Math.floor((endUtc - startUtc) / 86400000) + 1;
}

function resolveChartBounds(history, bounds, today) {
  if (bounds?.start && bounds?.end) return bounds;
  const dates = history
    .map((transaction) => transaction.date)
    .filter((date) => parseDateKey(date))
    .sort();
  if (dates.length > 0) {
    return { ...bounds, mode: bounds?.mode || "all", start: dates[0], end: dates.at(-1) };
  }
  const end = new Date(today);
  end.setHours(12, 0, 0, 0);
  return {
    ...bounds,
    mode: bounds?.mode || "all",
    start: localDateKey(addDays(end, -6)),
    end: localDateKey(end),
  };
}

function chooseGranularity(bounds, dayCount) {
  if (bounds.mode === "year") return "month";
  if (bounds.mode === "month") return "week";
  if (dayCount <= 14) return "day";
  if (dayCount <= 183) return "week";
  return "month";
}

function createDailyPoints(start, end) {
  const points = [];
  for (let cursor = new Date(start); cursor <= end; cursor = addDays(cursor, 1)) {
    points.push({
      date: localDateKey(cursor),
      endDate: localDateKey(cursor),
      periodLabel: fullDate(cursor),
      axisLabel: `${cursor.getDate()}/${cursor.getMonth() + 1}`,
      income: 0,
      expense: 0,
    });
  }
  return points;
}

function createWeeklyPoints(start, end) {
  const points = [];
  for (let cursor = new Date(start); cursor <= end; cursor = addDays(cursor, 7)) {
    const bucketEnd = addDays(cursor, 6) < end ? addDays(cursor, 6) : new Date(end);
    points.push({
      date: localDateKey(cursor),
      endDate: localDateKey(bucketEnd),
      periodLabel: rangeLabel(cursor, bucketEnd),
      axisLabel: `${cursor.getDate()}/${cursor.getMonth() + 1}`,
      income: 0,
      expense: 0,
    });
  }
  return points;
}

function createMonthlyPoints(start, end) {
  const points = [];
  const firstMonth = new Date(start.getFullYear(), start.getMonth(), 1, 12);
  for (let cursor = firstMonth; cursor <= end; cursor = addMonths(cursor, 1)) {
    const monthEnd = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0, 12);
    const bucketStart = cursor < start ? new Date(start) : new Date(cursor);
    const bucketEnd = monthEnd > end ? new Date(end) : monthEnd;
    const isWholeMonth = bucketStart.getDate() === 1 && bucketEnd.getDate() === monthEnd.getDate();
    points.push({
      date: localDateKey(bucketStart),
      endDate: localDateKey(bucketEnd),
      periodLabel: isWholeMonth ? monthLabel(cursor) : rangeLabel(bucketStart, bucketEnd),
      axisLabel: new Intl.DateTimeFormat("id-ID", { month: "short" }).format(cursor),
      income: 0,
      expense: 0,
    });
  }
  return points;
}

export function describeChartPoint(point) {
  const parsed = new Date(`${point.date}T12:00:00`);
  const dateLabel = point.periodLabel || fullDate(parsed);
  return {
    dateLabel,
    incomeLabel: formatRupiah(point.income),
    expenseLabel: formatRupiah(point.expense),
    ariaLabel: `${dateLabel}. Pemasukan ${formatRupiah(point.income)}, pengeluaran ${formatRupiah(point.expense)}.`,
  };
}

export function describePeriodInsight(periodLabel, totals) {
  const income = Number(totals.income) || 0;
  const expense = Number(totals.expense) || 0;
  const balance = income - expense;
  if (!income && !expense) {
    return {
      state: "empty",
      text: `Belum ada transaksi pada ${periodLabel.toLocaleLowerCase("id-ID")}.`,
    };
  }
  if (balance > 0) {
    return {
      state: "positive",
      text: `${periodLabel} mencatat pemasukan ${formatRupiah(income)} dan pengeluaran ${formatRupiah(expense)}, sehingga menghasilkan surplus ${formatRupiah(balance)}.`,
    };
  }
  if (balance < 0) {
    return {
      state: "negative",
      text: `${periodLabel} mencatat pemasukan ${formatRupiah(income)} dan pengeluaran ${formatRupiah(expense)}, sehingga mengalami defisit ${formatRupiah(balance)}.`,
    };
  }
  return {
    state: "balanced",
    text: `${periodLabel} mencatat pemasukan dan pengeluaran seimbang sebesar ${formatRupiah(income)}.`,
  };
}

export function getLastSevenDateKeys(today = new Date()) {
  const dates = [];
  for (let offset = 6; offset >= 0; offset -= 1) {
    const date = new Date(today);
    date.setHours(12, 0, 0, 0);
    date.setDate(date.getDate() - offset);
    dates.push(localDateKey(date));
  }
  return dates;
}

export function aggregateWeeklyTransactions(history, today = new Date()) {
  const points = getLastSevenDateKeys(today).map((date) => ({ date, income: 0, expense: 0 }));
  const byDate = new Map(points.map((point) => [point.date, point]));
  history.forEach((transaction) => {
    const point = byDate.get(transaction.date);
    const value = Number(transaction.total_price);
    if (!point || !Number.isFinite(value)) return;
    if (transaction.transaction_type === "income") point.income += value;
    if (transaction.transaction_type === "expense") point.expense += value;
  });
  return points;
}

/** Aggregate transaction totals using the same date bounds as the history filter. */
export function aggregateTransactionsByPeriod(history, bounds, today = new Date()) {
  const resolvedBounds = resolveChartBounds(history, bounds, today);
  const start = parseDateKey(resolvedBounds.start);
  const end = parseDateKey(resolvedBounds.end);
  if (!start || !end || start > end) throw new Error("Periode grafik tidak valid.");

  const dayCount = countDays(start, end);
  const granularity = chooseGranularity(resolvedBounds, dayCount);
  const points = granularity === "day"
    ? createDailyPoints(start, end)
    : granularity === "week"
      ? createWeeklyPoints(start, end)
      : createMonthlyPoints(start, end);

  history.forEach((transaction) => {
    const value = Number(transaction.total_price);
    if (!parseDateKey(transaction.date) || !Number.isFinite(value)) return;
    const point = points.find(
      (candidate) => transaction.date >= candidate.date && transaction.date <= candidate.endDate,
    );
    if (!point) return;
    if (transaction.transaction_type === "income") point.income += value;
    if (transaction.transaction_type === "expense") point.expense += value;
  });

  return { points, granularity, bounds: resolvedBounds };
}

// Lebar SVG selalu 100% panel, jadi tingginya ikut lebar layar. Di layar lebar
// kanvas dipendekkan 20%; di hp ruangnya sudah sempit, jadi rasio penuh
// dipertahankan supaya grafik tidak jadi terlalu ceper.
export const CHART_WIDE_HEIGHT = 216;
export const CHART_COMPACT_HEIGHT = 270;
export const CHART_WIDE_MEDIA_QUERY = "(min-width: 480px)";

export function chartHeight() {
  const query = globalThis.matchMedia?.(CHART_WIDE_MEDIA_QUERY);
  return query && !query.matches ? CHART_COMPACT_HEIGHT : CHART_WIDE_HEIGHT;
}

function svgElement(name, attributes = {}) {
  const element = document.createElementNS(SVG_NS, name);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
  return element;
}

function linePath(points, key, xFor, yFor) {
  return points.map((point, index) => `${index ? "L" : "M"}${xFor(index)} ${yFor(point[key])}`).join(" ");
}

export function renderTransactionChart(svg, points, options = {}) {
  svg.replaceChildren();
  const width = 700;
  const height = chartHeight();
  const margin = { top: 20, right: 18, bottom: 42, left: 72 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const dataMax = Math.max(0, ...points.flatMap((point) => [point.income, point.expense]));
  const maxValue = dataMax || 1000;
  const xFor = (index) => points.length === 1
    ? margin.left + plotWidth / 2
    : margin.left + (plotWidth * index) / Math.max(1, points.length - 1);
  const yFor = (value) => margin.top + plotHeight - (Number(value) / maxValue) * plotHeight;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

  const verticalGuide = svgElement("line", {
    x1: margin.left,
    y1: margin.top,
    x2: margin.left,
    y2: margin.top + plotHeight,
    class: "chart-hover-guide",
    visibility: "hidden",
    "aria-hidden": "true",
  });
  const horizontalGuide = svgElement("line", {
    x1: margin.left,
    y1: margin.top + plotHeight,
    x2: width - margin.right,
    y2: margin.top + plotHeight,
    class: "chart-hover-guide",
    visibility: "hidden",
    "aria-hidden": "true",
  });
  svg.append(verticalGuide, horizontalGuide);

  const showGuide = (index, value) => {
    const x = xFor(index);
    const y = yFor(value);
    verticalGuide.setAttribute("x1", String(x));
    verticalGuide.setAttribute("x2", String(x));
    verticalGuide.setAttribute("y1", String(y));
    verticalGuide.setAttribute("y2", String(margin.top + plotHeight));
    horizontalGuide.setAttribute("x1", String(margin.left));
    horizontalGuide.setAttribute("x2", String(x));
    horizontalGuide.setAttribute("y1", String(y));
    horizontalGuide.setAttribute("y2", String(y));
    verticalGuide.setAttribute("visibility", "visible");
    horizontalGuide.setAttribute("visibility", "visible");
  };

  const showDateGuide = (index) => {
    const x = xFor(index);
    verticalGuide.setAttribute("x1", String(x));
    verticalGuide.setAttribute("x2", String(x));
    verticalGuide.setAttribute("y1", String(margin.top));
    verticalGuide.setAttribute("y2", String(margin.top + plotHeight));
    verticalGuide.setAttribute("visibility", "visible");
    horizontalGuide.setAttribute("visibility", "hidden");
  };

  const hideGuide = () => {
    verticalGuide.setAttribute("visibility", "hidden");
    horizontalGuide.setAttribute("visibility", "hidden");
  };

  [0, 0.5, 1].forEach((ratio) => {
    const value = maxValue * ratio;
    const y = yFor(value);
    svg.append(svgElement("line", {
      x1: margin.left,
      y1: y,
      x2: width - margin.right,
      y2: y,
      class: "chart-grid-line",
    }));
    const label = svgElement("text", { x: margin.left - 10, y: y + 4, class: "chart-axis-label", "text-anchor": "end" });
    label.textContent = formatCompactRupiah(value);
    svg.append(label);
  });

  const labelStep = Math.max(1, Math.ceil(points.length / 12));
  points.forEach((point, index) => {
    if (index % labelStep !== 0 && index !== points.length - 1) return;
    const label = svgElement("text", {
      x: xFor(index),
      y: height - 14,
      class: "chart-axis-label",
      "text-anchor": "middle",
    });
    label.textContent = point.axisLabel || (() => {
      const date = new Date(`${point.date}T12:00:00`);
      return `${date.getDate()}/${date.getMonth() + 1}`;
    })();
    svg.append(label);
  });

  points.forEach((point, index) => {
    const currentX = xFor(index);
    const previousX = index === 0 ? margin.left : xFor(index - 1);
    const nextX = index === points.length - 1 ? width - margin.right : xFor(index + 1);
    const left = index === 0 ? margin.left : (previousX + currentX) / 2;
    const right = index === points.length - 1 ? width - margin.right : (currentX + nextX) / 2;
    const zone = svgElement("rect", {
      x: left,
      y: margin.top,
      width: Math.max(1, right - left),
      height: plotHeight,
      class: "chart-hover-zone",
      fill: "transparent",
      "pointer-events": "all",
      "aria-hidden": "true",
    });
    const show = (trigger, event) => {
      showDateGuide(index);
      options.onPointShow?.({ point, target: zone, trigger, pointerEvent: event });
    };
    const hide = (trigger) => {
      const shouldHide = options.onPointHide?.({ point, target: zone, trigger });
      if (shouldHide !== false) hideGuide();
    };
    zone.addEventListener("pointerenter", (event) => show("hover", event));
    zone.addEventListener("pointerleave", () => hide("hover"));
    zone.addEventListener("click", (event) => show("click", event));
    svg.append(zone);
  });

  [
    ["income", "chart-income-line", "chart-income-dot"],
    ["expense", "chart-expense-line", "chart-expense-dot"],
  ].forEach(([key, lineClass, dotClass]) => {
    svg.append(svgElement("path", {
      d: linePath(points, key, xFor, yFor),
      class: `chart-line ${lineClass}`,
    }));
    points.forEach((point, index) => {
      const description = describeChartPoint(point);
      const circle = svgElement("circle", {
        cx: xFor(index),
        cy: yFor(point[key]),
        r: 4,
        class: `chart-point ${dotClass}`,
        role: "button",
        tabindex: "0",
        focusable: "true",
        "aria-label": description.ariaLabel,
      });
      const show = (trigger) => {
        showGuide(index, point[key]);
        options.onPointShow?.({ point, target: circle, trigger });
      };
      const hide = (trigger) => {
        const shouldHide = options.onPointHide?.({ point, target: circle, trigger });
        if (shouldHide !== false) hideGuide();
      };
      circle.addEventListener("pointerenter", () => show("hover"));
      circle.addEventListener("pointerleave", () => hide("hover"));
      circle.addEventListener("focus", () => show("focus"));
      circle.addEventListener("blur", () => hide("focus"));
      circle.addEventListener("click", () => show("click"));
      circle.addEventListener("keydown", (event) => {
        if (!["Enter", " "].includes(event.key)) return;
        event.preventDefault();
        show("click");
      });
      svg.append(circle);
    });
  });

  const income = points.reduce((total, point) => total + point.income, 0);
  const expense = points.reduce((total, point) => total + point.expense, 0);
  svg.setAttribute(
    "aria-label",
    `Grafik ${options.periodLabel || "periode dipilih"}. Total pemasukan ${formatRupiah(income)}, total pengeluaran ${formatRupiah(expense)}.`,
  );
  return { income, expense };
}

// Kept as a compatibility alias for existing imports and tests.
export const renderWeeklyChart = renderTransactionChart;
