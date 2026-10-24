# Panduan penggunaan

Panduan ini ditujukan untuk pengguna aplikasi CatatKas. Semua langkah dilakukan
dari browser; tidak ada aplikasi tambahan yang perlu dipasang selain PWA
opsional.

## 1. Masuk ke aplikasi

1. Buka alamat CatatKas, misalnya <http://localhost:8000/>.
2. Pilih **Daftar** jika belum punya akun, atau **Masuk** jika sudah.
3. Gunakan email dan password yang valid.

Setelah login, aplikasi utama akan menampilkan form pencatatan, ringkasan,
riwayat, dan grafik. Setiap akun memiliki data sendiri. Pengguna lain tidak
dapat melihat atau mengubah transaksi Anda.

## 2. Mencatat lewat teks

1. Pilih tab **Teks**.
2. Tulis satu transaksi, misalnya:

   ```text
   kemarin beli gas 3kg 2 tabung total 180rb
   ```

3. Tekan tombol kirim.
4. Periksa hasil ekstraksi pada dialog **Konfirmasi transaksi**.
5. Lengkapi atau perbaiki field yang masih kosong.
6. Pilih kategori, lalu tekan **Simpan transaksi**.

Satu input hanya boleh berisi satu transaksi. Jika ingin mencatat beberapa
transaksi, ulangi prosesnya satu per satu.

### Contoh kalimat yang dikenali

```text
Beli tepung terigu 2 karung total 250rb
Jual nasi goreng 10 porsi total 200rb
Pemasukkan hari ini 3 juta
Pelanggan bayar pesanan nasi kotak 300rb
```

Arah transaksi ditentukan oleh aturan, bukan tebakan model. Kalimat yang
ambigu, misalnya `transfer 500rb`, akan ditolak dengan pesan agar konteksnya
diperjelas.

## 3. Mencatat lewat suara

1. Pilih tab **Suara**.
2. Tekan tombol rekam dan ucapkan satu transaksi dengan jelas.
3. Hentikan rekaman.
4. Tunggu proses transkripsi dan normalisasi angka.
5. Periksa transkrip asli dan hasil yang sudah dirapikan.
6. Konfirmasi dan simpan seperti pada input teks.

Contoh ucapan:

```text
Kemarin beli tepung terigu dua karung total dua ratus lima puluh ribu
```

Angka lisan seperti `dua ratus lima puluh ribu` akan diubah menjadi `250000`.
Koreksi typo dibatasi agar tidak mengubah angka. Jika koreksi gagal, sistem
memakai normalisasi berbasis aturan.

Rekaman hanya diproses selama request dan tidak disimpan permanen. Transkrip
asli tetap ditampilkan agar Anda bisa membandingkannya dengan teks yang sudah
dinormalisasi.

## 4. Scan Nota

1. Pilih tab **Foto nota**.
2. Ambil foto dengan kamera belakang atau pilih file JPEG, PNG, atau WebP.
3. Tekan **Scan nota**.
4. Tunggu proses OCR dan ekstraksi.
5. Periksa nama toko, tanggal, dan rincian barang pada editor.
6. Perbaiki nama barang, quantity, unit, harga satuan, atau total barang bila
   perlu. Barang juga dapat ditambah atau dihapus.
7. Konfirmasi editor, lalu pilih kategori.

Hal yang perlu diketahui:

- Satu nota menghasilkan **satu transaksi induk**. Banyak barang pada nota
  disimpan sebagai rincian, bukan transaksi terpisah.
- Total transaksi dihitung dari jumlah total harga barang.
- Tanggal otomatis memakai tanggal lokal hari ini dan tetap bisa diubah.
- Nomor nota, subtotal, diskon, pajak, dan biaya layanan tidak disimpan untuk
  transaksi nota baru.
- Teks OCR tidak disimpan sebagai data transaksi atau cache lokal. Untuk
  keperluan audit, salinan terbatas (maksimal 20.000 karakter) dapat tercatat di
  tabel `audit_logs` dan ditandai jika terpotong.
- Jika sebagian item gagal dibaca, field yang tidak yakin dibiarkan kosong dan
  diberi peringatan. Periksa dan lengkapi secara manual.

Scan Nota paling cocok untuk nota cetak yang terang dan tidak terpotong. Nota
tulisan tangan, sangat pudar, atau bertata letak rumit dapat gagal dibaca.

## 5. Menambah transaksi manual

Gunakan tombol **Tambah manual** jika ingin mencatat tanpa memanggil model AI.

- Jenis transaksi, tanggal, dan nominal wajib diisi.
- Nama barang, quantity, unit, dan catatan opsional.
- Field kosong akan disimpan sebagai `null`.
- Saat memakai Supabase, perangkat harus online agar data benar-benar
  tersimpan di server.

## 6. Dialog konfirmasi dan kategori

Sebelum transaksi dikirim ke server, hasil ekstraksi selalu ditampilkan pada
dialog **Konfirmasi transaksi**. Dialog ini dapat mengubah:

- jenis transaksi (pemasukan/pengeluaran),
- tanggal,
- nominal,
- nama barang,
- quantity dan unit,
- catatan,
- kategori.

Jika nominal tidak terbaca dari input, dialog akan menampilkan peringatan dan
meminta Anda mengisinya sebelum menyimpan.

