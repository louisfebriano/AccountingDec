# CatatKas — Pencatat Transaksi UMKM

Dikembangkan oleh **Louis Febriano**.

Ekstraksi satu transaksi teks atau suara menjadi JSON terstruktur menggunakan soft
prompt tuning pada **Llama 3.2 3B-Instruct**. Jalur suara memakai `faster-whisper`
untuk transkripsi bahasa Indonesia, lalu memakai pipeline Llama yang sama dengan
endpoint teks. Fitur **Scan Nota** memakai PaddleOCR lokal untuk membaca nota cetak,
kemudian Llama dengan Soft Prompt Nota untuk ekstraksi semantik, validasi aturan, dan
konfirmasi pengguna sebelum hasil disimpan.

Arsitektur produksi:

```text
Teks  → Llama + Soft Prompt Transaksi ┐
Voice → faster-whisper → Llama + Soft Prompt Transaksi ├→ validasi → konfirmasi/hasil → penyimpanan
Foto  → PaddleOCR → Llama + Soft Prompt Nota ┘
```

Adapter transaksi dan nota memakai **satu base Llama yang sama**. Pemilihan adapter
dan `model.generate()` dikunci agar request concurrent tidak saling menukar adapter.

## Setup

1. Minta akses ke
   [meta-llama/Llama-3.2-3B-Instruct](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct).
2. Login dengan `huggingface-cli login`, atau salin `.env.example` menjadi `.env`
   lalu isi `HF_TOKEN` secara lokal. Jangan commit file `.env`.
3. Pasang semua dependensi, termasuk `faster-whisper`, `python-multipart`, Pillow,
   PaddleOCR, dan PaddlePaddle CPU:

   ```bash
   pip install -r requirements.txt
   ```

   Versi NumPy, OpenCV, Albumentations, Albucore, PaddleOCR, dan PaddlePaddle dikunci
   pada kombinasi yang menyediakan wheel Windows untuk Python 3.11. Ini menghindari
   fallback kompilasi `stringzilla` yang membutuhkan Microsoft C++ Build Tools.

4. Untuk memeriksa GPU yang dipakai Llama:

   ```bash
   python -c "import torch; print(torch.cuda.is_available())"
   ```

Whisper tidak dilatih atau di-fine-tune. Model pretrained `small` akan diunduh oleh
`faster-whisper` ketika endpoint audio pertama kali digunakan, lalu instance model
di-cache selama proses API hidup. Secara default Whisper berjalan pada CPU dengan
komputasi `int8`, sehingga tidak berebut VRAM dengan Llama. VAD diaktifkan untuk
mengabaikan bagian audio tanpa suara.

Model pretrained PaddleOCR bahasa Indonesia juga tidak dilatih ulang. Model OCR baru
diunduh ketika endpoint Scan Nota pertama kali digunakan, lalu instance-nya di-cache
selama proses API hidup. OCR berjalan pada CPU (`use_gpu=False`) dan dipisahkan dari
pipeline Llama serta Whisper. Unduhan pertama membutuhkan koneksi internet; request
berikutnya menggunakan cache model lokal PaddleOCR.

Konfigurasi audio berikut dapat disalin dari `.env.example` dan diubah melalui
environment variable:

```dotenv
WHISPER_MODEL_SIZE=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_LANGUAGE=id
WHISPER_VAD_FILTER=true
AUDIO_MAX_SIZE_MB=10
RECEIPT_MAX_SIZE_MB=10
RECEIPT_OCR_LANGUAGE=id
RECEIPT_MIN_CONFIDENCE=0.50
RECEIPT_MAX_IMAGE_DIMENSION=2400
RECEIPT_OCR_TARGET_LONG_EDGE=2000
RECEIPT_MAX_IMAGE_PIXELS=25000000
RECEIPT_OCR_MULTIPASS=true
RECEIPT_OCR_DET_BOX_THRESHOLD=0.30
RECEIPT_OCR_DROP_SCORE=0.25
RECEIPT_ADAPTER_OUTPUT_DIR=adapters/soft-prompt-nota
RECEIPT_TRAIN_DATA_PATH=data/processed/receipt-train.jsonl
RECEIPT_VALIDATION_DATA_PATH=data/processed/receipt-validation.jsonl
RECEIPT_EVAL_DATA_PATH=data/processed/receipt-eval.jsonl
RECEIPT_SOFT_PROMPT_CONTRACT_VERSION=1
RECEIPT_LLM_ENABLED=true
RECEIPT_RULE_FALLBACK_ENABLED=true
```

