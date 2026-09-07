# Folder gambar nota

Letakkan foto atau soft-copy nota ke salah satu folder berikut:

- `train/` untuk data pelatihan;
- `validation/` untuk pemantauan selama pelatihan;
- `evaluation/` untuk evaluasi akhir yang tidak ikut dilatih.

Format yang didukung adalah JPEG, PNG, dan WebP. File gambar dalam folder ini
diabaikan Git. Jangan menaruh token, file `.env`, atau data pribadi yang tidak
diperlukan dalam gambar.

Setelah gambar ditambahkan, jalankan dari root repository:

```powershell
python -m src.prepare_receipt_dataset ocr --reference-date 2026-08-31
```

Periksa berkas yang dibuat di `data/processed/receipt-annotations`, koreksi bagian
`output` berdasarkan gambar asli, lalu ubah `annotation_status` menjadi `verified`.
Setelah itu jalankan:

```powershell
python -m src.prepare_receipt_dataset build
```

Jangan mengedit `receipt-real-*.jsonl` secara langsung karena file tersebut dibuat
ulang dari anotasi saat perintah `build` dijalankan.
