# JESCA (Jessica Assets) - Asset Management System

JESCA (Jessica Assets) adalah aplikasi web manajemen aset dan inventaris yang dibuat menggunakan Python Flask, SQLite (Flask-SQLAlchemy), dan Bootstrap 5. 

Aplikasi ini awalnya dirancang untuk mempermudah pencatatan aset kantor, pelacakan peminjaman barang, pengelolaan jadwal servis rutin teknisi, hingga alur pengadaan barang (Purchase Order) agar semuanya rapi, terdokumentasi, dan punya jejak audit yang jelas.

---

## Fitur Utama

### 1. Manajemen Inventaris Aset
- Pencatatan data aset lengkap: nama, kategori, lokasi penempatan, tanggal beli, harga perolehan, foto barang, serta vendor supplier.
- Pembuatan kode aset otomatis (auto-coding) sesuai kategori (contoh: Tech/001, Tools/001, Furn/001, Vehicle/001, Office/001) atau bisa diisi manual jika kantor sudah punya format kode sendiri.
- Pembuatan QR Code otomatis untuk setiap aset yang bisa dicetak langsung ke stiker label.
- Fitur scan QR Code langsung lewat kamera laptop atau HP (menggunakan library html5-qrcode).
- Halaman ringkasan publik (/scan/<kode_aset>) untuk mempermudah pengecekan fisik barang di lapangan tanpa perlu login jika hanya ingin melihat status barang.
- Perhitungan depresiasi otomatis menggunakan metode garis lurus (Straight-Line Depreciation) untuk mengetahui perkiraan nilai buku aset saat ini.
- Riwayat sirkulasi peminjaman dan pengembalian barang, lengkap dengan notifikasi jika ada barang yang telat dikembalikan lebih dari 7 hari.
- Riwayat perpindahan lokasi atau cabang (Asset Transfer Log).

### 2. Alur Servis & Pemeliharaan Teknisi (/maintenance)
- Tata kelola servis yang bertahap dan teratur demi akuntabilitas data:
  1. Status Mendekati / Jatuh Tempo Servis.
  2. Mulai Servis oleh Teknisi (status barang otomatis berubah jadi "Dalam Perbaikan").
  3. Selesaikan Servis & Bukti (teknisi mengisi tindakan yang diambil, biaya suku cadang/jasa, tanggal pengerjaan, upload berkas bukti nota/invoice, dan jadwal servis periode berikutnya otomatis dihitung ulang).
- Pemisahan hak akses: Staf biasa tidak bisa langsung menandai servis selesai. Staf disediakan tombol "Lapor Kendala Aset" untuk mengirimkan keluhan kerusakan ke antrean teknisi.
- Alert lonceng dan banner dashboard otomatis bersih begitu barang mulai diservis maupun setelah servis diselesaikan.

### 3. Alur Pengadaan Barang (Purchase Order Workflow)
- Siklus pengajuan bertahap: Draft -> Diajukan (Submitted) -> Disetujui Admin (Approved) -> Dipesan ke Vendor (Ordered) -> Barang Diterima (Received) -> Dikonversi Menjadi Aset Resmi (Converted).
- Wajib melampirkan berkas bukti fisik (invoice DP saat status pemesanan, dan Surat Jalan / BAST saat barang sampai) sebelum unit bisa masuk ke daftar aset.
- Riwayat persetujuan tercatat lengkap pada timeline audit Purchase Order.

### 4. Hak Akses Pengguna (Role-Based Access Control / RBAC)
Sistem membagi pengguna ke dalam 4 peran yang memiliki batas wewenang masing-masing:
- Admin / Administrator: Punya akses menyeluruh ke semua menu, persetujuan PO, backup database, kelola user, dan pengaturan sistem.
- Staff: Bisa mendaftarkan aset baru, mengajukan PO, meminjam/mengembalikan aset, dan melaporkan barang rusak.
- Teknisi: Khusus menangani perbaikan aset, konfirmasi mulai pengerjaan servis, mengunggah bukti selesai servis, dan memantau laporan kendala perangkat.
- Auditor: Akses read-only untuk melihat laporan rekapitulasi, jejak riwayat log aktivitas, dan melakukan ekspor data.

