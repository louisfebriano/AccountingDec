export const EMPTY_VALUE = "—";

export const TYPE_LABELS = {
  income: "Pemasukan",
  expense: "Pengeluaran",
  unknown: "Perlu ditinjau",
};

export function formatRupiah(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return EMPTY_VALUE;
  return `Rp${Math.round(Math.abs(number)).toLocaleString("id-ID")}`;
}

export function formatOptional(value) {
  return value === null || value === undefined || value === "" ? EMPTY_VALUE : String(value);
}

export function formatTransactionDate(value, localDate) {
  if (!value) return EMPTY_VALUE;
  if (value === localDate) return "Hari ini";
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("id-ID", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(parsed);
}

export function presentTransaction(record, localDate) {
  return {
    type: TYPE_LABELS[record.transaction_type] || TYPE_LABELS.unknown,
    price: formatRupiah(record.total_price),
    date: formatTransactionDate(record.date, localDate),
    item: formatOptional(record.item_name),
    quantity: formatOptional(record.quantity),
    unit: formatOptional(record.unit),
    source: record.source === "voice" ? "Suara" : "Teks",
  };
}
