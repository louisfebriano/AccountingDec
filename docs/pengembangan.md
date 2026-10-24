# Pengembangan dan evaluasi

Dokumen ini menjelaskan arsitektur, dataset, training, evaluasi, dan pengujian
CatatKas. Cocok untuk pengembang yang ingin mengubah pipeline atau mereproduksi
hasil penelitian.

## 1. Arsitektur

```text
Teks  → Llama + Soft Prompt Transaksi ┐
Suara → Whisper → koreksi typo Llama  │
      → normalisasi bilangan          ├→ validasi → konfirmasi → PostgreSQL
Foto  → PaddleOCR → Soft Prompt Nota  ┘
```

Prinsip utama:

- **Satu input = satu transaksi.**
- Adapter transaksi dan nota memakai **satu base Llama yang sama**.
- Pemilihan adapter dan `model.generate()` dilindungi lock agar request
  konkuren tidak bertukar adapter.
- Model dimuat *lazy* sebagai singleton. Login, CRUD, dan startup default tidak
  memuat model.
- Arah transaksi ditentukan classifier aturan, bukan model.
- Field yang tidak dapat dilacak ke input diisi `null`, bukan dikarang.

## 2. Peta kode

| Path | Fungsi |
|---|---|
| `src/api.py` | Semua endpoint FastAPI dan penyajian PWA. |
| `src/config.py` | Sumber tunggal konfigurasi dan environment variable. |
| `src/inference.py` | Pipeline Llama transaksi, lazy singleton, dan lock adapter. |
| `src/postprocess.py` | Parsing/validasi JSON dan penelusuran bukti input. |
| `src/transaction_type.py` | Klasifikasi `income`/`expense`/`unknown`. |
| `src/number_utils.py` | Normalisasi bilangan lisan Indonesia. |
| `src/date_utils.py`, `src/price_utils.py` | Utilitas tanggal dan nominal. |
| `src/validation.py` | Validasi konteks transaksi. |
| `src/prompt_utils.py` | Prompt training, inference, dan baseline. |
| `src/train.py`, `src/evaluate.py` | Training dan evaluasi empat konfigurasi. |
| `src/audio_service.py` | Whisper lazy dan transkripsi. |
| `src/voice_normalization.py` | Koreksi typo transkrip dengan Llama base. |
| `src/receipt_service.py` | Praproses gambar dan PaddleOCR lazy. |
| `src/receipt_parser.py` | Kandidat tanggal, total, dan item dari OCR. |
| `src/receipt_schema.py` | Schema ketat Soft Prompt Nota. |
| `src/receipt_inference.py` | Inference adapter nota pada base model bersama. |
| `src/receipt_validation.py` | Validasi silang Llama dan parser nota. |
| `src/prepare_receipt_dataset.py` | OCR gambar → anotasi → JSONL nyata. |
| `src/train_receipt.py`, `src/evaluate_receipt.py` | Training dan evaluasi nota. |
| `src/database.py` | Engine dan connection pool PostgreSQL lazy. |
| `src/auth_service.py` | Supabase Auth dan validasi session server-side. |
| `src/audit_service.py` | Audit log generik dengan metadata JSONB. |
| `src/transaction_schema.py` | Kontrak Pydantic CRUD transaksi. |
| `src/transaction_repository.py` | Query atomik, selalu dibatasi `user_id`. |
| `pwa/` | Frontend PWA tanpa framework atau build step. |
| `sql/` | Schema awal dan migrasi manual yang idempoten. |
| `tests/` | Tes backend `unittest` dan frontend `node:test`. |

## 3. Klasifikasi jenis transaksi

Setiap objek `data` yang berhasil memiliki `transaction_type`:

- `income`: penjualan atau penerimaan pembayaran.
- `expense`: pembelian stok/bahan atau biaya operasional.
- `unknown`: arah transaksi tidak jelas atau saling bertentangan.

`unknown` menghentikan pipeline sebelum Llama dimuat. API mengembalikan
`success: false`, `data: null`, dan pesan agar konteks diperjelas.

