export const HISTORY_KEY = "catatkas.transactions.v1";
const LEGACY_HISTORY_KEY = "accountingdec.transactions.v1";
export const MAX_HISTORY_ITEMS = 50;
export const MAX_TEXT_LENGTH = 500;
export const MAX_RECEIPT_ITEMS = 50;

const TRANSACTION_TYPES = new Set(["income", "expense"]);

function nullableText(value) {
  const text = String(value ?? "").trim().slice(0, MAX_TEXT_LENGTH);
  return text || null;
}

function nullablePositiveNumber(value, fieldName) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) {
    throw new Error(`${fieldName} harus berupa angka positif.`);
  }
  return number;
}

function nullableNonNegativeNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function normalizeReceiptItem(value) {
  if (!value || typeof value !== "object") return null;
  const itemName = nullableText(value.item_name);
  if (!itemName) return null;
  const quantity = nullableNonNegativeNumber(value.quantity);
  const unitPrice = nullableNonNegativeNumber(value.unit_price);
  const lineTotal = nullableNonNegativeNumber(value.line_total);
  const confidence = nullableNonNegativeNumber(value.confidence);
  return {
    item_name: itemName,
    quantity: quantity && quantity > 0 ? quantity : null,
    unit: nullableText(value.unit),
    unit_price: unitPrice,
    line_total: lineTotal,
    confidence: confidence === null ? null : Math.min(confidence, 1),
  };
}

function normalizeReceipt(value, confirmedTotal = null) {
  if (!value || typeof value !== "object") return null;
  const items = Array.isArray(value.items)
    ? value.items.slice(0, MAX_RECEIPT_ITEMS).map(normalizeReceiptItem).filter(Boolean)
    : [];
  const detectedTotal = nullableNonNegativeNumber(value.total);
  return {
    merchant_name: nullableText(value.merchant_name),
    receipt_number: nullableText(value.receipt_number),
    subtotal: nullableNonNegativeNumber(value.subtotal),
    discount: nullableNonNegativeNumber(value.discount),
    tax: nullableNonNegativeNumber(value.tax),
    service_charge: nullableNonNegativeNumber(value.service_charge),
    total: nullableNonNegativeNumber(confirmedTotal) ?? detectedTotal,
    items,
  };
}

function validDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ""))) return false;
  const [year, month, day] = String(value).split("-").map(Number);
  const parsed = new Date(year, month - 1, day, 12);
  return parsed.getFullYear() === year
    && parsed.getMonth() === month - 1
    && parsed.getDate() === day;
}

function newRecordId(now = new Date()) {
  const randomId = globalThis.crypto?.randomUUID?.();
  return randomId || `${now.getTime()}-${Math.random().toString(16).slice(2)}`;
}

function isTransactionData(value) {
  return value
    && typeof value === "object"
    && Number.isFinite(Number(value.total_price));
}

function normalizeStoredRecord(value, index, now) {
  const source = ["text", "voice", "manual", "receipt"].includes(value.source) ? value.source : "text";
  const legacyInput = nullableText(value.original_text);
  return {
    id: nullableText(value.id) || newRecordId(new Date(now.getTime() + index)),
    source,
    original_text: source === "text" ? legacyInput : null,
    transcript: source === "voice" ? nullableText(value.transcript) || legacyInput : null,
    normalized_text: source === "voice" ? nullableText(value.normalized_text) : null,
    note: nullableText(value.note) || (source === "manual" ? legacyInput : null),
    receipt: source === "receipt" ? normalizeReceipt(value.receipt, value.total_price) : null,
    item_name: nullableText(value.item_name),
    quantity: value.quantity === null || value.quantity === undefined || value.quantity === ""
      ? null
      : Number(value.quantity),
    unit: nullableText(value.unit),
    total_price: Number(value.total_price),
    date: validDate(value.date) ? value.date : null,
    transaction_type: ["income", "expense", "unknown"].includes(value.transaction_type)
      ? value.transaction_type
      : "unknown",
    created_at: nullableText(value.created_at) || now.toISOString(),
    updated_at: nullableText(value.updated_at),
  };
}

export function loadHistory(storage = localStorage, options = {}) {
  try {
    const currentValue = storage.getItem(HISTORY_KEY);
    const legacyValue = currentValue === null ? storage.getItem(LEGACY_HISTORY_KEY) : null;
    const serialized = currentValue || legacyValue || "[]";
    const parsed = JSON.parse(serialized);
    if (!Array.isArray(parsed)) return [];

    const now = options.now || new Date();
    const history = parsed
      .filter(isTransactionData)
      .slice(0, MAX_HISTORY_ITEMS)
      .map((record, index) => normalizeStoredRecord(record, index, now));
    const migrated = JSON.stringify(history);
    if (legacyValue !== null || migrated !== serialized) {
      storage.setItem(HISTORY_KEY, migrated);
      storage.removeItem(LEGACY_HISTORY_KEY);
    }
    return history;
  } catch {
    return [];
  }
}

export function saveHistory(history, storage = localStorage) {
  const now = new Date();
  const safeHistory = history
    .filter(isTransactionData)
    .slice(0, MAX_HISTORY_ITEMS)
    .map((record, index) => normalizeStoredRecord(record, index, now));
  storage.setItem(HISTORY_KEY, JSON.stringify(safeHistory));
  return safeHistory;
}

