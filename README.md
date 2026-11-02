# JESCA (Jessica Assets) — Asset Management System

**JESCA (Jessica Assets)** adalah sistem web manajemen aset, inventaris, dan pengadaan modern berbasis **Python Flask**, **SQLite (Flask-SQLAlchemy)**, dan **Bootstrap 5**.

Dirancang dengan arsitektur modular, ringan, aman, dan siap produksi (*production-ready*), JESCA menyediakan solusi menyeluruh mulai dari pendaftaran aset, pemeliharaan teknis, sirkulasi peminjaman, pengadaan barang (*Purchase Order*), hingga pelaporan audit dan notifikasi otomatis.

---

## 🚀 Fitur Utama & Keunggulan

### 1. 🔐 Keamanan & Hak Akses Berbasis Peran (RBAC)
- **4 Role Pengguna Terisolasi & Terverifikasi**:
  - **Admin / Administrator**: Akses penuh (Pengaturan sistem, backup/restore, kelola akun, persetujuan PO, resolusi laporan masukan/bug publik).
  - **Staff**: Pengajuan aset baru, pengajuan PO, peminjaman/pengembalian barang, transfer lokasi/site, dan **Lapor Kendala Aset**. *Catatan Integritas: Staf tidak diperkenankan memulai servis maupun menyelesaikan status perbaikan secara langsung tanpa verifikasi teknis.*
  - **Teknisi**: Workbench operasional pemeliharaan aset (`/maintenance`), konfirmasi eksekusi perbaikan ("Mulai Servis"), penyelesaian servis berdokumen bukti ("Selesaikan Servis & Bukti"), serta menerima lonceng notifikasi kendala perangkat & laporan bug sistem.
  - **Auditor**: Pemeriksaan log aktivitas, laporan audit kepatuhan periode, dan ekspor data (read-only tanpa izin modifikasi).
- **Proteksi Brute-force & Rate Limiting**: Penguncian akun otomatis setelah percobaan login gagal berturut-turut.
- **Sesi Otomatis**: Session timeout dengan peringatan dini sebelum sesi berakhir.
- **Sudo Mode (Step-Up Authentication)**: Konfirmasi kata sandi ulang otomatis saat mengakses menu Pengaturan Sistem (`/settings`). Sesi verifikasi aktif selama 15 menit dengan tombol kunci manual instan demi mencegah akses tidak sah jika laptop ditinggalkan tanpa pengawasan (*unattended laptop*).
- **Keamanan Kredensial**: Hashing password modern via Werkzeug dan deteksi password default bawaan di dashboard.

### 2. ⚡ Dynamic SMTP, Jaringan, Domain &amp; Pembaruan Otomatis (`/settings`)
- **Pembaruan Sistem Mandiri (Safe Self-Updater)**:
  - Pengecekan versi rilis terbaru dari repositori GitHub secara otomatis (mendukung 3-layer fallback: GitHub Releases &rarr; Tags &rarr; SemVer comparator).
  - Eksekusi pembaruan 1-klik (*One-Click Update*): Menjalankan `git pull`, update pustaka `pip install`, dan *graceful reload* proses Gunicorn (`SIGHUP`) tanpa *downtime*.
  - Jaminan *Safe Mode*: Database SQLite (`jesca.db`) dan seluruh file bukti lampiran/foto tetap utuh dan aman.
  - Log proses *real-time* ditampilkan di terminal mini web.
- **Konfigurasi Email Tanpa Restart**: Pengaturan SMTP (Gmail, Hostinger, Outlook, Mailgun, cPanel, atau SMTP bisnis internal kantor) dapat diubah langsung dari UI web tanpa menyentuh file server atau restart instance.
- **Proteksi Perimeter IP &amp; VPN Whitelist**: Kunci akses aplikasi ke jaringan kantor atau subnet VPN internal (mendukung single IP seperti `103.160.95.2` dan CIDR subnet seperti `192.168.1.0/24`, `10.8.0.0/24`). User di luar jaringan yang sah akan otomatis diarahkan ke halaman **403 Network Access Denied**.
- **Domain Kustom &amp; Enforce HTTPS**: Tentukan domain publik resmi (contoh: `https://assets.perusahaan.com`) agar tautan QR Code dan tautan email notifikasi otomatis mengarah ke domain tersebut. Opsi **Enforce HTTPS** otomatis mengalihkan request HTTP biasa ke protokol aman HTTPS (301 Permanent Redirect).
- **Background Dispatcher (Asinkron)**: Pengiriman notifikasi email berjalan di latar belakang menggunakan *thread* terpisah, sehingga tidak memperlambat respon aplikasi.
- **Uji Koneksi Instan (Live Test)**: Tombol pengujian koneksi, handshake port TLS/SSL, dan kredensial langsung ke email tujuan di tab yang sama.
- **Diagnostik Kesehatan Sistem**: Pemantauan kapasitas file database SQLite, deteksi IP klien real-time, jumlah baris data relasional, dan informasi runtime (Docker vs Local).
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

