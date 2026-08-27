import { ApiError, extractAudio, extractReceipt, extractText, getLocalReferenceDate } from "/api.js?v=16";
import {
  aggregateTransactionsByPeriod,
  describeChartPoint,
  describePeriodInsight,
  renderTransactionChart,
} from "/chart.js?v=16";
import { filterTransactionsByPeriod } from "/filters.js?v=16";
import {
  EMPTY_VALUE,
  formatRupiah,
  presentTransaction,
  presentTransactionDetail,
} from "/formatters.js?v=16";
import { RecorderSession } from "/recorder.js?v=16";
import { RequestGate } from "/request-gate.js?v=16";
import {
  calculateSummary,
  clearHistory,
  createManualTransaction,
  createReceiptTransaction,
  deleteTransaction,
  loadHistory,
  recordSuccessfulResponse,
  updateTransaction,
} from "/storage.js?v=16";
import { applyTheme, loadTheme, nextTheme, saveTheme } from "/theme.js?v=16";

const $ = (selector) => document.querySelector(selector);
const elements = {
  connection: $("#connection-status"),
  connectionLabel: $("#connection-label"),
  offlineBanner: $("#offline-banner"),
  installButton: $("#install-button"),
  settingsButton: $("#settings-button"),
  bottomSettings: $("#bottom-settings"),
  settingsDialog: $("#settings-dialog"),
  themeToggle: $("#theme-toggle"),
  closeSettings: $("#close-settings"),
  doneSettings: $("#done-settings"),
  iosHint: $("#ios-install-hint"),
  tabs: [...document.querySelectorAll('[role="tab"]')],
  textPanel: $("#text-panel"),
  voicePanel: $("#voice-panel"),
  receiptPanel: $("#receipt-panel"),
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
  receiptForm: $("#receipt-form"),
  receiptFile: $("#receipt-file"),
  receiptSubmit: $("#receipt-submit"),
  receiptChangeButton: $("#receipt-change-button"),
  receiptPreview: $("#receipt-preview"),
  receiptPreviewImage: $("#receipt-preview-image"),
  receiptFileName: $("#receipt-file-name"),
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
  emptyHistoryTitle: $("#empty-history-title"),
  emptyHistoryDescription: $("#empty-history-description"),
  clearHistoryButton: $("#clear-history-button"),
  dialogClearHistory: $("#dialog-clear-history"),
  addManualButton: $("#add-manual-button"),
  summaryBalance: $("#summary-balance"),
  summaryIncome: $("#summary-income"),
  summaryExpense: $("#summary-expense"),
  summaryPeriodLabel: $("#summary-period-label"),
  trendEyebrow: $("#trend-eyebrow"),
  trendTitle: $("#trend-title"),
  weeklyChart: $("#weekly-chart"),
  trendPanel: $(".trend-panel"),
  chartTooltip: $("#chart-tooltip"),
  chartTooltipDate: $("#chart-tooltip-date"),
  chartTooltipIncome: $("#chart-tooltip-income"),
  chartTooltipExpense: $("#chart-tooltip-expense"),
  chartInsight: $("#chart-insight"),
  chartInsightPeriod: $("#chart-insight-period"),
  chartSummary: $("#chart-summary"),
  periodMode: $("#period-mode"),
  weekFilterField: $("#week-filter-field"),
  weekFilterDate: $("#week-filter-date"),
  monthFilterField: $("#month-filter-field"),
  monthFilterValue: $("#month-filter-value"),
  yearFilterField: $("#year-filter-field"),
  yearFilterValue: $("#year-filter-value"),
  customFilterFields: $("#custom-filter-fields"),
  customStartDate: $("#custom-start-date"),
  customEndDate: $("#custom-end-date"),
  resetFilterButton: $("#reset-filter-button"),
  activePeriod: $("#active-period"),
  filterError: $("#filter-error"),
  detailDialog: $("#transaction-detail-dialog"),
  closeDetailButton: $("#close-detail-button"),
  doneDetailButton: $("#done-detail-button"),
  editTransactionButton: $("#edit-transaction-button"),
  deleteTransactionButton: $("#delete-transaction-button"),
  detailType: $("#detail-type"),
  detailPrice: $("#detail-price"),
  detailDate: $("#detail-date"),
  detailItem: $("#detail-item"),
  detailQuantity: $("#detail-quantity"),
  detailUnit: $("#detail-unit"),
  detailSource: $("#detail-source"),
  detailCreatedAt: $("#detail-created-at"),
  detailOriginalSection: $("#detail-original-section"),
  detailOriginalLabel: $("#detail-original-label"),
  detailOriginalText: $("#detail-original-text"),
  detailNormalizedSection: $("#detail-normalized-section"),
  detailNormalizedText: $("#detail-normalized-text"),
  detailReceiptSection: $("#detail-receipt-section"),
  detailReceiptMerchant: $("#detail-receipt-merchant"),
  detailReceiptNumber: $("#detail-receipt-number"),
  detailReceiptSubtotal: $("#detail-receipt-subtotal"),
  detailReceiptDiscount: $("#detail-receipt-discount"),
  detailReceiptTax: $("#detail-receipt-tax"),
  detailReceiptService: $("#detail-receipt-service"),
  detailReceiptItems: $("#detail-receipt-items"),
  receiptConfirmDialog: $("#receipt-confirm-dialog"),
  closeReceiptConfirmButton: $("#close-receipt-confirm-button"),
  receiptConfirmForm: $("#receipt-confirm-form"),
  receiptConfirmMerchant: $("#receipt-confirm-merchant"),
  receiptConfirmNumber: $("#receipt-confirm-number"),
  receiptConfirmDate: $("#receipt-confirm-date"),
  receiptConfirmTotal: $("#receipt-confirm-total"),
  receiptTotalCandidates: $("#receipt-total-candidates"),
  receiptTotalCandidateButtons: $("#receipt-total-candidate-buttons"),
  receiptWarningBox: $("#receipt-warning-box"),
  receiptWarningList: $("#receipt-warning-list"),
  receiptConfirmItems: $("#receipt-confirm-items"),
  receiptConfirmEmptyItems: $("#receipt-confirm-empty-items"),
  receiptOcrText: $("#receipt-ocr-text"),
  receiptConfirmError: $("#receipt-confirm-error"),
  receiptRetakeButton: $("#receipt-retake-button"),
  transactionFormDialog: $("#transaction-form-dialog"),
  transactionFormTitle: $("#transaction-form-title"),
  closeTransactionFormButton: $("#close-transaction-form-button"),
  cancelTransactionFormButton: $("#cancel-transaction-form-button"),
  manualTransactionForm: $("#manual-transaction-form"),
  manualTransactionType: $("#manual-transaction-type"),
  manualDate: $("#manual-date"),
  manualTotalPrice: $("#manual-total-price"),
  manualItemName: $("#manual-item-name"),
  manualQuantity: $("#manual-quantity"),
  manualUnit: $("#manual-unit"),
  manualNote: $("#manual-note"),
  manualFormError: $("#manual-form-error"),
};