### Memilih kategori

Kategori membantu merapikan laporan usaha. Tersedia preset antara lain:

- Bahan baku
- Operasional
- Gaji karyawan
- Sewa
- Listrik & air
- Transportasi
- Perawatan alat
- Pajak
- Penjualan
- Jasa
- Pendapatan lain
- Modal usaha
- Lainnya
- Belum dikategorikan

Anda juga dapat menulis kategori sendiri pada input **Kategori lain**. Setiap
preset memiliki ikon agar mudah dibedakan, tetapi yang disimpan ke database
adalah nama kategorinya saja.

Tombol **Simpan transaksi** mewajibkan kategori. Tombol **Lewati kategori**
menyimpan kategori lama saat mengedit, atau `Belum dikategorikan` untuk
transaksi baru. Kategori selalu dapat diubah lagi lewat tombol **Edit**.

## 7. Riwayat, detail, dan edit

- Klik salah satu item riwayat untuk membuka detail transaksi.
- Detail menampilkan data transaksi, sumber input, waktu pencatatan, dan input
  asli.
- Tombol **Edit** memperbarui transaksi dengan ID yang sama.
- Tombol **Hapus** meminta konfirmasi sebelum menghapus satu transaksi.
- Perubahan langsung memperbarui ringkasan, riwayat, dan grafik.

Transaksi lama yang belum memiliki kategori akan tampil sebagai
`Belum dikategorikan` dan dapat dikategorikan saat diedit.

## 8. Filter dan ringkasan

Riwayat dan kartu ringkasan dapat difilter berdasarkan:

- minggu kalender Senin–Minggu,
- bulan,
- tahun,
- rentang tanggal khusus,
- seluruh data.

Filter **Kategori** berdiri sendiri dan hanya menyaring tampilan riwayat,
ringkasan, serta grafik. Pilihannya dibuat dari kategori yang benar-benar ada
pada riwayat akun Anda.

Panel **Ringkasan kategori** menjumlahkan pemasukan dan pengeluaran per
kategori pada periode aktif, diurutkan dari nominal terbesar, dan menampilkan
jumlah transaksi pada setiap baris.

Filter tidak menghapus atau mengubah data yang tersimpan. Perhitungan memakai
tanggal lokal agar tidak bergeser karena zona waktu UTC.

## 9. Grafik tren

Grafik menampilkan pemasukan (hijau) dan pengeluaran (merah) selama tujuh hari
kalender terakhir, termasuk hari ini.

- Hari tanpa transaksi tetap ditampilkan dengan nilai nol.
- Transaksi berjenis `unknown` tidak dimasukkan.
- Arahkan pointer, fokuskan dengan keyboard, atau tekan titik untuk melihat
  tanggal dan nominal.
- Tooltip dapat ditutup dengan tombol Escape atau klik di luar grafik.

## 10. Tema terang dan gelap

Tombol tema pada header berpindah antara tema terang dan gelap. Pilihan
disimpan di browser. Jika belum pernah memilih, aplikasi mengikuti preferensi
warna perangkat.

## 11. Memasang PWA

Pada browser yang mendukung, tombol **Pasang aplikasi** muncul di header.

- **Android/desktop**: tekan tombol tersebut, lalu setujui instalasi.
- **iPhone/iPad**: buka menu **Bagikan**, lalu pilih **Tambahkan ke Layar
  Utama**.

Tombol tidak ditampilkan jika aplikasi sudah berjalan dalam mode standalone.

### Offline

Service worker hanya menyimpan application shell dan aset statis. Saat offline:

- riwayat yang sudah ada di cache masih dapat dibaca,
- inferensi AI dan operasi Supabase dinonaktifkan,
- tambah, edit, dan hapus tidak diantrekan diam-diam.

Database tetap menjadi sumber utama. `localStorage` hanya cache tampilan
maksimal 50 transaksi per akun. Cache lama tanpa pemilik tidak diimpor otomatis.

## 12. Hal yang tidak disimpan

Demi privasi, CatatKas tidak menyimpan:

- rekaman suara,
- foto nota,
- teks OCR sebagai data transaksi,
- temporary path,
- token atau password,
- output mentah model.

Foto dan audio hanya dipakai selama proses berlangsung, lalu dihapus. Satu-
satunya salinan teks OCR di database adalah metadata audit yang dibatasi
20.000 karakter dan hanya dipakai untuk penelusuran masalah.

## 13. Jika terjadi masalah

| Masalah | Yang bisa dicoba |
|---|---|
| Tombol mikrofon tidak muncul | Akses mikrofon membutuhkan HTTPS, bukan HTTP alamat IP. |
| Hasil suara tidak terbaca | Rekam ulang di tempat yang lebih tenang dan ucapkan satu transaksi dengan jelas. |
| Nota gagal dipindai | Pastikan foto terang, tidak buram, tidak terpotong, dan merupakan nota cetak. |
| Nominal kosong | Isi nominal secara manual pada dialog konfirmasi. |
| Data tidak tersimpan | Pastikan perangkat online dan backend dapat diakses. |
| Aplikasi menampilkan versi lama | Unregister service worker dan bersihkan site data melalui DevTools. |

Untuk masalah instalasi atau database, lihat
[Panduan instalasi dan konfigurasi](instalasi.md).