Frasa `stok <barang>` dianggap restock, sehingga masuk `expense`. Contoh:

```text
barusan stok telur 10kg 120rb
kmrn stok gas 2 tabung totalnya 90rb
ngisi stok bakso 3 bungkus totalnya 60rb
```

Namun laporan penjualan yang hanya menyebut kondisi stok tetap `income`:

```text
Kemarin jualan laku 150rb, stok tinggal sedikit
Stok habis, semua dagangan laku 300rb
```

Classifier membedakan:

- **Pemasukan umum** — hanya nominal, misalnya `pemasukkan hari ini 3 juta`.
  `item_name`, `quantity`, dan `unit` bernilai `null`.
- **Penjualan barang** — menyebut barang, misalnya `3 bakmi laku terjual 60
  ribu`.

Nilai produksi selalu ditimpa oleh classifier aturan. Adapter tetap dilatih
menghasilkan `transaction_type` agar keluaran mentah dapat dievaluasi, tetapi
tebakan model tidak dipercaya.

## 4. Kontrak enam field transaksi

```json
{
  "item_name": "Bakmi",
  "quantity": 3,
  "unit": null,
  "total_price": 60000,
  "date": "2026-08-21",
  "transaction_type": "income"
}
```

Aturan:

- `item_name`, `quantity`, dan `unit` hanya diisi jika benar-benar disebutkan.
- `total_price` hanya diisi jika nominal disebutkan pada input.
- `date` memakai format `YYYY-MM-DD` dan diselesaikan dengan `reference_date`
  eksplisit.
- Nominal adalah integer rupiah tanpa simbol, desimal tersembunyi, atau nilai
  negatif.
- Ukuran yang merupakan bagian nama produk, seperti `Gas 3kg`, tidak otomatis
  dianggap quantity/unit transaksi.

## 5. Dataset transaksi

Dataset utama berada di `data/processed/*.jsonl`. File penting:

| File | Isi |
|---|---|
| `train.jsonl` | Data training transaksi. |
| `train-augmentation.jsonl` | Contoh generalisasi tambahan (opsional). |
| `validation-six-fields.jsonl` | 24 contoh held-out yang seimbang. |
| `eval-six-fields.jsonl` | 52 input evaluasi dengan ground truth eksplisit. |
| `eval.jsonl` | Dataset evaluasi lama yang dipertahankan. |

`eval-six-fields.jsonl` memakai reference date tetap `2026-08-24`:

- input tanpa tanggal → `2026-08-24`,
- `Tanggal 10 Juli` → `2026-07-10`,
- `kmrn` → `2026-08-23`.

Dataset ini berisi 39 `expense` dan 13 `income`, mencakup pembelian, restock,
penjualan barang, pembayaran pelanggan, dan pemasukan umum.

Evaluator dan training memeriksa overlap teks persis antara train, validation,
dan evaluation. Duplikasi identik dihapus. Validation tidak masuk training
maupun final evaluation.

## 6. Training Soft Prompt transaksi

Konfigurasi default:

```dotenv
TRAIN_REFERENCE_DATE=2026-08-24
TRAIN_VALIDATION_DATA_PATH=data/processed/validation-six-fields.jsonl
TRAIN_REFERENCE_DATE_VARIANTS=4
TRAIN_REFERENCE_DATE_STEP_DAYS=7
TRAIN_VALIDATION_RATIO=0.1
TRAIN_SEED=42
BALANCE_TRANSACTION_TYPES=true
```

Jalankan:

```bash
python -m src.train
```

Adapter dan metadata kontrak tersimpan di
`adapters/soft-prompt-transaksi/`. File `catatkas_contract.json` menyimpan
versi kontrak, base model, JSON schema, format prompt, reference date training,
seed, dan path dataset.

