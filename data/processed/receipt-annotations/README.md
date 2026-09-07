# Anotasi nota nyata

Perintah `python -m src.prepare_receipt_dataset ocr` membuat satu file JSON untuk
setiap gambar nota. Nilai `output` yang dibuat parser hanyalah rancangan awal dan
bukan ground truth.

Sebelum data boleh masuk ke training:

1. bandingkan `ocr.text` dan `output` dengan gambar asli;
2. koreksi nama toko, tanggal, rincian barang, quantity, satuan, harga, dan total;
3. isi `template_id` hanya jika beberapa gambar benar-benar berasal dari template
   nota yang sama;
4. ubah `annotation_status` dari `pending_review` menjadi `verified`.

Jangan mengubah `receipt_id`, `source_image`, atau `source_sha256`. Jika gambar
diganti, jalankan OCR lagi agar anotasi baru memiliki checksum yang sesuai.
