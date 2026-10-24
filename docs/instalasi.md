# Instalasi dan konfigurasi

Panduan ini menjelaskan cara menyiapkan CatatKas dari nol, menghubungkannya ke
Supabase, dan mengatasi masalah yang paling sering muncul.

## 1. Prasyarat

- **Python 3.11**.
- **Akun Hugging Face** yang sudah mendapatkan akses ke
  [meta-llama/Llama-3.2-3B-Instruct](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct).
- **Proyek Supabase** dengan provider Email aktif.
- **GPU** sangat disarankan. Tanpa GPU, Llama tetap bisa berjalan di CPU tetapi
  sangat lambat.
- **Node.js 20+** hanya diperlukan untuk menjalankan tes frontend.

## 2. Menyiapkan Python

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### macOS / Linux

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Versi NumPy, OpenCV, Albumentations, PaddleOCR, dan PaddlePaddle dikunci pada
kombinasi yang menyediakan wheel Windows untuk Python 3.11. Ini menghindari
proses kompilasi yang membutuhkan Microsoft C++ Build Tools.

Untuk memeriksa apakah PyTorch mendeteksi GPU:

```bash
python -c "import torch; print(torch.cuda.is_available())"
```

## 3. Mengatur akses Hugging Face

Llama adalah model *gated*, sehingga token Hugging Face wajib diisi.

1. Buka halaman model di Hugging Face dan setujui ketentuan aksesnya.
2. Buat token di **Settings → Access Tokens**.
3. Isi `HF_TOKEN` pada `.env`, atau login melalui terminal:

```bash
huggingface-cli login
```

Jangan pernah commit token ke Git.

## 4. Menyiapkan Supabase

### Membuat proyek