## Klasifikasi jenis transaksi

Setiap objek `data` yang berhasil memiliki field `transaction_type` dengan nilai:

- `income`: penjualan atau penerimaan pembayaran dari pelanggan.
- `expense`: pembelian stok/bahan atau pembayaran biaya operasional.

Classifier juga dapat menghasilkan `unknown` ketika arah transaksi tidak memiliki
petunjuk kuat atau mengandung sinyal yang saling bertentangan. Nilai ini tidak
diteruskan sebagai transaksi berhasil: pipeline berhenti sebelum memuat Llama dan
mengembalikan `success: false`, `data: null`, serta pesan agar konteks diperjelas.

Klasifikasi final pada pipeline produksi dilakukan dengan aturan kata/frasa dan
konteks berbatas kata. Adapter v2 tetap dilatih menghasilkan `transaction_type` agar
keluaran mentah enam field dapat dievaluasi, tetapi nilai produksi selalu ditimpa oleh
classifier aturan dan tidak mempercayai tebakan model.

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
│   ├── receipt_service.py  # praproses gambar dan lazy loading PaddleOCR
│   ├── receipt_parser.py   # ekstraksi tanggal, total, serta rincian nota
│   ├── receipt_schema.py   # schema JSON ketat Soft Prompt Nota
│   ├── receipt_inference.py # inference adapter nota pada base Llama bersama
│   ├── receipt_validation.py # validasi silang Llama dan parser nota
│   ├── train_receipt.py    # training adapter nota terpisah
│   ├── evaluate_receipt.py # metrik evaluasi khusus nota
│   ├── number_utils.py     # normalisasi bilangan lisan Indonesia
│   ├── transaction_type.py # klasifikasi income/expense/unknown
│   ├── inference.py        # pipeline inferensi Llama
│   ├── evaluate.py         # evaluasi empat konfigurasi secara terkontrol
│   ├── postprocess.py      # parsing dan validasi JSON
│   └── config.py           # konfigurasi model, training, audio, dan OCR
├── pwa/                    # frontend mobile-first tanpa framework
│   ├── index.html          # shell aplikasi satu halaman
│   ├── styles.css          # desain responsif dan aksesibel
│   ├── app.js              # state UI, instalasi, dan integrasi form
│   ├── api.js              # client endpoint teks, suara, dan Scan Nota
│   ├── storage.js          # CRUD dan riwayat lokal maksimal 50 transaksi
│   ├── filters.js          # filter tanggal lokal minggu/bulan/tahun/custom
│   ├── chart.js            # agregasi dan grafik tren tujuh hari
│   ├── theme.js            # tema putih/gelap dan preferensi perangkat
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
2. Atur kontrak training bila perlu. Nilai default yang digunakan evaluator adalah:

   ```dotenv
   TRAIN_REFERENCE_DATE=2026-08-24
   TRAIN_VALIDATION_DATA_PATH=data/processed/validation-six-fields.jsonl
   TRAIN_REFERENCE_DATE_VARIANTS=4
   TRAIN_REFERENCE_DATE_STEP_DAYS=7
   TRAIN_VALIDATION_RATIO=0.1
   TRAIN_SEED=42
   BALANCE_TRANSACTION_TYPES=true
   ```

3. Jalankan:

   ```bash
   python -m src.train
   ```

4. Adapter dan metadata kontrak `catatkas_contract.json` tersimpan di
   `adapters/soft-prompt-transaksi/`.

Penambahan input suara dan klasifikasi jenis transaksi tidak mengubah base model,
konfigurasi soft prompt, atau adapter yang sudah ada. Whisper dan classifier
rule-based juga tidak ikut dilatih. Data augmentasi opsional untuk retraining Soft
Prompt dijelaskan pada bagian evaluasi berikutnya.

## Soft Prompt Nota

Soft Prompt transaksi di `adapters/soft-prompt-transaksi` tetap memakai enam field
transaksi. Soft Prompt Nota adalah adapter berbeda di `adapters/soft-prompt-nota`
dengan schema:

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

