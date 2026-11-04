/**
 * app.js adalah pusat state dan seluruh interaksi UI CatatKas.
 *
 * Isi berkas ini, dari atas ke bawah:
 * 1. Import modul kecil (api, storage, chart, filters, formatters, kategori).
 * 2. `elements`  : daftar elemen HTML yang dipakai berulang.
 * 3. Pemilih kategori dan dialog konfirmasi transaksi.
 * 4. Autentikasi (login, register, auto-login, logout).
 * 5. Render riwayat, ringkasan, grafik, dan filter.
 * 6. Alur tiga fitur input: teks, suara, dan foto nota.
 * 7. Form manual, detail, edit, hapus, dan inisialisasi aplikasi.
 *
 * Alur singkat: input pengguna -> panggil API -> dialog konfirmasi editable ->
 * simpan ke Supabase -> render ulang riwayat.
 */

import {
  ApiError,
  autoLoginAccount,
  clearTransactionsRemote,
  createTransactionRemote,
  deleteTransactionRemote,
  extractAudio,
  extractReceipt,
  extractText,
  getCurrentUser,
  getLocalReferenceDate,
  listTransactions,
  loginAccount,
  logoutAccount,
  refreshSession,
  registerAccount,
  updateTransactionRemote,
} from "/api.js?v=20";
import {
  aggregateTransactionsByPeriod,
  describeChartPoint,
  describePeriodInsight,
  renderTransactionChart,
  CHART_WIDE_MEDIA_QUERY,
} from "/chart.js?v=19";
import {
  filterTransactionsByCategory,
  filterTransactionsByPeriod,
  summarizeCategories,
} from "/filters.js?v=17";
import {
  EMPTY_VALUE,
  formatRupiah,
  presentTransaction,
  presentTransactionDetail,
} from "/formatters.js?v=17";
import {
  CATEGORY_PRESETS,
  UNCATEGORIZED,
  categoryFromChoice,
  categoryLabel,
  categoryPresentation,
  normalizeCategory,
} from "/categories.js?v=3";
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
  saveHistory,
  setHistoryUser,
  updateTransaction,
} from "/storage.js?v=21";
import { applyTheme, loadTheme, nextTheme, saveTheme } from "/theme.js?v=17";

const $ = (selector) => document.querySelector(selector);
const elements = {
  authScreen: $("#auth-screen"),
  authLoading: $("#auth-loading"),
  authContent: $("#auth-content"),
  authStatus: $("#auth-status"),
  loginTab: $("#login-tab"),
  registerTab: $("#register-tab"),
  loginPanel: $("#login-panel"),
  registerPanel: $("#register-panel"),
  loginForm: $("#login-form"),
  loginEmail: $("#login-email"),
  loginPassword: $("#login-password"),
  loginSubmit: $("#login-submit"),
  registerForm: $("#register-form"),
  registerEmail: $("#register-email"),
  registerPassword: $("#register-password"),
  registerPasswordConfirmation: $("#register-password-confirmation"),
  registerSubmit: $("#register-submit"),
  authUserEmail: $("#auth-user-email"),
  logoutButton: $("#logout-button"),
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
  resultCategory: $("#result-category"),
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
  categoryFilter: $("#category-filter"),
  activePeriod: $("#active-period"),
  filterError: $("#filter-error"),
  categorySummary: $("#category-summary"),
  categorySummaryList: $("#category-summary-list"),
  categorySummaryPeriod: $("#category-summary-period"),
  categoryPresets: $("#category-presets"),
  detailDialog: $("#transaction-detail-dialog"),
  closeDetailButton: $("#close-detail-button"),
  doneDetailButton: $("#done-detail-button"),
  editTransactionButton: $("#edit-transaction-button"),
  deleteTransactionButton: $("#delete-transaction-button"),
  detailType: $("#detail-type"),
  detailPrice: $("#detail-price"),
  detailDate: $("#detail-date"),
  detailCategory: $("#detail-category"),
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
  detailReceiptItems: $("#detail-receipt-items"),
  receiptConfirmDialog: $("#receipt-confirm-dialog"),
  closeReceiptConfirmButton: $("#close-receipt-confirm-button"),
  receiptConfirmForm: $("#receipt-confirm-form"),
  receiptConfirmMerchant: $("#receipt-confirm-merchant"),
  receiptConfirmDate: $("#receipt-confirm-date"),
  receiptConfirmCalculatedTotal: $("#receipt-confirm-calculated-total"),
  receiptConfirmItems: $("#receipt-confirm-items"),
  receiptConfirmEmptyItems: $("#receipt-confirm-empty-items"),
  receiptAddItemButton: $("#receipt-add-item-button"),
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
  categoryPickDialog: $("#category-pick-dialog"),
  categoryPickSummary: $("#category-pick-summary"),
  categoryPickGrid: $("#category-pick-grid"),
  categoryPickCustom: $("#category-pick-custom"),
  categoryPickError: $("#category-pick-error"),
  categoryPickSkip: $("#category-pick-skip"),
  categoryPickConfirm: $("#category-pick-confirm"),
  confirmDialog: $("#transaction-confirm-dialog"),
  closeConfirmButton: $("#close-transaction-confirm-button"),
  confirmForm: $("#transaction-confirm-form"),
  confirmSource: $("#transaction-confirm-source"),
  confirmPriceWarning: $("#transaction-confirm-price-warning"),
  confirmType: $("#transaction-confirm-type"),
  confirmDate: $("#transaction-confirm-date"),
  confirmTotalPrice: $("#transaction-confirm-total-price"),
  confirmItemName: $("#transaction-confirm-item-name"),
  confirmQuantity: $("#transaction-confirm-quantity"),
  confirmUnit: $("#transaction-confirm-unit"),
  confirmNoteField: $("#transaction-confirm-note-field"),
  confirmNote: $("#transaction-confirm-note"),
  confirmCategoryGrid: $("#transaction-confirm-category-grid"),
  confirmCategoryCustom: $("#transaction-confirm-custom-category"),
  confirmError: $("#transaction-confirm-error"),
  confirmCancelButton: $("#transaction-confirm-cancel-button"),
  confirmSkipButton: $("#transaction-confirm-skip-button"),
  manualCategoryGrid: $("#manual-form-category-grid"),
  manualCategoryCustom: $("#manual-form-custom-category"),
  actionPopup: $("#action-popup"),
  actionPopupIcon: $("#action-popup-icon"),
  actionPopupMessage: $("#action-popup-message"),
  actionPopupClose: $("#action-popup-close"),
};