const gate = new RequestGate();
const recorder = new RecorderSession();
let history = loadHistory();
let activeTransactionId = null;
let editingTransactionId = null;
let installPrompt = null;
let timerInterval = null;
let limitTimeout = null;
let recordingStartedAt = 0;
let recordingActive = false;
let selectedReceiptFile = null;
let receiptPreviewUrl = null;
let pendingReceipt = null;
let activeTheme = applyTheme(loadTheme());
let chartTooltipPinned = false;

function setStatus(message, kind = "") {
  elements.requestStatus.textContent = message;
  elements.requestStatus.dataset.kind = kind;
}

function updateThemeButton() {
  const nextLabel = activeTheme === "dark" ? "Aktifkan tema putih" : "Aktifkan mode gelap";
  elements.themeToggle.setAttribute("aria-label", nextLabel);
  elements.themeToggle.title = nextLabel;
  elements.themeToggle.setAttribute("aria-pressed", String(activeTheme === "dark"));
}

elements.themeToggle.addEventListener("click", () => {
  activeTheme = applyTheme(nextTheme(activeTheme));
  saveTheme(activeTheme);
  updateThemeButton();
});

updateThemeButton();

function showDialog(dialog) {
  if (typeof dialog.showModal === "function" && !dialog.open) dialog.showModal();
}

function closeDialog(dialog) {
  if (dialog.open) dialog.close();
}

