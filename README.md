# JESCA (Jessica Assets) — Asset Management System

**JESCA (Jessica Assets)** adalah sistem web manajemen aset, inventaris, dan pengadaan modern berbasis **Python Flask**, **SQLite (Flask-SQLAlchemy)**, dan **Bootstrap 5**.

Dirancang dengan arsitektur modular, ringan, aman, dan siap produksi (*production-ready*), JESCA menyediakan solusi menyeluruh mulai dari pendaftaran aset, pemeliharaan teknis, sirkulasi peminjaman, pengadaan barang (*Purchase Order*), hingga pelaporan audit dan notifikasi otomatis.

---

## 🚀 Fitur Utama & Keunggulan

### 1. 🔐 Keamanan & Hak Akses Berbasis Peran (RBAC)
- **4 Role Pengguna Terisolasi**:
  - **Admin**: Akses penuh (Pengaturan sistem, backup/restore, kelola akun, approval PO).
  - **Staff**: Pengajuan aset, pengajuan PO, peminjaman barang, dan transfer lokasi.
  - **Auditor**: Pemeriksaan log, laporan audit periode, dan ekspor data (read-only).
  - **Teknisi**: Workbench pemeliharaan aset (`/maintenance`), eksekusi perbaikan, dan upload bukti servis.
- **Proteksi Brute-force & Rate Limiting**: Penguncian akun otomatis setelah percobaan login gagal berturut-turut.
- **Sesi Otomatis**: Session timeout dengan peringatan dini sebelum sesi berakhir.
- **Keamanan Kredensial**: Hashing password modern via Werkzeug dan deteksi password default bawaan di dashboard.

### 2. ⚡ Dynamic SMTP, Keamanan Jaringan &amp; Domain Kustom (`/settings`)
- **Konfigurasi Email Tanpa Restart**: Pengaturan SMTP (Gmail, Hostinger, Outlook, Mailgun, cPanel, atau SMTP bisnis internal kantor) dapat diubah langsung dari UI web tanpa menyentuh file server atau restart instance.
- **Proteksi Perimeter IP &amp; VPN Whitelist**: Kunci akses aplikasi ke jaringan kantor atau subnet VPN internal (mendukung single IP seperti `103.160.95.2` dan CIDR subnet seperti `192.168.1.0/24`, `10.8.0.0/24`). User di luar jaringan yang sah akan otomatis diarahkan ke halaman **403 Network Access Denied**.
- **Domain Kustom &amp; Enforce HTTPS**: Tentukan domain publik resmi (contoh: `https://assets.perusahaan.com`) agar tautan QR Code dan tautan email notifikasi otomatis mengarah ke domain tersebut. Opsi **Enforce HTTPS** otomatis mengalihkan request HTTP biasa ke protokol aman HTTPS (301 Permanent Redirect).
- **Background Dispatcher (Asinkron)**: Pengiriman notifikasi email berjalan di latar belakang menggunakan *thread* terpisah, sehingga tidak memperlambat respon aplikasi.
- **Uji Koneksi Instan (Live Test)**: Tombol pengujian koneksi, handshake port TLS/SSL, dan kredensial langsung ke email tujuan.
- **Diagnostik Kesehatan Sistem**: Pemantauan kapasitas file database SQLite, deteksi IP klien real-time, jumlah baris data, dan informasi runtime (Docker vs Local).
- **Trigger Otomatis**:
  - Peringatan email instan saat status aset diubah menjadi **Rusak** atau **Afkir**.
  - Notifikasi email otomatis ke Administrator saat ada pengajuan **Purchase Order Baru**.

### 3. 📦 Alur Pengadaan Barang (Purchase Order Workflow)
- **Siklus Status PO Terstruktur**: `DRAFT` &rarr; `SUBMITTED` &rarr; `APPROVED` &rarr; `ORDERED` &rarr; `RECEIVED` &rarr; `CONVERTED` / `CANCELLED`.
- **Wajib Upload Bukti Fisik**:
  - Upload bukti pemesanan (*Order Proof / Invoice DP*) saat status `ORDERED`.
  - Wajib upload Surat Jalan / Bukti Terima Fisik (BAST) sebelum unit PO bisa dikonversi menjadi aset resmi.
