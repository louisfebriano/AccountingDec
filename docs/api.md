# API

CatatKas memakai FastAPI. Dokumentasi interaktif tersedia di
<http://localhost:8000/docs> saat server berjalan.

Endpoint ekstraksi dan transaksi memerlukan login. Register dan login dapat
diakses tanpa session; health dan halaman PWA juga terbuka. Endpoint seperti
`/auth/me` memerlukan session aktif. Session disimpan pada cookie `HttpOnly`
first-party; token tidak pernah dikirim ke JavaScript.

## Autentikasi

| Method | Path | Fungsi |
|---|---|---|
| `POST` | `/auth/register` | Mendaftarkan akun baru. |
| `POST` | `/auth/login` | Masuk dan membuat session. |
| `POST` | `/auth/refresh` | Memperbarui session. |
| `GET` | `/auth/me` | Mengambil profil pengguna aktif. |
| `POST` | `/auth/logout` | Menghapus session. |

Body register/login:

```json
{
  "email": "pengguna@example.com",
  "password": "password-yang-kuat"
}
```

Contoh:

```bash
curl -i -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"pengguna@example.com","password":"rahasia"}'
```

Gunakan cookie jar agar cookie session ikut dikirim pada request berikutnya:

```bash
curl -c cookies.txt -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"pengguna@example.com","password":"rahasia"}'

curl -b cookies.txt http://localhost:8000/auth/me
```

## Transaksi

| Method | Path | Fungsi |
|---|---|---|
| `GET` | `/transactions` | Daftar transaksi milik pengguna aktif. |
| `GET` | `/transactions/{id}` | Detail satu transaksi. |
| `POST` | `/transactions` | Menyimpan satu transaksi terkonfirmasi. |
| `POST` | `/transactions/import` | Impor eksplisit maksimal 50 record. |
| `PUT` | `/transactions/{id}` | Mengedit transaksi. |
| `DELETE` | `/transactions/{id}` | Menghapus satu transaksi. |
| `DELETE` | `/transactions` | Menghapus seluruh transaksi pengguna. |

Semua query dibatasi `WHERE user_id = <user aktif>`. `user_id` diambil dari
session server, bukan dari body request.

Contoh menyimpan transaksi:

```bash
curl -b cookies.txt -X POST http://localhost:8000/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "source": "text",
    "transaction_type": "expense",
    "item_name": "Gas 3kg",
    "quantity": 2,
    "unit": "tabung",
    "total_price": 180000,
    "date": "2026-08-21",
    "category": "Bahan baku"
  }'
```

Untuk transaksi nota, `source` harus `receipt`, `transaction_type` harus
`expense`, dan objek `receipt` wajib berisi daftar `items`. Transaksi non-nota
tidak boleh mengirim objek `receipt`.

## Ekstraksi teks

```bash
curl -b cookies.txt -X POST http://localhost:8000/extract \
  -H "Content-Type: application/json" \
  -d '{"text":"Kemarin beli Gas 3kg sebanyak 10 tabung, totalnya 180rb"}'
```

Respons berhasil:

```json
{
  "success": true,
  "source": "text",
  "data": {
    "item_name": "Gas 3kg",
    "quantity": 10,
    "unit": "tabung",
    "total_price": 180000,
    "date": "2026-08-20",
    "transaction_type": "expense"
  },
  "error": null,
  "out_of_context": false
}
```

Jika arah transaksi tidak jelas:

```json
{
  "success": false,
  "input": "Transfer 500rb",
  "data": null,
  "error": "Jenis transaksi tidak dapat ditentukan. Gunakan konteks pemasukan atau pengeluaran yang lebih jelas.",
  "raw_output": null,
  "out_of_context": false
}
```

## Ekstraksi suara

Field multipart:

- `file` — file audio.
- `reference_date` — opsional, format `YYYY-MM-DD`.