### 4. 🛠️ Tata Kelola Pemeliharaan Aset & Teknisi Workbench (`/maintenance`)
- **Alur Perbaikan Berintegritas (Strict Workflow)**:
  - Alur wajib bertahap demi akuntabilitas: **Jatuh Tempo** &rarr; **Mulai Servis** (status aset berubah menjadi `Dalam Perbaikan`) &rarr; **Selesaikan Servis & Bukti** (pencatatan tindakan teknis, biaya suku cadang/jasa, bukti invoice/nota, serta kalkulasi otomatis tanggal servis periode berikutnya).
  - Shortcut penyelesaian langsung tanpa pengerjaan telah ditiadakan agar seluruh proses servis dapat dipertanggungjawabkan dalam audit.
- **Pemisahan Otoritas Staf & Teknisi**:
  - Tombol aksi eksekusi pemeliharaan diproteksi ketat hanya untuk role **Teknisi** dan **Admin**.
  - Pengguna dengan role **Staff** disediakan tombol khusus **Lapor Kendala Aset** untuk meneruskan kendala fisik barang secara langsung ke antrean notifikasi teknisi tanpa dapat mengubah status operasional aset secara sepihak.

### 5. 💬 Pusat Laporan, Bug & Masukan Sistem (`/feedbacks`)
- **Pusat Pengaduan & Masukan Terintegrasi**:
  - Menerima aduan dari form login publik (`/submit-feedback`), kendala fisik aset dari staf lapangan, laporan bug teknis, serta saran pengembangan fitur.
  - Submenu khusus **Laporan & Masukan** di sidebar utama untuk **Admin** dan **Teknisi**, lengkap dengan kartu statistik resolusi, filter kategori, tab status *Pending* vs *Resolved*, dan riwayat nama petugas penangan beserta catatan tindakan solusinya.
- **Penyaluran Notifikasi Real-Time**:
  - Alert lonceng notifikasi navbar menyala otomatis saat ada aduan baru masuk, dilengkapi pintasan langsung ke menu manajemen laporan.

### 6. 🏷️ Auto-Coding & QR Code Scanner
- **Auto-Generate Kode Real-Time**: `<Prefix>/<3-Digit Sequential Number>` (contoh: `Tech/001`, `Tools/001`, `Furn/001`, `Vehicle/001`, `Office/001`).
- **QR Code Terintegrasi**: QR Code otomatis dibuat per aset untuk dicetak pada label fisik.
- **Kamera Scanner**: Scan QR Code langsung melalui kamera browser laptop/smartphone via `html5-qrcode`.
- **Halaman Scan Publik Ringkas**: `/scan/<asset_code>` untuk audit dan verifikasi cepat barang di lapangan.

### 7. 📊 Nilai Buku, Depresiasi & Sirkulasi Peminjaman
- **Metode Garis Lurus (Straight-Line Depreciation)**: Perhitungan nilai buku aset terkini secara otomatis berdasarkan masa manfaat (*useful life*) dan nilai residu.
- **Riwayat Sirkulasi Peminjaman**: Pencatatan lengkap nama peminjam, tanggal keluar, tanggal kembali, dan durasi hari peminjaman (`asset_circulation_logs`).
- **Alert Keterlambatan**: Notifikasi peringatan aset yang terlambat dikembalikan pada ikon lonceng navbar.

