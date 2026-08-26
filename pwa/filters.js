const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

export function localDateKey(value = new Date()) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseLocalDate(value) {
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

function monthName(month, year) {
  return new Intl.DateTimeFormat("id-ID", { month: "long", year: "numeric" })
    .format(new Date(year, month - 1, 1, 12));
}

function shortDate(value) {
  return new Intl.DateTimeFormat("id-ID", { day: "numeric", month: "short", year: "numeric" })
    .format(value);
}

export function getPeriodBounds(selection, today = new Date()) {
  const mode = selection.mode || "month";
  if (mode === "all") return { mode, start: null, end: null, label: "Semua transaksi" };

  if (mode === "week") {
    const selected = parseLocalDate(selection.weekDate) || today;
    const mondayOffset = (selected.getDay() + 6) % 7;
    const startDate = addDays(selected, -mondayOffset);
    const endDate = addDays(startDate, 6);
    return {
      mode,
      start: localDateKey(startDate),
      end: localDateKey(endDate),
      label: `${shortDate(startDate)}–${shortDate(endDate)}`,
    };
  }

  if (mode === "month") {
    const fallback = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
    const value = /^\d{4}-\d{2}$/.test(selection.month || "") ? selection.month : fallback;
    const [year, month] = value.split("-").map(Number);
    if (month < 1 || month > 12) throw new Error("Bulan yang dipilih tidak valid.");
    const lastDay = new Date(year, month, 0, 12).getDate();
    return {
      mode,
      start: `${value}-01`,
      end: `${value}-${String(lastDay).padStart(2, "0")}`,
      label: monthName(month, year),
    };
  }

  if (mode === "year") {
    const year = Number(selection.year || today.getFullYear());
    if (!Number.isInteger(year) || year < 1900 || year > 9999) {
      throw new Error("Tahun yang dipilih tidak valid.");
    }
    return { mode, start: `${year}-01-01`, end: `${year}-12-31`, label: `Tahun ${year}` };
  }

  if (mode === "custom") {
    const startDate = parseLocalDate(selection.startDate);
    const endDate = parseLocalDate(selection.endDate);
    if (!startDate || !endDate) throw new Error("Tanggal mulai dan akhir wajib diisi.");
    if (selection.startDate > selection.endDate) {
      throw new Error("Tanggal mulai tidak boleh melewati tanggal akhir.");
    }
    return {
      mode,
      start: selection.startDate,
      end: selection.endDate,
      label: `${shortDate(startDate)}–${shortDate(endDate)}`,
    };
  }

  throw new Error("Filter periode tidak dikenali.");
}

export function filterTransactionsByPeriod(history, selection, today = new Date()) {
  const bounds = getPeriodBounds(selection, today);
  if (bounds.mode === "all") return { transactions: [...history], bounds };
  return {
    transactions: history.filter(
      (transaction) => transaction.date >= bounds.start && transaction.date <= bounds.end,
    ),
    bounds,
  };
}