const gate = new RequestGate();
const recorder = new RecorderSession();

CATEGORY_PRESETS.forEach((preset) => {
  const option = document.createElement("option");
  option.value = preset;
  // Value yang terisi ke input tetap nama polos agar normalizeCategory cocok,
  // sedangkan label membantu pengguna membedakan preset lewat logo.
  option.label = categoryPresentation(preset);
  elements.categoryPresets.append(option);
});

// Popup pemilihan kategori. Muncul untuk semua input (teks, suara, nota,
// manual, dan edit) tepat sebelum transaksi dikirim ke Supabase.
let selectedCategory = null;
let categoryPickResolver = null;
// Nilai yang dipakai saat tombol Lewati/Escape ditekan: kategori lama untuk edit,
// "Belum dikategorikan" untuk transaksi baru.
let categoryPickKeep = UNCATEGORIZED;

// Dialog konfirmasi transaksi: menggantikan popup kategori untuk teks, suara,
// manual, dan edit. Data hasil ekstraksi / form dapat diedit sebelum disimpan.
let pendingConfirmation = null;
let confirmCategorySelected = null;
let confirmCategoryKeep = UNCATEGORIZED;
let confirmSaving = false;

// Pemilih kategori pada form manual/edit. Kategori dipilih langsung di form,
// diteruskan sudah terseleksi ke dialog konfirmasi, dan ikut disimpan.
let manualCategorySelected = null;

// Ketiga pemilih kategori (popup Scan Nota, dialog konfirmasi, dan form manual)
// memakai bentuk chip yang sama. Dua helper di bawah membangun dan menandai chip
// agar tidak ada tiga salinan kode yang harus diubah bersamaan.
function appendCategoryChips(container, onSelect) {
  const chips = CATEGORY_PRESETS.map((preset) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "category-chip";
    chip.dataset.category = preset;
    chip.textContent = categoryPresentation(preset);
    chip.setAttribute("aria-pressed", "false");
    chip.addEventListener("click", () => onSelect(preset));
    return chip;
  });
  container.append(...chips);
}

function syncCategoryChips(container, selected) {
  container.querySelectorAll(".category-chip").forEach((chip) => {
    const active = chip.dataset.category === selected;
    chip.classList.toggle("is-selected", active);
    chip.setAttribute("aria-pressed", String(active));
  });
}

function buildCategoryPicker() {
  appendCategoryChips(elements.categoryPickGrid, selectCategoryChip);
}

function syncCategoryPickerSelection() {
  syncCategoryChips(elements.categoryPickGrid, selectedCategory);
}

function selectCategoryChip(preset) {
  selectedCategory = selectedCategory === preset ? null : preset;
  elements.categoryPickCustom.value = "";
  elements.categoryPickError.textContent = "";
  syncCategoryPickerSelection();
}

function transactionSummaryText(fields = {}) {
  const typeLabel = fields.transaction_type === "income"
    ? "Pemasukan"
    : fields.transaction_type === "expense"
      ? "Pengeluaran"
      : "";
  const parts = [
    typeLabel,
    Number(fields.total_price) > 0 ? formatRupiah(fields.total_price) : "",
    fields.item_name || "",
    fields.merchant_name ? `Belanja di ${fields.merchant_name}` : "",
  ];
  return parts.filter(Boolean).join(" · ") || "Transaksi baru";
}

function askCategory({ summary, current = null } = {}) {
  if (categoryPickResolver) resolveCategoryPicker(categoryPickKeep);
  const isPreset = CATEGORY_PRESETS.includes(current);
  selectedCategory = isPreset ? current : null;
  elements.categoryPickCustom.value = current && !isPreset ? String(current) : "";
  categoryPickKeep = normalizeCategory(current) ?? UNCATEGORIZED;
  elements.categoryPickError.textContent = "";
  elements.categoryPickSummary.textContent = summary || "Transaksi baru";
  syncCategoryPickerSelection();
  showDialog(elements.categoryPickDialog);
  return new Promise((resolve) => {
    categoryPickResolver = resolve;
  });
}

function resolveCategoryPicker(value) {
  const resolve = categoryPickResolver;
  categoryPickResolver = null;
  closeDialog(elements.categoryPickDialog);
  resolve?.(value);
}

buildCategoryPicker();

elements.categoryPickCustom.addEventListener("input", () => {
  elements.categoryPickError.textContent = "";
  if (elements.categoryPickCustom.value.trim()) {
    selectedCategory = null;
    syncCategoryPickerSelection();
  }
});

elements.categoryPickConfirm.addEventListener("click", () => {
  const category = categoryFromChoice(selectedCategory, elements.categoryPickCustom.value);
  if (!category) {
    elements.categoryPickError.textContent = "Pilih satu kategori atau tekan Lewati.";
    return;
  }
  resolveCategoryPicker(category);
});

elements.categoryPickSkip.addEventListener("click", () => resolveCategoryPicker(categoryPickKeep));

elements.categoryPickDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  resolveCategoryPicker(categoryPickKeep);
});

function buildConfirmCategoryPicker() {
  appendCategoryChips(elements.confirmCategoryGrid, selectConfirmCategoryChip);
}

