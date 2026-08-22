# CatatKas — Pencatat Transaksi UMKM

Dikembangkan oleh **Louis Febriano**.

Ekstraksi satu transaksi teks atau suara menjadi JSON terstruktur menggunakan soft
prompt tuning pada **Llama 3.2 3B-Instruct**. Jalur suara memakai `faster-whisper`
untuk transkripsi bahasa Indonesia, lalu memakai pipeline Llama yang sama dengan
endpoint teks.

## Setup

1. Minta akses ke
   [meta-llama/Llama-3.2-3B-Instruct](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct).
2. Login dengan `huggingface-cli login`, atau salin `.env.example` menjadi `.env`
   lalu isi `HF_TOKEN` secara lokal. Jangan commit file `.env`.
3. Pasang semua dependensi, termasuk `faster-whisper` dan `python-multipart`:

   ```bash
   pip install -r requirements.txt
   ```

4. Untuk memeriksa GPU yang dipakai Llama:

   ```bash
   python -c "import torch; print(torch.cuda.is_available())"
   ```

Whisper tidak dilatih atau di-fine-tune. Model pretrained `small` akan diunduh oleh
`faster-whisper` ketika endpoint audio pertama kali digunakan, lalu instance model
di-cache selama proses API hidup. Secara default Whisper berjalan pada CPU dengan
komputasi `int8`, sehingga tidak berebut VRAM dengan Llama. VAD diaktifkan untuk
mengabaikan bagian audio tanpa suara.

Konfigurasi audio berikut dapat disalin dari `.env.example` dan diubah melalui
environment variable:

```dotenv
WHISPER_MODEL_SIZE=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_LANGUAGE=id
WHISPER_VAD_FILTER=true
AUDIO_MAX_SIZE_MB=10
```

## Klasifikasi jenis transaksi

Setiap objek `data` yang berhasil memiliki field `transaction_type` dengan nilai:

- `income`: penjualan atau penerimaan pembayaran dari pelanggan.
- `expense`: pembelian stok/bahan atau pembayaran biaya operasional.

Classifier juga dapat menghasilkan `unknown` ketika arah transaksi tidak memiliki
petunjuk kuat atau mengandung sinyal yang saling bertentangan. Nilai ini tidak
diteruskan sebagai transaksi berhasil: pipeline berhenti sebelum memuat Llama dan
mengembalikan `success: false`, `data: null`, serta pesan agar konteks diperjelas.

Klasifikasi dilakukan dengan aturan kata/frasa dan konteks berbatas kata, bukan oleh
Llama dan bukan melalui training ulang. Hasil aturan selalu diprioritaskan apabila
model kebetulan menghasilkan field yang sama.

Sistem membedakan dua bentuk pemasukan:

- **Pemasukan umum** hanya menyatakan nominal, misalnya `pemasukkan hari ini 3 juta`
  atau `duit masuk 300 ribu`. Jalur ini diproses secara deterministik tanpa meminta
  Llama menebak barang. `item_name`, `quantity`, dan `unit` diisi `null`.
- **Penjualan barang** menyebutkan barang, misalnya `3 bakmi laku terjual 60 ribu`.
  Llama tetap mengekstrak informasi barang, dengan fallback deterministik untuk pola
  jumlah dan nama barang yang sangat jelas. Unit tidak dibuat otomatis apabila tidak
  disebutkan.

Pengeluaran berupa pembelian atau biaya operasional tetap diproses seperti sebelumnya.
Variasi bahasa kasual seperti `pemasukkan`, `duit masuk`, `omzet`, dan `penghasilan`
juga dikenali. Kata `masuk` tanpa konteks uang—misalnya `stok masuk 10 karung`—tidak
otomatis dianggap pemasukan.

`item_name`, `quantity`, dan `unit` hanya diisi apabila informasinya benar-benar
disebutkan pada teks atau transkrip pengguna. Post-processing akan mengganti nilai
hasil model menjadi `null` jika tidak dapat dilacak ke input; angka harga dan tanggal
tidak diperlakukan sebagai quantity. Ukuran produk yang menjadi bagian nama barang,
seperti `Gas 3kg`, juga tidak otomatis dianggap sebagai quantity/unit transaksi.

Contoh pemasukan umum:

```json
{
  "item_name": null,
  "quantity": null,
  "unit": null,
  "total_price": 3000000,
  "date": "2026-08-21",
  "transaction_type": "income"
}
```

Contoh penjualan barang tanpa satuan eksplisit:

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

Contoh pemasukan:

```text
Jual nasi goreng 10 porsi total 200rb -> income
Pelanggan bayar pesanan nasi kotak 300rb -> income
```

Contoh pengeluaran:

```text
Beli tepung terigu 2 karung total 250rb -> expense
Bayar listrik toko 300rb -> expense
```

Contoh ambigu:

```text
Transfer 500rb -> error (jenis transaksi unknown)
Beli tepung lalu jual kembali total 300rb -> error (jenis transaksi unknown)
```

Contoh respons untuk jenis transaksi yang tidak dapat ditentukan:

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

## Struktur utama

```text
skripsi/
├── adapters/               # hasil soft prompt tuning
├── data/processed/         # data JSONL untuk training/evaluasi
├── src/
│   ├── api.py              # endpoint FastAPI
│   ├── audio_service.py    # lazy loading dan transkripsi Whisper
│   ├── number_utils.py     # normalisasi bilangan lisan Indonesia
│   ├── transaction_type.py # klasifikasi income/expense/unknown
│   ├── inference.py        # pipeline inferensi Llama
│   ├── postprocess.py      # parsing dan validasi JSON
│   └── config.py           # konfigurasi model, training, dan audio
├── pwa/                    # frontend mobile-first tanpa framework
│   ├── index.html          # shell aplikasi satu halaman
│   ├── styles.css          # desain responsif dan aksesibel
│   ├── app.js              # state UI, instalasi, dan integrasi form
│   ├── api.js              # client endpoint teks dan suara
│   ├── storage.js          # riwayat lokal maksimal 50 transaksi
│   ├── recorder.js         # abstraksi MediaRecorder
│   ├── manifest.webmanifest
│   ├── sw.js               # application shell offline
│   └── icons/              # ikon 192, 512, dan maskable
├── scripts/
│   └── generate_pwa_icons.py
├── tests/
├── package.json            # perintah tes frontend tanpa dependensi tambahan
└── requirements.txt
```

## Training soft prompt

1. Siapkan `data/processed/train.jsonl` sesuai format contoh data.
2. Jalankan:

   ```bash
   python -m src.train
   ```

3. Adapter tersimpan di `adapters/soft-prompt-transaksi/`.

Penambahan input suara dan klasifikasi jenis transaksi tidak mengubah base model,
konfigurasi soft prompt, adapter, atau dataset training. Whisper dan classifier
rule-based juga tidak ikut dilatih.

## Menjalankan API

```bash
uvicorn src.api:app --reload --port 8000
```

