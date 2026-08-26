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

export function formatCompactRupiah(value) {
  const number = Math.abs(Number(value));
  if (!Number.isFinite(number)) return EMPTY_VALUE;
  if (number >= 1_000_000_000) return `Rp${(number / 1_000_000_000).toLocaleString("id-ID", { maximumFractionDigits: 1 })}M`;
  if (number >= 1_000_000) return `Rp${(number / 1_000_000).toLocaleString("id-ID", { maximumFractionDigits: 1 })}jt`;
  if (number >= 1_000) return `Rp${(number / 1_000).toLocaleString("id-ID", { maximumFractionDigits: 1 })}rb`;
  return `Rp${Math.round(number).toLocaleString("id-ID")}`;
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
    source: record.source === "voice" ? "Suara" : record.source === "manual" ? "Manual" : "Teks",
  };
}

export function formatDateTime(value) {
  if (!value) return EMPTY_VALUE;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("id-ID", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function presentTransactionDetail(record, localDate) {
  const view = presentTransaction(record, localDate);
  let originalLabel = "Input asli";
  let originalText = record.original_text;
  if (record.source === "voice") {
    originalLabel = "Transkrip asli";
    originalText = record.transcript;
  } else if (record.source === "manual") {
    originalLabel = "Catatan";
    originalText = record.note;
  }
  return {
    ...view,
    createdAt: formatDateTime(record.created_at),
    originalLabel,
    originalText: formatOptional(originalText),
    normalizedText: formatOptional(record.normalized_text),
  };
}