function setBusy(busy, mode = "text") {
  elements.textSubmit.disabled = busy || !navigator.onLine;
  elements.textSubmit.classList.toggle("is-loading", busy && mode === "text");
  elements.recordButton.disabled = busy || !navigator.onLine || !recorder.supported;
  elements.recordVisual.disabled = !recordingActive
    && (busy || !navigator.onLine || !recorder.supported);
  elements.receiptFile.disabled = busy;
  elements.receiptSubmit.disabled = busy || !navigator.onLine || !selectedReceiptFile;
  elements.receiptSubmit.classList.toggle("is-loading", busy && mode === "receipt");
  elements.tabs.forEach((tab) => { tab.disabled = busy; });
}

function setRecordingVisual(recording) {
  recordingActive = recording;
  elements.recordVisual.classList.toggle("is-recording", recording);
  const label = recording ? "Berhenti merekam suara" : "Mulai merekam suara";
  elements.recordVisual.setAttribute("aria-label", label);
  elements.recordVisual.title = label;
  if (recording) elements.recordVisual.disabled = false;
}

function updateConnection() {
  const online = navigator.onLine;
  elements.connection.classList.toggle("is-offline", !online);
  elements.connectionLabel.textContent = online ? "Online" : "Offline";
  elements.offlineBanner.hidden = online;
  setBusy(gate.busy);
  if (!online) setStatus("Koneksi server diperlukan untuk input teks, suara, atau Scan Nota. Transaksi manual tetap tersedia.", "warning");
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
  elements.receiptPanel.hidden = selectedTab.id !== "receipt-tab";
}

function transactionTitle(transaction) {
  if (transaction.source === "receipt" && transaction.receipt?.merchant_name) {
    return `Belanja di ${transaction.receipt.merchant_name}`;
  }
  if (transaction.item_name) return transaction.item_name;
  if (transaction.transaction_type === "income") return "Pemasukan umum";
  if (transaction.transaction_type === "expense") return "Pengeluaran umum";
  return "Transaksi";
}

function readPeriodSelection() {
  return {
    mode: elements.periodMode.value,
    weekDate: elements.weekFilterDate.value,
    month: elements.monthFilterValue.value,
    year: elements.yearFilterValue.value,
    startDate: elements.customStartDate.value,
    endDate: elements.customEndDate.value,
  };
}

function renderSummary(transactions) {
  const summary = calculateSummary(transactions);
  elements.summaryBalance.textContent = `${summary.balance < 0 ? "−" : ""}${formatRupiah(summary.balance)}`;
  elements.summaryIncome.textContent = formatRupiah(summary.income);
  elements.summaryExpense.textContent = formatRupiah(summary.expense);
}

function renderHistory(transactions) {
  elements.historyList.replaceChildren();
  elements.emptyHistory.hidden = transactions.length > 0;
  elements.clearHistoryButton.disabled = history.length === 0;
  elements.dialogClearHistory.disabled = history.length === 0;

  if (history.length === 0) {
    elements.emptyHistoryTitle.textContent = "Belum ada transaksi";
    elements.emptyHistoryDescription.textContent = "Tambahkan transaksi melalui teks, suara, Foto nota, atau form manual.";
  } else if (transactions.length === 0) {
    elements.emptyHistoryTitle.textContent = "Tidak ada transaksi pada periode ini";
    elements.emptyHistoryDescription.textContent = "Ubah filter periode atau pilih Semua untuk melihat riwayat lainnya.";
  }

  transactions.forEach((transaction) => {
    const item = document.createElement("li");
    item.className = `history-item type-${transaction.transaction_type}`;

    const button = document.createElement("button");
    button.type = "button";
    button.className = "history-item-button";
    button.setAttribute("aria-label", `Buka detail ${transactionTitle(transaction)}`);
    button.addEventListener("click", () => openTransactionDetail(transaction.id));

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
    button.append(main, amount);
    item.append(button);
    elements.historyList.append(item);
  });
}

function hideChartTooltip(force = false) {
  if (chartTooltipPinned && !force) return false;
  chartTooltipPinned = false;
  elements.chartTooltip.hidden = true;
  elements.weeklyChart
    .querySelectorAll(".chart-hover-guide")
    .forEach((guide) => guide.setAttribute("visibility", "hidden"));
  return true;
}