- **Anti-Inflasi Harga**: Parsing presisi format mata uang Rupiah (`Rp 10.200.000` &rarr; `10200000.0`).
- **Jejak Audit PO**: Riwayat perjalanan status per PO tercatat lengkap di tabel `po_histories`.

### 4. 🛠️ Pemeliharaan Aset & Teknisi Workbench (`/maintenance`)
- Antarmuka khusus Teknisi untuk menangani antrean aset yang perlu diservis.
- Perubahan status otomatis ke `Dalam Perbaikan` saat teknisi mulai bekerja.
- Penyelesaian servis disertai input biaya perbaikan, tindakan servis, upload bukti nota, serta perpanjangan otomatis tanggal servis berikutnya.

### 5. 🏷️ Auto-Coding & QR Code Scanner
- **Auto-Generate Kode Real-Time**: `<Prefix>/<3-Digit Sequential Number>` (contoh: `Tech/001`, `Tools/001`, `Furn/001`, `Vehicle/001`, `Office/001`).
- **QR Code Terintegrasi**: QR Code otomatis dibuat per aset untuk dicetak pada label fisik.
- **Kamera Scanner**: Scan QR Code langsung melalui kamera browser laptop/smartphone via `html5-qrcode`.
- **Halaman Scan Publik Ringkas**: `/scan/<asset_code>` untuk audit dan verifikasi cepat barang di lapangan.

### 6. 📊 Nilai Buku, Depresiasi & Sirkulasi Peminjaman
- **Metode Garis Lurus (Straight-Line Depreciation)**: Perhitungan nilai buku aset terkini secara otomatis berdasarkan masa manfaat (*useful life*) dan nilai residu.
- **Riwayat Sirkulasi Peminjaman**: Pencatatan lengkap nama peminjam, tanggal keluar, tanggal kembali, dan durasi hari peminjaman (`asset_circulation_logs`).
- **Alert Keterlambatan**: Notifikasi peringatan aset yang terlambat dikembalikan pada ikon lonceng navbar.

### 7. 📑 Ekspor & Laporan Profesional
- **Ekspor PDF Formal**: Landscape A4 rapi, penataan tabel presisi, warna aksen elegan pada judul tabel, tanpa emoji, dan kop resmi.
- **Ekspor CSV Kompatibel Excel**: Encoding UTF-8 dengan BOM (`\ufeff`) dan delimiter rapi yang langsung terbagi ke kolom masing-masing di Microsoft Excel.
- **Laporan Audit Terpisah**: Laporan berbasis rentang tanggal periode (`/reports/audit`) khusus untuk kepatuhan dan audit internal.

### 8. 🎨 Multi-Tema & Desain Responsif
- 5 Pilihan Tema Tampilan: **Light**, **Dark Mode (Midnight Slate)**, **Sakura Pink**, **Forest Green**, dan **Ocean Blue**.
- **Avatar Profil Solid**: Huruf avatar profil dan foto pengguna tetap tajam dan kontras tinggi di semua mode tema.
- **Foto Profil Pengguna**: Dukungan unggah foto profil mandiri maupun melalui pengelolaan akun admin.

---

## 🛠️ Cara Menjalankan Aplikasi

### Cara 1: Menggunakan Docker (Sangat Direkomendasikan)

Pastikan Docker & Docker Compose sudah terpasang, lalu jalankan:

```bash
docker compose up -d --build
```

Buka peramban (browser) dan akses:
```
http://localhost:5000
```

Untuk menghentikan:
```bash
docker compose down
```

---

### Cara 2: Menjalankan Secara Lokal (Python Virtual Environment)

