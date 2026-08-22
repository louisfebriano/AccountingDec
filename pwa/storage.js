export const HISTORY_KEY = "catatkas.transactions.v1";
const LEGACY_HISTORY_KEY = "accountingdec.transactions.v1";
export const MAX_HISTORY_ITEMS = 50;

function isTransactionData(value) {
  return value && typeof value === "object" && Number.isFinite(Number(value.total_price));
}

export function loadHistory(storage = localStorage) {
  try {
    const currentValue = storage.getItem(HISTORY_KEY);
    const legacyValue = currentValue === null ? storage.getItem(LEGACY_HISTORY_KEY) : null;
    const value = JSON.parse(currentValue || legacyValue || "[]");
    if (currentValue === null && legacyValue !== null) {
      storage.setItem(HISTORY_KEY, JSON.stringify(value));
      storage.removeItem(LEGACY_HISTORY_KEY);
    }
    return Array.isArray(value) ? value.filter(isTransactionData).slice(0, MAX_HISTORY_ITEMS) : [];
  } catch {
    return [];
  }
}

export function saveHistory(history, storage = localStorage) {
  const safeHistory = history.filter(isTransactionData).slice(0, MAX_HISTORY_ITEMS);
  storage.setItem(HISTORY_KEY, JSON.stringify(safeHistory));
  return safeHistory;
}

export function clearHistory(storage = localStorage) {
  storage.removeItem(HISTORY_KEY);
  storage.removeItem(LEGACY_HISTORY_KEY);
}

export function recordSuccessfulResponse(response, source, originalText, options = {}) {
  if (!response || response.success !== true || !isTransactionData(response.data)) {
    throw new Error("Respons gagal tidak boleh disimpan sebagai transaksi.");
  }

  const storage = options.storage || localStorage;
  const now = options.now || new Date();
  const data = response.data;
  const record = {
    id: `${now.getTime()}-${Math.random().toString(16).slice(2)}`,
    source,
    original_text: String(originalText || "").slice(0, 500),
    item_name: data.item_name ?? null,
    quantity: data.quantity ?? null,
    unit: data.unit ?? null,
    total_price: Number(data.total_price),
    date: data.date || null,
    transaction_type: ["income", "expense", "unknown"].includes(data.transaction_type)
      ? data.transaction_type
      : "unknown",
    created_at: now.toISOString(),
  };

  const history = saveHistory([record, ...loadHistory(storage)], storage);
  return { record, history };
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