function showChartTooltip({ point, target, trigger, pointerEvent }) {
  if (chartTooltipPinned && trigger !== "click") return;
  if (trigger === "click") chartTooltipPinned = true;
  const description = describeChartPoint(point);
  elements.chartTooltipDate.textContent = description.dateLabel;
  elements.chartTooltipIncome.textContent = description.incomeLabel;
  elements.chartTooltipExpense.textContent = description.expenseLabel;
  elements.chartTooltip.hidden = false;

  const panelRect = elements.trendPanel.getBoundingClientRect();
  const pointRect = target.getBoundingClientRect();
  const tooltipRect = elements.chartTooltip.getBoundingClientRect();
  const anchorLeft = Number.isFinite(pointerEvent?.clientX)
    ? pointerEvent.clientX
    : pointRect.left + pointRect.width / 2;
  const anchorTop = Number.isFinite(pointerEvent?.clientY) ? pointerEvent.clientY : pointRect.top;
  const idealLeft = anchorLeft - panelRect.left - tooltipRect.width / 2;
  const left = Math.max(10, Math.min(idealLeft, elements.trendPanel.clientWidth - tooltipRect.width - 10));
  let top = anchorTop - panelRect.top - tooltipRect.height - 10;
  if (top < 64) top = anchorTop - panelRect.top + 14;
  elements.chartTooltip.style.left = `${Math.round(left)}px`;
  elements.chartTooltip.style.top = `${Math.round(top)}px`;
}

function renderChartInsight(bounds, totals) {
  const insight = describePeriodInsight(bounds.label, totals);
  elements.chartInsightPeriod.textContent = bounds.label;
  elements.chartInsight.dataset.state = insight.state;
  elements.chartSummary.textContent = insight.text;
}

function renderChart(transactions, bounds) {
  hideChartTooltip(true);
  const chart = aggregateTransactionsByPeriod(transactions, bounds);
  const granularityLabels = {
    day: "Tren harian",
    week: "Tren mingguan",
    month: "Tren bulanan",
  };
  elements.trendEyebrow.textContent = bounds.label;
  elements.trendTitle.textContent = granularityLabels[chart.granularity];
  const totals = renderTransactionChart(elements.weeklyChart, chart.points, {
    periodLabel: bounds.label,
    onPointShow: showChartTooltip,
    onPointHide: () => hideChartTooltip(),
  });
  renderChartInsight(bounds, totals);
}

document.addEventListener("pointerdown", (event) => {
  if (elements.chartTooltip.hidden) return;
  if (event.target.closest?.(".chart-point, .chart-hover-zone, .chart-tooltip")) return;
  hideChartTooltip(true);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") hideChartTooltip(true);
});

function renderFilteredViews() {
  try {
    const result = filterTransactionsByPeriod(history, readPeriodSelection());
    elements.filterError.textContent = "";
    elements.activePeriod.textContent = `Menampilkan ${result.bounds.label.toLocaleLowerCase("id-ID")} (${result.transactions.length} transaksi).`;
    elements.summaryPeriodLabel.textContent = result.bounds.label;
    renderSummary(result.transactions);
    renderHistory(result.transactions);
    renderChart(result.transactions, result.bounds);
  } catch (error) {
    elements.filterError.textContent = error.message;
  }
}

function renderAll() {
  renderFilteredViews();
}

function resultOriginalText(record) {
  if (record.source === "voice") return record.transcript;
  if (record.source === "manual") return record.note;
  if (record.source === "receipt") return record.receipt?.merchant_name
    ? `Belanja di ${record.receipt.merchant_name}`
    : "Hasil Scan Nota";
  return record.original_text;
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
  const original = resultOriginalText(record);
  elements.resultInput.textContent = original ? `“${original}”` : EMPTY_VALUE;
  elements.resultCard.hidden = false;
}

function acceptSuccess(response, source, originalText) {
  const saved = recordSuccessfulResponse(response, source, originalText);
  history = saved.history;
  renderResult(saved.record);
  renderAll();
  setStatus("Transaksi berhasil dicatat pada perangkat ini.", "success");
}

