export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function getLocalReferenceDate(value = new Date()) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function extractErrorMessage(payload, fallback) {
  if (typeof payload?.detail === "string") return payload.detail;
  if (typeof payload?.error === "string") return payload.error;
  return fallback;
}

async function readResponse(response) {
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError("Server mengirim respons yang tidak dapat dibaca.", response.status);
  }

  if (!response.ok) {
    throw new ApiError(
      extractErrorMessage(payload, "Transaksi gagal diproses oleh server."),
      response.status,
    );
  }
  if (!payload || payload.success !== true || !payload.data) {
    throw new ApiError(
      extractErrorMessage(payload, "Transaksi belum dapat dikenali. Perjelas kalimat Anda."),
      response.status,
    );
  }
  return payload;
}

async function readDatabaseResponse(response) {
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError("Server database mengirim respons yang tidak dapat dibaca.", response.status);
  }
  if (!response.ok || payload?.success !== true) {
    throw new ApiError(
      extractErrorMessage(payload, "Operasi database gagal diproses."),
      response.status,
    );
  }
  return payload.data;
}

async function readAuthResponse(response) {
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError("Server autentikasi mengirim respons yang tidak dapat dibaca.", response.status);
  }
  if (!response.ok || payload?.success !== true) {
    throw new ApiError(
      extractErrorMessage(payload, "Autentikasi gagal diproses."),
      response.status,
    );
  }
  return payload.data;
}

async function plainFetch(path, options = {}) {
  const fetchImpl = options.fetchImpl || fetch;
  const requestOptions = { credentials: "same-origin", ...options };
  delete requestOptions.fetchImpl;
  try {
    return await fetchImpl(path, requestOptions);
  } catch {
    throw new ApiError("Server tidak dapat dijangkau. Periksa koneksi Anda.");
  }
}

export async function refreshSession(options = {}) {
  const response = await plainFetch("/auth/refresh", {
    fetchImpl: options.fetchImpl,
    method: "POST",
    headers: { Accept: "application/json" },
  });
  return readAuthResponse(response);
}

async function sessionFetch(path, options = {}) {
  const fetchImpl = options.fetchImpl || fetch;
  let response = await plainFetch(path, { ...options, fetchImpl });
  if (response.status !== 401 || path.startsWith("/auth/")) return response;
  try {
    await refreshSession({ fetchImpl });
    response = await plainFetch(path, { ...options, fetchImpl });
  } catch {
    // Respons 401 awal dipertahankan agar caller menampilkan permintaan login.
  }
  return response;
}