```bash
curl -b cookies.txt -X POST http://localhost:8000/extract/audio \
  -F "file=@contoh_transaksi.wav" \
  -F "reference_date=2026-08-21"
```

Format minimum: WAV, MP3, M4A, WEBM, dan OGG. Ukuran maksimal default 10 MB.
File disimpan dengan nama acak di lokasi sementara dan selalu dihapus setelah
diproses.

Contoh respons:

```json
{
  "success": true,
  "source": "voice",
  "transcript": "Kemarin beli tepung terigu dua karung total dua ratus lima puluh ribu",
  "normalized_text": "Kemarin beli tepung terigu 2 karung total 250000",
  "data": {
    "item_name": "Tepung terigu",
    "quantity": 2,
    "unit": "karung",
    "total_price": 250000,
    "date": "2026-08-20",
    "transaction_type": "expense"
  },
  "error": null,
  "out_of_context": false
}
```

Jika tidak ada ucapan yang dikenali (`HTTP 422`):

```json
{
  "detail": "Tidak ditemukan ucapan yang dapat dikenali pada audio"
}
```

## Scan Nota

Field multipart:

- `file` — foto nota JPEG, PNG, atau WebP.
- `reference_date` — opsional, format `YYYY-MM-DD`.

```bash
curl -b cookies.txt -X POST http://localhost:8000/extract/receipt \
  -F "file=@contoh_nota.jpg" \
  -F "reference_date=2026-08-26"
```

Contoh respons:

```json
{
  "success": true,
  "source": "receipt",
  "requires_confirmation": true,
  "data": {
    "item_name": null,
    "quantity": null,
    "unit": null,
    "total_price": 180000,
    "date": "2026-08-26",
    "transaction_type": "expense",
    "receipt": {
      "merchant_name": "Toko Makmur",
      "total": 180000,
      "items": [
        {
          "item_name": "Beras",
          "quantity": 2,
          "unit": "kg",
          "unit_price": 15000,
          "line_total": 30000
        }
      ],
      "warnings": []
    }
  },
  "ocr_text": "teks OCR lengkap untuk konfirmasi dan audit",
  "ocr_model_text": "teks OCR ringkas berisi barang, harga, dan total untuk model",
  "extraction_method": "llama_soft_prompt_receipt",
  "validation": {
    "status": "valid",
    "warnings": []
  },
  "error": null
}
```

Foto asli dan raw output model tidak pernah dikembalikan. Teks OCR tidak
disimpan sebagai data transaksi atau cache lokal, tetapi salinan terbatas
(maksimal 20.000 karakter) dapat tercatat pada audit log.

## Health check

| Method | Path | Fungsi |
|---|---|---|
| `GET` | `/health` | Status API. |
| `GET` | `/health/database` | Status koneksi dan schema database. |
| `GET` | `/health/auth` | Status konfigurasi Supabase Auth. |

```bash
curl http://localhost:8000/health/database
curl http://localhost:8000/health/auth
```

Status `503` berarti konfigurasi belum lengkap atau layanan tidak dapat
dijangkau. Status `500` dengan pesan schema berarti struktur tabel belum sesuai.

## Kode error

| Status | Arti |
|---|---|
| `400` | Request tidak valid, file kosong/rusak, atau `reference_date` salah. |
| `401` | Belum login atau session tidak valid. |
| `404` | Transaksi tidak ditemukan. |
| `409` | Terjadi konflik data saat menyimpan perubahan. |
| `413` | Ukuran file melebihi batas. |
| `415` | Format file tidak didukung. |
| `422` | Input di luar konteks atau tidak ada teks/ucapan yang terbaca. |
| `429` | Terlalu banyak request. |
| `500` | Kesalahan internal dengan pesan generik. |
| `503` | Layanan atau adapter yang diwajibkan belum tersedia. |

Error ke klien tidak memuat stack trace, path internal, SQL, token, atau raw
output model.