1. **Buat Virtual Environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Di Linux/macOS
   # venv\Scripts\activate   # Di Windows
   ```

2. **Pasang Dependensi:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Jalankan Aplikasi:**
   ```bash
   python app.py
   ```
   *Atau dengan Gunicorn di lingkungan produksi:*
   ```bash
   gunicorn --bind 0.0.0.0:5000 app:app
   ```

4. **Akses Aplikasi:**
   ```
   http://localhost:5000
   ```

---

## 🔑 Kredensial Pengujian Bawaan

| Username | Password Default | Peran (Role) | Hak Akses |
|---|---|---|---|
| `Admin` | `Admin123` | **Admin** | Akses penuh (Pengaturan sistem, backup, akun, PO) |
| `staff1` | `staff123` | **Staff** | Input aset, pinjam barang, pengajuan PO |
| `auditor` | `audit123` | **Auditor** | Laporan audit, ekspor inventaris (read-only) |
| `teknisi` | `teknisi123` | **Teknisi** | Pemeliharaan & servis aset (`/maintenance`) |

> **Catatan Keamanan:** Segera ganti password akun Administrator setelah instalasi awal melalui menu profil di pojok kanan atas.

---

## 📂 Struktur Direktori Proyek

```
jesca-assets/
├── app.py                     # Inti aplikasi Flask (Model, Routing, Dynamic SMTP, RBAC)
├── requirements.txt           # Daftar dependensi Python
├── Dockerfile                 # Konfigurasi container Docker
├── docker-compose.yml         # Konfigurasi orkestrasi & Volume Mapping
├── .env.example               # Contoh konfigurasi environment
├── README.md                  # Dokumentasi resmi proyek
├── data/                      # Direktori persisten database SQLite (jesca.db)
├── backups/                   # Direktori arsip pencadangan database
├── static/
│   ├── css/
│   │   └── style.css          # Styling kustom Bootstrap 5, palet multi-tema & animasi
│   ├── js/
│   │   └── app.js             # Skrip frontend, shortcut keyboard, QR scanner, tema
│   ├── uploads/
│   │   └── avatars/           # Foto profil pengguna
│   └── attachments/
│       ├── po/                # Bukti dokumen pengadaan PO (Surat Jalan/BAST/Invoice)
│       └── maintenance/       # Bukti servis & nota reparasi teknisi
└── templates/
    ├── base.html              # Template induk, sidebar dinamis, navbar & modal global
    ├── login.html             # Halaman autentikasi aman
    ├── dashboard.html         # Dashboard analitik, valuasi, Chart.js & peringatan
    ├── assets.html            # Manajemen inventaris, filter kategori, auto-coding & modal CRUD
    ├── maintenance.html       # Workbench servis teknisi & log riwayat pemeliharaan
    ├── purchase_orders.html   # Daftar manajemen Purchase Order
    ├── purchase_order_detail.html # Detail PO, timeline persetujuan, upload bukti & konversi unit
    ├── purchase_order_form.html   # Form pembuatan & pengeditan PO
    ├── settings.html          # Pengaturan Dynamic SMTP, IP Whitelist, HTTPS & Diagnostik Sistem
    ├── 403_network.html       # Halaman blokir akses jika IP di luar Whitelist / VPN
    ├── accounts.html          # Pengelolaan akun pengguna, peran & REST API key
    ├── audit_report.html      # Laporan audit kepatuhan periode
    ├── history.html           # Riwayat log aktivitas operasional dengan sticky header
    ├── vendors.html           # Manajemen data rekanan & vendor supplier
    ├── sites.html             # Manajemen cabang lokasi fisik aset
    └── admin_backups.html     # Manajemen backup & restore database
```

---

## 📄 Hak Cipta & Pengembang

Dikembangkan dengan dedikasi untuk sistem inventaris aset yang modern, transparan, dan akuntabel.

&copy; 2026 **JESCA** &bull; Jessica Assets Management System  
*Contributors: Loraxsian &amp; Jessica Nova Lya Mendrofa*