function syncConfirmCategoryPickerSelection() {
  syncCategoryChips(elements.confirmCategoryGrid, confirmCategorySelected);
}

function selectConfirmCategoryChip(preset) {
  confirmCategorySelected = confirmCategorySelected === preset ? null : preset;
  elements.confirmCategoryCustom.value = "";
  elements.confirmError.textContent = "";
  syncConfirmCategoryPickerSelection();
}

function buildManualCategoryPicker() {
  appendCategoryChips(elements.manualCategoryGrid, selectManualCategoryChip);
}

function syncManualCategoryPickerSelection() {
  syncCategoryChips(elements.manualCategoryGrid, manualCategorySelected);
}

function selectManualCategoryChip(preset) {
  manualCategorySelected = manualCategorySelected === preset ? null : preset;
  elements.manualCategoryCustom.value = "";
  syncManualCategoryPickerSelection();
}

function isValidDateString(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ""))) return false;
  const [year, month, day] = String(value).split("-").map(Number);
  const parsed = new Date(year, month - 1, day, 12);
  return parsed.getFullYear() === year
    && parsed.getMonth() === month - 1
    && parsed.getDate() === day;
}

// Nominal dibatasi maksimal 15 digit dan diformat dengan pemisah ribuan
// Indonesia (titik) agar mudah dibaca di dialog konfirmasi.
function formatNumberInput(value) {
  const digits = String(value ?? "").replace(/\D/g, "").slice(0, 15);
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

function rawDigits(value) {
  return String(value ?? "").replace(/\D/g, "");
}

function readConfirmFields() {
  return {
    transaction_type: elements.confirmType.value,
    date: elements.confirmDate.value,
    total_price: rawDigits(elements.confirmTotalPrice.value),
    item_name: elements.confirmItemName.value.trim(),
    quantity: elements.confirmQuantity.value,
    unit: elements.confirmUnit.value.trim(),
    note: elements.confirmNote.value,
  };
}

function validateConfirmFields(fields) {
  if (!["income", "expense"].includes(fields.transaction_type)) {
    return "Jenis transaksi harus pemasukan atau pengeluaran.";
  }
  if (!isValidDateString(fields.date)) {
    return "Tanggal transaksi wajib diisi dengan benar.";
  }
  const nominal = Number(fields.total_price);
  if (!Number.isFinite(nominal) || nominal <= 0) {
    const lacksExplicitPrice = pendingConfirmation?.source === "text"
      || pendingConfirmation?.source === "voice";
    return lacksExplicitPrice
      ? "Nominal tidak terbaca dari input. Isi nominal sebelum transaksi disimpan."
      : "Nominal wajib diisi dan harus lebih besar dari nol.";
  }
  return null;
}

function setConfirmSaving(saving) {
  confirmSaving = saving;
  const submit = elements.confirmForm.querySelector(".button-primary");
  submit.disabled = saving;
  submit.classList.toggle("is-loading", saving);
  elements.confirmSkipButton.disabled = saving;
  elements.closeConfirmButton.disabled = saving;
  elements.confirmCancelButton.disabled = saving;
  elements.confirmForm.querySelectorAll("input, select, textarea").forEach((field) => {
    field.disabled = saving;
  });
}

function openTransactionConfirmation({
  source,
  response = null,
  originalText = "",
  fields = {},
  category = null,
  editingId = null,
  snapshot = null,
}) {
  pendingConfirmation = { source, response, originalText, editingId, snapshot };
  const data = fields;
  elements.confirmType.value = ["income", "expense"].includes(data.transaction_type)
    ? data.transaction_type
    : "income";
  elements.confirmDate.value = data.date || getLocalReferenceDate();
  const hasPrice = Number(data.total_price) > 0;
  elements.confirmTotalPrice.value = hasPrice
    ? formatNumberInput(String(Math.round(Number(data.total_price))))
    : "";
  elements.confirmPriceWarning.hidden = hasPrice;
  elements.confirmItemName.value = data.item_name ?? "";
  elements.confirmQuantity.value = data.quantity ?? "";
  elements.confirmUnit.value = data.unit ?? "";
  elements.confirmNote.value = data.note ?? "";
  const isEditableManual = source === "manual" || source === "edit";
  elements.confirmNoteField.hidden = !isEditableManual;
  const original = source === "text" || source === "voice"
    ? (originalText || response?.transcript || "")
    : "";
  elements.confirmSource.hidden = !original;
  elements.confirmSource.textContent = original ? `Input asli: “${original}”` : "";

  const isPreset = CATEGORY_PRESETS.includes(category);
  confirmCategorySelected = isPreset ? category : null;
  elements.confirmCategoryCustom.value = category && !isPreset ? String(category) : "";
  confirmCategoryKeep = normalizeCategory(category) ?? UNCATEGORIZED;
  syncConfirmCategoryPickerSelection();
  elements.confirmError.textContent = "";
  setConfirmSaving(false);
  showDialog(elements.confirmDialog);
}

function closeTransactionConfirmation() {
  pendingConfirmation = null;
  closeDialog(elements.confirmDialog);
}

function cancelTransactionConfirmation() {
  const pending = pendingConfirmation;
  if (!pending) return;
  closeTransactionConfirmation();
  // Teks/suara: hasil batal tanpa menyimpan apa pun. Manual/edit: buka kembali
  // form dengan data yang sudah diketik agar tidak hilang.
  if (pending.source === "manual" || pending.source === "edit") {
    restoreTransactionForm(pending.snapshot || {}, pending.editingId);
  }
}

async function commitConfirmedTransaction(category) {
  if (confirmSaving || !pendingConfirmation) return;
  const pending = pendingConfirmation;
  const fields = readConfirmFields();
  const validationError = validateConfirmFields(fields);
  if (validationError) {
    elements.confirmError.textContent = validationError;
    return;
  }

  setConfirmSaving(true);
  const previousHistory = [...history];
  try {
    let saved;
    const action = pending.source === "edit" ? "diperbarui" : "disimpan";
    if (pending.source === "text" || pending.source === "voice") {
      const data = { ...(pending.response?.data || {}), ...fields };
      const editedResponse = { ...pending.response, data };
      const local = recordSuccessfulResponse(
        editedResponse,
        pending.source,
        pending.originalText,
        { category },
      );
      saved = await persistCreatedRecord(local, previousHistory);
    } else if (pending.source === "edit") {
      const input = { ...fields, category };
      const local = updateTransaction(pending.editingId, input);
      saved = local;
      if (databaseEnabled) {
        try {
          const record = await updateTransactionRemote(pending.editingId, input);
          const nextHistory = local.history.map((item) => (
            item.id === pending.editingId ? record : item
          ));
          saved = { record, history: saveHistory(nextHistory) };
        } catch (error) {
          saveHistory(previousHistory);
          throw error;
        }
      } else {
        saveHistory(previousHistory);
        throw new ApiError("Database Supabase belum siap. Transaksi tidak disimpan.", 503);
      }
    } else {
      const local = createManualTransaction({ ...fields, category });
      saved = await persistCreatedRecord(local, previousHistory);
    }

    history = saved.history;
    renderResult(saved.record);
    closeTransactionConfirmation();
    renderAll();
    setStatus(
      databaseEnabled
        ? `Transaksi berhasil ${action} ke Supabase.`
        : `Transaksi berhasil ${action} pada perangkat ini.`,
      "success",
    );
    if (pending.source === "edit") showActionPopup("Perubahan transaksi berhasil disimpan.");
    if (pending.source === "voice") {
      elements.voiceStatus.textContent = pending.response?.transcript
        ? `Transkrip: ${pending.response.transcript}`
        : "Transaksi suara berhasil diproses.";
    }
  } catch (error) {
    setConfirmSaving(false);
    if (error instanceof ApiError && error.status === 401) {
      showAuthentication();
      setAuthStatus("Sesi telah berakhir. Silakan login kembali.", "error");
    }
    elements.confirmError.textContent = error.message || "Transaksi tidak dapat disimpan.";
  }
}

buildConfirmCategoryPicker();
buildManualCategoryPicker();

elements.confirmCategoryCustom.addEventListener("input", () => {
  elements.confirmError.textContent = "";
  if (elements.confirmCategoryCustom.value.trim()) {
    confirmCategorySelected = null;
    syncConfirmCategoryPickerSelection();
  }
});

elements.confirmTotalPrice.addEventListener("input", () => {
  // Simpan kembali format titik ribuan dan sembunyikan peringatan saat terisi.
  const digits = rawDigits(elements.confirmTotalPrice.value);
  elements.confirmTotalPrice.value = formatNumberInput(digits);
  elements.confirmPriceWarning.hidden = Number(digits || 0) > 0;
});

elements.manualCategoryCustom.addEventListener("input", () => {
  if (elements.manualCategoryCustom.value.trim()) {
    manualCategorySelected = null;
    syncManualCategoryPickerSelection();
  }
});

elements.closeConfirmButton.addEventListener("click", cancelTransactionConfirmation);
elements.confirmCancelButton.addEventListener("click", cancelTransactionConfirmation);
elements.confirmDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  cancelTransactionConfirmation();
});

