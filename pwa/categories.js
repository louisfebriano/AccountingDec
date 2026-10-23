export const CATEGORY_MAX_LENGTH = 50;
export const UNCATEGORIZED = "Belum dikategorikan";

// Preset kategori UMKM: pemasukan dahulu, lalu pengeluaran. Nilai teks bebas
// tetap diterima, hanya dicocokkan tanpa memperhatikan huruf besar/kecil agar
// pilihan pengguna tidak terpecah menjadi kategori yang berbeda-beda.
export const CATEGORY_PRESETS = Object.freeze([
  UNCATEGORIZED,
  "Penjualan",
  "Jasa",
  "Pendapatan lain",
  "Modal usaha",
  "Bahan baku",
  "Operasional",
  "Gaji karyawan",
  "Sewa",
  "Listrik & air",
  "Transportasi",
  "Perawatan alat",
  "Pajak",
  "Lainnya",
]);

export function normalizeCategory(value) {
  const text = String(value ?? "").trim().slice(0, CATEGORY_MAX_LENGTH);
  if (!text) return null;
  const preset = CATEGORY_PRESETS.find(
    (candidate) => candidate.toLowerCase() === text.toLowerCase(),
  );
  return preset || text;
}

export function categoryLabel(value) {
  const text = String(value ?? "").trim();
  return text || UNCATEGORIZED;
}

// Logo emoji tiap preset agar kategori mudah dibedakan secara visual pada
// chip pemilih, dropdown filter, ringkasan, dan label detail/riwayat.
export const CATEGORY_ICONS = Object.freeze({
  [UNCATEGORIZED]: "🏷️",
  "Penjualan": "🛒",
  "Jasa": "🤝",
  "Pendapatan lain": "💸",
  "Modal usaha": "💼",
  "Bahan baku": "📦",
  "Operasional": "⚙️",
  "Gaji karyawan": "👥",
  "Sewa": "🏢",
  "Listrik & air": "💡",
  "Transportasi": "🚚",
  "Perawatan alat": "🔧",
  "Pajak": "🧾",
  "Lainnya": "📌",
});

// Logo preset untuk sebuah kategori. Kategori kustom tidak memiliki logo dan
// mengembalikan string kosong agar layar tidak menampilkan prefix aneh.
export function categoryIcon(value) {
  const normalized = normalizeCategory(value) ?? categoryLabel(value);
  return CATEGORY_ICONS[normalized] ?? "";
}

// Label tampilan "logo + nama" untuk area yang hanya bersifat presentasi.
// Nilai yang disimpan ke database tetap nama polos, bukan string ber-emoji.
export function categoryPresentation(value) {
  const label = categoryLabel(value);
  const icon = categoryIcon(value);
  return icon ? `${icon} ${label}` : label;
}

// Nilai yang dikirim ke backend dari pilihan popup kategori: input kustom
// memenangkan chip preset, keduanya kosong menghasilkan null (dihitung sebagai
// pilihan "Lewati" oleh pemanggil).
export function categoryFromChoice(selected, custom) {
  const customValue = normalizeCategory(custom);
  if (customValue) return customValue;
  return normalizeCategory(selected);
}