1. Buat proyek baru di [Supabase](https://supabase.com/).
2. Buka **SQL Editor**.
3. Jalankan seluruh isi [`sql/supabase_schema.sql`](../sql/supabase_schema.sql).
4. Buka **Authentication → Sign In / Providers**, lalu pastikan provider
   **Email** aktif.

### Mengambil kredensial

Buka menu **Connect** pada dashboard Supabase.

- Tab **Direct** menyediakan connection string PostgreSQL untuk `DATABASE_URL`.
- Tab **Framework** menyediakan Project URL dan Publishable Key. Masukkan ke
  `SUPABASE_URL` dan `SUPABASE_PUBLISHABLE_KEY`.

Jika dashboard menampilkan nama `NEXT_PUBLIC_SUPABASE_URL` dan
`NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, salin nilainya ke nama tanpa prefix
`NEXT_PUBLIC_`. Kedua nama bawaan Next.js juga masih diterima sebagai fallback.

Publishable Key bukan password database, tetapi tetap hanya dipakai di backend.

### Memilih mode koneksi

| Mode | Kapan dipakai | Nilai `.env` |
|---|---|---|
| Direct connection | Server berjalan terus dan jaringan mendukung IPv6. | `DATABASE_POOL_MODE=session` |
| Supavisor session mode | Jaringan lokal tidak mendukung IPv6. | `DATABASE_POOL_MODE=session` |
| Transaction pooler | Connection string memakai port `6543`. | `DATABASE_POOL_MODE=transaction` |

Pada mode transaksi, CatatKas otomatis memakai `NullPool` dan mematikan
prepared statement pada driver.

Karakter khusus pada password connection string harus di-*percent-encode*
(misalnya `@` menjadi `%40`).

### Migrasi untuk database lama

Database baru cukup memakai `sql/supabase_schema.sql`. Jika database sudah
berisi tabel CatatKas versi sebelumnya, jalankan migrasi berikut melalui
**SQL Editor** sesuai kebutuhan:

| File | Kegunaan |
|---|---|
| [`sql/supabase_auth_audit_migration.sql`](../sql/supabase_auth_audit_migration.sql) | Menambahkan `transactions.user_id` dan tabel `audit_logs`. |
| [`sql/add_transaction_category.sql`](../sql/add_transaction_category.sql) | Menambahkan kolom kategori transaksi. |
| [`sql/alter_users_name_to_text.sql`](../sql/alter_users_name_to_text.sql) | Mengubah kolom `name` pada tabel profil menjadi `text`. |
| [`sql/fix_receipt_relationships.sql`](../sql/fix_receipt_relationships.sql) | Memperbaiki relasi tabel nota lama. |

Migrasi bersifat aditif dan idempoten. Data transaksi lama tidak otomatis
diberikan kepada akun tertentu. Setelah akun terdaftar, isi `user_id` data lama
dengan UUID yang benar dari **Authentication → Users**, lalu ubah kolom tersebut
menjadi `NOT NULL` mengikuti petunjuk di file migrasi.

## 5. Mengisi `.env`

Salin contoh konfigurasi:

```powershell
Copy-Item .env.example .env
```

Nilai minimum yang wajib diisi:

```dotenv
HF_TOKEN=token_huggingface_anda
DATABASE_URL=postgresql://postgres.PROJECT_REF:PASSWORD@HOST:5432/postgres
DATABASE_POOL_MODE=session
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_xxx
AUTH_COOKIE_SECURE=false
MODEL_WARMUP_ON_STARTUP=false
```

`.env.example` memuat semua opsi lain. Beberapa kelompok penting:

### Database dan autentikasi

| Variabel | Default | Keterangan |
|---|---|---|
| `DATABASE_URL` | — | Connection string PostgreSQL Supabase. |
| `DATABASE_POOL_MODE` | `session` | Gunakan `transaction` untuk port `6543`. |
| `DATABASE_POOL_SIZE` | `5` | Jumlah koneksi pada pool. |
| `DATABASE_MAX_OVERFLOW` | `5` | Koneksi tambahan saat pool penuh. |
| `DATABASE_CONNECT_TIMEOUT_SECONDS` | `10` | Batas waktu koneksi. |
| `SUPABASE_URL` | — | Project URL Supabase. |
| `SUPABASE_PUBLISHABLE_KEY` | — | Publishable/anon key dari dashboard. |
| `AUTH_COOKIE_SECURE` | `false` | Wajib `true` untuk HTTPS. |
| `AUTH_COOKIE_SAMESITE` | `lax` | Kebijakan cookie session. |
| `AUDIT_LOG_ENABLED` | `true` | Menulis audit log ke `audit_logs`. |
| `MODEL_WARMUP_ON_STARTUP` | `false` | `true` memuat Llama saat server mulai. |

> `.env.example` saat ini memuat `MODEL_WARMUP_ON_STARTUP=true`. Untuk setup
> awal, ubah menjadi `false` agar layar login dapat dibuka tanpa mengalokasikan
> GPU. Aktifkan `true` hanya jika server memang siap memuat model sejak awal.

Nama tabel juga dapat diubah melalui `DATABASE_TRANSACTIONS_TABLE`,
`DATABASE_RECEIPTS_TABLE`, `DATABASE_RECEIPT_ITEMS_TABLE`, dan
`DATABASE_AUDIT_LOGS_TABLE`.

### Suara

| Variabel | Default | Keterangan |
|---|---|---|
| `WHISPER_MODEL_SIZE` | `small` | Ukuran model Whisper. |
| `WHISPER_DEVICE` | `cpu` | Perangkat untuk Whisper. |
| `WHISPER_COMPUTE_TYPE` | `int8` | Komputasi hemat memori. |
| `WHISPER_LANGUAGE` | `id` | Bahasa transkripsi. |
| `WHISPER_VAD_FILTER` | `true` | Mengabaikan bagian audio tanpa suara. |
| `AUDIO_MAX_SIZE_MB` | `10` | Batas ukuran file audio. |
| `VOICE_LLM_NORMALIZATION_ENABLED` | `true` | Koreksi typo transkrip dengan Llama base. |

Whisper tidak dilatih ulang. Model diunduh saat endpoint suara pertama kali
dipakai, lalu di-cache selama proses API hidup. Secara default Whisper berjalan
di CPU agar tidak berebut VRAM dengan Llama.

### Scan Nota

| Variabel | Default | Keterangan |
|---|---|---|
| `RECEIPT_MAX_SIZE_MB` | `10` | Batas ukuran foto nota. |
| `RECEIPT_OCR_LANGUAGE` | `id` | Bahasa OCR. |
| `RECEIPT_MIN_CONFIDENCE` | `0.50` | Ambang confidence OCR. |
| `RECEIPT_MAX_IMAGE_DIMENSION` | `2400` | Batas dimensi gambar. |
| `RECEIPT_OCR_TARGET_LONG_EDGE` | `2000` | Ukuran sisi panjang hasil praproses. |
| `RECEIPT_OCR_MULTIPASS` | `true` | Mencoba beberapa varian gambar. |
| `RECEIPT_OCR_COMPACT_FOR_MODEL` | `true` | Mengirim ringkasan OCR ke model. |
| `RECEIPT_LLM_ENABLED` | `true` | Mengaktifkan Soft Prompt Nota. |
| `RECEIPT_RULE_FALLBACK_ENABLED` | `true` | Memakai fallback aturan jika adapter nota belum ada. |
| `RECEIPT_ADAPTER_OUTPUT_DIR` | `adapters/soft-prompt-nota` | Lokasi adapter nota. |

PaddleOCR juga tidak dilatih ulang. Model diunduh pada penggunaan pertama dan
berjalan di CPU (`use_gpu=False`).

### Training

| Variabel | Default | Keterangan |
|---|---|---|
| `TRAIN_REFERENCE_DATE` | `2026-08-24` | Tanggal acuan untuk melatih tanggal relatif. |
| `TRAIN_VALIDATION_DATA_PATH` | `data/processed/validation-six-fields.jsonl` | Data validasi. |
| `TRAIN_REFERENCE_DATE_VARIANTS` | `4` | Variasi reference date saat training. |
| `TRAIN_REFERENCE_DATE_STEP_DAYS` | `7` | Jarak antar variasi tanggal. |
| `TRAIN_VALIDATION_RATIO` | `0.1` | Rasio split validasi fallback. |
| `TRAIN_SEED` | `42` | Seed training. |
| `BALANCE_TRANSACTION_TYPES` | `true` | Menyeimbangkan kelas pada data training. |
| `RECEIPT_MAX_SEQ_LENGTH` | `768` | Batas token training nota. |
| `RECEIPT_TRAIN_BATCH_SIZE` | `1` | Batch size nota untuk GPU kecil. |
| `RECEIPT_GRADIENT_ACCUMULATION_STEPS` | `8` | Akumulasi gradien. |
| `RECEIPT_MIN_FREE_GPU_GB` | `4.5` | Batas minimum VRAM bebas sebelum training. |

## 6. Menjalankan aplikasi

```bash
uvicorn src.api:app --reload --port 8000
```

Buka <http://localhost:8000/>. FastAPI menyajikan API dan PWA dari origin yang
sama.

Periksa kesehatan layanan:

```bash
curl http://localhost:8000/health/database
curl http://localhost:8000/health/auth
```

- `503` berarti konfigurasi belum lengkap atau layanan tidak dapat dijangkau.
- `500` dengan pesan schema berarti struktur tabel belum sesuai.

Koneksi database dibuat secara *lazy* dan di-cache. Login dan CRUD tidak memuat
model Llama/Whisper. Dengan `MODEL_WARMUP_ON_STARTUP=false`, model baru dimuat
saat ekstraksi pertama.

## 7. Mengakses dari HP

Jalankan server agar dapat dijangkau dari jaringan lokal:

```bash
uvicorn src.api:app --host 0.0.0.0 --port 8000
```

Buka alamat IP komputer dan port tersebut dari ponsel pada jaringan yang sama.

Form teks dapat dipakai lewat HTTP lokal, tetapi mikrofon dan service worker
umumnya membutuhkan **HTTPS**. `localhost` dianggap *secure context*, sedangkan
alamat IP lokal melalui HTTP belum tentu. Untuk menguji suara di ponsel,
gunakan deployment HTTPS atau reverse proxy HTTPS yang dipercaya perangkat.

## 8. Troubleshooting

### Model Llama gagal diunduh

Pastikan `HF_TOKEN` valid dan akun sudah mendapat akses ke repositori model.
Jalankan ulang `huggingface-cli login` bila perlu.

### Database tidak bisa dihubungkan

- Pastikan password pada `DATABASE_URL` sudah di-*percent-encode*.
- Jika jaringan tidak mendukung IPv6, gunakan **Supavisor session mode**.
- Jika memakai port `6543`, set `DATABASE_POOL_MODE=transaction`.
- Cek `/health/database` untuk melihat apakah masalahnya konfigurasi atau
  schema.

### Error foreign key `receipt_items_id_fkey`

Jalankan [`sql/fix_receipt_relationships.sql`](../sql/fix_receipt_relationships.sql).
Migrasi akan memeriksa data orphan terlebih dahulu dan membatalkan proses bila
relasi lama belum valid.

### GPU kehabisan memori saat training

Hentikan Uvicorn terlebih dahulu. Gunakan preset low-VRAM, lalu bila perlu:

```powershell
$env:PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
python -m src.train_receipt
```

### PaddleOCR atau Whisper mengunduh model terus

Unduhan pertama memang membutuhkan internet. Setelah berhasil, model disimpan
di cache lokal. Pastikan folder cache tidak dihapus dan proses memiliki izin
tulis.

### PWA menampilkan versi lama

Buka DevTools → **Application** → **Service Workers → Unregister**, lalu
**Storage → Clear site data**, dan muat ulang halaman.

### Mikrofon tidak muncul di HP

Akses mikrofon memerlukan HTTPS. Gunakan deployment HTTPS atau tunnel HTTPS,
bukan alamat IP HTTP biasa.

## 9. Catatan keamanan

- Jangan commit `.env`, token, kredensial database, foto nota, atau output model.
- Gunakan `AUTH_COOKIE_SECURE=true` untuk semua deployment HTTPS.
- Password database, access token, refresh token, dan `DATABASE_URL` tidak
  pernah dikirim ke JavaScript.
- Audit log tidak menyimpan password, token, audio/foto biner, temporary path,
  atau raw output model.