Semua field wajib ada; nilai yang tidak ditemukan harus `null`. Model tidak menghasilkan
confidence. Prompt training dan inference memakai format yang sama, mempertahankan line
break OCR, menyertakan `REFERENCE_DATE` dan `SOURCE: receipt_ocr`, serta melarang model
menambahkan barang yang tidak ada pada OCR.

### Dataset nota

Repository menyediakan generator data **sintetis** untuk bootstrap eksperimen. Data ini
bukan hasil foto nota nyata dan tidak boleh digunakan untuk mengklaim akurasi produksi.
Jalankan:

```bash
python -m src.generate_receipt_synthetic_data
```

Generator memakai seed tetap dan secara default membuat 400 contoh train, 80 validation,
dan 80 evaluation pada:

- `data/processed/receipt-train.jsonl`
- `data/processed/receipt-validation.jsonl`
- `data/processed/receipt-eval.jsonl`

Setiap baris menggunakan format berikut:

```json
{"receipt_id":"synthetic-train-00001","template_id":"synthetic-layout-0","data_origin":"synthetic","input":"TOKO BERKAH\nTOTAL 53.000","reference_date":"2026-08-26","output":{"merchant_name":"TOKO BERKAH","receipt_number":null,"date":"2026-08-26","items":[],"subtotal":53000,"discount":0,"tax":0,"service_charge":0,"total":53000,"transaction_type":"expense"}}
```

`receipt_id`, `template_id`, dan `data_origin` opsional pada schema file. Nilai
`data_origin` yang didukung adalah `synthetic`, `real`, atau `augmented`. Receipt dan
template sangat disarankan agar
foto berbeda dari nota/template yang sama tidak tersebar ke split lain. Training selalu
menolak OCR text persis, `receipt_id`, atau `template_id` yang overlap antara train,
validation, dan evaluation. Target dengan field hilang, field tambahan, tipe salah,
tanggal tidak valid, nominal negatif, atau `transaction_type` selain `expense` ditolak
sebelum base model dimuat.

Layout sintetis untuk train, validation, dan evaluation sengaja dipisahkan. Isinya
mencakup 1–5 item, nota tanpa rincian terbaca, field yang tersedia maupun `null`, angka
rupiah dengan beberapa separator, quantity pecahan berbobot, diskon, pajak, biaya
layanan, serta noise OCR ringan pada label. Untuk evaluasi skripsi yang bermakna,
tambahkan nota nyata yang dianotasi manual, simpan `data_origin: "real"`, dan pertahankan
split berdasarkan `receipt_id`/`template_id`. Laporkan metrik sintetis dan nyata secara
terpisah.

### Training dan evaluasi nota

Setelah ketiga dataset tersedia, jalankan training secara eksplisit:

```bash
python -m src.train_receipt
```

Untuk GPU 6 GB, hentikan API/Uvicorn lebih dahulu karena proses training tidak dapat
berbagi salinan base model yang sudah dimuat oleh proses server. Preset receipt memakai
4-bit NF4 double quantization, batch 1, dynamic padding, gradient checkpointing, BF16
pada GPU yang mendukung, dan accumulation 8. Contoh yang melebihi batas token ditolak
daripada memotong JSON target secara diam-diam. Konfigurasi low-VRAM dapat diubah lewat:

```env
RECEIPT_MAX_SEQ_LENGTH=768
RECEIPT_TRAIN_BATCH_SIZE=1
RECEIPT_GRADIENT_ACCUMULATION_STEPS=8
RECEIPT_MIN_FREE_GPU_GB=4.5
```

Jika allocator CUDA mengalami fragmentasi, set variabel berikut sebelum memulai proses
Python baru:

```powershell
$env:PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
python -m src.train_receipt
```

Preflight training menampilkan VRAM bebas dan berhenti dengan pesan yang jelas apabila
proses lain menyisakan kurang dari batas minimum. Menurunkan `RECEIPT_MAX_SEQ_LENGTH`
di bawah panjang contoh tidak akan memangkas target; training akan meminta data OCR
diringkas atau batas dinaikkan.

Sebelum training penuh, verifikasi satu forward/backward step tanpa menghasilkan
adapter atau checkpoint permanen:

```bash
python -m src.train_receipt --smoke-test
```

