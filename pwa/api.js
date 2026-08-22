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

export async function extractText(text, options = {}) {
  const fetchImpl = options.fetchImpl || fetch;
  const referenceDate = options.referenceDate || getLocalReferenceDate();
  let response;
  try {
    response = await fetchImpl("/extract", {
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
    response = await fetchImpl("/extract/audio", { method: "POST", body: form });
  } catch {
    throw new ApiError("API audio tidak dapat dijangkau. Periksa koneksi dan server Anda.");
  }
  return readResponse(response);
}