### 5. Riwayat, Laporan & Masukan (/feedbacks)
- Submenu Laporan & Masukan di kelompok menu Riwayat & Laporan untuk menampung aduan dari publik di halaman login (misalnya lupa akun atau laporan bug sistem), serta laporan kendala fisik aset dari staf.
- Admin dan Teknisi bisa meninjau aduan, mengubah status penanganan, dan mencatat solusi tindakan yang sudah dilakukan.
- Log Aktivitas dan Laporan Audit Kepatuhan untuk meninjau riwayat mutasi dan aktivitas operasional.

### 6. Ekspor Data Terpadu (1 Menu Pilihan Format)
- Menu "Export Data" terpadu dalam satu dialog modal praktis dengan 3 opsi format unduhan:
  - Ekspor Excel Asli (.xlsx): Menggunakan pustaka openpyxl dengan penyesuaian lebar kolom otomatis (auto-fit), format angka ribuan Rupiah, dan header warna navy.
  - Ekspor PDF Formal: Menggunakan ReportLab dengan layout landscape A4 yang rapi dan siap cetak untuk laporan bulanan/tahunan.
  - Ekspor CSV Kompatibel Excel: Format UTF-8 dengan BOM agar tanda baca dan angka tidak berantakan saat dibuka di Microsoft Excel.

### 7. Keamanan, Pengaturan Sistem & Ketahanan Aplikasi
- Sudo Mode: Konfirmasi password ulang saat membuka menu Pengaturan Sistem (/settings) demi keamanan jika laptop ditinggal sebentar di meja kantor.
- Penyederhanaan Akses Jaringan & Deteksi Jaringan Kantor: Pengguna dapat memilih 3 mode koneksi dengan 1 klik (Komputer Sendiri, Jaringan Lokal Kabel LAN / Wi-Fi, atau Domain Sendiri/VPS). Tersedia tombol "Cek Ulang IP Jaringan" untuk mendeteksi ulang alamat IP komputer secara otomatis jika router me-restart atau kabel LAN dipindahkan.
- Uji Coba Akses Luar Otomatis (Tunnel Instan 1-Klik): Sistem dapat membuatkan tautan internet sementara yang aman (HTTPS) secara otomatis langsung dari dalam aplikasi tanpa perlu membeli domain atau membuka terminal. Dilengkapi keterangan lengkap fungsi tautan, batas waktu aktif (expired), dan tombol salin/terapkan ke Base URL.
- Dynamic SMTP: Pengaturan server email (Gmail, cPanel, Outlook, dsb.) bisa diubah langsung dari halaman web tanpa perlu restart aplikasi.
- IP Whitelist & VPN Access: Pembatasan akses web hanya untuk jaringan kantor atau VPN internal tertentu.
- Mode SQLite WAL & Busy Timeout: Menggunakan Write-Ahead Logging (WAL) dan timeout antrean 30 detik untuk mencegah error database terkunci saat banyak aksi dijalankan bersamaan.
- Halaman Error Ramah & Auto-Rollback: Jika terjadi gangguan tak terduga, sistem tidak menampilkan layar putih error server, melainkan halaman kustom JESCA dengan tombol kembali yang aman dan otomatis membatalkan transaksi database (rollback) agar data tidak rusak.
- Proteksi brute-force login dan penggantian password default otomatis pada login pertama.

### 8. Tur Interaktif Tanda Tunjuk & Panduan Sistem
- Tur Interaktif (Spotlight Tour): Panduan visual langsung dengan sorotan tanda tunjuk ke tombol dan menu utama (bilah navigasi modul, kamera QR Code, tombol tambah aset baru, lonceng notifikasi, dan shortcut Ctrl+K) agar pengguna awam langsung paham apa yang harus ditekan.
- Buku Panduan Modul: Ringkasan lengkap peran pengguna (RBAC), alur pengadaan barang (PO), meja kerja servis teknisi, dan ekspor laporan yang dapat dibuka kembali kapan saja via menu "Panduan Sistem".