Hasil disimpan hanya ke `adapters/soft-prompt-nota`. Adapter transaksi tidak ditimpa.
Metadata `catatkas_contract.json` menyimpan versi kontrak, base model, JSON schema,
format prompt, reference date training, seed, dan path dataset.

Evaluasi langsung dengan adapter nyata:

```bash
python -m src.evaluate_receipt --data data/processed/receipt-eval.jsonl --output results/receipt-evaluation-report.json
```

Atau evaluasi file prediksi JSONL yang sudah dihasilkan sebelumnya tanpa memuat model:

```bash
python -m src.evaluate_receipt --data data/processed/receipt-eval.jsonl --predictions results/receipt-predictions.jsonl --output results/receipt-evaluation-report.json
```

Setiap prediksi berisi `{"raw_output":"...JSON model..."}` atau `{"output":{...}}`.
Evaluator melaporkan JSON validity, field accuracy, merchant/date/total accuracy,
precision/recall/F1 nama item, accuracy quantity/unit/unit-price/line-total, dan exact
transaction match. JSON rusak dihitung gagal; evaluator tidak memperbaiki prediksi dan
tidak menulis hasil jika adapter/model yang diminta tidak tersedia.

### Aktivasi dan fallback

`RECEIPT_LLM_ENABLED=true` membuat setiap OCR text mencoba Soft Prompt Nota. Adapter
divalidasi terhadap base model, schema, format prompt, dan contract version sebelum
digunakan. Karena repository ini belum berisi adapter nota, default
`RECEIPT_RULE_FALLBACK_ENABLED=true` mempertahankan endpoint dengan respons
`extraction_method: rule_based_fallback` dan warning eksplisit. Atur fallback ke
`false` untuk memperoleh HTTP 503 sampai adapter yang valid tersedia. Fallback tidak
pernah diberi label sebagai hasil Llama.

## Evaluasi empat konfigurasi

Evaluator membandingkan **Llama + Explicit Instruction**, **Llama + Soft Prompt**,
**Llama + Explicit Instruction + Post-processing**, dan **Llama + Soft Prompt +
Post-processing**. Base Llama menerima instruksi enam field dan reference date melalui
chat template tokenizer. Soft Prompt menerima format
`REFERENCE_DATE: ...\nKalimat: ...\nJSON:` yang sama saat training, API, dan evaluasi.
Raw masing-masing model digunakan ulang oleh varian post-processing, sehingga total
hanya ada dua inference pass dan dua kali pemuatan model.

Training membaca `data/processed/train.jsonl` lalu menambahkan contoh generalisasi
dari `data/processed/train-augmentation.jsonl` bila file tersebut tersedia. Contoh
augmentasi memakai kalimat yang berbeda dari dataset evaluasi dan mencakup modifier
nama barang, unit singkat, angka rapat, pecahan sederhana, kemasan bertingkat, variasi
tanggal, serta contoh `income` dan `expense`. Sumber training lama yang memiliki lima
field diperkaya secara deterministik menjadi enam field. Tanggal diselesaikan terhadap
beberapa reference date yang diturunkan dari `TRAIN_REFERENCE_DATE`, sehingga adapter
tidak sekadar menghafal satu tanggal evaluasi. Jenis transaksi diambil hanya dari arah
yang eksplisit dan input ambigu dikeluarkan. Split validation dibuat terstratifikasi
dari data training hanya sebagai fallback. Secara default training memakai
`validation-six-fields.jsonl`, yaitu 24 contoh held-out yang seimbang (12 income dan
12 expense) dengan variasi bahasa kasual, tanggal, unit singkat, field null, biaya,
penjualan barang, pembayaran pelanggan, dan pemasukan umum. Validation tidak masuk
training maupun final evaluation. Kelas minoritas hanya di-oversample pada split
training jika `BALANCE_TRANSACTION_TYPES=true`.

Training memeriksa exact overlap antara training, validation, dan final evaluation
sebelum model dimuat ke Trainer. Validation dipakai untuk memantau generalisasi, bukan
untuk memaksa skor ke rentang tertentu; nilai 60–80% hanya sah bila benar-benar muncul
dari keluaran model.

Perubahan kontrak ini baru memengaruhi Soft Prompt setelah adapter dilatih ulang:

```bash
python -m src.train
```

