import test from "node:test";
import assert from "node:assert/strict";

import { ApiError, extractAudio, extractText, getLocalReferenceDate } from "../../pwa/api.js";

const successfulPayload = {
  success: true,
  input: "3 bakmi laku terjual 60 ribu",
  data: {
    item_name: "Bakmi",
    quantity: 3,
    unit: null,
    total_price: 60000,
    date: "2026-08-22",
    transaction_type: "income",
  },
};

test("input teks dikirim ke endpoint dengan tanggal lokal dan body yang benar", async () => {
  let captured;
  const fetchImpl = async (url, options) => {
    captured = { url, options };
    return new Response(JSON.stringify(successfulPayload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  await extractText("3 bakmi laku terjual 60 ribu", {
    fetchImpl,
    referenceDate: "2026-08-22",
  });

  assert.equal(captured.url, "/extract");
  assert.equal(captured.options.method, "POST");
  assert.deepEqual(JSON.parse(captured.options.body), {
    text: "3 bakmi laku terjual 60 ribu",
    reference_date: "2026-08-22",
  });
});

test("tanggal referensi menggunakan komponen tanggal lokal", () => {
  const localLikeDate = new Date(2026, 7, 22, 0, 5, 0);
  assert.equal(getLocalReferenceDate(localLikeDate), "2026-08-22");
});

test("audio dikirim sebagai FormData tanpa header multipart manual", async () => {
  let captured;
  const payload = { ...successfulPayload, source: "voice", transcript: "tiga bakmi" };
  const fetchImpl = async (url, options) => {
    captured = { url, options };
    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  await extractAudio(new Blob(["audio"], { type: "audio/webm;codecs=opus" }), {
    fetchImpl,
    referenceDate: "2026-08-22",
  });

  assert.equal(captured.url, "/extract/audio");
  assert.equal(captured.options.method, "POST");
  assert.ok(captured.options.body instanceof FormData);
  assert.equal(captured.options.headers, undefined);
  assert.equal(captured.options.body.get("reference_date"), "2026-08-22");
});

test("status 422 memakai pesan API dan tidak menghasilkan data palsu", async () => {
  const fetchImpl = async () => new Response(
    JSON.stringify({ detail: "Input di luar konteks transaksi" }),
    { status: 422, headers: { "Content-Type": "application/json" } },
  );

  await assert.rejects(
    extractText("cuaca hari ini", { fetchImpl }),
    (error) => error instanceof ApiError && error.status === 422 && error.message.includes("di luar konteks"),
  );
});
