import { ApiError, extractAudio, extractText, getLocalReferenceDate } from "/api.js";
import { EMPTY_VALUE, formatRupiah, presentTransaction } from "/formatters.js";
import { RecorderSession } from "/recorder.js";
import { RequestGate } from "/request-gate.js";
import {
  calculateSummary,
  clearHistory,
  loadHistory,
  recordSuccessfulResponse,
} from "/storage.js";

const $ = (selector) => document.querySelector(selector);
const elements = {
  connection: $("#connection-status"),
  connectionLabel: $("#connection-label"),
  offlineBanner: $("#offline-banner"),
  installButton: $("#install-button"),
  settingsButton: $("#settings-button"),
  bottomSettings: $("#bottom-settings"),
  settingsDialog: $("#settings-dialog"),
  closeSettings: $("#close-settings"),
  doneSettings: $("#done-settings"),
  iosHint: $("#ios-install-hint"),
  tabs: [...document.querySelectorAll('[role="tab"]')],
  textPanel: $("#text-panel"),
  voicePanel: $("#voice-panel"),
  textForm: $("#text-form"),
  textInput: $("#transaction-text"),
  characterCount: $("#character-count"),
  textSubmit: $("#text-submit"),
  recordButton: $("#record-button"),
  stopButton: $("#stop-button"),
  recordVisual: $("#record-visual"),
  recordTimer: $("#record-timer"),
  voiceStatus: $("#voice-status"),
  voiceHelp: $("#voice-help"),
  requestStatus: $("#request-status"),
  resultCard: $("#result-card"),
  resultType: $("#result-type"),
  resultPrice: $("#result-price"),
  resultDate: $("#result-date"),
  resultItem: $("#result-item"),
  resultQuantity: $("#result-quantity"),
  resultUnit: $("#result-unit"),
  resultSource: $("#result-source"),
  resultInput: $("#result-input"),
  historyList: $("#history-list"),
  emptyHistory: $("#empty-history"),
  clearHistoryButton: $("#clear-history-button"),
  dialogClearHistory: $("#dialog-clear-history"),
  summaryBalance: $("#summary-balance"),
  summaryIncome: $("#summary-income"),
  summaryExpense: $("#summary-expense"),
};

const gate = new RequestGate();
const recorder = new RecorderSession();
let history = loadHistory();
let installPrompt = null;
let timerInterval = null;
let limitTimeout = null;
let recordingStartedAt = 0;

function setStatus(message, kind = "") {
  elements.requestStatus.textContent = message;
  elements.requestStatus.dataset.kind = kind;
}

function setBusy(busy, mode = "text") {
  elements.textSubmit.disabled = busy || !navigator.onLine;
  elements.textSubmit.classList.toggle("is-loading", busy && mode === "text");
  elements.recordButton.disabled = busy || !navigator.onLine || !recorder.supported;
  elements.tabs.forEach((tab) => { tab.disabled = busy; });
}

function updateConnection() {
  const online = navigator.onLine;
  elements.connection.classList.toggle("is-offline", !online);
  elements.connectionLabel.textContent = online ? "Online" : "Offline";
  elements.offlineBanner.hidden = online;
  setBusy(gate.busy);
  if (!online) setStatus("Koneksi server diperlukan untuk mencatat transaksi.", "warning");
}

function switchTab(selectedTab) {
  elements.tabs.forEach((tab) => {
    const active = tab === selectedTab;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
  });
  elements.textPanel.hidden = selectedTab.id !== "text-tab";
  elements.voicePanel.hidden = selectedTab.id !== "voice-tab";
}

function renderSummary() {
  const summary = calculateSummary(history);
  elements.summaryBalance.textContent = `${summary.balance < 0 ? "−" : ""}${formatRupiah(summary.balance)}`;
  elements.summaryIncome.textContent = formatRupiah(summary.income);
  elements.summaryExpense.textContent = formatRupiah(summary.expense);
}

function transactionTitle(transaction) {
  if (transaction.item_name) return transaction.item_name;
  return transaction.transaction_type === "income" ? "Pemasukan umum" : "Pengeluaran umum";
}