function humanizeError(error, mode = "text") {
  if (!navigator.onLine) return "Anda sedang offline. Sambungkan perangkat untuk memproses transaksi.";
  if (error instanceof ApiError) return error.message;
  if (error?.name === "NotAllowedError") return "Izin mikrofon ditolak. Izinkan mikrofon melalui pengaturan browser.";
  if (error?.name === "NotFoundError") return "Mikrofon tidak ditemukan pada perangkat ini.";
  if (mode === "voice") return "Rekaman tidak dapat diproses. Silakan coba kembali.";
  if (mode === "receipt") return "Foto nota tidak dapat diproses. Silakan coba kembali.";
  return "Transaksi tidak dapat diproses. Silakan coba kembali.";
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

const RECEIPT_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const RECEIPT_MAX_SIZE_BYTES = 10 * 1024 * 1024;

function clearReceiptPreview() {
  if (receiptPreviewUrl) URL.revokeObjectURL(receiptPreviewUrl);
  receiptPreviewUrl = null;
  elements.receiptPreviewImage.removeAttribute("src");
  elements.receiptPreview.hidden = true;
}

function clearReceiptConfirmation() {
  pendingReceipt = null;
  elements.receiptOcrText.textContent = "";
  elements.receiptWarningList.replaceChildren();
  elements.receiptConfirmItems.replaceChildren();
  elements.receiptTotalCandidateButtons.replaceChildren();
  elements.receiptConfirmError.textContent = "";
}

function resetReceiptSelection() {
  clearReceiptConfirmation();
  clearReceiptPreview();
  selectedReceiptFile = null;
  elements.receiptFile.value = "";
  elements.receiptFileName.textContent = "Belum ada foto dipilih.";
  elements.receiptSubmit.disabled = true;
}

function releaseProcessedReceiptFile() {
  clearReceiptPreview();
  selectedReceiptFile = null;
  elements.receiptFile.value = "";
  elements.receiptFileName.textContent = "Foto selesai diproses dan dilepas dari browser.";
  elements.receiptSubmit.disabled = true;
}

function receiptItemDescription(item) {
  const quantity = item.quantity == null ? "" : `${item.quantity}${item.unit ? ` ${item.unit}` : ""}`;
  const unitPrice = item.unit_price == null
    ? ""
    : quantity
      ? ` × ${formatRupiah(item.unit_price)}`
      : `Harga ${formatRupiah(item.unit_price)}`;
  return `${quantity}${unitPrice}`.trim() || "Rincian jumlah tidak terbaca";
}

function appendReceiptItems(container, items) {
  container.replaceChildren();
  items.forEach((item) => {
    const row = document.createElement("li");
    const label = document.createElement("strong");
    label.textContent = item.item_name || "Barang tanpa nama";
    const value = document.createElement("span");
    const total = item.line_total == null ? "—" : formatRupiah(item.line_total);
    value.textContent = `${receiptItemDescription(item)} · ${total}`;
    row.append(label, value);
    container.append(row);
  });
}

function renderReceiptConfirmation(response) {
  pendingReceipt = response;
  const receipt = response.data.receipt;
  const items = Array.isArray(receipt.items) ? receipt.items : [];
  const warnings = Array.isArray(receipt.warnings) ? receipt.warnings : [];
  const candidates = [...new Set((response.total_candidates || []).map(Number).filter(Number.isFinite))];

  elements.receiptConfirmMerchant.textContent = receipt.merchant_name || EMPTY_VALUE;
  elements.receiptConfirmNumber.textContent = receipt.receipt_number || EMPTY_VALUE;
  elements.receiptConfirmDate.value = response.data.date || "";
  elements.receiptConfirmTotal.value = response.data.total_price || candidates[0] || "";
  elements.receiptConfirmError.textContent = "";
  elements.receiptOcrText.textContent = response.ocr_text || "";

  elements.receiptTotalCandidateButtons.replaceChildren();
  candidates.forEach((candidate) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "receipt-candidate-button";
    button.textContent = formatRupiah(candidate);
    button.addEventListener("click", () => {
      elements.receiptConfirmTotal.value = String(candidate);
    });
    elements.receiptTotalCandidateButtons.append(button);
  });
  elements.receiptTotalCandidates.hidden = candidates.length < 2;

  elements.receiptWarningList.replaceChildren();
  warnings.forEach((warning) => {
    const item = document.createElement("li");
    item.textContent = warning;
    elements.receiptWarningList.append(item);
  });
  elements.receiptWarningBox.hidden = warnings.length === 0;
  appendReceiptItems(elements.receiptConfirmItems, items);
  elements.receiptConfirmEmptyItems.hidden = items.length > 0;
  showDialog(elements.receiptConfirmDialog);
}