### 9. Sinkronisasi Stok Opname Lapangan Offline (IndexedDB Background Sync)
- Petugas di area buta sinyal (seperti gudang bawah tanah atau ruang server tertutup) tetap dapat melakukan scan QR Code aset dan mencatat verifikasi fisik stok opname.
- Data verifikasi disimpan sementara di penyimpanan browser menggunakan IndexedDB tanpa memerlukan koneksi internet aktif.
- Begitu perangkat kembali terhubung ke internet, sistem secara otomatis menyinkronkan seluruh antrean data opname ke server di latar belakang tanpa mengganggu alur kerja pengguna.

---

## Cara Menjalankan Aplikasi

### Cara 1: Menggunakan Docker (Paling Praktis)

Pastikan Docker dan Docker Compose sudah terpasang di komputer/server Anda, lalu buka terminal dan jalankan:

```bash
docker compose up -d --build
```

Setelah proses selesai, buka browser dan akses:
```
http://localhost:5000
```

Untuk menghentikan aplikasi:
```bash
docker compose down
```

---

### Cara 2: Menjalankan Secara Manual (Python Virtual Environment)

1. Buat dan aktifkan virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate    # Di Linux / macOS
   # venv\Scripts\activate     # Di Windows
   ```

2. Pasang semua dependensi yang dibutuhkan:
   ```bash
   pip install -r requirements.txt
   ```

3. Jalankan aplikasi:
   ```bash
   python app.py
   ```
   Atau jika menggunakan Gunicorn di server Linux:
   ```bash
   gunicorn --bind 0.0.0.0:5000 app:app
   ```

4. Buka browser di alamat:
   ```
   http://localhost:5000
   ```

---

## Akun Awal (Bawaan)

Saat pertama kali dipasang, database berada dalam kondisi bersih tanpa data uji coba atau aset sampel. Sistem secara otomatis menyiapkan satu akun Administrator default:

- Username: `Admin`
- Password: `Admin123`

Catatan Keamanan:  
Saat pertama kali login dengan password bawaan ini, sistem akan langsung meminta Anda membuat password baru yang aman. Setelah masuk, Anda bisa membuatkan akun untuk staf, teknisi, atau auditor melalui menu Kelola Akun (/accounts).

---

## Struktur Folder Proyek

```
jesca-assets/
├── app.py                     # File utama aplikasi (routing, database model, logika bisnis)
├── requirements.txt           # Daftar pustaka Python yang digunakan
├── Dockerfile                 # Konfigurasi container Docker
├── docker-compose.yml         # Konfigurasi orkestrasi container dan volume penyimpanan
├── .env.example               # Contoh pengaturan environment variabel
├── README.md                  # Dokumentasi proyek
├── data/                      # Folder penyimpanan database SQLite (jesca.db)
├── backups/                   # Folder arsip backup database otomatis dan manual
├── static/
│   ├── css/
│   │   └── style.css          # Kustomisasi styling dan tema tampilan
│   ├── js/
│   │   └── app.js             # Skrip interaksi UI, scanner QR, dan shortcut keyboard
│   ├── uploads/
│   │   └── avatars/           # Foto profil pengguna
│   └── attachments/
│       ├── po/                # Dokumen pendukung Purchase Order (invoice, surat jalan)
│       └── maintenance/       # Bukti foto/nota servis dari teknisi
└── templates/
    ├── base.html              # Template induk (layout, navbar, sidebar)
    ├── 404.html               # Halaman kustom jika URL tidak ditemukan
    ├── 500.html               # Halaman kustom penanganan gangguan server
    ├── login.html             # Halaman masuk sistem
    ├── dashboard.html         # Ringkasan statistik inventaris dan grafik
    ├── assets.html            # Halaman utama daftar aset dan pencarian
    ├── maintenance.html       # Meja kerja servis teknisi
    ├── purchase_orders.html   # Daftar pengadaan barang
    ├── purchase_order_detail.html # Detail transaksi PO dan upload bukti terima
    ├── feedbacks.html         # Pengelolaan laporan bug dan masukan pengguna
    ├── settings.html          # Pengaturan SMTP, IP Whitelist, dan diagnostik
    ├── accounts.html          # Pengelolaan akun pengguna dan role
    └── ...
