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
│   ├── number_utils.py     # normalisasi bilangan lisan Indonesia
│   ├── transaction_type.py # klasifikasi income/expense/unknown
│   ├── inference.py        # pipeline inferensi Llama
│   ├── evaluate.py         # evaluasi empat konfigurasi secara terkontrol
│   ├── postprocess.py      # parsing dan validasi JSON
│   └── config.py           # konfigurasi model, training, dan audio
├── pwa/                    # frontend mobile-first tanpa framework
│   ├── index.html          # shell aplikasi satu halaman
│   ├── styles.css          # desain responsif dan aksesibel
│   ├── app.js              # state UI, instalasi, dan integrasi form
│   ├── api.js              # client endpoint teks dan suara
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

Tes rumus evaluator secara khusus dapat dijalankan tanpa model dengan:

```bash
python -m unittest tests.test_evaluate -v
```

Jalankan tes frontend berbasis Node.js dengan:

```bash
npm run test:frontend
```

Tes frontend menggunakan mock untuk `fetch`, `MediaRecorder`, media stream, dan Web
Storage. Tidak diperlukan mikrofon fisik, model, koneksi internet, maupun instalasi
package npm tambahan. Pengujian mencakup CRUD manual, migrasi riwayat lama,
transkrip suara, filter periode, detail transaksi, dan agregasi grafik tujuh hari.

## Batasan tahap pertama

- Satu rekaman hanya boleh memuat satu transaksi; multi-transaksi belum didukung.
- Satu input teks juga hanya boleh memuat satu transaksi.
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