elements.confirmSkipButton.addEventListener("click", () => {
  if (!confirmSaving) commitConfirmedTransaction(confirmCategoryKeep);
});

elements.confirmForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (confirmSaving) return;
  const category = categoryFromChoice(confirmCategorySelected, elements.confirmCategoryCustom.value);
  if (!category) {
    elements.confirmError.textContent = "Pilih satu kategori atau tekan Lewati kategori.";
    return;
  }
  await commitConfirmedTransaction(category);
});

let history = [];
let databaseEnabled = false;
let currentUser = null;
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
let actionPopupTimeout = null;

function setStatus(message, kind = "") {
  elements.requestStatus.textContent = message;
  elements.requestStatus.dataset.kind = kind;
}

function setAuthStatus(message, kind = "") {
  elements.authStatus.textContent = message;
  elements.authStatus.dataset.kind = kind;
}

function hideActionPopup() {
  if (actionPopupTimeout) clearTimeout(actionPopupTimeout);
  actionPopupTimeout = null;
  elements.actionPopup.classList.remove("is-visible");
  elements.actionPopup.hidden = true;
}

function showActionPopup(message, kind = "success") {
  if (actionPopupTimeout) clearTimeout(actionPopupTimeout);
  elements.actionPopupMessage.textContent = message;
  elements.actionPopupIcon.textContent = kind === "delete" ? "×" : "✓";
  elements.actionPopup.dataset.kind = kind;
  elements.actionPopup.hidden = false;
  requestAnimationFrame(() => elements.actionPopup.classList.add("is-visible"));
  actionPopupTimeout = setTimeout(hideActionPopup, 3500);
}

elements.actionPopupClose.addEventListener("click", hideActionPopup);

function switchAuthTab(mode) {
  const loginActive = mode === "login";
  elements.loginTab.classList.toggle("is-active", loginActive);
  elements.registerTab.classList.toggle("is-active", !loginActive);
  elements.loginTab.setAttribute("aria-selected", String(loginActive));
  elements.registerTab.setAttribute("aria-selected", String(!loginActive));
  elements.loginPanel.hidden = !loginActive;
  elements.registerPanel.hidden = loginActive;
  setAuthStatus("");
}

function setAuthBusy(busy) {
  elements.loginSubmit.disabled = busy;
  elements.registerSubmit.disabled = busy;
  elements.loginSubmit.classList.toggle("is-loading", busy && !elements.loginPanel.hidden);
  elements.registerSubmit.classList.toggle("is-loading", busy && !elements.registerPanel.hidden);
  elements.loginTab.disabled = busy;
  elements.registerTab.disabled = busy;
}