export async function registerAccount(email, password, options = {}) {
  const response = await plainFetch("/auth/register", {
    fetchImpl: options.fetchImpl,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return readAuthResponse(response);
}

export async function loginAccount(email, password, options = {}) {
  const response = await plainFetch("/auth/login", {
    fetchImpl: options.fetchImpl,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return readAuthResponse(response);
}

export async function getCurrentUser(options = {}) {
  const response = await plainFetch("/auth/me", {
    fetchImpl: options.fetchImpl,
    method: "GET",
    headers: { Accept: "application/json" },
  });
  return readAuthResponse(response);
}

export async function logoutAccount(options = {}) {
  const response = await plainFetch("/auth/logout", {
    fetchImpl: options.fetchImpl,
    method: "POST",
    headers: { Accept: "application/json" },
  });
  return readAuthResponse(response);
}

async function databaseFetch(path, options = {}) {
  try {
    return await sessionFetch(path, options);
  } catch {
    throw new ApiError("Database tidak dapat dijangkau. Periksa koneksi dan server Anda.");
  }
}

function optionalNumber(value) {
  return value === null || value === undefined || value === "" ? null : Number(value);
}

function transactionPayload(record) {
  return {
    source: record.source,
    transaction_type: record.transaction_type,
    item_name: record.item_name ?? null,
    quantity: optionalNumber(record.quantity),
    unit: record.unit ?? null,
    total_price: Number(record.total_price),
    date: record.date,
    original_text: record.original_text ?? null,
    transcript: record.transcript ?? null,
    normalized_text: record.normalized_text ?? null,
    note: record.note ?? null,
    category: record.category ?? null,
    reference_date: record.reference_date ?? null,
    extraction_method: record.extraction_method ?? null,
    receipt: record.source === "receipt" ? record.receipt : null,
  };
}

function transactionUpdatePayload(changes) {
  const payload = {};
  const copy = (name, transform = (value) => value) => {
    if (Object.hasOwn(changes, name)) payload[name] = transform(changes[name]);
  };
  const optionalText = (value) => String(value ?? "").trim() || null;
  copy("transaction_type");
  copy("item_name", optionalText);
  copy("quantity", optionalNumber);
  copy("unit", optionalText);
  copy("total_price", Number);
  copy("date");
  copy("note", optionalText);
  copy("category", optionalText);
  return payload;
}

export async function listTransactions(options = {}) {
  const response = await databaseFetch("/transactions?limit=500", {
    fetchImpl: options.fetchImpl,
    method: "GET",
    headers: { Accept: "application/json" },
  });
  return readDatabaseResponse(response);
}

export async function createTransactionRemote(record, options = {}) {
  const response = await databaseFetch("/transactions", {
    fetchImpl: options.fetchImpl,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(transactionPayload(record)),
  });
  return readDatabaseResponse(response);
}

export async function importLocalTransactions(records, options = {}) {
  const response = await databaseFetch("/transactions/import", {
    fetchImpl: options.fetchImpl,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transactions: records.map(transactionPayload) }),
  });
  return readDatabaseResponse(response);
}

export async function updateTransactionRemote(id, changes, options = {}) {
  const response = await databaseFetch(`/transactions/${encodeURIComponent(id)}`, {
    fetchImpl: options.fetchImpl,
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(transactionUpdatePayload(changes)),
  });
  return readDatabaseResponse(response);
}

export async function deleteTransactionRemote(id, options = {}) {
  const response = await databaseFetch(`/transactions/${encodeURIComponent(id)}`, {
    fetchImpl: options.fetchImpl,
    method: "DELETE",
    headers: { Accept: "application/json" },
  });
  return readDatabaseResponse(response);
}

export async function clearTransactionsRemote(options = {}) {
  const response = await databaseFetch("/transactions", {
    fetchImpl: options.fetchImpl,
    method: "DELETE",
    headers: { Accept: "application/json" },
  });
  return readDatabaseResponse(response);
}

export async function extractText(text, options = {}) {
  const fetchImpl = options.fetchImpl || fetch;
  const referenceDate = options.referenceDate || getLocalReferenceDate();
  let response;
  try {
    response = await sessionFetch("/extract", {
      fetchImpl,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, reference_date: referenceDate }),
    });
  } catch {
    throw new ApiError("API tidak dapat dijangkau. Periksa koneksi dan server Anda.");
  }
  return readResponse(response);
}

function extensionForMimeType(mimeType) {
  if (mimeType.includes("mp4")) return "m4a";
  if (mimeType.includes("ogg")) return "ogg";
  return "webm";
}

export async function extractAudio(blob, options = {}) {
  const fetchImpl = options.fetchImpl || fetch;
  const referenceDate = options.referenceDate || getLocalReferenceDate();
  const form = new FormData();
  const mimeType = blob.type || "audio/webm";
  form.append("file", blob, `transaksi.${extensionForMimeType(mimeType)}`);
  form.append("reference_date", referenceDate);

  let response;
  try {
    response = await sessionFetch("/extract/audio", { fetchImpl, method: "POST", body: form });
  } catch {
    throw new ApiError("API audio tidak dapat dijangkau. Periksa koneksi dan server Anda.");
  }
  return readResponse(response);
}

export async function extractReceipt(file, options = {}) {
  const fetchImpl = options.fetchImpl || fetch;
  const referenceDate = options.referenceDate || getLocalReferenceDate();
  const form = new FormData();
  form.append("file", file, file.name || "nota.jpg");
  form.append("reference_date", referenceDate);

  let response;
  try {
    response = await sessionFetch("/extract/receipt", { fetchImpl, method: "POST", body: form });
  } catch {
    throw new ApiError("API Scan Nota tidak dapat dijangkau. Periksa koneksi dan server Anda.");
  }
  return readResponse(response);
}