Adapter lama memang akan tetap menghasilkan `date: null` dan tidak memiliki
`transaction_type`; evaluator tidak mengisi kedua field pada konfigurasi raw dan tidak
membuat skor palsu. Evaluator memeriksa metadata kontrak adapter dan akan meminta
retraining bila `catatkas_contract.json` belum tersedia atau versinya tidak cocok.

Karena prompt base Llama dan Soft Prompt berbeda, tabel ini membandingkan konfigurasi
praktis dan bukan ablation murni yang hanya mengubah adapter. Dataset, urutan contoh,
tokenizer, base model, kuantisasi, decoding deterministik, seed, batas token, dan
reference date tetap sama.

Dataset evaluasi harus berupa JSONL dan setiap `output` wajib memiliki enam field:
`item_name`, `quantity`, `unit`, `total_price`, `date`, serta `transaction_type`.
Target `transaction_type` evaluasi hanya boleh `income` atau `expense`; `unknown`
merupakan status penolakan input ambigu pada pipeline produksi, bukan kelas transaksi
yang dinilai sebagai ground truth.
Nilai target selalu dinilai apa adanya dan evaluator tidak mengisi tanggal target.
Pada `data/processed/eval-six-fields.jsonl`, ground truth tanggal sudah ditulis
eksplisit dengan reference date tetap `2026-08-24`: input tanpa tanggal memakai
`2026-08-24`, `Tanggal 10 Juli` memakai `2026-07-10`, dan `kmrn` memakai
`2026-08-23`. Dataset ini berisi 52 input unik yang terdiri dari 39 `expense` dan 13
`income`, termasuk pembelian, restock, penjualan barang, pembayaran pelanggan, dan
pemasukan umum. Tanggal mencakup input tanpa tanggal, eksplisit, `hari ini`, `tadi`,
`kemarin`, singkatan `kmrn`, serta hitungan hari/minggu lalu. Duplikasi identik dan
overlap teks persis dengan data training/augmentasi sudah dihapus. Quantity dan unit
diberi `null` bila tidak disebutkan, dan anotasi nama barang tidak menambahkan kata
yang tidak ada pada input. Dataset asal `data/processed/eval.jsonl` tetap dipertahankan
tanpa perubahan.

Jalankan evaluasi setelah dataset enam field siap:

```bash
python -m src.evaluate --data data/processed/eval-six-fields.jsonl --train-data data/processed/train.jsonl --adapter adapters/soft-prompt-transaksi --reference-date 2026-08-24 --output results/evaluation_report.json
```

`--reference-date` wajib agar resolver tanggal post-processing tidak bergantung pada
tanggal komputer. Evaluasi model memerlukan akses ke Llama yang gated, dependensi
model, adapter, dan GPU yang didukung konfigurasi proyek. Jika salah satunya tidak
tersedia, proses gagal dengan pesan ringkas dan tidak membuat angka performa palsu.

Laporan terminal dan JSON hanya memakai metrik utama berikut:

- **JSON validity rate**: objek JSON valid dibagi seluruh data. Varian raw memakai
  `json.loads` atas seluruh keluaran tanpa mengambil atau memperbaiki substring JSON.
- **Precision/recall/F1 micro global**: pasangan `(field, nilai)` non-null menjadi
  unit informasi. Nilai non-null yang salah menambah satu FP dan satu FN.
- **Field-level accuracy**: kecocokan setiap field dibagi seluruh data, serta total
  field benar dibagi `jumlah data × 6` untuk overall field accuracy.

Target null dan prediksi null benar untuk field accuracy tetapi tidak menambah
TP/FP/FN. Prediksi pada target null menambah FP. Prediksi null atau field hilang pada
target non-null menambah FN. Field hilang tetap salah untuk field accuracy, termasuk
saat target null. JSON tidak valid membuat keenam field salah dan menambah FN untuk
setiap target non-null. Normalisasi evaluasi hanya merapikan spasi/case string dan
menerima representasi numerik setara untuk `quantity` serta `total_price`.

Laporan juga menyimpan seluruh keluaran mentah dua lintasan, TP/FP/FN, jumlah JSON
valid/tidak valid, beberapa contoh salah, audit kecocokan teks persis terhadap data
training, dan catatan metodologi. Audit
overlap bukan bukti penuh bahwa dataset independen karena provenance adapter dan
kemiripan semantik tetap perlu diverifikasi. Kontrak training efektif mempunyai enam
field, tetapi adapter harus dilatih ulang setelah perubahan kontrak; evaluator tidak
mengarang field model yang hilang.