function showAuthentication() {
  currentUser = null;
  databaseEnabled = false;
  history = [];
  setHistoryUser(null);
  document.body.dataset.authState = "unauthenticated";
  elements.authLoading.hidden = true;
  elements.authContent.hidden = false;
  elements.loginPassword.value = "";
  elements.registerPassword.value = "";
  elements.registerPasswordConfirmation.value = "";
  switchAuthTab("login");
}

async function enterAuthenticatedApp(user) {
  if (!user?.id) throw new Error("User ID Supabase tidak tersedia.");
  currentUser = user;
  databaseEnabled = false;
  setHistoryUser(user.id);
  history = loadHistory();
  elements.authUserEmail.textContent = user.email || user.id;
  document.body.dataset.authState = "loading";
  elements.authLoading.hidden = false;
  elements.authContent.hidden = true;
  renderAll();
  await initializeDatabaseHistory();
  document.body.dataset.authState = "authenticated";
  updateConnection();
}

async function tryAutomaticLogin() {
  let result;
  try {
    result = await autoLoginAccount();
  } catch (error) {
    // 403 berarti server tidak mengaktifkan mode demo; tampilkan form login biasa.
    if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
      return false;
    }
    showAuthentication();
    setAuthStatus(error.message || "Login otomatis gagal.", "error");
    return true;
  }
  await enterAuthenticatedApp(result.user);
  setStatus("Mode demo: Anda masuk otomatis memakai akun uji.", "success");
  return true;
}

async function initializeAuthentication() {
  document.body.dataset.authState = "loading";
  elements.authLoading.hidden = false;
  elements.authContent.hidden = true;
  try {
    let session;
    try {
      session = await getCurrentUser();
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401)) throw error;
      await refreshSession();
      session = await getCurrentUser();
    }
    await enterAuthenticatedApp(session.user);
  } catch (error) {
    const needsLogin = error instanceof ApiError && error.status === 401;
    try {
      if (needsLogin && (await tryAutomaticLogin())) return;
    } catch (autoLoginError) {
      showAuthentication();
      setAuthStatus(autoLoginError.message || "Login otomatis gagal.", "error");
      return;
    }
    showAuthentication();
    if (!needsLogin) {
      setAuthStatus(error.message || "Autentikasi belum dapat digunakan.", "error");
    }
  }
}

elements.loginTab.addEventListener("click", () => switchAuthTab("login"));
elements.registerTab.addEventListener("click", () => switchAuthTab("register"));

elements.loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setAuthBusy(true);
  setAuthStatus("Memeriksa akun…");
  try {
    const result = await loginAccount(
      elements.loginEmail.value.trim(),
      elements.loginPassword.value,
    );
    await enterAuthenticatedApp(result.user);
    elements.loginForm.reset();
    setStatus("Login berhasil. Riwayat akun Anda telah dimuat.", "success");
  } catch (error) {
    setAuthStatus(error.message || "Login gagal.", "error");
  } finally {
    setAuthBusy(false);
  }
});

elements.registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (elements.registerPassword.value !== elements.registerPasswordConfirmation.value) {
    setAuthStatus("Konfirmasi password tidak sama.", "error");
    return;
  }
  setAuthBusy(true);
  setAuthStatus("Membuat akun…");
  try {
    const result = await registerAccount(
      elements.registerEmail.value.trim(),
      elements.registerPassword.value,
    );
    if (result.authenticated) {
      await enterAuthenticatedApp(result.user);
      elements.registerForm.reset();
      setStatus("Akun berhasil dibuat dan login aktif.", "success");
    } else {
      const registeredEmail = elements.registerEmail.value.trim();
      elements.registerForm.reset();
      switchAuthTab("login");
      elements.loginEmail.value = registeredEmail;
      setAuthStatus(
        "Akun berhasil dibuat. Periksa email untuk konfirmasi, kemudian login.",
        "success",
      );
    }
  } catch (error) {
    setAuthStatus(error.message || "Registrasi gagal.", "error");
  } finally {
    setAuthBusy(false);
  }
});

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
  elements.addManualButton.disabled = busy || !navigator.onLine || !databaseEnabled;
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
  if (!online) setStatus("Koneksi server diperlukan untuk membaca atau menyimpan transaksi Supabase.", "warning");
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
    const category = elements.categoryFilter.value;
    elements.emptyHistoryTitle.textContent = category
      ? "Tidak ada transaksi pada kategori ini"
      : "Tidak ada transaksi pada periode ini";
    elements.emptyHistoryDescription.textContent = category
      ? "Pilih kategori lain atau tekan Semua untuk melihat riwayat lainnya."
      : "Ubah filter periode atau pilih Semua untuk melihat riwayat lainnya.";
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
    const category = document.createElement("span");
    category.className = "history-category";
    category.textContent = view.category;
    main.append(title, meta, category);

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

// Tinggi kanvas chart berbeda di bawah dan di atas breakpoint, jadi viewBox harus
// digambar ulang saat layar melewatinya (rotasi hp, resize desktop).
window.matchMedia(CHART_WIDE_MEDIA_QUERY).addEventListener("change", () => {
  renderFilteredViews();
});

document.addEventListener("pointerdown", (event) => {
  if (elements.chartTooltip.hidden) return;
  if (event.target.closest?.(".chart-point, .chart-hover-zone, .chart-tooltip")) return;
  hideChartTooltip(true);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") hideChartTooltip(true);
});