```

---

## Rencana Pengembangan Selanjutnya (Roadmap)

Untuk pengembangan sistem ke depannya (rencana rilis versi besar selanjutnya), beberapa ide dan masukan operasional yang telah kami catat meliputi:

1. Efisiensi Media & Penyimpanan (Storage Management):
   - Kompresi gambar otomatis menggunakan pustaka Pillow di Python.
   - Mengubah ukuran foto aset, bukti nota servis, dan surat jalan secara otomatis ke resolusi maksimal 1080p serta konversi ke format modern WebP agar menghemat kapasitas disk server hingga 80-90% dan mempercepat loading di HP.

2. Webhook & Notifikasi Cepat Tim:
   - Integrasi Webhook ke grup Telegram Bot atau Slack agar teknisi dan admin langsung mendapat notifikasi instan saat ada staf yang melaporkan barang rusak atau saat ada pengajuan Purchase Order baru.

3. Logika Pemeliharaan Pintar (Smart Maintenance):
   - Menambahkan deteksi otomatis untuk aset yang terlalu sering rusak (misalnya dilaporkan rusak lebih dari 3 kali dalam 2 bulan).
   - Sistem akan menandai aset tersebut sebagai prioritas kritis dan memberikan saran ke Admin untuk mempertimbangkan pengadaan unit baru (replacement) daripada terus mengeluarkan biaya servis rutin.

4. Verifikasi Dua Langkah (2FA / TOTP):
   - Penambahan opsi keamanan login 2FA menggunakan aplikasi authenticator (seperti Google Authenticator) khusus untuk akun Admin, terutama saat mengakses menu pengaturan sistem atau menyetujui Purchase Order bernilai besar.

5. Struktur Lokasi Bertingkat (Hierarchical Multi-Location):
   - Mengembangkan struktur lokasi fisik aset yang bercabang/nested (contoh: Kantor Pusat -> Lantai 3 -> Ruang IT -> Rak Server A) untuk mempermudah pencarian aset berukuran kecil.

6. Sinkronisasi Stok Opname Lapangan Offline (Selesai pada v2.5.5):
   - Fitur scan QR dan pencatatan kondisi fisik barang saat stok opname di area tanpa sinyal telah diimplementasikan menggunakan IndexedDB browser lokal dan otomatis sinkron saat online kembali di latar belakang.

7. Optimalisasi Database Skala Besar (status: soon / rencana ke depan):
   - Opsi migrasi dari SQLite ke database server seperti PostgreSQL atau MySQL jika jumlah aset sudah mencapai puluhan ribu dan pengguna aktif bersamaan semakin banyak.
   - Pemanfaatan caching (seperti Redis) untuk data analitik dashboard dan token sesi.

8. Pemisahan Arsitektur Kode (Flask Blueprint):
   - Restrukturisasi file utama app.py menjadi modul-modul terpisah (routes, models, services) menggunakan Flask Blueprints agar kode lebih rapi dan bebas konflik saat dikembangkan bersama tim developer di Git.

---

## Kontributor

Aplikasi ini dikembangkan untuk menyediakan sistem inventaris yang mudah digunakan, transparan, dan dapat dipertanggungjawabkan.

Jessica Assets Management System (JESCA) - 2026  
Pengembang: Loraxsian & And Jessica Nova Lya Mendrofa
