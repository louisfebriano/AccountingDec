# CatatKas

**Pencatat transaksi UMKM yang bisa menerima teks, suara, dan foto nota.**

CatatKas mengubah satu kalimat, satu rekaman suara, atau satu foto nota menjadi
transaksi yang rapi. Hasil ekstraksi selalu ditampilkan lebih dulu untuk
diperiksa dan diedit sebelum disimpan ke database.

Dikembangkan oleh **Louis Febriano** dengan Python, FastAPI, PostgreSQL
Supabase, dan Llama 3.2 3B-Instruct.

## Fitur utama

- **Catat lewat teks** — tulis transaksi seperti biasa, misalnya
  `kemarin beli gas 3kg 2 tabung total 180rb`.
- **Catat lewat suara** — rekam ucapan, lalu transkrip dan angkanya dirapikan
  otomatis.
- **Scan nota** — foto nota cetak, lalu rincian barang dibaca dengan OCR dan
  ditampilkan untuk dikonfirmasi.
- **Tambah manual** — isi transaksi tanpa memanggil model AI.
- **Kategori UMKM** — kelompokkan transaksi sebagai bahan baku, operasional,
  penjualan, dan lain-lain.
- **Riwayat dan laporan** — cari, edit, hapus, filter periode/kategori, serta
  lihat ringkasan dan grafik tujuh hari.
- **PWA** — bisa dipasang di layar utama HP dan tetap bisa membuka riwayat
  terakhir saat offline.
- **Multi-akun** — setiap pengguna hanya dapat melihat datanya sendiri.

## Cara kerja singkat

```text
Teks   ─────────────────────────────┐
Suara  → Whisper → koreksi angka   ─┼→ validasi → konfirmasi → PostgreSQL
Foto   → OCR → Soft Prompt Nota    ─┘
```

Semua input melewati aturan **satu input = satu transaksi**. Satu foto nota
menghasilkan satu transaksi induk; barang-barangnya disimpan sebagai rincian
nota, bukan transaksi terpisah.

## Mulai cepat

### Yang perlu disiapkan

| Kebutuhan | Keterangan |
|---|---|
| Python 3.11 | Versi lain mungkin belum didukung oleh semua dependensi. |
| Akun Hugging Face | Untuk mengunduh Llama 3.2 3B-Instruct yang aksesnya dibatasi (gated). |
| Proyek Supabase | Untuk database PostgreSQL dan login email/password. |
| GPU (opsional) | CPU bisa dipakai, tetapi inferensi akan terasa jauh lebih lambat. |
| Node.js 20+ (opsional) | Hanya diperlukan untuk menjalankan tes frontend. |

### 1. Siapkan proyek