Training menambahkan `train-augmentation.jsonl` bila tersedia. Setiap baris
training harus memiliki `transaction_type` yang valid. Tanggal diselesaikan
ulang terhadap beberapa reference date agar adapter tidak menghafal satu
tanggal evaluasi. Kelas minoritas di-oversample hanya pada split training jika
`BALANCE_TRANSACTION_TYPES=true`.

Jika prompt, schema, atau field wajib berubah, naikkan versi kontrak dan latih
ulang adapter. Evaluator harus gagal dengan jelas jika metadata adapter tidak
cocok.

## 7. Evaluasi empat konfigurasi

Evaluator membandingkan:

1. Llama + Explicit Instruction
2. Llama + Soft Prompt
3. Llama + Explicit Instruction + Post-processing
4. Llama + Soft Prompt + Post-processing

Raw output dari dua lintasan pertama dipakai ulang oleh varian post-processing,
sehingga hanya ada dua inference pass dan dua kali pemuatan model.

Jalankan (PowerShell):

```powershell
python -m src.evaluate --data data/processed/eval-six-fields.jsonl `
  --train-data data/processed/train.jsonl `
  --adapter adapters/soft-prompt-transaksi `
  --reference-date 2026-08-24 `
  --output results/evaluation_report.json
```

Pada bash/macOS/Linux, ganti backtick dengan `\` atau tulis perintah dalam satu
baris.

`--reference-date` wajib agar resolver tanggal tidak bergantung pada jam
komputer. Evaluasi memerlukan akses Llama, dependensi model, adapter, dan GPU
yang sesuai. Jika salah satunya tidak tersedia, proses gagal dengan pesan
ringkas dan tidak membuat angka palsu.

### Metrik

- **JSON validity rate** — objek JSON valid dibagi seluruh data. Varian raw
  memakai `json.loads` atas seluruh keluaran tanpa memperbaiki substring.
- **Precision/recall/F1 micro global** — pasangan `(field, nilai)` non-null
  menjadi unit informasi. Nilai non-null yang salah menambah FP dan FN.
- **Field-level accuracy** — kecocokan tiap field dibagi jumlah data, plus
  overall accuracy dari total field benar dibagi `jumlah data × 6`.

Target null dan prediksi null benar untuk field accuracy, tetapi tidak menambah
TP/FP/FN. Prediksi pada target null menambah FP. Prediksi null atau field hilang
pada target non-null menambah FN. JSON tidak valid membuat keenam field salah.

Laporan menyimpan raw output dua lintasan, TP/FP/FN, contoh kesalahan, audit
overlap, dan catatan metodologi. Evaluator tidak memperbaiki target atau
prediksi.

## 8. Soft Prompt Nota

Adapter nota berada di `adapters/soft-prompt-nota` dan memakai schema berbeda:

```json
{
  "merchant_name": "string atau null",
  "receipt_number": "string atau null",
  "date": "YYYY-MM-DD atau null",
  "items": [
    {
      "item_name": "string",
      "quantity": "number atau null",
      "unit": "string atau null",
      "unit_price": "integer atau null",
      "line_total": "integer atau null"
    }
  ],
  "subtotal": "integer atau null",
  "discount": "integer atau null",
  "tax": "integer atau null",
  "service_charge": "integer atau null",
  "total": "integer atau null",
  "transaction_type": "expense"
}
```

Semua field wajib ada; nilai yang tidak ditemukan harus `null`. Model tidak
menghasilkan confidence. Prompt training dan inference memakai format yang
sama, mempertahankan line break OCR, menyertakan `REFERENCE_DATE` dan
`SOURCE: receipt_ocr`, serta melarang penambahan barang yang tidak ada pada
OCR.

## 9. Dataset nota sintetis

Generator data sintetis dipakai untuk bootstrap eksperimen:

```bash
python -m src.generate_receipt_synthetic_data
```

Default output:

- `data/processed/receipt-train.jsonl` (400 contoh)
- `data/processed/receipt-validation.jsonl` (80 contoh)
- `data/processed/receipt-eval.jsonl` (80 contoh)

Contoh baris:

```json
{"receipt_id":"synthetic-train-00001","template_id":"synthetic-layout-0","data_origin":"synthetic","input":"TOKO BERKAH\nTOTAL 53.000","reference_date":"2026-08-26","output":{"merchant_name":"TOKO BERKAH","receipt_number":null,"date":"2026-08-26","items":[],"subtotal":53000,"discount":0,"tax":0,"service_charge":0,"total":53000,"transaction_type":"expense"}}
```

`data_origin` hanya boleh `synthetic`, `real`, atau `augmented`. Data sintetis
tidak boleh dipakai untuk mengklaim akurasi produksi. Laporkan metrik sintetis
dan nyata secara terpisah.

Split train, validation, dan evaluation memakai layout yang sengaja dipisahkan.
Training menolak overlap teks OCR persis, `receipt_id`, atau `template_id`
antar split. Target dengan field hilang, tipe salah, tanggal tidak valid,
nominal negatif, atau `transaction_type` selain `expense` ditolak sebelum base
model dimuat.

## 10. Menyiapkan dataset nota nyata

Letakkan gambar pada split yang sesuai:

```text
data/processed/image/
├── train/
├── validation/
└── evaluation/
```

Gunakan nota berbeda pada tiap split. Foto lain dari nota yang sama harus tetap
berada pada split yang sama. Isi folder gambar diabaikan Git.

Jalankan OCR dengan reference date eksplisit:

```powershell
python -m src.prepare_receipt_dataset ocr --reference-date 2026-08-31
```

Perintah ini membuat draft JSON per gambar di
`data/processed/receipt-annotations/<split>/`. Draft berisi checksum gambar,
teks OCR mentah, teks OCR bersih, teks ringkas untuk model, diagnosis OCR, dan
output awal parser. Output awal **bukan ground truth**.

Bandingkan draft dengan gambar asli, perbaiki bagian `output`, lalu ubah:

```json
"annotation_status": "verified"
```

Jangan mengubah `receipt_id`, `source_image`, atau `source_sha256`. Perintah OCR
tidak menimpa anotasi yang sudah ada. Opsi `--overwrite` tersedia, tetapi akan
menghapus koreksi manual pada draft tersebut.

Setelah selesai, kompilasi dataset:

```powershell
python -m src.prepare_receipt_dataset build
```

Compiler hanya memasukkan anotasi `verified`, memvalidasi schema, memeriksa
checksum, dan menolak kebocoran antar split. Output ditulis terpisah agar data
sintetis tidak tertimpa:

- `data/processed/receipt-real-train.jsonl`
- `data/processed/receipt-real-validation.jsonl`
- `data/processed/receipt-real-eval.jsonl`

Lakukan koreksi hanya pada file anotasi; JSONL akan dibuat ulang.

## 11. Training dan evaluasi nota

Training penuh:

```bash
python -m src.train_receipt
```

Uji satu forward/backward step tanpa menyimpan adapter:

```bash
python -m src.train_receipt --smoke-test
```

Preset nota memakai 4-bit NF4 double quantization, batch 1, dynamic padding,
gradient checkpointing, BF16 pada GPU yang mendukung, dan accumulation 8.
Contoh yang melebihi batas token ditolak, bukan dipotong diam-diam.

Untuk GPU 6 GB, hentikan API terlebih dahulu. Konfigurasi low-VRAM dapat diubah:

```env
RECEIPT_MAX_SEQ_LENGTH=768
RECEIPT_TRAIN_BATCH_SIZE=1
RECEIPT_GRADIENT_ACCUMULATION_STEPS=8
RECEIPT_MIN_FREE_GPU_GB=4.5
```

Jika allocator CUDA terfragmentasi:

```powershell
$env:PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
python -m src.train_receipt
```

Preflight training menampilkan VRAM bebas dan berhenti jika kurang dari batas
minimum. Hasil hanya disimpan ke `adapters/soft-prompt-nota`; adapter transaksi
tidak ditimpa.

Evaluasi dengan adapter:

```powershell
python -m src.evaluate_receipt `
  --data data/processed/receipt-eval.jsonl `
  --output results/receipt-evaluation-report.json