FastAPI menyajikan API dan PWA dari origin yang sama. Setelah server siap, buka
[http://localhost:8000/](http://localhost:8000/) di browser desktop. Endpoint
`/extract`, `/extract/audio`, dan `/health` tetap tersedia seperti sebelumnya.

Frontend tidak memerlukan proses build atau framework JavaScript. Perubahan file di
folder `pwa/` dapat dilihat dengan memuat ulang browser ketika Uvicorn dijalankan
dengan opsi `--reload`.

### Mengakses dari perangkat mobile

Untuk membuat server dapat dijangkau dari jaringan lokal, jalankan:

```bash
uvicorn src.api:app --reload --host 0.0.0.0 --port 8000
```

Buka alamat IP komputer dan port tersebut dari ponsel yang berada pada jaringan yang
sama. Form teks dapat dipakai melalui HTTP jaringan lokal, tetapi browser mobile pada
umumnya mensyaratkan **HTTPS** untuk akses mikrofon dan service worker. `localhost`
di komputer pengembangan diperlakukan sebagai secure context, sedangkan alamat IP
lokal melalui HTTP tidak selalu demikian. Untuk pengujian suara pada ponsel, sajikan
aplikasi melalui deployment HTTPS atau reverse proxy HTTPS yang dipercaya perangkat.

### Memasang PWA

Pada browser yang mendukung event instalasi, tombol **Pasang aplikasi** muncul di
header. Pada iPhone atau iPad, buka menu **Bagikan**, lalu pilih **Tambahkan ke Layar
Utama**. Tombol tidak ditampilkan ketika aplikasi sudah berjalan dalam mode
standalone.

Service worker hanya menyimpan application shell dan aset statis. Request API, respons
`/extract`, respons `/extract/audio`, serta audio tidak dimasukkan ke cache. Ketika
offline, riwayat tetap dapat dibaca tetapi inferensi transaksi dinonaktifkan karena
Llama dan Whisper tetap berjalan pada backend.

Riwayat berisi maksimal 50 transaksi dan hanya tersimpan di `localStorage` perangkat
pengguna. Rekaman suara, token, output mentah model, dan rahasia API tidak disimpan.
Gunakan tombol **Hapus riwayat** untuk membersihkannya.

Selama pengembangan, cache PWA dapat dibersihkan melalui DevTools browser: buka panel
**Application**, pilih **Service Workers → Unregister**, kemudian **Storage → Clear
site data**, lalu muat ulang halaman.

Endpoint teks lama tetap tersedia:

```bash
curl -X POST http://localhost:8000/extract \
  -H "Content-Type: application/json" \
  -d '{"text":"Kemarin beli Gas 3kg sebanyak 10 tabung, totalnya 180rb"}'
```

Endpoint suara menerima field multipart `file` dan `reference_date` opsional dalam
format `YYYY-MM-DD`:

```bash
curl -X POST http://localhost:8000/extract/audio \
  -F "file=@contoh_transaksi.wav" \
  -F "reference_date=2026-08-21"
```

Format minimum yang didukung adalah WAV, MP3, M4A, WEBM, dan OGG. Ukuran maksimal
default adalah 10 MB. File hanya disimpan dengan nama acak di lokasi sementara selama
request dan selalu dihapus setelah pemrosesan.

Contoh respons berhasil:

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

Contoh respons gagal ketika tidak ada ucapan yang dikenali (`HTTP 422`):

```json
{
  "detail": "Tidak ditemukan ucapan yang dapat dikenali pada audio"
}
```

Input di luar konteks transaksi juga menghasilkan `HTTP 422`, konsisten dengan
endpoint teks. Format yang tidak didukung menghasilkan `HTTP 415`, file kosong
menghasilkan `HTTP 400`, dan `reference_date` yang tidak valid menghasilkan `HTTP 400`.

## Pengujian

Jalankan seluruh tes dengan:

```bash
python -m unittest discover -s tests -v
```

Tes menggunakan mock untuk transkripsi Whisper dan ekstraksi Llama, sehingga tidak
mengunduh model, tidak membutuhkan internet, dan tidak membutuhkan GPU.

Jalankan tes frontend berbasis Node.js dengan:

```bash
npm run test:frontend
```

Tes frontend menggunakan mock untuk `fetch`, `MediaRecorder`, media stream, dan Web
Storage. Tidak diperlukan mikrofon fisik, model, koneksi internet, maupun instalasi
package npm tambahan.

## Batasan tahap pertama

- Satu rekaman hanya boleh memuat satu transaksi; multi-transaksi belum didukung.
- Satu input teks juga hanya boleh memuat satu transaksi.
- PWA tidak menjalankan ekstraksi secara offline; koneksi ke backend tetap diperlukan.
- Riwayat belum memiliki sinkronisasi, autentikasi, database, atau cadangan cloud dan
  hanya tersedia pada browser/perangkat tempat transaksi dicatat.
- Tidak ada streaming audio, penyimpanan rekaman permanen, atau inferensi multimodal
  langsung.
- Normalisasi bilangan mencakup bentuk baku satuan, puluhan, ratusan, ribuan, dan
  jutaan. Pecahan, kata “setengah”, angka desimal lisan, serta ucapan bilangan yang
  ambigu belum diinterpretasikan sebagai nilai pecahan/desimal pada tahap ini.
- Kata ambigu seperti `bayar`, `transfer`, `masuk`, dan `keluar` memerlukan konteks
  yang jelas; jika tidak, API mengembalikan error jenis transaksi tanpa memanggil
  Llama.
- Modal, pinjaman, pengembalian dana, dan multi-transaksi belum diklasifikasikan
  otomatis apabila arah transaksinya tidak jelas.
- Akurasi transkripsi tetap dipengaruhi kualitas rekaman, kebisingan, dan pelafalan.