function refreshCategoryFilter() {
  const current = elements.categoryFilter.value;
  const labels = [...new Set(
    history.map((transaction) => categoryLabel(transaction.category)),
  )].sort((left, right) => left.localeCompare(right, "id"));
  const allOption = document.createElement("option");
  allOption.value = "";
  allOption.textContent = "Semua kategori";
  const options = [allOption, ...labels.map((label) => {
    const option = document.createElement("option");
    // value tetap nama polos agar filter mencocokkan data tersimpan, teks
    // hanya menampilkan logo agar pilihan mudah dibedakan.
    option.value = label;
    option.textContent = categoryPresentation(label);
    return option;
  })];
  elements.categoryFilter.replaceChildren(...options);
  elements.categoryFilter.value = labels.includes(current) ? current : "";
}

function renderCategorySummary(transactions, periodLabel) {
  const rows = summarizeCategories(transactions);
  elements.categorySummaryList.replaceChildren();
  elements.categorySummary.hidden = rows.length === 0;
  elements.categorySummaryPeriod.textContent = periodLabel;
  rows.forEach((row) => {
    const item = document.createElement("li");
    item.className = `category-summary-row type-${row.transaction_type}`;
    const label = document.createElement("span");
    label.className = "category-summary-label";
    label.textContent = categoryPresentation(row.label);
    const count = document.createElement("span");
    count.className = "category-summary-count";
    count.textContent = `${row.count} transaksi`;
    const amount = document.createElement("strong");
    amount.className = "category-summary-amount";
    const sign = row.transaction_type === "income" ? "+" : "−";
    amount.textContent = `${sign}${formatRupiah(row.total)}`;
    item.append(label, count, amount);
    elements.categorySummaryList.append(item);
  });
}