function renderHistory() {
  elements.historyList.replaceChildren();
  const recent = history.slice(0, 5);
  elements.emptyHistory.hidden = recent.length > 0;
  elements.clearHistoryButton.disabled = history.length === 0;
  elements.dialogClearHistory.disabled = history.length === 0;

  recent.forEach((transaction) => {
    const item = document.createElement("li");
    item.className = `history-item type-${transaction.transaction_type}`;

    const main = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = transactionTitle(transaction);
    const meta = document.createElement("span");
    const view = presentTransaction(transaction, getLocalReferenceDate());
    meta.textContent = `${view.date} · ${view.source}`;
    main.append(title, meta);

    const amount = document.createElement("strong");
    amount.className = "history-amount";
    const sign = transaction.transaction_type === "income" ? "+" : transaction.transaction_type === "expense" ? "−" : "";
    amount.textContent = `${sign}${formatRupiah(transaction.total_price)}`;
    item.append(main, amount);
    elements.historyList.append(item);
  });
}

function renderResult(record) {
  const view = presentTransaction(record, getLocalReferenceDate());
  elements.resultType.textContent = view.type;
  elements.resultType.className = `type-pill type-${record.transaction_type}`;
  elements.resultPrice.textContent = view.price;
  elements.resultDate.textContent = view.date;
  elements.resultItem.textContent = view.item;
  elements.resultQuantity.textContent = view.quantity;
  elements.resultUnit.textContent = view.unit;
  elements.resultSource.textContent = view.source;
  elements.resultInput.textContent = record.original_text ? `“${record.original_text}”` : EMPTY_VALUE;
  elements.resultCard.hidden = false;
}

function acceptSuccess(response, source, originalText) {
  const saved = recordSuccessfulResponse(response, source, originalText);
  history = saved.history;
  renderResult(saved.record);
  renderHistory();
  renderSummary();
  setStatus("Transaksi berhasil dicatat pada perangkat ini.", "success");
}

function humanizeError(error, mode = "text") {
  if (!navigator.onLine) return "Anda sedang offline. Sambungkan perangkat untuk memproses transaksi.";
  if (error instanceof ApiError) return error.message;
  if (error?.name === "NotAllowedError") return "Izin mikrofon ditolak. Izinkan mikrofon melalui pengaturan browser.";
  if (error?.name === "NotFoundError") return "Mikrofon tidak ditemukan pada perangkat ini.";
  return mode === "voice"
    ? "Rekaman tidak dapat diproses. Silakan coba kembali."
    : "Transaksi tidak dapat diproses. Silakan coba kembali.";
}

elements.textForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = elements.textInput.value.trim();
  if (!text || !navigator.onLine) {
    setStatus(text ? "Koneksi server diperlukan untuk mencatat transaksi." : "Masukkan kalimat transaksi terlebih dahulu.", "error");
    return;
  }

  const outcome = await gate.run(async () => {
    setBusy(true, "text");
    setStatus("Sedang memproses kalimat transaksi…");
    try {
      const response = await extractText(text);
      acceptSuccess(response, "text", response.input || text);
      elements.textInput.value = "";
      elements.characterCount.textContent = "0";
    } catch (error) {
      setStatus(humanizeError(error), "error");
    } finally {
      setBusy(false);
    }
  });
  if (outcome.skipped) setStatus("Permintaan sebelumnya masih diproses.", "warning");
});

elements.textInput.addEventListener("input", () => {
  elements.characterCount.textContent = String(elements.textInput.value.length);
});

function clearRecordingTimers() {
  clearInterval(timerInterval);
  clearTimeout(limitTimeout);
  timerInterval = null;
  limitTimeout = null;
}

function updateRecordingTimer() {
  const elapsed = Math.min(30, Math.floor((Date.now() - recordingStartedAt) / 1000));
  elements.recordTimer.textContent = `00:${String(elapsed).padStart(2, "0")}`;
}

async function stopAndUploadRecording() {
  clearRecordingTimers();
  elements.stopButton.disabled = true;
  elements.recordVisual.classList.remove("is-recording");
  elements.voiceStatus.textContent = "Menyiapkan rekaman…";

  const blob = await recorder.stop();
  if (!blob || blob.size === 0) throw new Error("Rekaman kosong");
  elements.voiceStatus.textContent = "Audio sedang diproses…";
  setStatus("Mengunggah dan memproses suara…");
  const response = await extractAudio(blob);
  acceptSuccess(response, "voice", response.transcript || "");
  elements.voiceStatus.textContent = response.transcript
    ? `Transkrip: ${response.transcript}`
    : "Transaksi suara berhasil diproses.";
}