### 8. 📑 Ekspor & Laporan Profesional
- **Ekspor Excel Asli (.xlsx)**: Menggunakan pustaka modern `openpyxl` dengan penyesuaian lebar kolom otomatis (*Auto-Fit Width*) sehingga bebas dari error teks terpotong atau tanggal bertanda pagar `#########`. Dilengkapi styling header resmi (*Navy Blue*), pemisah ribuan Rupiah (`#,##0`), freeze panes baris atas, dan zebra striping.
- **Ekspor PDF Formal**: Landscape A4 rapi, penataan tabel presisi, warna aksen elegan pada judul tabel, tanpa emoji, dan kop resmi.
- **Ekspor CSV Kompatibel Excel**: Encoding UTF-8 dengan BOM (`\ufeff`) dan format tanggal `DD/MM/YYYY` yang langsung terbagi ke kolom masing-masing di Microsoft Excel.
- **Laporan Audit Terpisah**: Laporan berbasis rentang tanggal periode (`/reports/audit`) khusus untuk kepatuhan dan audit internal.

### 9. 🎨 Multi-Tema & Desain Responsif
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

## 🔑 Inisialisasi Akun Awal (Clean Install)

Repositori ini hadir dalam kondisi **bersih (*clean slate*) tanpa data dummy, sampel aset, atau akun uji coba** agar siap langsung digunakan untuk inventaris resmi instansi/perusahaan Anda.

Saat aplikasi pertama kali dijalankan, sistem secara otomatis menginisialisasi satu akun Administrator awal:
- **Username**: `Admin`
- **Password Bawaan**: `Admin123`

> 🛡️ **Wajib Ganti Password (Force Password Change)**:  
> Demi keamanan, saat pertama kali login menggunakan akun bawaan, sistem akan secara otomatis mewajibkan Administrator membuat kata sandi baru yang aman sebelum dapat mengakses menu aplikasi.  
> Akun staf, teknisi, maupun auditor dapat ditambahkan secara mandiri sesuai kebutuhan melalui menu **Kelola Akun** (`/accounts`).

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
    ├── confirm_sudo.html      # Halaman verifikasi kata sandi Sudo Mode (15 menit)
    ├── 403_network.html       # Halaman blokir akses jika IP di luar Whitelist / VPN
    ├── accounts.html          # Pengelolaan akun pengguna, peran & REST API key
    ├── audit_report.html      # Laporan audit kepatuhan periode
    ├── history.html           # Riwayat log aktivitas operasional dengan sticky header
    ├── vendors.html           # Manajemen data rekanan & vendor supplier
    ├── sites.html             # Manajemen cabang lokasi fisik aset
    └── admin_backups.html     # Manajemen backup & restore database
```

---

## 🔮 Roadmap Pengembangan Mendatang (Coming Soon)

Seiring dengan bertumbuhnya volume aset dan jumlah pengguna aktif yang bersamaan (*high concurrency*), langkah-langkah optimalisasi arsitektur berikut direncanakan pada rilis selanjutnya:

1. **Optimalisasi Database & Skalabilitas Concurrency**:
   - **Migrasi Engine RDBMS**: Opsi dukungan penuh untuk engine enterprise seperti **PostgreSQL 16+** atau **MySQL 8.0+** disamping SQLite bawaan saat ini.
   - **Connection Pooling Terdistribusi**: Pemanfaatan *SQLAlchemy QueuePool* dengan konfigurasi pool size dan overflow presisi untuk menangani ratusan transaksi simultan tanpa locking.
   - **Database Indexing Tingkat Lanjut**: Penambahan indeks komposit pada kolom-kolom kritis pencarian (`asset_code`, `status`, `next_maintenance_date`, `vendor_id`, dan `created_at`).
   - **In-Memory Caching (Redis)**: Penyimpanan sementara (*cache*) hasil agregasi analitik dashboard dan token sesi pengguna guna meminimalkan beban I/O database.

2. **Integrasi Notifikasi Eksternal**:
   - Integrasi webhook pesan instan (Telegram Bot & WhatsApp Business API) untuk eskalasi cepat saat ada aset rusak parah atau pengajuan Purchase Order bernilai tinggi.

---

## 📄 Hak Cipta & Pengembang

Dikembangkan dengan dedikasi untuk sistem inventaris aset yang modern, transparan, dan akuntabel.

&copy; 2026 **JESCA** &bull; Jessica Assets Management System  
*Contributors: Loraxsian &amp; And Jessica Nova Lya Mendrofa*
