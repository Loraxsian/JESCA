# JESCA (Jessica Assets) - Asset Management System

**JESCA (Jessica Assets)** adalah aplikasi web manajemen inventaris dan aset modern berbasis **Python Flask**, **SQLite (Flask-SQLAlchemy)**, dan **Bootstrap 5**.

Aplikasi ini dilengkapi dengan fitur login administrator, sistem auto-coding kode aset otomatis berbasis kategori (seperti `Tech/001`, `Tools/001`, `Furn/001`, dll.), dashboard visualisasi statistik real-time, serta manajemen CRUD data aset lengkap.

---

## 🚀 Fitur Utama

1. **Autentikasi & Hak Akses Administrator**:
   - Akun admin bawaan: Username `Admin` & Password `Admin123`.
   - Penyimpanan password menggunakan hashing aman (`Werkzeug security`).
   - Tombol *Auto-Fill* pada halaman login untuk pengujian cepat.

2. **Auto-Coding Aset Berdasarkan Kategori**:
   - Format standar: `<Prefix>/<3-Digit Sequential Number>`.
   - Contoh:
     - `Tech` &rarr; `Tech/001`, `Tech/002`, dst.
     - `Tools` &rarr; `Tools/001`, `Tools/002`, dst.
     - `Furniture` &rarr; `Furn/001`, `Furn/002`, dst.
     - `Vehicle` &rarr; `Vehicle/001`, `Vehicle/002`, dst.
     - `Office` &rarr; `Office/001`, `Office/002`, dst.
   - Endpoint API terintegrasi `/api/generate-code` yang melakukan pratinjau kode berikutnya secara real-time saat kategori dipilih di form penambahan aset.

3. **Dashboard Statistik & Visualisasi**:
   - Kartu metrik: Total Aset, Total Valuasi (format Rupiah `Rp xxx.xxx`), Aset Aktif, dan Aset Butuh Perhatian.
   - **Chart.js**:
     - *Doughnut Chart*: Distribusi persentase per kategori.
     - *Bar Chart*: Distribusi kondisi operasional aset (Aktif, Perbaikan, Rusak, Dipinjam, Afkir).
   - Ringkasan portofolio per kategori beserta subtotal nilai.
   - Tabel 5 aset terbaru yang baru ditambahkan.

4. **Tabel & Manajemen Kelola Aset (CRUD)**:
   - Pencarian kata kunci fleksibel (nama, kode, lokasi, deskripsi).
   - Filter dropdown berdasarkan Kategori dan Status Operasional.
   - Tambah Aset Baru dengan modal interaktif dan auto-coding otomatis.
   - Edit & Perbarui data aset.
   - Detail lengkap aset dalam modal popup.
   - Hapus aset dengan modal konfirmasi aman.
   - **Export Laporan ke CSV** (didukung format UTF-8 BOM untuk kompatibilitas Microsoft Excel).

---

## 📂 Struktur Direktori Proyek

```
jesca-assets/
├── app.py                 # File aplikasi Flask utama (Model, Controller, Routes)
├── requirements.txt       # Daftar dependensi Python
├── Dockerfile             # Konfigurasi container Docker
├── docker-compose.yml     # Konfigurasi orkestrasi Docker Compose
├── .env.example           # Contoh konfigurasi environment variables
├── .gitignore             # File yang diabaikan oleh Git
├── README.md              # Dokumentasi lengkap proyek
├── data/                  # Direktori database SQLite (jesca.db)
├── static/
│   ├── css/
│   │   └── style.css      # Styling kustom Bootstrap 5 & UI
│   └── js/
│       └── app.js         # Logika interaktif frontend
└── templates/
    ├── base.html          # Template induk dengan sidebar, navbar, & alerts
    ├── login.html         # Halaman login administrator
    ├── dashboard.html     # Halaman dashboard metrik & grafik Chart.js
    └── assets.html        # Halaman tabel kelola aset & modal-modal CRUD
```

---

## 🛠️ Cara Menjalankan Aplikasi

### Cara 1: Menggunakan Docker Compose (Direkomendasikan)

Pastikan Docker dan Docker Compose sudah terpasang di sistem Anda, lalu jalankan:

```bash
docker compose up -d --build
```

Buka browser dan akses:
```
http://localhost:5000
```

Untuk menghentikan container:
```bash
docker compose down
```

---

### Cara 2: Menjalankan Secara Lokal (Python Virtual Environment)

1. **Buat Virtual Environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Pasang Dependensi:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Jalankan Aplikasi Flask:**
   ```bash
   python app.py
   ```
   *Atau dengan Gunicorn:*
   ```bash
   gunicorn --bind 0.0.0.0:5000 app:app
   ```

4. **Buka Aplikasi di Browser:**
   ```
   http://localhost:5000
   ```

---

## 🔑 Kredensial Login Default

| Parameter | Kredensial |
|---|---|
| **URL Login** | `http://localhost:5000/login` |
| **Username** | `Admin` |
| **Password** | `Admin123` |
| **Peran** | Administrator |

---

## 🧪 Pengujian Fitur Auto-Coding

1. Masuk ke halaman **Kelola Data Aset** (`/assets`).
2. Klik tombol **Tambah Aset Baru**.
3. Pilih dropdown **Kategori Aset** (misal: *Tech*).
4. Kotak input **Kode Aset** akan secara otomatis memunculkan kode berikutnya, contoh: `Tech/004`.
5. Ubah kategori ke *Tools*, maka kode otomatis akan langsung beralih ke `Tools/004`.
6. Simpan aset dan pastikan kode unik tersebut tersimpan di tabel dan database SQLite.