function renderFilteredViews() {
  try {
    refreshCategoryFilter();
    const result = filterTransactionsByPeriod(history, readPeriodSelection());
    const category = elements.categoryFilter.value;
    const visible = filterTransactionsByCategory(result.transactions, category);
    elements.filterError.textContent = "";
    elements.activePeriod.textContent = `Menampilkan ${result.bounds.label.toLocaleLowerCase("id-ID")}${category ? ` · kategori ${categoryPresentation(category)}` : ""} (${visible.length} transaksi).`;
    elements.summaryPeriodLabel.textContent = result.bounds.label;
    renderSummary(visible);
    renderHistory(visible);
    renderChart(visible, result.bounds);
    renderCategorySummary(result.transactions, result.bounds.label);
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
  elements.resultCategory.textContent = view.category;
  elements.resultItem.textContent = view.item;
  elements.resultQuantity.textContent = view.quantity;
  elements.resultUnit.textContent = view.unit;
  elements.resultSource.textContent = view.source;
  const original = resultOriginalText(record);
  elements.resultInput.textContent = original ? `“${original}”` : EMPTY_VALUE;
  elements.resultCard.hidden = false;
}

async function persistCreatedRecord(saved, previousHistory) {
  if (!databaseEnabled) {
    saveHistory(previousHistory);
    throw new ApiError("Database Supabase belum siap. Transaksi tidak disimpan.", 503);
  }
  try {
    const record = await createTransactionRemote(saved.record);
    const historyWithoutLocalRecord = saved.history.filter((item) => item.id !== saved.record.id);
    const nextHistory = saveHistory([record, ...historyWithoutLocalRecord]);
    return { record: nextHistory[0], history: nextHistory };
  } catch (error) {
    saveHistory(previousHistory);
    throw error;
  }
}

function humanizeError(error, mode = "text") {
  if (!navigator.onLine) return "Anda sedang offline. Sambungkan perangkat untuk memproses transaksi.";
  if (error instanceof ApiError && error.status === 401) {
    showAuthentication();
    setAuthStatus("Sesi telah berakhir. Silakan login kembali.", "error");
    return "Sesi telah berakhir. Silakan login kembali.";
  }
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
      elements.textInput.value = "";
      elements.characterCount.textContent = "0";
      setStatus("Periksa dan konfirmasi data transaksi sebelum disimpan.");
      openTransactionConfirmation({
        source: "text",
        response,
        originalText: response.input || text,
        fields: response.data,
      });
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
  elements.receiptConfirmItems.replaceChildren();
  elements.receiptConfirmCalculatedTotal.textContent = formatRupiah(0);
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

function receiptEditorNumber(value, { allowZero = false } = {}) {
  if (value === null || value === undefined || value === "") return "";
  const number = Number(value);
  if (!Number.isFinite(number) || (allowZero ? number < 0 : number <= 0)) return "";
  return String(number);
}

function createReceiptEditorField(labelText, fieldName, input) {
  const label = document.createElement("label");
  label.className = `receipt-item-editor-field receipt-item-editor-${fieldName.replace("_", "-")}`;
  const caption = document.createElement("span");
  caption.textContent = labelText;
  input.dataset.receiptField = fieldName;
  label.append(caption, input);
  return label;
}

function updateReceiptEditorTotal() {
  const rows = [...elements.receiptConfirmItems.querySelectorAll("[data-receipt-item-row]")];
  const total = rows.reduce((sum, row) => {
    const value = Number(row.querySelector('[data-receipt-field="line_total"]')?.value);
    return sum + (Number.isFinite(value) && value > 0 ? value : 0);
  }, 0);
  elements.receiptConfirmCalculatedTotal.textContent = formatRupiah(total);
  elements.receiptConfirmEmptyItems.hidden = rows.length > 0;
}

function appendReceiptItemEditor(item = {}) {
  const row = document.createElement("div");
  row.className = "receipt-item-editor-row";
  row.dataset.receiptItemRow = "true";

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.maxLength = 200;
  nameInput.required = true;
  nameInput.placeholder = "Nama barang";
  nameInput.value = item.item_name || "";

  const quantityInput = document.createElement("input");
  quantityInput.type = "number";
  quantityInput.min = "0.001";
  quantityInput.step = "any";
  quantityInput.inputMode = "decimal";
  quantityInput.placeholder = "Opsional";
  quantityInput.value = receiptEditorNumber(item.quantity);

  const unitInput = document.createElement("input");
  unitInput.type = "text";
  unitInput.maxLength = 50;
  unitInput.placeholder = "kg, pcs, botol";
  unitInput.value = item.unit || "";

  const unitPriceInput = document.createElement("input");
  unitPriceInput.type = "number";
  unitPriceInput.min = "0";
  unitPriceInput.step = "1";
  unitPriceInput.inputMode = "numeric";
  unitPriceInput.placeholder = "Opsional";
  unitPriceInput.value = receiptEditorNumber(item.unit_price, { allowZero: true });

  const detectedLineTotal = receiptEditorNumber(item.line_total);
  const calculatedLineTotal = quantityInput.value && unitPriceInput.value
    ? String(Math.round(Number(quantityInput.value) * Number(unitPriceInput.value)))
    : "";
  const lineTotalInput = document.createElement("input");
  lineTotalInput.type = "number";
  lineTotalInput.min = "1";
  lineTotalInput.step = "1";
  lineTotalInput.inputMode = "numeric";
  lineTotalInput.required = true;
  lineTotalInput.placeholder = "Wajib diisi";
  lineTotalInput.value = detectedLineTotal || calculatedLineTotal;

  const removeButton = document.createElement("button");
  removeButton.type = "button";
  removeButton.className = "receipt-item-remove-button";
  removeButton.textContent = "Hapus barang";
  removeButton.addEventListener("click", () => {
    row.remove();
    updateReceiptEditorTotal();
  });

  const syncLineTotal = () => {
    const quantity = Number(quantityInput.value);
    const unitPrice = Number(unitPriceInput.value);
    if (
      quantityInput.value !== ""
      && unitPriceInput.value !== ""
      && quantity > 0
      && Number.isFinite(unitPrice)
      && unitPrice >= 0
    ) {
      lineTotalInput.value = String(Math.round(quantity * unitPrice));
    }
    updateReceiptEditorTotal();
  };
  quantityInput.addEventListener("input", syncLineTotal);
  unitPriceInput.addEventListener("input", syncLineTotal);
  lineTotalInput.addEventListener("input", updateReceiptEditorTotal);

  row.append(
    createReceiptEditorField("Nama barang", "item_name", nameInput),
    createReceiptEditorField("Quantity", "quantity", quantityInput),
    createReceiptEditorField("Unit", "unit", unitInput),
    createReceiptEditorField("Harga satuan", "unit_price", unitPriceInput),
    createReceiptEditorField("Total harga barang", "line_total", lineTotalInput),
    removeButton,
  );
  elements.receiptConfirmItems.append(row);
  updateReceiptEditorTotal();
}

function renderReceiptItemEditors(items) {
  elements.receiptConfirmItems.replaceChildren();
  if (items.length === 0) appendReceiptItemEditor();
  else items.forEach((item) => appendReceiptItemEditor(item));
  updateReceiptEditorTotal();
}

function collectReceiptEditorItems() {
  const rows = [...elements.receiptConfirmItems.querySelectorAll("[data-receipt-item-row]")];
  if (rows.length === 0) throw new Error("Tambahkan minimal satu barang dari nota.");
  return rows.map((row, index) => {
    const field = (name) => row.querySelector(`[data-receipt-field="${name}"]`)?.value.trim() || "";
    const itemName = field("item_name");
    if (!itemName) throw new Error(`Nama barang ke-${index + 1} wajib diisi.`);

    const quantityText = field("quantity");
    const quantity = quantityText === "" ? null : Number(quantityText);
    if (quantity !== null && (!Number.isFinite(quantity) || quantity <= 0)) {
      throw new Error(`Quantity barang ke-${index + 1} harus lebih besar dari nol.`);
    }

    const unitPriceText = field("unit_price");
    const unitPrice = unitPriceText === "" ? null : Number(unitPriceText);
    if (unitPrice !== null && (!Number.isFinite(unitPrice) || unitPrice < 0)) {
      throw new Error(`Harga satuan barang ke-${index + 1} tidak valid.`);
    }

    const lineTotal = Number(field("line_total"));
    if (!Number.isFinite(lineTotal) || lineTotal <= 0) {
      throw new Error(`Total harga barang ke-${index + 1} wajib lebih besar dari nol.`);
    }
    return {
      item_name: itemName,
      quantity,
      unit: field("unit") || null,
      unit_price: unitPrice,
      line_total: Math.round(lineTotal),
    };
  });
}

function renderReceiptConfirmation(response) {
  pendingReceipt = response;
  const receipt = response.data.receipt;
  const items = Array.isArray(receipt.items) ? receipt.items : [];

  elements.receiptConfirmMerchant.textContent = receipt.merchant_name || EMPTY_VALUE;
  elements.receiptConfirmDate.value = getLocalReferenceDate();
  elements.receiptConfirmError.textContent = "";
  elements.receiptOcrText.textContent = response.ocr_text || "";
  renderReceiptItemEditors(items);
  showDialog(elements.receiptConfirmDialog);
}

elements.receiptAddItemButton.addEventListener("click", () => appendReceiptItemEditor());

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

elements.receiptConfirmForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!pendingReceipt) {
    elements.receiptConfirmError.textContent = "Hasil nota sudah tidak tersedia. Scan ulang foto nota.";
    return;
  }
  try {
    const previousHistory = [...history];
    const items = collectReceiptEditorItems();
    const itemsTotal = items.reduce((sum, item) => sum + (item.line_total || 0), 0);
    const category = await askCategory({
      summary: transactionSummaryText({
        transaction_type: "expense",
        total_price: itemsTotal,
        merchant_name: pendingReceipt.data.receipt?.merchant_name,
      }),
    });
    const local = createReceiptTransaction(pendingReceipt, {
      date: elements.receiptConfirmDate.value,
      items,
      category,
    });
    const saved = await persistCreatedRecord(local, previousHistory);
    history = saved.history;
    renderResult(saved.record);
    closeDialog(elements.receiptConfirmDialog);
    resetReceiptSelection();
    renderAll();
    setStatus("Nota dikonfirmasi dan disimpan sebagai satu transaksi pengeluaran.", "success");
    showActionPopup("Transaksi nota berhasil disimpan.");
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
  elements.voiceStatus.textContent = "Transkrip sudah diproses. Periksa dialog konfirmasi sebelum transaksi disimpan.";
  setStatus("Periksa dan konfirmasi data transaksi sebelum disimpan.");
  openTransactionConfirmation({
    source: "voice",
    response,
    originalText: response.transcript || "",
    fields: response.data,
  });
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

async function requestClearHistory() {
  if (history.length === 0) return;
  if (!databaseEnabled) {
    setStatus("Database Supabase belum siap. Riwayat tidak dihapus.", "error");
    return;
  }
  const location = "akun Supabase Anda";
  if (!window.confirm(`Hapus seluruh riwayat transaksi pada ${location}?`)) return;
  try {
    await clearTransactionsRemote();
    clearHistory();
    history = [];
    closeDialog(elements.settingsDialog);
    renderAll();
    setStatus(`Riwayat di ${location} telah dihapus.`, "success");
  } catch (error) {
    setStatus(humanizeError(error), "error");
  }
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
  elements.detailCategory.textContent = view.category;
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

function restoreTransactionForm(snapshot = {}, editingId = null) {
  editingTransactionId = editingId;
  elements.manualTransactionForm.reset();
  elements.manualFormError.textContent = "";
  elements.transactionFormTitle.textContent = editingId ? "Edit transaksi" : "Tambah transaksi manual";
  elements.manualTransactionType.value = ["income", "expense"].includes(snapshot.transaction_type)
    ? snapshot.transaction_type
    : "income";
  elements.manualDate.value = snapshot.date || getLocalReferenceDate();
  elements.manualTotalPrice.value = snapshot.total_price ?? "";
  elements.manualItemName.value = snapshot.item_name ?? "";
  elements.manualQuantity.value = snapshot.quantity ?? "";
  elements.manualUnit.value = snapshot.unit ?? "";
  elements.manualNote.value = snapshot.note ?? "";
  const selectedPreset = CATEGORY_PRESETS.includes(snapshot.category)
    ? snapshot.category
    : null;
  manualCategorySelected = selectedPreset;
  elements.manualCategoryCustom.value = snapshot.category && !selectedPreset
    ? String(snapshot.category)
    : "";
  syncManualCategoryPickerSelection();
  showDialog(elements.transactionFormDialog);
}

function openTransactionForm(record = null) {
  restoreTransactionForm(
    {
      transaction_type: record?.transaction_type,
      date: record?.date,
      total_price: record?.total_price ?? "",
      item_name: record?.item_name ?? "",
      quantity: record?.quantity ?? "",
      unit: record?.unit ?? "",
      note: record?.note ?? "",
      category: record?.category ?? null,
    },
    record?.id || null,
  );
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

elements.deleteTransactionButton.addEventListener("click", async () => {
  const record = history.find((transaction) => transaction.id === activeTransactionId);
  if (!record) return;
  if (!window.confirm(`Hapus transaksi ${transactionTitle(record)}?`)) return;
  try {
    if (!databaseEnabled) throw new ApiError("Database Supabase belum siap.", 503);
    await deleteTransactionRemote(record.id);
    history = deleteTransaction(record.id);
    closeTransactionDetail();
    renderAll();
    setStatus("Transaksi telah dihapus dari Supabase.", "success");
    showActionPopup("Transaksi berhasil dihapus.", "delete");
  } catch (error) {
    setStatus(error.message, "error");
  }
});

elements.manualTransactionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const editingId = editingTransactionId;
  const formCategory = categoryFromChoice(
    manualCategorySelected,
    elements.manualCategoryCustom.value,
  );
  const snapshot = {
    transaction_type: elements.manualTransactionType.value,
    date: elements.manualDate.value,
    total_price: elements.manualTotalPrice.value,
    item_name: elements.manualItemName.value.trim(),
    quantity: elements.manualQuantity.value,
    unit: elements.manualUnit.value.trim(),
    note: elements.manualNote.value,
    category: formCategory,
  };
  closeTransactionForm();
  openTransactionConfirmation({
    source: editingId ? "edit" : "manual",
    editingId,
    snapshot,
    fields: snapshot,
    category: formCategory,
  });
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
  elements.categoryFilter,
].forEach((control) => {
  control.addEventListener("change", () => {
    updateFilterFields();
    renderFilteredViews();
  });
});

elements.resetFilterButton.addEventListener("click", () => {
  elements.periodMode.value = "all";
  elements.categoryFilter.value = "";
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

async function initializeDatabaseHistory() {
  try {
    const remoteHistory = await listTransactions();
    databaseEnabled = true;
    history = saveHistory(remoteHistory);
    renderAll();
    setStatus("Riwayat Supabase berhasil dimuat.", "success");
  } catch (error) {
    databaseEnabled = false;
    setStatus(
      error instanceof ApiError
        ? `${error.message} Cache akun hanya dapat dibaca; perubahan dinonaktifkan.`
        : "Supabase belum dapat dijangkau. Cache akun hanya dapat dibaca.",
      "warning",
    );
    renderAll();
  }
}

elements.logoutButton.addEventListener("click", async () => {
  elements.logoutButton.disabled = true;
  try {
    await logoutAccount();
    closeDialog(elements.settingsDialog);
    elements.resultCard.hidden = true;
    showAuthentication();
    setAuthStatus("Anda telah logout.", "success");
  } catch (error) {
    setStatus(error.message || "Logout gagal.", "error");
  } finally {
    elements.logoutButton.disabled = false;
  }
});

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
initializeAuthentication();