```powershell
git clone <URL_REPOSITORY>
cd skripsi
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Pengguna macOS/Linux dapat mengaktifkan virtual environment dengan
`source .venv/bin/activate`.

### 2. Siapkan file `.env`

```powershell
Copy-Item .env.example .env
```

Buka `.env`, lalu isi minimal nilai berikut:

```dotenv
HF_TOKEN=token_huggingface_anda
DATABASE_URL=postgresql://postgres.PROJECT_REF:PASSWORD@HOST:5432/postgres
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_xxx
MODEL_WARMUP_ON_STARTUP=false
```

Jangan pernah commit file `.env`. Untuk pengembangan lokal, biarkan
`AUTH_COOKIE_SECURE=false`; ubah menjadi `true` jika aplikasi diakses lewat
HTTPS.

### 3. Siapkan database

1. Buat proyek baru di [Supabase](https://supabase.com/).
2. Buka **SQL Editor**, lalu jalankan isi
   [`sql/supabase_schema.sql`](sql/supabase_schema.sql).
3. Aktifkan login email di **Authentication → Sign In / Providers → Email**.
4. Ambil connection string dan API key dari menu **Connect** di dashboard
   Supabase, lalu masukkan ke `.env`.

Sudah punya database CatatKas versi lama? Jalankan migrasi yang sesuai dari
folder [`sql/`](sql/) — lihat [panduan instalasi](docs/instalasi.md).

### 4. Jalankan aplikasi

```powershell
uvicorn src.api:app --reload --port 8000
```

Buka <http://localhost:8000/>. Daftar akun, login, lalu coba catat transaksi
pertama.

> Saat pertama kali dipakai, model Llama, Whisper, dan PaddleOCR akan diunduh.
> Proses ini membutuhkan internet dan bisa memakan waktu beberapa menit.
> Request pertama juga akan lebih lambat karena model harus dimuat ke memori.

### 5. Pastikan layanan siap

```powershell
curl http://localhost:8000/health/database
curl http://localhost:8000/health/auth
```

Kedua endpoint harus mengembalikan status siap. Jika muncul `503`, periksa
kembali isi `.env` dan koneksi Supabase.

## Perintah yang sering dipakai

| Perintah | Fungsi |
|---|---|
| `uvicorn src.api:app --reload --port 8000` | Menjalankan API dan PWA. |
| `python -m unittest discover -s tests -v` | Menjalankan seluruh tes backend. |
| `npm run test:frontend` | Menjalankan tes frontend (tanpa install package tambahan). |
| `python -m src.train` | Melatih ulang Soft Prompt transaksi. |
| `python -m src.train_receipt --smoke-test` | Uji satu langkah training nota tanpa menyimpan adapter. |
| `python -m src.train_receipt` | Melatih Soft Prompt nota. |

Hentikan server sebelum training jika GPU hanya 6 GB. Training dan server tidak
bisa berbagi satu salinan base model.

## Dokumentasi

| Dokumen | Isi |
|---|---|
| [Panduan penggunaan](docs/penggunaan.md) | Cara memakai teks, suara, Scan Nota, kategori, riwayat, dan PWA. |
| [Instalasi dan konfigurasi](docs/instalasi.md) | Setup Supabase, daftar environment variable, akses dari HP, dan troubleshooting. |
| [Pengembangan dan evaluasi](docs/pengembangan.md) | Arsitektur kode, dataset, training, evaluasi, dan pengujian. |
| [API](docs/api.md) | Endpoint, contoh request/response, dan kode error. |

## Struktur proyek

```text
src/       Backend FastAPI, pipeline AI, OCR, database, dan autentikasi
pwa/       Frontend PWA tanpa framework atau proses build
sql/       Schema awal dan migrasi Supabase
docs/      Panduan penggunaan, instalasi, pengembangan, dan API
tests/     Tes backend (unittest) dan frontend (node:test)
data/      Dataset JSONL, anotasi, dan gambar nota
adapters/  Hasil training Soft Prompt (tidak di-commit)
```

## Batasan penting

- Satu input hanya boleh berisi **satu transaksi**.
- PWA tidak menjalankan AI secara offline; backend tetap harus dapat diakses.
- Scan Nota saat ini fokus pada **nota cetak** berbahasa Indonesia. Nota tulisan
  tangan, buram, atau terpotong bisa gagal dibaca.
- Ekstraksi item dan nominal bersifat *best-effort*. Selalu periksa dialog
  konfirmasi sebelum menyimpan.
- Adapter Soft Prompt Nota belum disertakan. Tanpa adapter, Scan Nota memakai
  fallback berbasis aturan yang ditandai jelas pada respons.
- Belum tersedia reset password dari UI, MFA, role admin, atau sinkronisasi
  offline.

## Keamanan dan privasi

- Password database, token, dan session tidak pernah dikirim ke JavaScript.
- Setiap query transaksi dibatasi oleh `user_id` dari session server.
- Foto dan audio tidak disimpan permanen; file sementara selalu dihapus.
- Teks OCR tidak menjadi data transaksi. Audit log hanya menyimpan salinan
  terbatas untuk keperluan audit.
- Output mentah model tidak dikirim ke database.
- `localStorage` hanya cache tampilan maksimal 50 transaksi per akun.

## Lisensi

Repositori ini dibuat untuk keperluan skripsi. Belum ada lisensi open source
yang dinyatakan secara eksplisit.