elements.recordButton.addEventListener("click", async () => {
  if (!recorder.supported) {
    setStatus("Browser ini tidak mendukung perekaman suara.", "error");
    return;
  }
  if (!navigator.onLine) {
    setStatus("Koneksi server diperlukan untuk mencatat transaksi.", "error");
    return;
  }

  const outcome = await gate.run(async () => {
    setBusy(true, "voice");
    elements.voiceStatus.textContent = "Meminta izin mikrofon…";
    try {
      await recorder.start();
      recordingStartedAt = Date.now();
      elements.recordTimer.textContent = "00:00";
      elements.voiceStatus.textContent = "Sedang merekam… ucapkan satu transaksi.";
      elements.recordVisual.classList.add("is-recording");
      elements.stopButton.disabled = false;
      timerInterval = setInterval(updateRecordingTimer, 250);
      limitTimeout = setTimeout(() => elements.stopButton.click(), 30000);

      await new Promise((resolve) => {
        elements.stopButton.addEventListener("click", resolve, { once: true });
      });
      if (recorder.recorder) await stopAndUploadRecording();
    } catch (error) {
      recorder.releaseTracks();
      setStatus(humanizeError(error, "voice"), "error");
      elements.voiceStatus.textContent = "Perekaman tidak tersedia.";
    } finally {
      clearRecordingTimers();
      elements.recordVisual.classList.remove("is-recording");
      elements.stopButton.disabled = true;
      setBusy(false);
    }
  });
  if (outcome.skipped) setStatus("Permintaan sebelumnya masih diproses.", "warning");
});

elements.tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => switchTab(tab));
  tab.addEventListener("keydown", (event) => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "ArrowRight" ? (index + 1) % elements.tabs.length : (index - 1 + elements.tabs.length) % elements.tabs.length;
    elements.tabs[next].focus();
    switchTab(elements.tabs[next]);
  });
});

function openSettings() {
  if (typeof elements.settingsDialog.showModal === "function") elements.settingsDialog.showModal();
}

function closeSettings() {
  elements.settingsDialog.close();
}

elements.settingsButton.addEventListener("click", openSettings);
elements.bottomSettings.addEventListener("click", openSettings);
elements.closeSettings.addEventListener("click", closeSettings);
elements.doneSettings.addEventListener("click", closeSettings);
elements.settingsDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  closeSettings();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && elements.settingsDialog.open) {
    event.preventDefault();
    closeSettings();
  }
});

function requestClearHistory() {
  if (history.length === 0) return;
  if (!window.confirm("Hapus seluruh riwayat transaksi yang tersimpan di perangkat ini?")) return;
  clearHistory();
  history = [];
  renderHistory();
  renderSummary();
  setStatus("Riwayat lokal telah dihapus.", "success");
}

elements.clearHistoryButton.addEventListener("click", requestClearHistory);
elements.dialogClearHistory.addEventListener("click", requestClearHistory);

const standalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
elements.iosHint.hidden = !(isIOS && !standalone);

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  installPrompt = event;
  if (!standalone) elements.installButton.hidden = false;
});

elements.installButton.addEventListener("click", async () => {
  if (!installPrompt) return;
  installPrompt.prompt();
  await installPrompt.userChoice;
  installPrompt = null;
  elements.installButton.hidden = true;
});

window.addEventListener("appinstalled", () => {
  installPrompt = null;
  elements.installButton.hidden = true;
});
window.addEventListener("online", updateConnection);
window.addEventListener("offline", updateConnection);

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js"));
}

if (!recorder.supported) {
  elements.recordButton.disabled = true;
  elements.voiceStatus.textContent = "Browser ini tidak mendukung perekaman suara.";
  elements.voiceHelp.textContent = "Gunakan browser modern dengan dukungan MediaRecorder, atau gunakan tab Teks.";
}

renderHistory();
renderSummary();
updateConnection();