export function clearHistory(storage = localStorage) {
  storage.removeItem(HISTORY_KEY);
  storage.removeItem(LEGACY_HISTORY_KEY);
}

export function validateEditableTransaction(input) {
  if (!TRANSACTION_TYPES.has(input.transaction_type)) {
    throw new Error("Jenis transaksi harus pemasukan atau pengeluaran.");
  }
  if (!validDate(input.date)) throw new Error("Tanggal transaksi wajib diisi dengan benar.");

  return {
    transaction_type: input.transaction_type,
    item_name: nullableText(input.item_name),
    quantity: nullablePositiveNumber(input.quantity, "Quantity"),
    unit: nullableText(input.unit),
    total_price: nullablePositiveNumber(input.total_price, "Nominal"),
    date: input.date,
    note: nullableText(input.note),
  };
}

export function createManualTransaction(input, options = {}) {
  const storage = options.storage || localStorage;
  const now = options.now || new Date();
  const fields = validateEditableTransaction(input);
  const record = {
    id: options.idFactory?.() || newRecordId(now),
    source: "manual",
    original_text: null,
    transcript: null,
    normalized_text: null,
    receipt: null,
    ...fields,
    created_at: now.toISOString(),
    updated_at: null,
  };
  const history = saveHistory([record, ...loadHistory(storage, { now })], storage);
  return { record, history };
}

export function updateTransaction(id, input, options = {}) {
  const storage = options.storage || localStorage;
  const now = options.now || new Date();
  const fields = validateEditableTransaction(input);
  const current = loadHistory(storage, { now });
  const index = current.findIndex((record) => record.id === id);
  if (index < 0) throw new Error("Transaksi tidak ditemukan.");

  const record = {
    ...current[index],
    ...fields,
    updated_at: now.toISOString(),
  };
  const history = [...current];
  history[index] = record;
  saveHistory(history, storage);
  return { record, history };
}

export function deleteTransaction(id, storage = localStorage) {
  const current = loadHistory(storage);
  const history = current.filter((record) => record.id !== id);
  if (history.length === current.length) throw new Error("Transaksi tidak ditemukan.");
  saveHistory(history, storage);
  return history;
}

export function recordSuccessfulResponse(response, source, originalText, options = {}) {
  if (!response || response.success !== true || !isTransactionData(response.data)) {
    throw new Error("Respons gagal tidak boleh disimpan sebagai transaksi.");
  }

  const storage = options.storage || localStorage;
  const now = options.now || new Date();
  const data = response.data;
  const isVoice = source === "voice";
  const record = {
    id: options.idFactory?.() || newRecordId(now),
    source: isVoice ? "voice" : "text",
    original_text: isVoice ? null : nullableText(response.input || originalText),
    transcript: isVoice ? nullableText(response.transcript || originalText) : null,
    normalized_text: isVoice ? nullableText(response.normalized_text) : null,
    note: null,
    receipt: null,
    item_name: nullableText(data.item_name),
    quantity: data.quantity ?? null,
    unit: nullableText(data.unit),
    total_price: Number(data.total_price),
    date: validDate(data.date) ? data.date : null,
    transaction_type: ["income", "expense", "unknown"].includes(data.transaction_type)
      ? data.transaction_type
      : "unknown",
    created_at: now.toISOString(),
    updated_at: null,
  };

  const history = saveHistory([record, ...loadHistory(storage, { now })], storage);
  return { record, history };
}

export function createReceiptTransaction(response, confirmation, options = {}) {
  if (
    !response
    || response.success !== true
    || response.source !== "receipt"
    || !response.data?.receipt
  ) {
    throw new Error("Hasil nota tidak valid dan tidak dapat disimpan.");
  }

  const storage = options.storage || localStorage;
  const now = options.now || new Date();
  const fields = validateEditableTransaction({
    transaction_type: "expense",
    date: confirmation.date,
    total_price: confirmation.total_price,
    item_name: response.data.item_name,
    quantity: response.data.quantity,
    unit: response.data.unit,
    note: null,
  });
  const receipt = normalizeReceipt(response.data.receipt, fields.total_price);
  if (!receipt) throw new Error("Rincian nota tidak valid.");

  const record = {
    id: options.idFactory?.() || newRecordId(now),
    source: "receipt",
    original_text: null,
    transcript: null,
    normalized_text: null,
    note: null,
    receipt,
    ...fields,
    transaction_type: "expense",
    created_at: now.toISOString(),
    updated_at: null,
  };
  const history = saveHistory([record, ...loadHistory(storage, { now })], storage);
  return { record: history[0], history };
}

export function calculateSummary(history) {
  return history.reduce(
    (summary, transaction) => {
      const value = Number(transaction.total_price) || 0;
      if (transaction.transaction_type === "income") summary.income += value;
      if (transaction.transaction_type === "expense") summary.expense += value;
      summary.balance = summary.income - summary.expense;
      return summary;
    },
    { balance: 0, income: 0, expense: 0 },
  );
}