```

Evaluasi file prediksi tanpa memuat model:

```powershell
python -m src.evaluate_receipt `
  --data data/processed/receipt-eval.jsonl `
  --predictions results/receipt-predictions.jsonl `
  --output results/receipt-evaluation-report.json
```

Setiap prediksi berisi `{"raw_output":"...JSON model..."}` atau
`{"output":{...}}`. Evaluator melaporkan JSON validity, field accuracy,
merchant/date/total accuracy, precision/recall/F1 nama item, accuracy
quantity/unit/unit-price/line-total, dan exact transaction match. JSON rusak
dihitung gagal; evaluator tidak memperbaiki prediksi.

## 12. Aktivasi dan fallback Scan Nota

`RECEIPT_LLM_ENABLED=true` membuat setiap teks OCR mencoba Soft Prompt Nota.
Adapter divalidasi terhadap base model, schema, format prompt, dan contract
version sebelum digunakan.

Karena adapter nota belum disertakan, default
`RECEIPT_RULE_FALLBACK_ENABLED=true` mempertahankan endpoint dengan respons
`extraction_method: rule_based_fallback` dan warning eksplisit. Fallback tidak
pernah diberi label sebagai hasil Llama. Set fallback ke `false` untuk
memperoleh HTTP `503` sampai adapter yang valid tersedia.