elements.receiptFile.addEventListener("change", () => {
  const file = elements.receiptFile.files?.[0] || null;
  clearReceiptPreview();
  clearReceiptConfirmation();
  selectedReceiptFile = null;

  if (!file) {
    elements.receiptFileName.textContent = "Belum ada foto dipilih.";
    elements.receiptSubmit.disabled = true;
    return;
  }
  if (!RECEIPT_TYPES.has(file.type)) {
    elements.receiptFile.value = "";
    elements.receiptFileName.textContent = "Format tidak didukung. Pilih JPEG, PNG, atau WebP.";
    setStatus("Format foto nota tidak didukung.", "error");
    return;
  }
  if (file.size === 0 || file.size > RECEIPT_MAX_SIZE_BYTES) {
    elements.receiptFile.value = "";
    elements.receiptFileName.textContent = file.size === 0
      ? "File foto kosong."
      : "Ukuran foto melebihi 10 MB.";
    setStatus(elements.receiptFileName.textContent, "error");
    return;
  }

  selectedReceiptFile = file;
  receiptPreviewUrl = URL.createObjectURL(file);
  elements.receiptPreviewImage.src = receiptPreviewUrl;
  elements.receiptPreview.hidden = false;
  elements.receiptFileName.textContent = file.name;
  elements.receiptSubmit.disabled = !navigator.onLine;
  setStatus("Foto siap dipindai.");
});

elements.receiptChangeButton.addEventListener("click", () => elements.receiptFile.click());

elements.receiptForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedReceiptFile) {
    setStatus("Pilih foto nota terlebih dahulu.", "error");
    return;
  }
  if (!navigator.onLine) {
    setStatus("Koneksi server diperlukan untuk Scan Nota.", "error");
    return;
  }

  const outcome = await gate.run(async () => {
    setBusy(true, "receipt");
    setStatus("Foto nota sedang dibaca…");
    try {
      const response = await extractReceipt(selectedReceiptFile);
      releaseProcessedReceiptFile();
      renderReceiptConfirmation(response);
      setStatus("Hasil Scan Nota siap dikonfirmasi.", "success");
    } catch (error) {
      clearReceiptConfirmation();
      setStatus(humanizeError(error, "receipt"), "error");
    } finally {
      setBusy(false);
    }
  });
  if (outcome.skipped) setStatus("Permintaan sebelumnya masih diproses.", "warning");
});

function discardReceiptResult() {
  clearReceiptConfirmation();
  closeDialog(elements.receiptConfirmDialog);
}

elements.closeReceiptConfirmButton.addEventListener("click", discardReceiptResult);
elements.receiptConfirmDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  discardReceiptResult();
});
elements.receiptRetakeButton.addEventListener("click", () => {
  closeDialog(elements.receiptConfirmDialog);
  resetReceiptSelection();
  elements.receiptFile.click();
});

elements.receiptConfirmForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!pendingReceipt) {
    elements.receiptConfirmError.textContent = "Hasil nota sudah tidak tersedia. Scan ulang foto nota.";
    return;
  }
  try {
    const saved = createReceiptTransaction(pendingReceipt, {
      date: elements.receiptConfirmDate.value,
      total_price: elements.receiptConfirmTotal.value,
    });
    history = saved.history;
    renderResult(saved.record);
    closeDialog(elements.receiptConfirmDialog);
    resetReceiptSelection();
    renderAll();
    setStatus("Nota dikonfirmasi dan disimpan sebagai satu transaksi pengeluaran.", "success");
  } catch (error) {
    elements.receiptConfirmError.textContent = error.message;
  }
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
  setRecordingVisual(false);
  elements.recordVisual.disabled = true;
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
      setRecordingVisual(true);
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
      setRecordingVisual(false);
      elements.stopButton.disabled = true;
      setBusy(false);
    }
  });
  if (outcome.skipped) setStatus("Permintaan sebelumnya masih diproses.", "warning");
});