Pipeline produksi mempunyai fast path rule-based untuk pemasukan agregat seperti
`duit masuk 300 ribu`. Dalam evaluasi, contoh tetap dikirim ke lintasan base explicit
dan Soft Prompt. Karena itu hasil fast path produksi tidak boleh diklaim sebagai
kemampuan model atau Soft Prompt.

## Menjalankan API

```bash
uvicorn src.api:app --reload --port 8000
```

FastAPI menyajikan API dan PWA dari origin yang sama. Setelah server siap, buka
[http://localhost:8000/](http://localhost:8000/) di browser desktop. Endpoint
`/extract`, `/extract/audio`, `/extract/receipt`, dan `/health` tersedia dari origin
yang sama. Kontrak endpoint teks dan suara tetap dipertahankan.

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
`/extract`, `/extract/audio`, `/extract/receipt`, audio, dan foto nota tidak dimasukkan
ke cache. Ketika offline, riwayat tetap dapat dibaca tetapi inferensi transaksi
dinonaktifkan karena Llama, Whisper, dan PaddleOCR tetap berjalan pada backend.

Riwayat berisi maksimal 50 transaksi dan hanya tersimpan di `localStorage` perangkat
pengguna. Rekaman suara, foto nota, teks OCR mentah, temporary path, token, output
mentah model, dan rahasia API tidak disimpan. Gunakan tombol **Hapus riwayat** untuk
membersihkannya.

### Riwayat, transaksi manual, dan grafik

Tombol **Tambah manual** membuka form transaksi lokal tanpa memanggil Llama atau
Whisper. Jenis transaksi, tanggal, dan nominal wajib diisi. Nama barang, quantity,
unit, dan catatan bersifat opsional; field yang kosong disimpan sebagai `null`.
Transaksi manual tetap dapat ditambahkan ketika perangkat offline.

Tekan salah satu item riwayat untuk membuka detailnya. Popup detail menampilkan data
transaksi, sumber, waktu pencatatan, dan input asli. Tombol **Edit** memperbarui data
dengan ID yang sama, sedangkan tombol **Hapus** meminta konfirmasi sebelum menghapus
satu transaksi. Semua perubahan langsung memperbarui ringkasan, riwayat, dan grafik.

Riwayat dan kartu ringkasan dapat difilter berdasarkan minggu kalender
Senin–Minggu, bulan, tahun, rentang tanggal khusus yang inklusif, atau seluruh data.
Perhitungan memakai tanggal lokal agar tanggal tidak bergeser karena UTC. Filter
tidak menghapus atau memodifikasi transaksi yang tersimpan.

Grafik tren menampilkan agregasi pemasukan berwarna hijau dan pengeluaran berwarna
merah untuk tujuh hari kalender terakhir, termasuk hari ini. Hari tanpa transaksi
tetap ditampilkan dengan nilai nol. Transaksi berjenis `unknown` tidak dimasukkan ke
kedua seri grafik. Arahkan pointer, fokuskan dengan keyboard, atau tekan salah satu
titik untuk melihat tanggal serta nominal pemasukan dan pengeluaran. Tooltip dapat
ditutup dengan menekan Escape atau area di luar grafik.

Tema terang menggunakan `#03BFB5` sebagai warna primer untuk tombol dan penekanan,
`#018076` sebagai warna sekunder serta warna pemasukan, dan `#EFF5F9` sebagai
background. Warna lain dipakai sebagai pendukung, dengan putih sebagai permukaan
kartu. Tombol tema pada header berpindah antara tema putih dan mode gelap. Pilihan
tersimpan hanya di browser; jika
belum ada pilihan, aplikasi mengikuti preferensi warna perangkat saat pertama dibuka.
Merah tetap digunakan sebagai warna semantik pengeluaran agar seri grafik mudah
dibedakan.

Untuk hasil input suara, PWA menyimpan `transcript` asli dan `normalized_text` sebagai
dua field terpisah. Detail menampilkan keduanya tanpa mengganti transkrip asli. Input
teks disimpan sebagai **Input asli**, sedangkan transaksi manual menyimpan
**Catatan**. Panjang setiap teks dibatasi 500 karakter. File audio dan `raw_output`
internal Llama tidak pernah dimasukkan ke `localStorage`. Riwayat versi lama otomatis
dimigrasikan ketika pertama kali dibaca.

### Scan Nota

Pilih tab **Foto nota**, ambil foto dengan kamera belakang atau pilih JPEG, PNG, atau
WebP dari galeri, lalu tekan **Scan nota**. Batas ukuran default adalah 10 MB. Server
memperbaiki orientasi EXIF, memperbesar foto kecil hingga sisi panjang 2.000 piksel,
menerapkan autocontrast dan sharpening, serta mencoba koreksi kemiringan kecil. Secara
default PaddleOCR dijalankan pada varian grayscale dan adaptive-threshold, lalu hasil
dengan struktur, confidence, keyword, dan nominal terbaik dipilih. Semua file varian
bersifat sementara dan selalu dihapus.

Normalisasi setelah OCR hanya memperbaiki pola yang dapat dipastikan, misalnya
`Ro.1.500` menjadi `Rp 1.500`, `Rp.10-000` menjadi `Rp 10.000`, header tabel yang
menempel, serta baris item yang melebur. Nama barang atau digit yang hilang tidak
ditebak. Teks mentah tetap tersedia hanya untuk audit internal, sedangkan teks bersih
ditampilkan untuk konfirmasi dan dikirim ke Llama. Teks OCR kemudian selalu dicoba pada Llama + Soft
Prompt Nota ketika fitur aktif. Parser regex tidak lagi menjadi ekstraktor semantik
utama; parser dipakai untuk kandidat total/tanggal/item, validasi silang, warning, dan
fallback eksplisit. Nama file pengguna tidak dipakai sebagai path; file sementara
selalu bernama acak dan dihapus pada jalur sukses maupun gagal.

Quantity dengan pemisah titik, misalnya `4.000 kg`, dibedakan dari quantity desimal
dengan mencocokkan harga satuan dan total baris yang tercetak. Total baris hasil OCR
tetap dipertahankan; bila `quantity x harga`, jumlah seluruh item, atau subtotal pada
nota tidak konsisten, CatatKas menampilkan warning dan tidak mengoreksi angka secara
diam-diam.

Hasil OCR tidak langsung dicatat. Dialog konfirmasi menampilkan nama toko, nomor nota,
kandidat total, warning, rincian item, dan teks OCR sementara. Pengguna wajib memeriksa
atau mengisi **tanggal transaksi** dan **total akhir**, kemudian menekan **Simpan
transaksi**. Tanggal pemindaian tidak digunakan diam-diam ketika tanggal nota gagal
dibaca.

CatatKas memakai prinsip **satu nota = satu transaksi keuangan**. Banyak barang pada
nota disimpan sebagai `receipt.items` di dalam satu transaksi induk berjenis `expense`.
Ringkasan, filter, grafik, dan Insight Arus Kas hanya menghitung `total_price` induk
satu kali. Edit transaksi induk mempertahankan rincian nota. Transaksi lama tanpa field
`receipt` tetap dapat dibaca.

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

Endpoint Scan Nota menerima gambar multipart dengan nama field `file` dan
`reference_date` opsional:

```bash
curl -X POST http://localhost:8000/extract/receipt \
  -F "file=@contoh_nota.jpg" \
  -F "reference_date=2026-08-26"
```

Contoh respons Scan Nota:

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
      "receipt_number": "INV-001",
      "subtotal": 170000,
      "discount": 5000,
      "tax": 10000,
      "service_charge": 5000,
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
      "confidence": 0.91,
      "warnings": []
    }
  },
  "ocr_text": "teks OCR hanya untuk konfirmasi sementara",
  "total_candidates": [180000],
  "extraction_method": "llama_soft_prompt_receipt",
  "validation": {
    "status": "valid",
    "warnings": []
  },
  "error": null
}
```

`HTTP 400` digunakan untuk gambar kosong/rusak atau isi yang tidak sesuai ekstensi,
`413` untuk ukuran berlebih, `415` untuk format yang tidak didukung, `422` ketika
tidak ada teks yang dapat dibaca, dan `503` ketika adapter nota wajib tetapi tidak
tersedia. Error internal memakai pesan generik tanpa stack trace. Foto asli dan raw
output Llama tidak pernah dikembalikan. Teks OCR hanya dikirim ke dialog konfirmasi dan
tidak dimasukkan ke `localStorage`.

## Pengujian

Jalankan seluruh tes dengan:

```bash
python -m unittest discover -s tests -v
```

Tes menggunakan mock untuk transkripsi Whisper, ekstraksi Llama, dan PaddleOCR,
sehingga tidak mengunduh model, tidak membutuhkan internet, dan tidak membutuhkan GPU.

Tes rumus evaluator secara khusus dapat dijalankan tanpa model dengan:

```bash
python -m unittest tests.test_evaluate -v
python -m unittest tests.test_receipt_evaluate -v
```

Jalankan tes frontend berbasis Node.js dengan:

```bash
npm run test:frontend
```

Tes frontend menggunakan mock untuk `fetch`, `MediaRecorder`, media stream, dan Web
Storage. Tidak diperlukan mikrofon fisik, model, koneksi internet, maupun instalasi
package npm tambahan. Pengujian mencakup CRUD manual, migrasi riwayat lama,
transkrip suara, Scan Nota dan konfirmasinya, privasi storage, filter periode, detail
transaksi, serta agregasi grafik.

## Batasan tahap pertama

- Satu rekaman hanya boleh memuat satu transaksi; multi-transaksi belum didukung.
- Satu input teks juga hanya boleh memuat satu transaksi.
- Satu foto nota hanya menghasilkan satu transaksi induk. Item nota bukan transaksi
  kas terpisah.
- PWA tidak menjalankan ekstraksi secara offline; koneksi ke backend tetap diperlukan.
- Riwayat belum memiliki sinkronisasi, autentikasi, database, atau cadangan cloud dan
  hanya tersedia pada browser/perangkat tempat transaksi dicatat.
- Tidak ada streaming audio, penyimpanan rekaman permanen, atau inferensi multimodal
  langsung.
- Normalisasi bilangan mencakup bentuk baku satuan, puluhan, ratusan, ribuan, jutaan,
  serta pecahan sederhana `setengah`, `seperempat`, dan `tiga perempat` apabila langsung
  diikuti unit ukuran. Angka desimal lisan seperti “dua koma lima” dan ucapan bilangan
  yang ambigu belum diinterpretasikan pada tahap ini.
- Kata ambigu seperti `bayar`, `transfer`, `masuk`, dan `keluar` memerlukan konteks
  yang jelas; jika tidak, API mengembalikan error jenis transaksi tanpa memanggil
  Llama.
- Modal, pinjaman, pengembalian dana, dan multi-transaksi belum diklasifikasikan
  otomatis apabila arah transaksinya tidak jelas.
- Akurasi transkripsi tetap dipengaruhi kualitas rekaman, kebisingan, dan pelafalan.
- OCR versi awal berfokus pada nota **cetak** berbahasa Indonesia. Nota tulisan tangan,
  sangat pudar, terpotong, tertutup, buram, atau bertata letak kompleks dapat gagal
  dibaca dan harus difoto ulang atau dicatat manual.
- Ekstraksi item bersifat best-effort. Jika item gagal tetapi total dapat dibaca,
  transaksi tetap dapat disimpan setelah pengguna mengonfirmasi total dan tanggal.
- Baris tabel barang tetap ditampilkan ketika sebagian quantity atau nominal gagal
  dibaca. Field yang ambigu dibiarkan `null` dan ditandai warning agar tidak ditebak
  atau dikoreksi otomatis.
- Interpretasi nominal memprioritaskan label total dan menghindari tunai/kembalian,
  tetapi kandidat ambigu tetap harus dipilih pengguna; angka tidak diperbaiki otomatis.
- Dataset dan adapter Soft Prompt Nota belum disertakan. Sebelum dilatih dengan data
  beranotasi nyata, Scan Nota menggunakan fallback rule-based yang ditandai eksplisit
  atau HTTP 503 jika fallback dinonaktifkan. Tidak ada klaim akurasi Soft Prompt Nota.
- Kesalahan PaddleOCR dapat merambat ke Llama. Validasi silang dan dialog konfirmasi
  mengurangi risiko, tetapi tidak menjamin merchant, item, atau nominal selalu benar.