## 13. Pengujian

Backend:

```bash
python -m unittest discover -s tests -v
```

Tes tertentu:

```bash
python -m unittest tests.test_transaction_type -v
python -m unittest tests.test_evaluate -v
python -m unittest tests.test_receipt_evaluate -v
```

Frontend:

```bash
npm run test:frontend
```

Tes memakai mock untuk Whisper, Llama, PaddleOCR, `fetch`, `MediaRecorder`,
media stream, Supabase Auth, database, dan Web Storage. Tidak diperlukan
mikrofon, model, internet, atau GPU.

Tes frontend mencakup gerbang login/register, request session, cache terpisah
per pengguna, CRUD manual, transkrip suara, Scan Nota, privasi storage, filter
periode, detail transaksi, dan agregasi grafik.

## 14. Konvensi kontrak dan data

- Prompt, schema, dan field wajib harus konsisten antara training, inference,
  API, dan evaluator.
- Perubahan kontrak menaikkan versi dan mewajibkan training ulang.
- Jangan mengubah `receipt_id`, `source_image`, atau `source_sha256`.
- Cegah kebocoran data antar split.
- Jangan commit artefak training/evaluasi kecuali diminta.
- Adapter default: `adapters/soft-prompt-transaksi` dan
  `adapters/soft-prompt-nota`; jangan saling menimpa.

## 15. Batasan penelitian

- Satu rekaman, satu teks, dan satu foto hanya menghasilkan satu transaksi.
- Belum ada multi-transaksi dalam satu input.
- PWA tidak menjalankan inferensi offline.
- Normalisasi bilangan belum mencakup desimal lisan seperti “dua koma lima”.
- Kata `bayar`, `transfer`, `masuk`, dan `keluar` memerlukan konteks yang jelas.
- Modal, pinjaman, pengembalian dana, dan multi-transaksi belum diklasifikasikan
  otomatis bila arahnya tidak jelas.
- Koreksi typo Llama bersifat best-effort; pengguna tetap harus memeriksa hasil.
- OCR fokus pada nota cetak; nota tulisan tangan atau buram dapat gagal.
- Item dan nominal bersifat best-effort; field ambigu dibiarkan `null` dengan
  warning.
- Adapter Soft Prompt Nota belum tersedia secara default.
- Kesalahan OCR dapat merambat ke Llama; validasi silang dan konfirmasi
  mengurangi risiko, tetapi tidak menjamin hasil selalu benar.