elements.recordVisual.addEventListener("click", () => {
  if (recordingActive) {
    if (!elements.stopButton.disabled) elements.stopButton.click();
    return;
  }
  elements.recordButton.click();
});

elements.tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => switchTab(tab));
  tab.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "ArrowRight"
      ? (index + 1) % elements.tabs.length
      : (index - 1 + elements.tabs.length) % elements.tabs.length;
    elements.tabs[next].focus();
    switchTab(elements.tabs[next]);
  });
});

function openSettings() {
  showDialog(elements.settingsDialog);
}

elements.settingsButton.addEventListener("click", openSettings);
elements.bottomSettings.addEventListener("click", openSettings);
elements.closeSettings.addEventListener("click", () => closeDialog(elements.settingsDialog));
elements.doneSettings.addEventListener("click", () => closeDialog(elements.settingsDialog));
elements.settingsDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  closeDialog(elements.settingsDialog);
});

function requestClearHistory() {
  if (history.length === 0) return;
  if (!window.confirm("Hapus seluruh riwayat transaksi yang tersimpan di perangkat ini?")) return;
  clearHistory();
  history = [];
  closeDialog(elements.settingsDialog);
  renderAll();
  setStatus("Riwayat lokal telah dihapus.", "success");
}

elements.clearHistoryButton.addEventListener("click", requestClearHistory);
elements.dialogClearHistory.addEventListener("click", requestClearHistory);

function openTransactionDetail(id) {
  const record = history.find((transaction) => transaction.id === id);
  if (!record) return;
  activeTransactionId = id;
  const view = presentTransactionDetail(record, getLocalReferenceDate());
  elements.detailType.textContent = view.type;
  elements.detailPrice.textContent = view.price;
  elements.detailDate.textContent = view.date;
  elements.detailItem.textContent = view.item;
  elements.detailQuantity.textContent = view.quantity;
  elements.detailUnit.textContent = view.unit;
  elements.detailSource.textContent = view.source;
  elements.detailCreatedAt.textContent = view.createdAt;
  elements.detailOriginalLabel.textContent = view.originalLabel;
  elements.detailOriginalText.textContent = view.originalText;
  elements.detailNormalizedText.textContent = view.normalizedText;
  elements.detailNormalizedSection.hidden = record.source !== "voice";
  elements.detailOriginalSection.hidden = record.source === "receipt";
  const isReceipt = record.source === "receipt" && record.receipt;
  elements.detailReceiptSection.hidden = !isReceipt;
  if (isReceipt) {
    elements.detailReceiptMerchant.textContent = record.receipt.merchant_name || EMPTY_VALUE;
    elements.detailReceiptNumber.textContent = record.receipt.receipt_number || EMPTY_VALUE;
    elements.detailReceiptSubtotal.textContent = record.receipt.subtotal == null
      ? EMPTY_VALUE
      : formatRupiah(record.receipt.subtotal);
    elements.detailReceiptDiscount.textContent = record.receipt.discount == null
      ? EMPTY_VALUE
      : formatRupiah(record.receipt.discount);
    elements.detailReceiptTax.textContent = record.receipt.tax == null
      ? EMPTY_VALUE
      : formatRupiah(record.receipt.tax);
    elements.detailReceiptService.textContent = record.receipt.service_charge == null
      ? EMPTY_VALUE
      : formatRupiah(record.receipt.service_charge);
    appendReceiptItems(elements.detailReceiptItems, record.receipt.items || []);
    if ((record.receipt.items || []).length === 0) {
      const empty = document.createElement("li");
      empty.textContent = "Tidak ada rincian barang yang tersimpan.";
      elements.detailReceiptItems.append(empty);
    }
  }
  showDialog(elements.detailDialog);
}

function closeTransactionDetail() {
  activeTransactionId = null;
  closeDialog(elements.detailDialog);
}

elements.closeDetailButton.addEventListener("click", closeTransactionDetail);
elements.doneDetailButton.addEventListener("click", closeTransactionDetail);
elements.detailDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  closeTransactionDetail();
});

function openTransactionForm(record = null) {
  editingTransactionId = record?.id || null;
  elements.manualTransactionForm.reset();
  elements.manualFormError.textContent = "";
  elements.transactionFormTitle.textContent = record ? "Edit transaksi" : "Tambah transaksi manual";
  elements.manualTransactionType.value = ["income", "expense"].includes(record?.transaction_type)
    ? record.transaction_type
    : "income";
  elements.manualDate.value = record?.date || getLocalReferenceDate();
  elements.manualTotalPrice.value = record?.total_price ?? "";
  elements.manualItemName.value = record?.item_name ?? "";
  elements.manualQuantity.value = record?.quantity ?? "";
  elements.manualUnit.value = record?.unit ?? "";
  elements.manualNote.value = record?.note ?? "";
  showDialog(elements.transactionFormDialog);
}

function closeTransactionForm() {
  editingTransactionId = null;
  closeDialog(elements.transactionFormDialog);
}

elements.addManualButton.addEventListener("click", () => openTransactionForm());
elements.closeTransactionFormButton.addEventListener("click", closeTransactionForm);
elements.cancelTransactionFormButton.addEventListener("click", closeTransactionForm);
elements.transactionFormDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  closeTransactionForm();
});

elements.editTransactionButton.addEventListener("click", () => {
  const record = history.find((transaction) => transaction.id === activeTransactionId);
  if (!record) return;
  closeTransactionDetail();
  openTransactionForm(record);
});

elements.deleteTransactionButton.addEventListener("click", () => {
  const record = history.find((transaction) => transaction.id === activeTransactionId);
  if (!record) return;
  if (!window.confirm(`Hapus transaksi ${transactionTitle(record)}?`)) return;
  try {
    history = deleteTransaction(record.id);
    closeTransactionDetail();
    renderAll();
    setStatus("Transaksi telah dihapus dari perangkat ini.", "success");
  } catch (error) {
    setStatus(error.message, "error");
  }
});

elements.manualTransactionForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const input = {
    transaction_type: elements.manualTransactionType.value,
    date: elements.manualDate.value,
    total_price: elements.manualTotalPrice.value,
    item_name: elements.manualItemName.value,
    quantity: elements.manualQuantity.value,
    unit: elements.manualUnit.value,
    note: elements.manualNote.value,
  };

  try {
    const saved = editingTransactionId
      ? updateTransaction(editingTransactionId, input)
      : createManualTransaction(input);
    const action = editingTransactionId ? "diperbarui" : "ditambahkan";
    history = saved.history;
    renderResult(saved.record);
    closeTransactionForm();
    renderAll();
    setStatus(`Transaksi berhasil ${action}.`, "success");
  } catch (error) {
    elements.manualFormError.textContent = error.message;
  }
});

function updateFilterFields() {
  const mode = elements.periodMode.value;
  elements.weekFilterField.hidden = mode !== "week";
  elements.monthFilterField.hidden = mode !== "month";
  elements.yearFilterField.hidden = mode !== "year";
  elements.customFilterFields.hidden = mode !== "custom";
}

[
  elements.periodMode,
  elements.weekFilterDate,
  elements.monthFilterValue,
  elements.yearFilterValue,
  elements.customStartDate,
  elements.customEndDate,
].forEach((control) => {
  control.addEventListener("change", () => {
    updateFilterFields();
    renderFilteredViews();
  });
});

elements.resetFilterButton.addEventListener("click", () => {
  elements.periodMode.value = "all";
  updateFilterFields();
  renderFilteredViews();
});

const localToday = getLocalReferenceDate();
elements.weekFilterDate.value = localToday;
elements.monthFilterValue.value = localToday.slice(0, 7);
elements.yearFilterValue.value = localToday.slice(0, 4);
elements.customStartDate.value = localToday;
elements.customEndDate.value = localToday;
updateFilterFields();

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
  window.addEventListener("load", async () => {
    try {
      const registration = await navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" });
      await registration.update();
    } catch {
      // The application remains usable online when service worker registration fails.
    }
  });
}

if (!recorder.supported) {
  elements.recordButton.disabled = true;
  elements.recordVisual.disabled = true;
  elements.voiceStatus.textContent = "Browser ini tidak mendukung perekaman suara.";
  elements.voiceHelp.textContent = "Gunakan browser modern dengan dukungan MediaRecorder, atau gunakan tab Teks.";
}

renderAll();
updateConnection();
