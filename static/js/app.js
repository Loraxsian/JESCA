// JESCA v2 — Main Application Script
// Jessica Assets Management System

// ==========================================
// 1. THEME SYSTEM
// ==========================================
(function() {
    var themeIcons = {
        light: 'bi-sun',
        dark: 'bi-moon-stars',
        pink: 'bi-hearts',
        ocean: 'bi-water',
        forest: 'bi-tree'
    };

    window.applyTheme = function(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('jesca_theme', theme);
        var icon = document.getElementById('themeIcon');
        if (icon) {
            icon.className = 'fs-5 text-secondary bi ' + (themeIcons[theme] || 'bi-palette');
        }
        document.querySelectorAll('[class*="theme-check-"]').forEach(function(el) {
            el.classList.add('d-none');
        });
        var check = document.querySelector('.theme-check-' + theme);
        if (check) check.classList.remove('d-none');
    };

    // Auto dark mode from system preference (if no manual preference)
    var saved = localStorage.getItem('jesca_theme');
    if (!saved) {
        saved = (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
    }
    window.applyTheme(saved);

    if (window.matchMedia) {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
            if (!localStorage.getItem('jesca_theme_manual')) {
                window.applyTheme(e.matches ? 'dark' : 'light');
            }
        });
    }
})();

// ==========================================
// 1B. DUAL LANGUAGE SYSTEM (ID / EN)
// ==========================================
window.JescaI18n = {
    flagSvgs: {
        id: '<svg width="20" height="14" viewBox="0 0 20 14" fill="none" class="rounded-1 border shadow-xs" style="vertical-align: middle;"><rect width="20" height="7" fill="#E11D48"/><rect y="7" width="20" height="7" fill="#FFFFFF"/></svg>',
        en: '<svg width="20" height="14" viewBox="0 0 60 30" fill="none" class="rounded-1 border shadow-xs" style="vertical-align: middle;"><clipPath id="uk-flag-clip-nav"><path d="M0 0h60v30H0z"/></clipPath><g clip-path="url(#uk-flag-clip-nav)"><path d="M0 0h60v30H0z" fill="#012169"/><path d="M0 0l60 30m0-30L0 30" stroke="#FFFFFF" stroke-width="6"/><path d="M0 0l60 30m0-30L0 30" stroke="#C8102E" stroke-width="4"/><path d="M30 0v30M0 15h60" stroke="#FFFFFF" stroke-width="10"/><path d="M30 0v30M0 15h60" stroke="#C8102E" stroke-width="6"/></g></svg>'
    },

    phraseMap: {
        "Tidak ada aset yang sesuai kriteria pencarian.": "No assets match your search criteria.",
        "Tidak ada jadwal maintenance dalam 7 hari ke depan. Semua perangkat beroperasi normal!": "No scheduled maintenance in the next 7 days. All assets operating normally!",
        "Tidak ada aset yang jatuh tempo servis atau sedang dalam perbaikan saat ini.": "No assets due for service or currently in repair.",
        "Belum ada aset terdaftar.": "No assets registered yet.",
        "Belum ada riwayat aktivitas yang tercatat.": "No activity logs recorded yet.",
        "Belum ada log aktivitas yang cocok dengan filter pencarian.": "No activity logs match the search filter.",
        "Belum Ada Vendor Terdaftar": "No Vendors Registered Yet",
        "Belum Ada Lokasi atau Site Terdaftar": "No Locations or Sites Registered Yet",
        "Tidak ada Purchase Order yang ditemukan.": "No Purchase Orders found.",
        "Tidak ada tiket laporan atau masukan saat ini.": "No tickets or feedback at this time.",
        "Tambahkan vendor atau supplier untuk melacak pengadaan aset.": "Add vendors or suppliers to track asset procurement.",
        "Tambahkan site (gedung, cabang, gudang) untuk mengelompokkan lokasi aset.": "Add sites (buildings, branches, warehouses) to group asset locations.",
        "Tambahkan vendor pertama Anda untuk memudahkan pencatatan pengadaan aset.": "Add your first vendor to facilitate tracking asset procurement.",
        "Tambahkan site pertama Anda untuk memudahkan pelacakan multi-lokasi.": "Add your first site to facilitate multi-location asset tracking.",
        "Mulai ajukan purchase order baru untuk pengadaan aset kantor.": "Start submitting new purchase orders for office asset procurement.",
        "Tidak ada aset yang memenuhi kriteria filter": "No assets meet the filter criteria",
        "Peringatan Keamanan: Kata Sandi Administrator Bawaan Masih Aktif": "Security Alert: Default Administrator Password Active",
        "Peringatan Keamanan: Password Administrator Bawaan Masih Aktif": "Security Alert: Default Administrator Password Active",
        "Akun Administrator masih menggunakan kata sandi bawaan sistem. Demi keamanan data inventaris, segera perbarui kata sandi Anda.": "The Administrator account is still using the system default password. For data protection, please update your password immediately.",
        "Akun Administrator masih menggunakan password default. Segera ubah password untuk melindungi sistem inventaris Anda.": "The Administrator account is still using the default password. Update your password immediately to protect your inventory system.",
        "Pengajuan Purchase Order Menunggu Persetujuan": "Purchase Orders Awaiting Approval",
        "Pengajuan Purchase Order Menunggu Approval": "Purchase Orders Awaiting Approval",
        "Keterlambatan Pengembalian (Overdue)": "Overdue Asset Returns",
        "Total Aset Terdaftar": "Total Registered Assets",
        "Total Aset": "Total Assets",
        "Nilai Perolehan": "Acquisition Value",
        "Nilai Buku Terkini": "Current Book Value",
        "Status Operasional": "Operational Status",
        "Akumulasi biaya beli": "Accumulated purchase cost",
        "Metode Garis Lurus": "Straight-line Method",
        "Sebaran Status Inventaris": "Asset Status Distribution",
        "Distribusi Kategori": "Category Distribution",
        "Aset Terakhir Ditambahkan": "Recently Added Assets",
        "Aktivitas Terkini": "Recent Activity",
        "Waktu Nyata": "Real-Time",
        "Ganti Sekarang": "Change Now",
        "Tinjau PO": "Review PO",
        "Semua Aset": "All Assets",
        "Lihat Log": "View Logs",
        "Item": "Items",
        "Aset": "Assets",
        "Kategori": "Categories",
        "Perlu Cek": "Needs Check",
        "Daftar Inventaris Aset Perusahaan": "Company Asset Inventory List",
        "Kelola data aset, garansi, depresiasi nilai buku, transfer site, lampiran dokumen, dan QR tag.": "Manage asset data, warranties, book value depreciation, site transfers, documents, and QR tags.",
        "Kelola Data Aset": "Manage Asset Data",
        "Inventaris & Aset": "Inventory & Assets",
        "Pencarian Aset": "Search Assets",
        "Semua Kategori": "All Categories",
        "Semua Status": "All Statuses",
        "Semua Lokasi": "All Locations",
        "Semua Site": "All Sites",
        "Semua Vendor": "All Vendors",
        "Filter Aset": "Filter Assets",
        "Reset Filter": "Reset Filters",
        "Pencarian kata kunci...": "Keyword search...",
        "Kode, nama, lokasi, peminjam...": "Code, name, location, borrower...",
        "aset dipilih": "assets selected",
        "Batal Pilih": "Deselect",
        "Ubah Status": "Change Status",
        "Pindah Kategori": "Move Category",
        "Perbandingan Aset": "Asset Comparison",
        "Bandingkan": "Compare",
        "Maksimal 2 aset untuk perbandingan.": "Maximum 2 assets for comparison.",
        "Tambah Aset": "Add Asset",
        "Tambah Aset Baru": "Add New Asset",
        "Tambah Vendor": "Add Vendor",
        "Tambah Site": "Add Site",
        "Tambah Pengguna": "Add User",
        "Buat Purchase Order": "Create Purchase Order",
        "Ajukan PO Baru": "Submit New PO",
        "Import CSV": "Import CSV",
        "Export PDF": "Export PDF",
        "Export Excel": "Export Excel",
        "Export CSV": "Export CSV",
        "Export Data": "Export Data",
        "Simpan": "Save",
        "Simpan Perubahan": "Save Changes",
        "Simpan Data": "Save Data",
        "Simpan Aset": "Save Asset",
        "Simpan Vendor": "Save Vendor",
        "Simpan Site": "Save Site",
        "Simpan Pengguna": "Save User",
        "Simpan & Lanjutkan": "Save & Continue",
        "Batal": "Cancel",
        "Tutup": "Close",
        "Hapus": "Delete",
        "Ya, Hapus": "Yes, Delete",
        "Edit": "Edit",
        "Lihat Detail": "View Details",
        "Detail Aset": "Asset Details",
        "Riwayat Servis": "Service History",
        "Riwayat Transfer": "Transfer History",
        "Pinjam Aset": "Check Out Asset",
        "Kembalikan Aset": "Return Asset",
        "Transfer Aset": "Transfer Asset",
        "Servis / Servis Aset": "Service Asset",
        "Cetak QR Tag": "Print QR Tag",
        "Unduh QR": "Download QR",
        "Upload Bukti": "Upload Proof",
        "Tutup Scanner": "Close Scanner",
        "Scan QR Code Aset": "Scan Asset QR Code",
        "Arahkan kamera ke QR Code pada label aset": "Point camera at the asset QR Code label",
        "Kode & Nama": "Code & Name",
        "Kode Aset": "Asset Code",
        "Nama Aset": "Asset Name",
        "Nilai Buku": "Book Value",
        "Aksi": "Actions",
        "Peminjam": "Borrower",
        "Peminjam / Penanggung Jawab": "Borrower / Person in Charge",
        "Tanggal Pinjam": "Borrow Date",
        "Tanggal Kembali": "Return Date",
        "Jadwal Servis": "Service Schedule",
        "Interval Servis": "Service Interval",
        "Terakhir Diservis": "Last Serviced",
        "Biaya": "Cost",
        "Biaya Servis": "Service Cost",
        "Pelaksana": "Technician / Performer",
        "Bengkel / Vendor Servis": "Service Workshop / Vendor",
        "Catatan Servis": "Service Notes",
        "Nomor PO": "PO Number",
        "Judul Pengadaan": "Procurement Title",
        "Total Estimasi": "Estimated Total",
        "Pemohon": "Requested By",
        "Disetujui Oleh": "Approved By",
        "Tanggal Pengajuan": "Submission Date",
        "Waktu": "Time",
        "Aktivitas": "Activity",
        "Pengguna": "User",
        "Nama Lengkap": "Full Name",
        "Peran Akses (Role)": "Access Role",
        "Terakhir Login": "Last Login",
        "Aktif": "Active",
        "Dipinjam": "Borrowed",
        "Dalam Perbaikan": "In Repair",
        "Perbaikan": "Repair",
        "Rusak": "Damaged",
        "Afkir": "Disposed",
        "Nonaktif": "Inactive",
        "Jatuh Tempo": "Due for Service",
        "Kondisi Baik": "Good Condition",
        "Sesuai & Baik": "Accurate & Good",
        "Rusak Ringan": "Minor Damage",
        "Rusak Berat": "Major Damage",
        "Hilang/Tidak Ditemukan": "Lost / Not Found",
        "Lokasi Berpindah": "Relocated",
        "Disetujui": "Approved",
        "Ditolak": "Rejected",
        "Menunggu Persetujuan": "Awaiting Approval",
        "Menunggu Approval": "Awaiting Approval",
        "Selesai Diterima": "Received & Verified",
        "Teknologi & IT": "Technology & IT",
        "Peralatan & Mesin": "Tools & Machinery",
        "Perabot & Furnitur": "Furniture & Fixtures",
        "Kendaraan Operasional": "Company Vehicles",
        "Kendaraan": "Vehicles",
        "Perlengkapan Kantor": "Office Supplies",
        "Kantor": "Office",
        "Inventaris Utama": "Main Inventory",
        "Riwayat & Laporan": "History & Reports",
        "Pengaturan": "Settings",
        "Kategori Aset": "Asset Categories",
        "Vendor & Lokasi": "Vendors & Locations",
        "Dashboard": "Dashboard",
        "Data Aset": "Asset Data",
        "Purchase Order": "Purchase Orders",
        "Pemeliharaan Aset": "Asset Maintenance",
        "Lokasi & Site": "Locations & Sites",
        "Vendor & Supplier": "Vendors & Suppliers",
        "Log Aktivitas": "Activity Logs",
        "Laporan Audit": "Audit Report",
        "Laporan & Masukan": "Feedback & Reports",
        "Kelola Pengguna": "User Management",
        "Kelola Akun": "User Management",
        "Backup & Restore": "Backup & Restore",
        "Pengaturan Sistem": "System Settings",
        "Ganti Password": "Change Password",
        "Ganti Kata Sandi": "Change Password",
        "Panduan Sistem": "System Guide",
        "Profil & Foto": "Profile & Photo",
        "Keluar (Logout)": "Sign Out",
        "Pilih Tema": "Select Theme",
        "Terang (Light)": "Light",
        "Gelap (Dark)": "Dark",
        "Command Palette": "Command Palette",
        "Pemberitahuan & Notifikasi": "Notifications",
        "Lokasi Penempatan": "Placement Location",
        "Nilai Perolehan (IDR)": "Acquisition Value (IDR)",
        "Deskripsi / Catatan": "Description / Notes",
        "Masa Manfaat (Tahun)": "Useful Life (Years)",
        "Nilai Residu / Sisa (IDR)": "Salvage Value (IDR)",
        "Garansi Mulai": "Warranty Start",
        "Garansi Berakhir": "Warranty End",
        "Perlu Pemeliharaan Berkala?": "Needs Scheduled Maintenance?",
        "Tidak Perlu (-)": "Not Needed (-)",
        "Ya, Perlu Servis Rutin": "Yes, Routine Service",
        "Interval Pemeliharaan (Hari)": "Maintenance Interval (Days)",
        "Pilih Vendor (Opsional)": "Select Vendor (Optional)",
        "Pilih Site (Opsional)": "Select Site (Optional)",
        "-- Tanpa Vendor --": "-- No Vendor --",
        "-- Tanpa Site --": "-- No Site --",
        "Foto Aset": "Asset Photo",
        "Informasi Umum": "General Information",
        "Garansi & Depresiasi": "Warranty & Depreciation",
        "Servis & Pemeliharaan": "Service & Maintenance",
        "Spesifikasi Kategori": "Category Specifications",
        "Dokumen & Lampiran": "Documents & Attachments",
        "Unggah Lampiran": "Upload Attachment",
        "Password Baru": "New Password",
        "Konfirmasi Password Baru": "Confirm New Password",
        "Alamat Kantor / Toko": "Office / Store Address",
        "Kontak / Telepon": "Contact / Phone",
        "Nama Site": "Site Name",
        "Deskripsi Lokasi": "Location Description",
        "Alasan Perpindahan": "Transfer Reason",
        "Lokasi Tujuan": "Destination Location",
        "Site Tujuan": "Destination Site",
        "Kondisi Fisik": "Physical Condition",
        "Catatan Kondisi": "Condition Notes",
        "Silahkan Masuk": "Please Sign In",
        "Ingat Saya": "Remember Me",
        "Masuk Sekarang": "Sign In Now",
        "Masa Garansi": "Warranty Period",
        "Status Garansi": "Warranty Status",
        "Garansi Aktif": "Active Warranty",
        "Garansi Kedaluwarsa": "Warranty Expired",
        "Garansi Segera Habis": "Warranty Expiring Soon",
        "Servis Rutin": "Routine Maintenance",
        "Jadwal Berikutnya": "Next Schedule",
        "Riwayat Pemeliharaan": "Maintenance History",
        "Servis Selesai": "Service Completed",
        "Servis Berkala": "Periodic Service",
        "Dalam Peminjaman": "Currently Borrowed",
        "Aset Tersedia": "Available Assets",
        "Siap Pakai": "Ready for Use",
        "Telah Dikembalikan": "Returned",
        "Terlambat": "Overdue",
        "Terlambat dikembalikan": "Overdue for return",
        "Pesanan Pembelian": "Purchase Orders",
        "Daftar Purchase Order": "Purchase Order List",
        "Detail Purchase Order": "Purchase Order Details",
        "Item Pengadaan": "Procurement Items",
        "Estimasi Biaya": "Estimated Cost",
        "Harga Satuan": "Unit Price",
        "Total Biaya": "Total Cost",
        "Keterangan Pengadaan": "Procurement Notes",
        "Lampiran Berkas": "File Attachments",
        "Unggah Bukti": "Upload Receipt / Document",
        "Menunggu": "Pending",
        "Dibatalkan": "Cancelled",
        "Diterima": "Received",
        "Barang Telah Tiba": "Items Received",
        "Tandai Selesai": "Mark Completed",
        "Batalkan PO": "Cancel PO",
        "Ajukan Persetujuan": "Submit for Approval",
        "Daftar Pengguna": "User List",
        "Kelola Akun Pengguna": "Manage User Accounts",
        "Peran": "Role",
        "Status Akun": "Account Status",
        "Kata Sandi": "Password",
        "Konfirmasi Kata Sandi": "Confirm Password",
        "Ubah Kata Sandi": "Change Password",
        "Profil Pengguna": "User Profile",
        "Foto Profil": "Profile Photo",
        "Unggah Foto": "Upload Photo",
        "Pengaturan Jaringan": "Network Settings",
        "Mode Koneksi": "Connection Mode",
        "Komputer Ini": "This Computer",
        "Jaringan Lokal": "Local Network (LAN)",
        "Domain Sendiri": "Custom Domain",
        "Tunneling Instan": "Instant Tunneling",
        "Riwayat Backup": "Backup History",
        "Buat Backup Baru": "Create New Backup",
        "Ukuran File": "File Size",
        "Tanggal Dibuat": "Created Date",
        "Pulihkan": "Restore",
        "Unduh File": "Download File",
        "Pilih Semua": "Select All",
        "Cari...": "Search...",
        "Semua Data": "All Data",
        "Tidak Ada": "None",
        "Ya": "Yes",
        "Tidak": "No",
        "Simpan Berhasil": "Saved Successfully",
        "Terjadi Kesalahan": "An Error Occurred",
        "Apakah Anda yakin?": "Are you sure?",
        "Tindakan ini tidak dapat dibatalkan.": "This action cannot be undone.",
        "Memuat data...": "Loading data...",
        "Harap tunggu...": "Please wait...",
        "Data berhasil disimpan.": "Data saved successfully.",
        "Data berhasil diperbarui.": "Data updated successfully.",
        "Data berhasil dihapus.": "Data deleted successfully.",
        "Tambah Site Cepat": "Quick Add Site",
        "Tambah Vendor Cepat": "Quick Add Vendor",
        "Nama Vendor / Toko": "Vendor / Store Name",
        "Gudang Barat, Cabang, dll": "West Warehouse, Branch, etc.",
        "Keterangan (Opsional)": "Notes (Optional)",
        "Keterangan singkat": "Brief notes",
        "PT. Jaya Abadi, Toko Komputer, dll": "PT. Vendor Name, Computer Store, etc.",
        "Kontak Person": "Contact Person",
        "No. Telepon": "Phone Number",
        "Hapus Aset?": "Delete Asset?",
        "akan dihapus permanen.": "will be permanently deleted.",
        "Proses Transfer": "Process Transfer",
        "Aset yang Ditransfer": "Asset to Transfer",
        "Lokasi Saat Ini": "Current Location",
        "Lokasi Baru": "New Location",
        "Rotasi karyawan, renovasi ruangan, dll.": "Employee rotation, room renovation, etc.",
        "Unggah Dokumen Baru": "Upload New Document",
        "Berkas Tersimpan:": "Saved Documents:",
        "Memuat dokumen...": "Loading documents...",
        "Memuat berkas...": "Loading files...",
        "Belum ada dokumen dilampirkan.": "No documents attached yet.",
        "Gunakan fitur ini untuk memasukkan data aset secara massal dari spreadsheet. Pastikan struktur kolom sesuai dengan template standar.": "Use this feature to import assets in bulk from spreadsheets. Ensure column headers match the template.",
        "Unduh Template CSV": "Download CSV Template",
        "Pilih File CSV": "Select CSV File",
        "Proses Impor Data": "Process Data Import",
        "Peminjaman Aset (Check Out)": "Asset Check Out",
        "Nama Peminjam / Karyawan": "Borrower / Employee Name",
        "Catatan Peminjaman": "Borrowing Notes",
        "Keperluan acara, proyek X, dll.": "Event requirements, Project X, etc.",
        "Konfirmasi Pinjam": "Confirm Check Out",
        "Pengembalian Aset (Check In)": "Asset Return (Check In)",
        "Status Aset Setelah Dikembalikan": "Asset Status After Return",
        "Aktif (Kondisi Baik & Siap Pakai)": "Active (Good Condition & Ready to Use)",
        "Perlu Perbaikan / Servis": "Needs Repair / Service",
        "Kondisi fisik saat diterima kembali...": "Physical condition upon return...",
        "Simpan Pengembalian": "Save Return",
        "Label QR Tag Aset": "Asset QR Tag Label",
        "Scan untuk verifikasi via JESCA": "Scan to verify via JESCA",
        "Atribut Spesifik Kategori": "Category Specific Attributes",
        "Ganti Foto Fisik": "Replace Photo",
        "Ruang IT / Lantai 2": "IT Room / 2nd Floor",
        "Kosongkan untuk auto-code": "Leave empty for auto-code",
        "Contoh: MacBook Pro M3 16 Inch": "e.g.: MacBook Pro M3 16 Inch",
        "Contoh: Gedung B Ruang 204": "e.g.: Building B Room 204",
        "Contoh: Budi Santoso (Divisi Marketing)": "e.g.: John Doe (Marketing Dept)",
        "Pinjamkan (Check Out)": "Check Out Asset",
        "Edit Data": "Edit Data",
        "Hapus Aset": "Delete Asset",
        "Print halaman ini": "Print this page",
        "Keterlambatan Pengembalian": "Overdue Returns",
        "Peminjam:": "Borrower:",
        "Lihat Semua Aset Jatuh Tempo": "View All Assets Due for Service",
        "Tambah Aset Baru ke Inventaris": "Add New Asset to Inventory",
        "ke Inventaris": "to Inventory",
        "dari Inventaris": "from Inventory",
        "Inventaris": "Inventory",
        "kriteria pencarian": "search criteria",
        "kriteria": "criteria",
        "pencarian": "search",
        "Daftar Inventaris": "Inventory List",
        "Daftar Aset": "Asset List",
        "Peminjaman": "Borrowing",
        "Pengembalian": "Return",
        "Pemeliharaan": "Maintenance",
        "Penyusutan": "Depreciation",
        "Nilai Residu": "Salvage Value",
        "Masa Manfaat": "Useful Life",
        "Nomor Seri": "Serial Number",
        "Pilih Status": "Select Status",
        "Pilih Kategori": "Select Category",
        "Pilih Lokasi": "Select Location",
        "Pilih Site": "Select Site",
        "Pilih Vendor": "Select Vendor",
        "Semua": "All",
        "Kondisi": "Condition",
        "Catatan": "Notes",
        "Spesifikasi": "Specifications",
        "Lampiran": "Attachments",
        "Dokumen": "Documents",
        "Informasi": "Information",
        "Konfirmasi": "Confirmation",
        "Peringatan": "Warning",
        "Pemberitahuan": "Notification",
        "Riwayat": "History",
        "Administrator": "Administrator",
        "Teknisi": "Technician",
        "Auditor": "Auditor",
        "Staff": "Staff",
        "Hari": "Days",
        "Bulan": "Months",
        "Tahun": "Years"
},

    sortedKeys: null,

    getSortedKeys: function() {
        if (!this.sortedKeys) {
            this.sortedKeys = Object.keys(this.phraseMap).sort(function(a, b) {
                return b.length - a.length;
            });
        }
        return this.sortedKeys;
    },

    translateString: function(str) {
        if (!str || typeof str !== 'string') return str;
        var trimmed = str.trim();
        if (!trimmed) return str;
        if (this.phraseMap[trimmed]) {
            return str.replace(trimmed, this.phraseMap[trimmed]);
        }
        var keys = this.getSortedKeys();
        var res = str;
        for (var i = 0; i < keys.length; i++) {
            var k = keys[i];
            if (res.indexOf(k) !== -1) {
                if (k.length <= 4) {
                    var regex = new RegExp('\b' + k + '\b', 'g');
                    res = res.replace(regex, this.phraseMap[k]);
                } else {
                    res = res.split(k).join(this.phraseMap[k]);
                }
            }
        }
        return res;
    },

    translateNode: function(node) {
        if (!node) return;
        var self = this;

        if (node.nodeType === 3) { // TEXT_NODE
            var parent = node.parentElement;
            if (parent) {
                var tag = parent.tagName.toUpperCase();
                if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'CODE' || tag === 'PRE') return;
            }
            if (node._jescaOrig === undefined) {
                node._jescaOrig = node.nodeValue;
            }
            node.nodeValue = self.translateString(node._jescaOrig);
            return;
        }

        if (node.nodeType === 1) { // ELEMENT_NODE
            var tag = node.tagName.toUpperCase();
            if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'CODE' || tag === 'PRE') return;

            // Translate attributes
            var attrs = ['placeholder', 'title', 'aria-label'];
            for (var a = 0; a < attrs.length; a++) {
                var attr = attrs[a];
                var val = node.getAttribute(attr);
                if (val) {
                    if (!node._jescaOrigAttrs) node._jescaOrigAttrs = {};
                    if (node._jescaOrigAttrs[attr] === undefined) {
                        node._jescaOrigAttrs[attr] = val;
                    }
                    node.setAttribute(attr, self.translateString(node._jescaOrigAttrs[attr]));
                }
            }

            // Walk children
            var children = node.childNodes;
            for (var c = 0; c < children.length; c++) {
                self.translateNode(children[c]);
            }
        }
    },

    restoreNode: function(node) {
        if (!node) return;
        var self = this;

        if (node.nodeType === 3) {
            if (node._jescaOrig !== undefined) {
                node.nodeValue = node._jescaOrig;
            }
            return;
        }

        if (node.nodeType === 1) {
            if (node._jescaOrigAttrs) {
                for (var attr in node._jescaOrigAttrs) {
                    node.setAttribute(attr, node._jescaOrigAttrs[attr]);
                }
            }
            var children = node.childNodes;
            for (var c = 0; c < children.length; c++) {
                self.restoreNode(children[c]);
            }
        }
    },

    observer: null,

    initObserver: function() {
        if (this.observer || typeof MutationObserver === 'undefined') return;
        var self = this;
        this.observer = new MutationObserver(function(mutations) {
            if (self.getCurrent() !== 'en') return;
            for (var i = 0; i < mutations.length; i++) {
                var added = mutations[i].addedNodes;
                for (var j = 0; j < added.length; j++) {
                    self.translateNode(added[j]);
                }
            }
        });
        if (document.body) {
            this.observer.observe(document.body, { childList: true, subtree: true });
        }
    },

    getCurrent: function() {
        return localStorage.getItem('jesca_lang') || 'id';
    },

    apply: function(lang) {
        lang = (lang === 'en') ? 'en' : 'id';
        localStorage.setItem('jesca_lang', lang);
        try {
            document.cookie = 'jesca_lang=' + lang + ';path=/;max-age=31536000';
        } catch(e) {}
        document.documentElement.setAttribute('lang', lang);
        document.documentElement.setAttribute('data-lang', lang);

        // Update Flag Icon in navbar button
        var flagContainer = document.getElementById('currentLangFlag');
        if (flagContainer && this.flagSvgs[lang]) {
            flagContainer.innerHTML = this.flagSvgs[lang];
        }
        var loginFlagContainer = document.getElementById('loginActiveFlag');
        if (loginFlagContainer && this.flagSvgs[lang]) {
            loginFlagContainer.innerHTML = this.flagSvgs[lang];
        }

        // Update Checkmarks in dropdown
        document.querySelectorAll('.lang-check-id, .lang-check-en').forEach(function(el) {
            el.classList.add('d-none');
        });
        var checkEl = document.querySelector('.lang-check-' + lang);
        if (checkEl) checkEl.classList.remove('d-none');

        // Apply recursive translation or restoration
        if (document.body) {
            if (lang === 'en') {
                this.translateNode(document.body);
                this.initObserver();
            } else {
                this.restoreNode(document.body);
            }
        }

        window.dispatchEvent(new CustomEvent('jesca:languageChanged', { detail: { lang: lang } }));
    }
};

// Auto-run early lang preference
try {
    var savedLang = localStorage.getItem('jesca_lang') || 'id';
    document.documentElement.setAttribute('lang', savedLang);
    document.documentElement.setAttribute('data-lang', savedLang);
} catch (e) {}

// ==========================================
// 2. TOAST NOTIFICATION SYSTEM
// ==========================================
window.JescaToast = {
    container: null,

    init: function() {
        if (this.container) return;
        this.container = document.createElement('div');
        this.container.id = 'jesca-toast-container';
        this.container.style.cssText = 'position:fixed;bottom:1.5rem;right:1.5rem;z-index:9999;display:flex;flex-direction:column;gap:0.5rem;max-width:380px;pointer-events:none;';
        document.body.appendChild(this.container);
    },

    show: function(message, type) {
        this.init();
        type = type || 'info';
        var icons = {
            success: 'bi-check-circle-fill',
            danger: 'bi-exclamation-octagon-fill',
            warning: 'bi-exclamation-triangle-fill',
            info: 'bi-info-circle-fill'
        };
        var colors = {
            success: '#10b981',
            danger: '#ef4444',
            warning: '#f59e0b',
            info: '#3b82f6'
        };

        var toast = document.createElement('div');
        toast.className = 'jesca-toast shadow-lg';
        toast.style.cssText = 'pointer-events:auto;background:white;border-radius:12px;padding:12px 16px;display:flex;align-items:flex-start;gap:12px;border-left:4px solid ' + (colors[type] || colors.info) + ';animation:slideInRight 0.3s ease;min-width:280px;box-shadow:0 10px 25px rgba(0,0,0,0.12);';
        toast.innerHTML = '<i class="bi ' + (icons[type] || icons.info) + '" style="color:' + (colors[type] || colors.info) + ';font-size:1.2rem;flex-shrink:0;margin-top:1px;"></i>' +
            '<div style="flex:1;font-size:0.875rem;color:#1e293b;line-height:1.45;word-break:break-word;">' + message + '</div>' +
            '<button onclick="this.parentElement.remove()" style="background:none;border:none;color:#94a3b8;cursor:pointer;padding:0;font-size:1.1rem;line-height:1;margin-left:4px;">&times;</button>';

        this.container.appendChild(toast);

        // Auto dismiss after 4.5 seconds
        setTimeout(function() {
            if (toast.parentElement) {
                toast.style.animation = 'slideOutRight 0.3s ease';
                setTimeout(function() {
                    if (toast.parentElement) toast.remove();
                }, 300);
            }
        }, 4500);
    }
};

// Convert standard Bootstrap flash alerts to toast notifications
document.addEventListener('DOMContentLoaded', function() {
    JescaToast.init();

    document.querySelectorAll('.alert[role="alert"]').forEach(function(alert) {
        var type = 'info';
        if (alert.classList.contains('alert-success')) type = 'success';
        else if (alert.classList.contains('alert-danger')) type = 'danger';
        else if (alert.classList.contains('alert-warning')) type = 'warning';

        var textEl = alert.querySelector('.flex-grow-1') || alert;
        var message = textEl.textContent.trim();
        if (message) {
            JescaToast.show(message, type);
        }
        alert.style.display = 'none';
    });
});

// ==========================================
// 3. SIDEBAR TOGGLE
// ==========================================
document.addEventListener('DOMContentLoaded', function() {
    var wrapper = document.getElementById('wrapper');
    var sidebarToggle = document.getElementById('sidebar-toggle');
    var sidebarClose = document.getElementById('sidebar-close');
    var pageContent = document.getElementById('page-content-wrapper');

    if (sidebarToggle && wrapper) {
        sidebarToggle.addEventListener('click', function(e) {
            e.preventDefault();
            wrapper.classList.toggle('toggled');
        });
    }
    if (sidebarClose && wrapper) {
        sidebarClose.addEventListener('click', function(e) {
            e.preventDefault();
            wrapper.classList.remove('toggled');
        });
    }
});

// ==========================================
// 4. SESSION IDLE TIMEOUT (30 minutes)
// ==========================================
(function() {
    var IDLE_TIMEOUT = 30 * 60 * 1000; // 30 minutes
    var WARNING_BEFORE = 5 * 60 * 1000; // 5 min warning
    var idleTimer, warningTimer;
    var warningShown = false;

    function resetTimer() {
        clearTimeout(idleTimer);
        clearTimeout(warningTimer);
        warningShown = false;

        warningTimer = setTimeout(function() {
            if (!warningShown) {
                warningShown = true;
                JescaToast.show('Sesi Anda akan berakhir dalam 5 menit karena tidak ada aktivitas.', 'warning');
            }
        }, IDLE_TIMEOUT - WARNING_BEFORE);

        idleTimer = setTimeout(function() {
            // Auto logout
            window.location.href = '/logout';
        }, IDLE_TIMEOUT);
    }

    if (document.getElementById('sidebar-wrapper')) {
        ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart', 'click'].forEach(function(evt) {
            document.addEventListener(evt, resetTimer, true);
        });
        resetTimer();
    }
})();

// ==========================================
// 5. KEYBOARD SHORTCUTS
// ==========================================
document.addEventListener('DOMContentLoaded', function() {
    var gKeyPending = false;

    document.addEventListener('keydown', function(e) {
        // Skip shortcut if typing in input/textarea/select
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT' || e.target.isContentEditable) {
            return;
        }

        // Ctrl+K / Cmd+K — Command palette
        if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
            e.preventDefault();
            openCommandPalette();
            return;
        }

        // Alt+N / Ctrl+N / Cmd+N — New asset modal
        if ((e.altKey && (e.key === 'n' || e.key === 'N')) || ((e.ctrlKey || e.metaKey) && (e.key === 'n' || e.key === 'N'))) {
            e.preventDefault();
            var modal = document.getElementById('addAssetModal');
            if (modal) {
                bootstrap.Modal.getOrCreateInstance(modal).show();
            } else {
                window.location.href = '/assets';
            }
            return;
        }

        // Ctrl+/ — Toggle sidebar
        if ((e.ctrlKey || e.metaKey) && e.key === '/') {
            e.preventDefault();
            var wrapper = document.getElementById('wrapper');
            if (wrapper) wrapper.classList.toggle('toggled');
            return;
        }

        // Ctrl+F — Focus search
        if ((e.ctrlKey || e.metaKey) && (e.key === 'f' || e.key === 'F')) {
            var search = document.getElementById('search') || document.querySelector('input[name="search"]');
            if (search) {
                e.preventDefault();
                search.focus();
                search.select();
            }
            return;
        }

        // G+Key navigation
        if (e.key === 'g' && !gKeyPending) {
            gKeyPending = true;
            setTimeout(function() { gKeyPending = false; }, 600);
            return;
        }
        if (gKeyPending) {
            gKeyPending = false;
            if (e.key === 'd') { window.location.href = '/dashboard'; return; }
            if (e.key === 'a') { window.location.href = '/assets'; return; }
            if (e.key === 'h') { window.location.href = '/history'; return; }
            if (e.key === 'v') { window.location.href = '/vendors'; return; }
            if (e.key === 's') { window.location.href = '/sites'; return; }
        }

        // Escape — close command palette
        if (e.key === 'Escape') {
            var palette = document.getElementById('command-palette');
            if (palette) palette.remove();
        }
    });
});

// ==========================================
// 6. COMMAND PALETTE (Ctrl+K)
// ==========================================
function openCommandPalette() {
    var existing = document.getElementById('command-palette');
    if (existing) { existing.remove(); return; }

    var commands = [
        { label: 'Dashboard', icon: 'bi-grid-1x2', action: function() { window.location.href = '/dashboard'; } },
        { label: 'Purchase Order (Pengadaan)', icon: 'bi-cart-check', action: function() { window.location.href = '/purchase-orders'; } },
        { label: 'Buat Purchase Order Baru', icon: 'bi-file-earmark-plus', action: function() { window.location.href = '/purchase-orders/create'; } },
        { label: 'Kelola Inventaris Aset', icon: 'bi-boxes', action: function() { window.location.href = '/assets'; } },
        { label: 'Tambah Aset Baru', icon: 'bi-plus-circle', action: function() { var m = document.getElementById('addAssetModal'); if (m) bootstrap.Modal.getOrCreateInstance(m).show(); else window.location.href = '/assets'; } },
        { label: 'Scan QR Code Kamera', icon: 'bi-camera', action: function() { JescaQRScanner.open(); } },
        { label: 'Import Aset dari CSV', icon: 'bi-upload', action: function() { var m = document.getElementById('importCsvModal'); if (m) bootstrap.Modal.getOrCreateInstance(m).show(); else window.location.href = '/assets'; } },
        { label: 'Export PDF Laporan', icon: 'bi-file-pdf', action: function() { window.location.href = '/assets/export/pdf'; } },
        { label: 'Export Excel (.xlsx)', icon: 'bi-file-earmark-excel', action: function() { window.location.href = '/assets/export/excel'; } },
        { label: 'Export CSV Data Aset', icon: 'bi-file-earmark-spreadsheet', action: function() { window.location.href = '/assets/export/csv'; } },
        { label: 'Laporan & Masukan', icon: 'bi-chat-square-text', action: function() { window.location.href = '/feedbacks'; } },
        { label: 'Vendor & Supplier', icon: 'bi-building', action: function() { window.location.href = '/vendors'; } },
        { label: 'Lokasi & Site', icon: 'bi-geo-alt', action: function() { window.location.href = '/sites'; } },
        { label: 'Laporan Audit', icon: 'bi-file-earmark-text', action: function() { window.location.href = '/reports/audit'; } },
        { label: 'Log & Riwayat Aktivitas', icon: 'bi-clock-history', action: function() { window.location.href = '/history'; } },
        { label: 'Backup & Restore Database', icon: 'bi-database', action: function() { window.location.href = '/admin/backups'; } },
        { label: 'Kelola Pengguna & Akun', icon: 'bi-person-badge', action: function() { window.location.href = '/accounts'; } },
        { label: 'Tema: Terang', icon: 'bi-sun', action: function() { applyTheme('light'); localStorage.setItem('jesca_theme_manual', '1'); } },
        { label: 'Tema: Gelap', icon: 'bi-moon-stars', action: function() { applyTheme('dark'); localStorage.setItem('jesca_theme_manual', '1'); } },
        { label: 'Tema: Ocean Blue', icon: 'bi-water', action: function() { applyTheme('ocean'); localStorage.setItem('jesca_theme_manual', '1'); } },
        { label: 'Tema: Forest Green', icon: 'bi-tree', action: function() { applyTheme('forest'); localStorage.setItem('jesca_theme_manual', '1'); } },
        { label: 'Tema: Jessica Pink', icon: 'bi-hearts', action: function() { applyTheme('pink'); localStorage.setItem('jesca_theme_manual', '1'); } },
    ];

    var overlay = document.createElement('div');
    overlay.id = 'command-palette';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(15,23,42,0.65);z-index:10000;display:flex;align-items:flex-start;justify-content:center;padding-top:12vh;backdrop-filter:blur(4px);';

    var box = document.createElement('div');
    box.style.cssText = 'background:white;border-radius:16px;width:100%;max-width:560px;box-shadow:0 25px 50px rgba(0,0,0,0.25);overflow:hidden;border:1px solid #e2e8f0;';

    var searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.placeholder = 'Ketik nama menu, aksi, atau tema...';
    searchInput.style.cssText = 'width:100%;padding:16px 20px;border:none;font-size:1rem;outline:none;border-bottom:1px solid #f1f5f9;font-family:inherit;color:#1e293b;background:transparent;';

    var list = document.createElement('div');
    list.style.cssText = 'max-height:360px;overflow-y:auto;padding:8px;';

    function renderList(filter) {
        list.innerHTML = '';
        var filtered = commands.filter(function(c) {
            return !filter || c.label.toLowerCase().includes(filter.toLowerCase());
        });
        if (!filtered.length) {
            list.innerHTML = '<div style="text-align:center;padding:24px;color:#94a3b8;font-size:0.875rem;">Tidak ada perintah yang cocok dengan "' + filter + '"</div>';
            return;
        }
        var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        var activeBg = isDark ? '#162035' : '#f0f4ff';
        var textColor = isDark ? '#f8fafc' : '#1e293b';

        filtered.forEach(function(cmd, idx) {
            var item = document.createElement('button');
            item.style.cssText = 'width:100%;text-align:left;padding:10px 14px;border:none;background:' + (idx === 0 ? activeBg : 'transparent') + ';border-radius:10px;cursor:pointer;display:flex;align-items:center;gap:12px;color:' + textColor + ';font-size:0.9rem;font-family:inherit;margin-bottom:2px;transition:background 0.1s;';
            item.innerHTML = '<i class="bi ' + cmd.icon + '" style="color:#3b82f6;font-size:1.1rem;width:22px;text-align:center;"></i><span>' + cmd.label + '</span>';
            item.addEventListener('mouseenter', function() { item.style.background = activeBg; });
            item.addEventListener('mouseleave', function() { item.style.background = 'transparent'; });
            item.addEventListener('click', function() {
                overlay.remove();
                cmd.action();
            });
            list.appendChild(item);
        });
    }

    var footer = document.createElement('div');
    footer.style.cssText = 'padding:10px 18px;border-top:1px solid #f1f5f9;display:flex;gap:16px;font-size:0.75rem;color:#94a3b8;background:#fafafa;';
    footer.innerHTML = '<span><kbd style="background:#e2e8f0;padding:2px 6px;border-radius:4px;color:#475569;">↑↓</kbd> Navigasi</span>' +
        '<span><kbd style="background:#e2e8f0;padding:2px 6px;border-radius:4px;color:#475569;">Enter</kbd> Pilih</span>' +
        '<span><kbd style="background:#e2e8f0;padding:2px 6px;border-radius:4px;color:#475569;">Esc</kbd> Tutup</span>';

    searchInput.addEventListener('input', function() { renderList(this.value); });
    overlay.addEventListener('click', function(e) { if (e.target === overlay) overlay.remove(); });

    // Dark mode support
    var currentTheme = document.documentElement.getAttribute('data-theme');
    if (currentTheme === 'dark') {
        box.style.background = '#101726';
        box.style.borderColor = '#1c263c';
        searchInput.style.color = '#f8fafc';
        searchInput.style.borderBottomColor = '#1c263c';
        footer.style.background = '#0b101c';
        footer.style.borderTopColor = '#1c263c';
    }

    box.appendChild(searchInput);
    box.appendChild(list);
    box.appendChild(footer);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    renderList('');
    searchInput.focus();
}

// ==========================================
// 7. BULK SELECT SYSTEM
// ==========================================
window.BulkSelect = {
    selected: new Set(),

    init: function() {
        var table = document.getElementById('assetsTable');
        if (!table) return;

        // Add checkbox header
        var thead = table.querySelector('thead tr');
        if (thead && !thead.querySelector('.bulk-select-all-th')) {
            var th = document.createElement('th');
            th.className = 'bulk-select-all-th ps-3';
            th.style.width = '42px';
            th.innerHTML = '<input type="checkbox" class="form-check-input" id="selectAllCheckbox" title="Pilih Semua">';
            thead.insertBefore(th, thead.firstChild);
        }

        // Add checkbox each row
        table.querySelectorAll('tbody tr[data-asset-id]').forEach(function(row) {
            if (!row.querySelector('.bulk-checkbox-td')) {
                var td = document.createElement('td');
                td.className = 'bulk-checkbox-td ps-3';
                td.innerHTML = '<input type="checkbox" class="form-check-input bulk-row-checkbox" data-id="' + row.dataset.assetId + '">';
                row.insertBefore(td, row.firstChild);
            }
        });

        // Select all event
        var selectAll = document.getElementById('selectAllCheckbox');
        if (selectAll) {
            selectAll.addEventListener('change', function() {
                document.querySelectorAll('.bulk-row-checkbox').forEach(function(cb) {
                    cb.checked = selectAll.checked;
                    if (selectAll.checked) BulkSelect.selected.add(cb.dataset.id);
                    else BulkSelect.selected.delete(cb.dataset.id);
                });
                BulkSelect.updateBar();
            });
        }

        // Single row checkbox event
        document.querySelectorAll('.bulk-row-checkbox').forEach(function(cb) {
            cb.addEventListener('change', function() {
                if (this.checked) BulkSelect.selected.add(this.dataset.id);
                else BulkSelect.selected.delete(this.dataset.id);
                BulkSelect.updateBar();
            });
        });
    },

    updateBar: function() {
        var bar = document.getElementById('bulk-action-bar');
        var count = this.selected.size;

        if (count === 0) {
            if (bar) bar.classList.add('d-none');
            return;
        }

        if (!bar) {
            bar = document.createElement('div');
            bar.id = 'bulk-action-bar';
            bar.style.cssText = 'position:fixed;bottom:1.5rem;left:50%;transform:translateX(-50%);z-index:1050;';
            document.body.appendChild(bar);
        }

        bar.className = '';
        bar.innerHTML = '<div class="d-flex align-items-center gap-2 bg-dark text-white rounded-pill px-4 py-2 shadow-lg" style="white-space:nowrap;">' +
            '<span class="badge bg-primary rounded-pill fs-7">' + count + '</span>' +
            '<span class="small fw-semibold">aset dipilih</span>' +
            '<div class="vr mx-1" style="opacity:0.4;"></div>' +
            '<button class="btn btn-sm btn-outline-light rounded-pill px-3" onclick="BulkSelect.action(\'export\')"><i class="bi bi-download me-1"></i>Export</button>' +
            '<button class="btn btn-sm btn-outline-warning rounded-pill px-3" onclick="BulkSelect.action(\'change_status\')"><i class="bi bi-arrow-repeat me-1"></i>Ubah Status</button>' +
            '<button class="btn btn-sm btn-outline-info rounded-pill px-3" onclick="BulkSelect.action(\'move_category\')"><i class="bi bi-folder-symlink me-1"></i>Pindah Kategori</button>' +
            '<button class="btn btn-sm btn-outline-danger rounded-pill px-3" onclick="BulkSelect.action(\'delete\')"><i class="bi bi-trash me-1"></i>Hapus</button>' +
            '<button class="btn btn-sm btn-link text-white ms-1 p-0" onclick="BulkSelect.clearAll()" title="Batal"><i class="bi bi-x-lg"></i></button>' +
            '</div>';
    },

    clearAll: function() {
        this.selected.clear();
        document.querySelectorAll('.bulk-row-checkbox, #selectAllCheckbox').forEach(function(cb) {
            cb.checked = false;
        });
        var bar = document.getElementById('bulk-action-bar');
        if (bar) bar.classList.add('d-none');
    },

    action: function(type) {
        if (this.selected.size === 0) return;
        var ids = Array.from(this.selected).join(',');

        if (type === 'delete') {
            if (!confirm('Hapus ' + this.selected.size + ' aset terpilih secara permanen? Tindakan ini tidak dapat dibatalkan.')) return;
            this.submitBulk('delete', ids, null);
        } else if (type === 'change_status') {
            var status = prompt('Masukkan status baru (Aktif / Dipinjam / Dalam Perbaikan / Rusak / Afkir):');
            if (status) this.submitBulk('change_status', ids, status, 'bulk_status');
        } else if (type === 'move_category') {
            var cat = prompt('Masukkan kategori baru (Tech / Tools / Furniture / Vehicle / Office):');
            if (cat) this.submitBulk('move_category', ids, cat, 'bulk_category');
        } else if (type === 'export') {
            this.submitBulk('export', ids, null);
        }
    },

    submitBulk: function(action, ids, value, valueField) {
        var form = document.createElement('form');
        form.method = 'POST';
        form.action = '/assets/bulk-action';

        function addInput(name, val) {
            var inp = document.createElement('input');
            inp.type = 'hidden'; inp.name = name; inp.value = val;
            form.appendChild(inp);
        }

        addInput('action', action);
        addInput('asset_ids', ids);
        if (value && valueField) addInput(valueField, value);

        document.body.appendChild(form);
        form.submit();
    }
};

// ==========================================
// 8. OFFLINE INDEXEDDB & STOCK OPNAME SYNC
// ==========================================
window.JescaOfflineDB = {
    db: null,
    dbName: 'jesca_offline_db',
    dbVersion: 1,

    init: function() {
        return new Promise(function(resolve) {
            if (JescaOfflineDB.db) {
                resolve(JescaOfflineDB.db);
                return;
            }
            if (!window.indexedDB) {
                resolve(null);
                return;
            }
            var request = window.indexedDB.open(JescaOfflineDB.dbName, JescaOfflineDB.dbVersion);
            request.onupgradeneeded = function(e) {
                var db = e.target.result;
                if (!db.objectStoreNames.contains('assets_cache')) {
                    db.createObjectStore('assets_cache', { keyPath: 'code' });
                }
                if (!db.objectStoreNames.contains('opname_queue')) {
                    db.createObjectStore('opname_queue', { keyPath: 'id', autoIncrement: true });
                }
            };
            request.onsuccess = function(e) {
                JescaOfflineDB.db = e.target.result;
                resolve(JescaOfflineDB.db);
            };
            request.onerror = function() {
                resolve(null);
            };
        });
    },

    cacheAssets: function() {
        if (!navigator.onLine) return Promise.resolve();
        return fetch('/api/assets/cache-summary')
            .then(function(res) {
                if (!res.ok) return null;
                return res.json();
            })
            .then(function(data) {
                if (!data || !data.data) return;
                return JescaOfflineDB.init().then(function(db) {
                    if (!db) return;
                    try {
                        var tx = db.transaction('assets_cache', 'readwrite');
                        var store = tx.objectStore('assets_cache');
                        data.data.forEach(function(item) {
                            store.put(item);
                        });
                    } catch (e) {}
                });
            })
            .catch(function() {});
    },

    getAsset: function(code) {
        return JescaOfflineDB.init().then(function(db) {
            if (!db) return null;
            return new Promise(function(resolve) {
                try {
                    var tx = db.transaction('assets_cache', 'readonly');
                    var store = tx.objectStore('assets_cache');
                    var req = store.get(code);
                    req.onsuccess = function() {
                        resolve(req.result || null);
                    };
                    req.onerror = function() {
                        resolve(null);
                    };
                } catch (e) {
                    resolve(null);
                }
            });
        });
    },

    queueOpname: function(record) {
        return JescaOfflineDB.init().then(function(db) {
            if (!db) return false;
            return new Promise(function(resolve, reject) {
                try {
                    var tx = db.transaction('opname_queue', 'readwrite');
                    var store = tx.objectStore('opname_queue');
                    record.is_offline = !navigator.onLine;
                    record.scanned_at = record.scanned_at || new Date().toISOString();
                    var req = store.add(record);
                    req.onsuccess = function() {
                        JescaOfflineDB.updateBadges();
                        resolve(true);
                    };
                    req.onerror = function(err) {
                        reject(err);
                    };
                } catch (e) {
                    reject(e);
                }
            });
        });
    },

    getQueueCount: function() {
        return JescaOfflineDB.init().then(function(db) {
            if (!db) return 0;
            return new Promise(function(resolve) {
                try {
                    var tx = db.transaction('opname_queue', 'readonly');
                    var store = tx.objectStore('opname_queue');
                    var req = store.count();
                    req.onsuccess = function() {
                        resolve(req.result || 0);
                    };
                    req.onerror = function() {
                        resolve(0);
                    };
                } catch (e) {
                    resolve(0);
                }
            });
        });
    },

    syncQueue: function() {
        if (!navigator.onLine) return Promise.resolve(0);
        return JescaOfflineDB.init().then(function(db) {
            if (!db) return 0;
            return new Promise(function(resolve) {
                try {
                    var tx = db.transaction('opname_queue', 'readonly');
                    var store = tx.objectStore('opname_queue');
                    var req = store.getAll();
                    req.onsuccess = function() {
                        var items = req.result || [];
                        if (!items || items.length === 0) {
                            resolve(0);
                            return;
                        }
                        var csrfMeta = document.querySelector('meta[name="csrf-token"]');
                        var headers = { 'Content-Type': 'application/json' };
                        if (csrfMeta) {
                            headers['X-CSRFToken'] = csrfMeta.getAttribute('content');
                        }
                        fetch('/api/stock-opname/sync', {
                            method: 'POST',
                            headers: headers,
                            body: JSON.stringify({ items: items })
                        })
                        .then(function(res) {
                            if (!res.ok) throw new Error('Status ' + res.status);
                            return res.json();
                        })
                        .then(function(resp) {
                            if (resp && resp.status === 'success') {
                                var clearTx = db.transaction('opname_queue', 'readwrite');
                                clearTx.objectStore('opname_queue').clear();
                                clearTx.oncomplete = function() {
                                    JescaToast.show('Sinkronisasi selesai: ' + items.length + ' data stok opname offline berhasil disimpan ke server.', 'success');
                                    JescaOfflineDB.updateBadges();
                                    resolve(items.length);
                                };
                            } else {
                                resolve(0);
                            }
                        })
                        .catch(function(err) {
                            console.error('Stock opname sync error:', err);
                            resolve(0);
                        });
                    };
                    req.onerror = function() {
                        resolve(0);
                    };
                } catch (e) {
                    resolve(0);
                }
            });
        });
    },

    updateBadges: function() {
        var netBadge = document.getElementById('qr-net-badge');
        var queueBadge = document.getElementById('qr-queue-badge');
        if (netBadge) {
            if (navigator.onLine) {
                netBadge.className = 'badge bg-success-subtle text-success border border-success-subtle rounded-pill font-monospace';
                netBadge.textContent = 'Online';
            } else {
                netBadge.className = 'badge bg-warning-subtle text-warning border border-warning-subtle rounded-pill font-monospace';
                netBadge.textContent = 'Offline (Lokal)';
            }
        }
        if (queueBadge) {
            JescaOfflineDB.getQueueCount().then(function(count) {
                if (count > 0) {
                    queueBadge.classList.remove('d-none');
                    queueBadge.textContent = 'Antrean: ' + count;
                } else {
                    queueBadge.classList.add('d-none');
                }
            });
        }
    }
};

window.addEventListener('online', function() {
    JescaOfflineDB.updateBadges();
    JescaToast.show('Koneksi internet kembali aktif. Menyinkronkan data di latar belakang...', 'info');
    JescaOfflineDB.syncQueue();
    JescaOfflineDB.cacheAssets();
});

window.addEventListener('offline', function() {
    JescaOfflineDB.updateBadges();
    JescaToast.show('Perangkat beralih ke mode offline. Hasil scan tetap dicatat ke memori lokal.', 'warning');
});

// ==========================================
// 9. CAMERA QR SCANNER & STOK OPNAME
// ==========================================
window.JescaQRScanner = {
    scanner: null,

    open: function() {
        var modal = document.getElementById('qrScannerModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'qrScannerModal';
            modal.className = 'modal fade';
            modal.setAttribute('tabindex', '-1');
            modal.innerHTML = '<div class="modal-dialog modal-dialog-centered">' +
                '<div class="modal-content border-0 shadow-lg rounded-4">' +
                '<div class="modal-header border-bottom py-3 px-4 d-flex justify-content-between align-items-center">' +
                '<div class="d-flex align-items-center gap-2">' +
                '<i class="bi bi-camera fs-5 text-primary"></i>' +
                '<div>' +
                '<h6 class="modal-title fw-bold mb-0">Scan QR Code &amp; Stok Opname</h6>' +
                '<div class="d-flex align-items-center gap-1 mt-1">' +
                '<span id="qr-net-badge" class="badge rounded-pill font-monospace" style="font-size:0.65rem;"></span>' +
                '<span id="qr-queue-badge" class="badge bg-primary-subtle text-primary border border-primary-subtle rounded-pill font-monospace d-none" style="font-size:0.65rem;"></span>' +
                '</div>' +
                '</div>' +
                '</div>' +
                '<button type="button" class="btn-close" data-bs-dismiss="modal" onclick="JescaQRScanner.stop()"></button>' +
                '</div>' +
                '<div class="modal-body p-3">' +
                '<div id="qr-reader" style="width:100%;min-height:280px;border-radius:12px;overflow:hidden;background:#000;"></div>' +
                '<div id="qr-verify-container" class="d-none"></div>' +
                '<p id="qr-hint-text" class="text-muted small text-center mt-2 mb-0">Arahkan kamera ke QR Code pada label aset JESCA</p>' +
                '</div>' +
                '<div class="modal-footer border-top px-4 py-2" id="qr-modal-footer">' +
                '<button type="button" class="btn btn-light border btn-sm" data-bs-dismiss="modal" onclick="JescaQRScanner.stop()">Tutup</button>' +
                '</div>' +
                '</div></div>';
            document.body.appendChild(modal);

            modal.addEventListener('hidden.bs.modal', function() {
                JescaQRScanner.stop();
            });
        }

        JescaOfflineDB.updateBadges();
        JescaOfflineDB.cacheAssets();

        // Reset display state inside modal
        var readerEl = document.getElementById('qr-reader');
        var verifyContainer = document.getElementById('qr-verify-container');
        var hintEl = document.getElementById('qr-hint-text');
        if (readerEl) readerEl.classList.remove('d-none');
        if (hintEl) hintEl.classList.remove('d-none');
        if (verifyContainer) {
            verifyContainer.classList.add('d-none');
            verifyContainer.innerHTML = '';
        }

        var bsModal = bootstrap.Modal.getOrCreateInstance(modal);
        bsModal.show();

        setTimeout(function() {
            JescaQRScanner.start(bsModal);
        }, 400);
    },

    start: function(bsModal) {
        JescaQRScanner.stop();
        var readerEl = document.getElementById('qr-reader');
        var verifyContainer = document.getElementById('qr-verify-container');
        var hintEl = document.getElementById('qr-hint-text');
        if (readerEl) readerEl.classList.remove('d-none');
        if (hintEl) hintEl.classList.remove('d-none');
        if (verifyContainer) verifyContainer.classList.add('d-none');

        if (!readerEl) return;
        readerEl.innerHTML = '';

        if (typeof Html5Qrcode !== 'undefined') {
            try {
                JescaQRScanner.scanner = new Html5Qrcode('qr-reader');
                JescaQRScanner.scanner.start(
                    { facingMode: 'environment' },
                    { fps: 10, qrbox: { width: 250, height: 250 } },
                    function(decodedText) {
                        JescaQRScanner.handleDecoded(decodedText, bsModal);
                    },
                    function() {}
                ).catch(function() {
                    readerEl.innerHTML = '<div class="text-center py-5 text-white"><i class="bi bi-camera-video-off fs-2 d-block mb-2 text-warning"></i><small>Tidak dapat mengakses kamera.<br>Pastikan izin kamera diberikan pada browser atau gunakan HTTPS.</small></div>';
                });
            } catch (e) {
                readerEl.innerHTML = '<div class="text-center py-5 text-white"><i class="bi bi-exclamation-octagon fs-2 d-block mb-2 text-danger"></i><small>Error inisialisasi kamera: ' + (e.message || e) + '</small></div>';
            }
        } else {
            readerEl.innerHTML = '<div class="text-center py-5 text-white"><i class="bi bi-qr-code fs-2 d-block mb-2 text-info"></i><small>Library kamera scanner belum siap.<br>Pastikan tersambung ke internet untuk memuat library.</small></div>';
        }
    },

    handleDecoded: function(decodedText, bsModal) {
        JescaQRScanner.stop();

        var raw = (decodedText || '').trim();
        var assetCode = raw;
        if (raw.indexOf('/scan/') !== -1) {
            assetCode = raw.substring(raw.lastIndexOf('/scan/') + 6).split('?')[0].split('#')[0];
        } else if (raw.indexOf('/') !== -1) {
            var parts = raw.split('/');
            assetCode = parts[parts.length - 1];
        }
        assetCode = decodeURIComponent(assetCode).trim();

        var readerEl = document.getElementById('qr-reader');
        var verifyContainer = document.getElementById('qr-verify-container');
        var hintEl = document.getElementById('qr-hint-text');

        if (readerEl) readerEl.classList.add('d-none');
        if (hintEl) hintEl.classList.add('d-none');
        if (verifyContainer) {
            verifyContainer.classList.remove('d-none');
            verifyContainer.innerHTML = '<div class="text-center py-4 text-muted"><div class="spinner-border spinner-border-sm text-primary me-2"></div>Memuat data aset ' + assetCode + '...</div>';
        }

        JescaOfflineDB.getAsset(assetCode).then(function(cachedAsset) {
            var name = cachedAsset ? cachedAsset.name : 'Aset Fisik';
            var cat = cachedAsset ? cachedAsset.category : 'Umum';
            var loc = cachedAsset ? cachedAsset.location : 'Kantor Pusat';
            var status = cachedAsset ? cachedAsset.status : 'Aktif';

            var cardHtml = '<div class="card border rounded-3 p-3 bg-light shadow-sm">' +
                '<div class="d-flex justify-content-between align-items-start mb-2">' +
                '<div>' +
                '<span class="badge bg-primary font-monospace" style="font-size:0.75rem;">' + assetCode + '</span>' +
                '<h6 class="fw-bold text-dark mt-1 mb-0">' + name + '</h6>' +
                '<small class="text-muted">' + cat + ' &bull; Lokasi: ' + loc + '</small>' +
                '</div>' +
                '<span class="badge bg-secondary-subtle text-secondary border font-monospace">' + status + '</span>' +
                '</div>' +
                '<div class="border-top pt-2 mt-2">' +
                '<label class="form-label small fw-bold mb-1 text-secondary">Kondisi Fisik Verifikasi:</label>' +
                '<div class="d-flex flex-column gap-1 mb-2">' +
                '<div class="form-check">' +
                '<input class="form-check-input" type="radio" name="opname_cond" id="cond1" value="Sesuai & Baik" checked>' +
                '<label class="form-check-label small" for="cond1">Sesuai &amp; Baik</label>' +
                '</div>' +
                '<div class="form-check">' +
                '<input class="form-check-input" type="radio" name="opname_cond" id="cond2" value="Rusak Ringan">' +
                '<label class="form-check-label small" for="cond2">Rusak Ringan</label>' +
                '</div>' +
                '<div class="form-check">' +
                '<input class="form-check-input" type="radio" name="opname_cond" id="cond3" value="Lokasi Berpindah">' +
                '<label class="form-check-label small" for="cond3">Lokasi Berpindah</label>' +
                '</div>' +
                '<div class="form-check">' +
                '<input class="form-check-input" type="radio" name="opname_cond" id="cond4" value="Hilang/Tidak Ditemukan">' +
                '<label class="form-check-label small" for="cond4">Hilang / Tidak Ditemukan</label>' +
                '</div>' +
                '</div>' +
                '<div class="mb-2">' +
                '<label class="form-label small fw-bold mb-1 text-secondary">Lokasi Dicek:</label>' +
                '<input type="text" id="opname_loc" class="form-control form-control-sm" value="' + loc + '" placeholder="Lokasi fisik ditemukan">' +
                '</div>' +
                '<div class="mb-3">' +
                '<label class="form-label small fw-bold mb-1 text-secondary">Catatan Verifikasi (Opsional):</label>' +
                '<input type="text" id="opname_notes" class="form-control form-control-sm" placeholder="Contoh: Unit bersih, stiker label utuh">' +
                '</div>' +
                '<div class="d-flex gap-2">' +
                '<button type="button" class="btn btn-primary btn-sm flex-grow-1 fw-bold" id="btn-save-opname">' +
                '<i class="bi bi-check2-circle me-1"></i>Simpan &amp; Lanjut Scan' +
                '</button>' +
                '<button type="button" class="btn btn-light border btn-sm" id="btn-cancel-opname">Scan Ulang</button>' +
                '</div>' +
                '</div>' +
                '</div>';

            if (verifyContainer) {
                verifyContainer.innerHTML = cardHtml;

                var btnSave = document.getElementById('btn-save-opname');
                var btnCancel = document.getElementById('btn-cancel-opname');

                if (btnCancel) {
                    btnCancel.onclick = function() {
                        JescaQRScanner.start(bsModal);
                    };
                }

                if (btnSave) {
                    btnSave.onclick = function() {
                        var checkedRadio = document.querySelector('input[name="opname_cond"]:checked');
                        var condition = checkedRadio ? checkedRadio.value : 'Sesuai & Baik';
                        var locInput = document.getElementById('opname_loc');
                        var notesInput = document.getElementById('opname_notes');

                        var opnameData = {
                            asset_code: assetCode,
                            asset_name: name,
                            physical_condition: condition,
                            location_checked: locInput ? locInput.value.trim() : loc,
                            notes: notesInput ? notesInput.value.trim() : '',
                            scanned_at: new Date().toISOString()
                        };

                        JescaOfflineDB.queueOpname(opnameData).then(function() {
                            if (navigator.onLine) {
                                JescaOfflineDB.syncQueue();
                            } else {
                                JescaToast.show('Data opname [' + assetCode + '] disimpan ke memori lokal.', 'info');
                            }
                            JescaQRScanner.start(bsModal);
                        }).catch(function() {
                            JescaQRScanner.start(bsModal);
                        });
                    };
                }
            }
        });
    },

    stop: function() {
        if (this.scanner) {
            try {
                this.scanner.stop().then(function() {
                    try { JescaQRScanner.scanner.clear(); } catch(e){}
                }).catch(function() {});
            } catch(e) {}
            this.scanner = null;
        }
    }
};

// ==========================================
// 9. LAZY LOADING CHARTS (IntersectionObserver)
// ==========================================
window.JescaCharts = {
    rendered: new Set(),

    init: function() {
        if (!window.IntersectionObserver) {
            document.querySelectorAll('[data-chart]').forEach(function(el) {
                JescaCharts.render(el);
            });
            return;
        }

        var observer = new IntersectionObserver(function(entries) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting && !JescaCharts.rendered.has(entry.target.id)) {
                    JescaCharts.rendered.add(entry.target.id);
                    JescaCharts.render(entry.target);
                }
            });
        }, { threshold: 0.1 });

        document.querySelectorAll('[data-chart]').forEach(function(el) {
            observer.observe(el);
        });
    },

    render: function(el) {
        var chartName = el.dataset.chart;
        var initFn = window['initChart_' + chartName];
        if (typeof initFn === 'function') {
            initFn(el);
        }
    }
};

// ==========================================
// 10. ASSET COMPARISON VIEW (Side-by-Side)
// ==========================================
window.AssetCompare = {
    selected: [],

    toggle: function(assetId) {
        var idx = this.selected.indexOf(assetId);
        if (idx > -1) {
            this.selected.splice(idx, 1);
        } else {
            if (this.selected.length >= 2) {
                JescaToast.show('Maksimal 2 aset untuk dibandingkan.', 'warning');
                return;
            }
            this.selected.push(assetId);
        }
        this.updateBar();
    },

    updateBar: function() {
        var bar = document.getElementById('compare-bar');
        if (this.selected.length === 0) {
            if (bar) bar.classList.add('d-none');
            return;
        }
        if (!bar) {
            bar = document.createElement('div');
            bar.id = 'compare-bar';
            bar.style.cssText = 'position:fixed;top:70px;right:1.5rem;z-index:1040;';
            document.body.appendChild(bar);
        }

        bar.className = '';
        bar.innerHTML = '<div class="card border-0 shadow-lg rounded-3 p-3" style="min-width:210px;background:white;">' +
            '<div class="small fw-bold mb-1"><i class="bi bi-layout-split me-1 text-primary"></i>Komparasi Aset</div>' +
            '<div class="small text-muted mb-2">' + this.selected.length + ' dari 2 aset dipilih</div>' +
            (this.selected.length === 2 ? '<button class="btn btn-primary btn-sm w-100 mb-1" onclick="AssetCompare.showModal()"><i class="bi bi-bar-chart-steps me-1"></i>Bandingkan</button>' : '') +
            '<button class="btn btn-light border btn-sm w-100" onclick="AssetCompare.clear()">Batal</button></div>';
    },

    clear: function() {
        this.selected = [];
        var bar = document.getElementById('compare-bar');
        if (bar) bar.classList.add('d-none');
    },

    showModal: function() {
        if (this.selected.length < 2) return;
        var id1 = this.selected[0], id2 = this.selected[1];

        Promise.all([
            fetch('/api/assets/' + id1).then(function(r) { return r.json(); }),
            fetch('/api/assets/' + id2).then(function(r) { return r.json(); })
        ]).then(function(results) {
            var a1 = results[0].data, a2 = results[1].data;
            var fields = [
                ['Kode Aset', 'asset_code'],
                ['Nama Aset', 'name'],
                ['Kategori', 'category'],
                ['Status', 'status'],
                ['Lokasi', 'location'],
                ['Nilai Perolehan', 'purchase_price'],
                ['Nilai Buku (Depresiasi)', 'current_book_value'],
                ['Peminjam', 'borrower'],
                ['Perlu Maintenance', 'needs_maintenance'],
                ['Jadwal Maintenance', 'next_maintenance_date'],
                ['Deskripsi', 'description']
            ];

            var rows = fields.map(function(f) {
                var v1 = String(a1[f[1]] !== null && a1[f[1]] !== undefined ? a1[f[1]] : '-');
                var v2 = String(a2[f[1]] !== null && a2[f[1]] !== undefined ? a2[f[1]] : '-');
                var isDiff = v1 !== v2;
                var style = isDiff ? 'background:#fffbeb;' : '';
                return '<tr style="' + style + '"><td class="text-muted small fw-semibold py-2 px-3">' + f[0] + '</td>' +
                    '<td class="py-2 px-3 small">' + v1 + '</td>' +
                    '<td class="py-2 px-3 small">' + v2 + '</td></tr>';
            }).join('');

            var existing = document.getElementById('compareModal');
            if (existing) existing.remove();

            var modal = document.createElement('div');
            modal.id = 'compareModal';
            modal.className = 'modal fade';
            modal.setAttribute('tabindex', '-1');
            modal.innerHTML = '<div class="modal-dialog modal-lg modal-dialog-centered">' +
                '<div class="modal-content border-0 shadow-lg rounded-4">' +
                '<div class="modal-header border-bottom py-3 px-4">' +
                '<h6 class="modal-title fw-bold"><i class="bi bi-layout-split me-2 text-primary"></i>Komparasi Side-by-Side Aset</h6>' +
                '<button type="button" class="btn-close" data-bs-dismiss="modal"></button>' +
                '</div>' +
                '<div class="modal-body p-0">' +
                '<div class="table-responsive"><table class="table mb-0">' +
                '<thead class="table-light"><tr><th class="py-2 px-3">Atribut</th><th class="py-2 px-3">' + (a1.asset_code || 'Aset 1') + '</th><th class="py-2 px-3">' + (a2.asset_code || 'Aset 2') + '</th></tr></thead>' +
                '<tbody>' + rows + '</tbody></table></div>' +
                '<p class="px-3 py-2 small text-muted mb-0" style="background:#fffbeb;"><i class="bi bi-info-circle me-1 text-warning"></i>Baris berwarna kuning menandakan perbedaan nilai antar kedua aset.</p>' +
                '</div>' +
                '<div class="modal-footer border-top px-4 py-2"><button class="btn btn-secondary btn-sm" data-bs-dismiss="modal">Tutup</button></div>' +
                '</div></div>';

            document.body.appendChild(modal);
            bootstrap.Modal.getOrCreateInstance(modal).show();
        }).catch(function() {
            JescaToast.show('Gagal memuat data aset untuk komparasi.', 'danger');
        });
    }
};

// ==========================================
// 11. WELCOME ONBOARDING & SPOTLIGHT TOUR
// ==========================================
window.JescaOnboarding = {
    modalId: 'onboardingModal',
    menuModalId: 'panduanMenuModal',
    currentTourStep: 0,
    tourActive: false,
    activeSteps: [],
    _boundReposition: null,

    desktopTourSteps: [
        {
            elementId: 'tourMenuDashboard',
            title: 'Dashboard (Ringkasan Sistem)',
            desc: 'Pusat ringkasan dan statistik utama seluruh aset kantor. Menampilkan total unit, perkiraan nilai aset rupiah, grafik status barang, dan peringatan dini secara real-time.',
            actionHint: 'Klik menu ini untuk melihat ringkasan performa inventaris Anda.'
        },
        {
            elementId: 'tourMenuAssets',
            title: 'Data Aset (Master Inventaris)',
            desc: 'Tempat utama untuk melihat, mencari, menambah barang baru, mencetak stiker barcode/QR Code, mengelola riwayat peminjaman, serta mengunggah foto dan invoice aset.',
            actionHint: 'Gunakan menu ini untuk mendata dan memantau aset fisik kantor.'
        },
        {
            elementId: 'tourMenuPO',
            title: 'Purchase Order (Pengadaan Aset)',
            desc: 'Tempat Anda mengajukan permohonan pembelian barang inventaris baru ke vendor, menyusun estimasi biaya, meminta persetujuan anggaran, dan mencatat barang yang tiba.',
            actionHint: 'Ajukan pengadaan unit barang baru melalui modul ini.'
        },
        {
            elementId: 'tourMenuMaintenance',
            title: 'Pemeliharaan Aset (Meja Servis)',
            desc: 'Tempat menjadwalkan servis rutin barang, mencatat riwayat perbaikan kerusakan oleh teknisi, pengajuan servis dari staf, serta memantau pengeluaran biaya perbaikan.',
            actionHint: 'Jadwalkan servis rutin agar usia pakai aset kantor lebih awet.'
        },
        {
            elementId: 'tourMenuSites',
            title: 'Lokasi & Site (Ruangan & Gedung)',
            desc: 'Tempat mengelompokkan barang berdasarkan gedung kantor, lantai, gudang, maupun kantor cabang. Memudahkan staf mengetahui di mana posisi fisik setiap barang berada.',
            actionHint: 'Atur ruangan dan cabang kantor untuk ketertiban posisi aset.'
        },
        {
            elementId: 'tourMenuVendors',
            title: 'Vendor & Supplier (Mitra Rekanan)',
            desc: 'Buku data rekanan toko atau supplier tempat kantor membeli barang inventaris, lengkap dengan kontak sales/PIC, alamat, dan daftar aset yang pernah dibeli.',
            actionHint: 'Simpan data kontak toko rekanan untuk kemudahan klaim garansi.'
        },
        {
            elementId: 'tourMenuHistory',
            title: 'Log Aktivitas (Audit Keamanan)',
            desc: 'Rekam jejak otomatis mencatat setiap aktivitas di sistem: siapa staf yang menambah, mengedit, meminjam, atau menghapus aset beserta tanggal dan jam pastinya.',
            actionHint: 'Pantau rekam jejak sistem untuk transparansi dan akuntabilitas tim.'
        },
        {
            elementId: 'tourMenuAudit',
            fallbackId: 'tourMenuExport',
            title: 'Laporan Audit & Export Data',
            desc: 'Cetak dokumen laporan inventaris resmi dalam format PDF standar eksekutif, serta ekspor seluruh data ke file Excel/CSV untuk rekonsiliasi pembukuan kantor.',
            actionHint: 'Cetak dokumen laporan PDF atau unduh data Excel dari modul ini.'
        },
        {
            elementId: 'tourMenuSettings',
            fallbackId: 'tourMenuChangePwd',
            title: 'Pengaturan Sistem & Keamanan Akun',
            desc: 'Pusat kontrol untuk mengelola keamanan kata sandi, akun pengguna, backup & restore database (cadangan data), proteksi jaringan, serta notifikasi email SMTP.',
            actionHint: 'Kelola keamanan akun dan konfigurasi sistem pada menu ini.'
        },
        {
            elementId: 'tourMenuCategories',
            title: 'Kategori Aset (Filter Cepat)',
            desc: 'Di kolom ini Anda bisa menyaring data aset berdasarkan jenisnya dengan satu klik: Tech/IT, Tools (Peralatan), Furnitur, Kendaraan, dan Kantor untuk pencarian instan.',
            actionHint: 'Klik salah satu kategori untuk langsung melihat aset terkait.'
        },
        {
            elementId: 'navbarQrBtn',
            title: 'Pemindai Kamera QR Code',
            desc: 'Klik tombol kamera ini kapan saja untuk memindai stiker QR Code fisik pada label aset langsung lewat kamera smartphone atau webcam laptop untuk cek data instan.',
            actionHint: 'Arahkan kamera ke stiker label aset untuk identifikasi cepat.'
        },
        {
            elementId: 'navbarAddAssetBtn',
            title: 'Tambah Aset Baru (Pintasan Cepat)',
            desc: 'Tombol pintas untuk mendaftarkan barang baru ke sistem dari halaman mana pun tanpa harus masuk ke menu Data Aset terlebih dahulu.',
            actionHint: 'Pencet tombol ini untuk input cepat penerimaan barang baru.'
        },
        {
            elementId: 'navbarNotifBell',
            title: 'Pusat Notifikasi & Pengingat',
            desc: 'Ikon lonceng ini akan menyala jika ada barang yang jatuh tempo jadwal servisnya, atau peminjaman aset kantor yang terlambat dikembalikan oleh staf.',
            actionHint: 'Periksa pemberitahuan berkala agar tidak ada aset yang terlewat.'
        },
        {
            elementId: 'footerCommandBadge',
            title: 'Pintasan Keyboard (Ctrl + K)',
            desc: 'Tekan tombol Ctrl + K pada keyboard Anda kapan saja. Jendela pencarian pintar akan terbuka untuk mencari nama barang, membuka menu, atau berpindah fitur secepat kilat.',
            actionHint: 'Tekan Ctrl + K di keyboard Anda untuk navigasi kilat.'
        }
    ],

    mobileTourSteps: [
        {
            elementId: 'mobileTourProfileCard',
            fallbackId: 'mobileNavDashboard',
            requiresSheet: false,
            scrollMode: 'top',
            title: 'Kartu Identitas & Status Role',
            desc: 'Menampilkan profil akun Anda, lencana hak akses (Admin, Staff, Teknisi, atau Auditor), serta ringkasan status operasional hari ini.',
            actionHint: 'Pastikan akun dan hak akses Anda sudah sesuai sebelum memulai aktivitas.'
        },
        {
            elementId: 'mobileTourContextBtn',
            fallbackId: 'mobileTourTopBar',
            requiresSheet: false,
            scrollMode: 'top',
            title: 'Pintasan Tugas Prioritas Role',
            desc: 'Bilah kontekstual pintar yang otomatis menyesuaikan peran Anda: persetujuan PO atau tambah aset bagi Admin/Staff, meja servis bagi Teknisi, dan laporan bagi Auditor.',
            actionHint: 'Ketuk tombol aksi di sebelah kanan bilah ini untuk langsung menjalankan tugas utama.'
        },
        {
            elementId: 'mobileTourMainGrid',
            fallbackId: 'mobileTourBottomNav',
            requiresSheet: false,
            scrollMode: 'belowNav',
            title: 'Menu Utama Super-App (4x2)',
            desc: 'Delapan ikon pintasan cepat ke modul utama JESCA (Data Aset, Purchase Order, Servis Aset, Lokasi, Vendor, Log, Laporan) yang tersusun rapi untuk layar sentuh.',
            actionHint: 'Ketuk salah satu ikon berwarna untuk membuka modul yang diinginkan.'
        },
        {
            elementId: 'mobileTourStatGrid',
            fallbackId: 'mobileTourBottomNav',
            requiresSheet: false,
            scrollMode: 'belowNav',
            title: 'Kartu Ringkasan Real-Time (2x2)',
            desc: 'Pantau cepat Total Aset Aktif, Nilai Buku Depresiasi, Unit Dipinjam, serta Aset yang Perlu Perhatian atau Jadwal Servis langsung dari beranda.',
            actionHint: 'Ketuk kartu ringkasan mana saja untuk langsung memfilter daftar aset.'
        },
        {
            elementId: 'mobileTourRecentAssets',
            fallbackId: 'mobileTourBottomNav',
            requiresSheet: false,
            scrollMode: 'belowNav',
            title: 'Daftar Aset & Aktivitas Terbaru',
            desc: 'Menampilkan daftar barang inventaris yang baru didaftarkan beserta status, nilai buku, dan aktivitas terakhir secara langsung di beranda HP.',
            actionHint: 'Ketuk salah satu baris aset untuk melihat rincian lengkapnya.'
        },
        {
            elementId: 'mobileTourTopActions',
            requiresSheet: false,
            isFixed: true,
            scrollMode: 'top',
            title: 'Pusat Notifikasi, Tema & Bahasa',
            desc: 'Ketuk ikon lonceng untuk memeriksa peringatan jadwal servis atau keterlambatan pinjam, serta tombol di sebelahnya untuk mengganti tema warna, bahasa (ID/EN), dan profil.',
            actionHint: 'Periksa ikon lonceng secara berkala agar tidak ada jadwal yang terlewat.'
        },
        {
            elementId: 'mobileNavAssets',
            requiresSheet: false,
            isFixed: true,
            title: 'Tab Navigasi Cepat: Data Aset',
            desc: 'Akses langsung ke Master Inventaris Aset untuk mencari barang, meminjam/mengembalikan aset, mengunggah lampiran, serta mencetak label QR Code.',
            actionHint: 'Ketuk tab Aset di bilah bawah untuk membuka daftar seluruh inventaris.'
        },
        {
            elementId: 'mobileTourQrFab',
            requiresSheet: false,
            isFixed: true,
            title: 'Tombol Utama Scan QR Kamera',
            desc: 'Tombol kamera di tengah navigasi bawah untuk langsung memindai stiker QR Code fisik pada aset atau menjalankan mode Stok Opname lapangan.',
            actionHint: 'Ketuk tombol biru tengah ini kapan saja saat berada di dekat fisik barang.'
        },
        {
            elementId: 'mobileNavService',
            fallbackId: 'mobileBottomMenuBtn',
            requiresSheet: false,
            isFixed: true,
            title: 'Tab Meja Servis & Pemeliharaan',
            desc: 'Pintasan cepat untuk memantau jadwal pemeliharaan rutin, mencatat perbaikan unit yang rusak, atau membuka Laporan Audit sesuai hak akses akun Anda.',
            actionHint: 'Perhatikan lencana angka merah pada ikon ini jika ada jadwal servis jatuh tempo.'
        },
        {
            elementId: 'mobileBottomMenuBtn',
            requiresSheet: false,
            isFixed: true,
            title: 'Tombol Laci Semua Menu',
            desc: 'Membuka laci menu lengkap dari bawah layar (Bottom Sheet) yang berisi seluruh fitur operasional, laporan, pengaturan akun, dan filter kategori aset.',
            actionHint: 'Ketuk tab Menu di pojok kanan bawah untuk membuka seluruh fitur JESCA.'
        },
        {
            elementId: 'mobileTourSheetOps',
            requiresSheet: true,
            sheetScroll: 'top',
            title: 'Semua Menu: Inventaris & Operasional',
            desc: 'Di dalam laci Semua Menu, bagian pertama ini memuat akses lengkap ke Dashboard, Data Aset, Scan QR, Purchase Order (PO), Servis Aset, Lokasi & Site, serta Data Vendor.',
            actionHint: 'Pilih salah satu ikon modul operasional untuk berpindah halaman dengan cepat.'
        },
        {
            elementId: 'mobileTourSheetReports',
            requiresSheet: true,
            sheetScroll: 'middle',
            title: 'Semua Menu: Riwayat, Audit & Export',
            desc: 'Bagian kedua memuat Log Aktivitas keamanan, Laporan Audit, Laporan Masuk/Kendala, serta fitur Export Data untuk mengunduh laporan Excel (.xlsx), PDF, atau CSV.',
            actionHint: 'Gunakan tombol Export Data untuk mengunduh laporan inventaris resmi.'
        },
        {
            elementId: 'mobileTourSheetSettings',
            requiresSheet: true,
            sheetScroll: 'middle',
            title: 'Semua Menu: Akun & Pengaturan Sistem',
            desc: 'Pusat pengaturan untuk mengelola Profil Saya, Ganti Kata Sandi, Panduan Aplikasi, serta menu Admin (Kelola Akun, Backup Database, dan Pengaturan Sistem).',
            actionHint: 'Ketuk ikon Panduan di bagian ini kapan saja jika ingin mengulang tur layar.'
        },
        {
            elementId: 'mobileTourSheetCategories',
            requiresSheet: true,
            sheetScroll: 'bottom',
            title: 'Semua Menu: Pintasan Kategori Aset',
            desc: 'Baris tombol geser di bagian bawah laci untuk menyaring aset berdasarkan kategori (Tech, Tools, Furniture, Vehicle, dan Office) hanya dengan satu sentuhan.',
            actionHint: 'Geser ke samping dan ketuk kategori untuk memfilter aset secara instan.'
        }
    ],

    getCompletionKey: function() {
        return window.innerWidth < 768 ? 'jesca_tour_completed_mobile' : 'jesca_tour_completed';
    },

    resolveStepTarget: function(step) {
        var el = null;
        if (step.elementId) {
            el = document.getElementById(step.elementId);
        }
        if (!el && step.fallbackId) {
            el = document.getElementById(step.fallbackId);
        }
        if (!el && step.selector) {
            el = document.querySelector(step.selector);
        }
        if (!el) return null;

        // Jangan ambil elemen di dalam Bottom Sheet kecuali langkah tersebut memang langkah Sheet
        if (!step.requiresSheet && el.closest && el.closest('#mobileAllMenuSheet')) {
            return null;
        }

        var style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') return null;

        // Untuk elemen di dalam Bottom Sheet pada layar HP, cek apakah sheet diizinkan tampil di layar HP
        if (step.requiresSheet) {
            var sheet = document.getElementById('mobileAllMenuSheet');
            if (!sheet || window.innerWidth >= 768) return null;
            return el;
        }

        if (el.offsetWidth === 0 && el.offsetHeight === 0 && el.getClientRects().length === 0) return null;
        return el;
    },

    buildActiveSteps: function() {
        var isMobile = window.innerWidth < 768;
        var source = isMobile ? this.mobileTourSteps : this.desktopTourSteps;
        var self = this;
        var wrapper = document.getElementById('wrapper');
        if (wrapper) {
            wrapper.classList.remove('toggled');
        }
        if (window.JescaMobileSheet && typeof window.JescaMobileSheet.close === 'function') {
            window.JescaMobileSheet.close(true);
        }
        this.activeSteps = source.filter(function(step) {
            return self.resolveStepTarget(step) !== null;
        });
    },

    init: function() {
        if (!document.getElementById('sidebar-wrapper')) {
            return;
        }

        // Selalu pasang listener carousel Buku Panduan agar tombol slide terakhir bekerja kapan saja
        var carouselEl = document.getElementById('onboardingCarousel');
        if (carouselEl && !carouselEl.dataset.boundOnboarding) {
            carouselEl.dataset.boundOnboarding = '1';
            carouselEl.addEventListener('slid.bs.carousel', function(e) {
                var nextBtn = document.getElementById('btn-onboarding-next');
                if (!nextBtn) return;
                if (e.to === 3) {
                    nextBtn.removeAttribute('data-bs-slide');
                    nextBtn.innerHTML = 'Mulai Gunakan JESCA <i class="bi bi-check2 ms-1"></i>';
                    nextBtn.onclick = function() {
                        JescaOnboarding.complete(true);
                    };
                } else {
                    nextBtn.setAttribute('data-bs-slide', 'next');
                    nextBtn.innerHTML = 'Selanjutnya <i class="bi bi-chevron-right ms-1"></i>';
                    nextBtn.onclick = null;
                }
            });
        }

        // Cek apakah halaman dibuka dari redirect _tour=1 (mis. mulai tur dari halaman selain Dashboard)
        var params = new URLSearchParams(window.location.search);
        if (params.get('_tour') === '1') {
            var cleanUrl = new URL(window.location);
            cleanUrl.searchParams.delete('_tour');
            window.history.replaceState({}, '', cleanUrl);
            setTimeout(function() {
                JescaOnboarding.startSpotlightTour(true);
            }, 350);
            return;
        }

        var completed = localStorage.getItem(this.getCompletionKey());
        if (completed === 'true') {
            return;
        }

        var dismissedThisSession = sessionStorage.getItem('jesca_tour_session_dismissed');
        if (dismissedThisSession === 'true') {
            return;
        }

        setTimeout(function() {
            JescaOnboarding.startSpotlightTour(false);
        }, 700);
    },

    showMenu: function() {
        if (window.JescaMobileSheet && typeof window.JescaMobileSheet.close === 'function') {
            window.JescaMobileSheet.close(true);
        }
        var menuEl = document.getElementById(this.menuModalId);
        if (menuEl) {
            var bsModal = bootstrap.Modal.getOrCreateInstance(menuEl);
            bsModal.show();
        } else {
            this.showModal();
        }
    },

    showModal: function() {
        var menuEl = document.getElementById(this.menuModalId);
        if (menuEl) {
            var bsMenu = bootstrap.Modal.getInstance(menuEl);
            if (bsMenu) bsMenu.hide();
        }
        var modalEl = document.getElementById(this.modalId);
        if (!modalEl) return;
        var carouselEl = document.getElementById('onboardingCarousel');
        if (carouselEl && typeof bootstrap !== 'undefined') {
            var c = bootstrap.Carousel.getOrCreateInstance(carouselEl);
            c.to(0);
        }
        var nextBtn = document.getElementById('btn-onboarding-next');
        if (nextBtn) {
            nextBtn.setAttribute('data-bs-slide', 'next');
            nextBtn.innerHTML = 'Selanjutnya <i class="bi bi-chevron-right ms-1"></i>';
            nextBtn.onclick = null;
        }
        var bsModal = bootstrap.Modal.getOrCreateInstance(modalEl);
        bsModal.show();
    },

    complete: function(isFinished) {
        if (isFinished === true) {
            localStorage.setItem(this.getCompletionKey(), 'true');
            localStorage.setItem('jesca_tour_completed', 'true');
            try { sessionStorage.removeItem('jesca_tour_session_dismissed'); } catch (e) {}
        } else {
            try { sessionStorage.setItem('jesca_tour_session_dismissed', 'true'); } catch (e) {}
            localStorage.removeItem(this.getCompletionKey());
            JescaToast.show('Panduan dilewati. Sesuai aturan, panduan akan otomatis muncul kembali pada sesi login berikutnya hingga selesai.', 'warning');
        }
        var modalEl = document.getElementById(this.modalId);
        if (modalEl) {
            var bsModal = bootstrap.Modal.getInstance(modalEl);
            if (bsModal) bsModal.hide();
        }
        var menuEl = document.getElementById(this.menuModalId);
        if (menuEl) {
            var bsMenu = bootstrap.Modal.getInstance(menuEl);
            if (bsMenu) bsMenu.hide();
        }
    },

    startSpotlightTour: function(fromManualTrigger) {
        var modalEl = document.getElementById(this.modalId);
        if (modalEl) {
            var bsModal = bootstrap.Modal.getInstance(modalEl);
            if (bsModal) bsModal.hide();
        }
        var menuEl = document.getElementById(this.menuModalId);
        if (menuEl) {
            var bsMenu = bootstrap.Modal.getInstance(menuEl);
            if (bsMenu) bsMenu.hide();
        }

        // Jika pengguna menekan Mulai Tur dari halaman selain Dashboard di HP, arahkan ke Dashboard agar seluruh 10 langkah tampil utuh
        if (window.innerWidth < 768 && !document.getElementById('mobileTourProfileCard')) {
            if (fromManualTrigger !== false && window.location.pathname !== '/dashboard') {
                window.location.href = '/dashboard?_tour=1';
                return;
            }
        }

        // Bersihkan sisa penguncian scroll dari modal Bootstrap agar halaman bebas di-scroll oleh tur
        document.body.classList.remove('modal-open');
        document.body.style.removeProperty('overflow');
        document.body.style.removeProperty('padding-right');
        document.querySelectorAll('.modal-backdrop').forEach(function(bd) { bd.remove(); });

        this.buildActiveSteps();
        if (!this.activeSteps || this.activeSteps.length === 0) {
            return;
        }
        this.tourActive = true;
        this.currentTourStep = 0;

        if (!this._boundReposition) {
            var self = this;
            this._boundReposition = function() {
                if (!self.tourActive) return;
                var step = self.activeSteps[self.currentTourStep];
                if (!step) return;
                var target = self.resolveStepTarget(step);
                if (!target) return;
                self.renderSpotlightUI(target.getBoundingClientRect(), step, self.currentTourStep + 1);
            };
            window.addEventListener('resize', this._boundReposition, { passive: true });
            window.addEventListener('scroll', this._boundReposition, { passive: true });
        }

        this.renderTourStep();
    },

    renderTourStep: function() {
        if (!this.tourActive) return;
        var step = this.activeSteps[this.currentTourStep];
        if (!step) {
            this.endTour(true);
            return;
        }

        // Pastikan sidebar desktop tidak pernah dibuka paksa di layar HP
        var wrapper = document.getElementById('wrapper');
        if (wrapper) {
            wrapper.classList.remove('toggled');
        }

        var isMobile = window.innerWidth < 768;

        // Buka atau tutup Bottom Sheet secara instan (0ms) sesuai kebutuhan langkah di HP
        if (isMobile && window.JescaMobileSheet) {
            if (step.requiresSheet) {
                window.JescaMobileSheet.open(true);
            } else {
                window.JescaMobileSheet.close(true);
            }
        }

        var target = this.resolveStepTarget(step);
        if (!target) {
            this.currentTourStep++;
            if (this.currentTourStep < this.activeSteps.length) {
                this.renderTourStep();
            } else {
                this.endTour(true);
            }
            return;
        }

        // Penyesuaian posisi scroll secara instan & deterministik (tanpa jeda smooth scroll yang meleset)
        if (isMobile) {
            if (step.requiresSheet) {
                var sheetBody = document.getElementById('mobileSheetScrollBody');
                if (sheetBody) {
                    if (step.sheetScroll === 'top') {
                        sheetBody.scrollTop = 0;
                    } else if (step.sheetScroll === 'bottom') {
                        sheetBody.scrollTop = sheetBody.scrollHeight;
                    } else {
                        sheetBody.scrollTop = Math.max(0, target.offsetTop - 70);
                    }
                }
            } else if (step.scrollMode === 'top') {
                window.scrollTo(0, 0);
            } else if (step.scrollMode === 'belowNav') {
                var r0 = target.getBoundingClientRect();
                var targetY = Math.max(0, window.pageYOffset + r0.top - 64);
                window.scrollTo(0, targetY);
            }
        } else {
            // Di Desktop, pastikan item di dalam sidebar-menu selalu ter-scroll ke area terlihat
            var sidebarMenu = target.closest && target.closest('.sidebar-menu');
            if (sidebarMenu) {
                var smRect = sidebarMenu.getBoundingClientRect();
                var tRect = target.getBoundingClientRect();
                if (tRect.top < smRect.top + 10 || tRect.bottom > smRect.bottom - 10) {
                    sidebarMenu.scrollTop = Math.max(0, target.offsetTop - (sidebarMenu.clientHeight / 2) + (target.offsetHeight / 2));
                }
            } else if (!step.isFixed) {
                try {
                    target.scrollIntoView({ behavior: 'instant', block: 'center' });
                } catch (e) {
                    target.scrollIntoView(false);
                }
            }
        }

        var stepNumber = this.currentTourStep + 1;
        var self = this;
        requestAnimationFrame(function() {
            if (!self.tourActive) return;
            var rect = target.getBoundingClientRect();
            self.renderSpotlightUI(rect, step, stepNumber);
        });
    },

    renderSpotlightUI: function(rect, step, stepNumber) {
        var overlay = document.getElementById('jesca-spotlight-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'jesca-spotlight-overlay';
            overlay.onclick = function(e) {
                if (e.target === overlay) {
                    JescaOnboarding.endTour(false);
                }
            };
            document.body.appendChild(overlay);
        }

        var box = document.getElementById('jesca-spotlight-box');
        if (!box) {
            box = document.createElement('div');
            box.id = 'jesca-spotlight-box';
            document.body.appendChild(box);
        }

        var winW = window.innerWidth;
        var winH = window.innerHeight;
        var pad = 6;
        var boxTop = Math.max(4, rect.top - pad);
        var boxLeft = Math.max(4, rect.left - pad);
        var boxWidth = Math.min(winW - boxLeft - 4, rect.width + (pad * 2));
        var boxHeight = Math.min(winH - boxTop - 4, rect.height + (pad * 2));

        box.style.top = boxTop + 'px';
        box.style.left = boxLeft + 'px';
        box.style.width = Math.max(24, boxWidth) + 'px';
        box.style.height = Math.max(24, boxHeight) + 'px';

        var popover = document.getElementById('jesca-spotlight-popover');
        if (!popover) {
            popover = document.createElement('div');
            popover.id = 'jesca-spotlight-popover';
            document.body.appendChild(popover);
        }

        var total = this.activeSteps.length;
        var cur = stepNumber || (this.currentTourStep + 1);
        var isLast = (cur === total);

        popover.innerHTML = '<div class="d-flex justify-content-between align-items-center mb-2">' +
            '<span class="badge bg-primary-subtle text-primary font-monospace rounded-pill px-2.5 py-1" style="font-size:0.7rem;">Langkah ' + cur + ' dari ' + total + '</span>' +
            '<button type="button" class="btn-close" style="font-size:0.75rem;" onclick="JescaOnboarding.endTour(false)"></button>' +
            '</div>' +
            '<div class="fw-bold text-dark mb-1" style="font-size:0.92rem;">' + cur + '. ' + step.title + '</div>' +
            '<p class="text-secondary small mb-2" style="font-size:0.78rem;line-height:1.45;">' + step.desc + '</p>' +
            '<div class="p-2 rounded-2 bg-light border mb-3 small text-muted d-flex align-items-center gap-2" style="font-size:0.72rem;">' +
            '<i class="bi bi-lightbulb-fill text-warning fs-6 flex-shrink-0"></i>' +
            '<span>' + step.actionHint + '</span>' +
            '</div>' +
            '<div class="d-flex justify-content-between align-items-center">' +
            '<button type="button" class="btn btn-outline-secondary btn-sm rounded-pill px-3 py-1" style="font-size:0.75rem;" onclick="JescaOnboarding.endTour(false)">Lewati</button>' +
            '<div class="d-flex gap-1.5">' +
            (this.currentTourStep > 0 ? '<button type="button" class="btn btn-light border btn-sm rounded-pill px-2.5 py-1 me-1" style="font-size:0.75rem;" onclick="JescaOnboarding.prevTourStep()"><i class="bi bi-chevron-left"></i></button>' : '') +
            '<button type="button" class="btn btn-primary btn-sm rounded-pill px-3 py-1 fw-bold" style="font-size:0.75rem;" onclick="JescaOnboarding.nextTourStep()">' +
            (isLast ? 'Selesai & Mulai <i class="bi bi-check2 ms-1"></i>' : 'Lanjut <i class="bi bi-chevron-right ms-1"></i>') +
            '</button>' +
            '</div>' +
            '</div>';

        var popW = winW < 768 ? Math.min(344, winW - 24) : 360;
        popover.style.width = popW + 'px';

        var popH = popover.offsetHeight || 225;
        var sidebarEl = document.getElementById('sidebar-wrapper');
        var sidebarRight = sidebarEl ? sidebarEl.getBoundingClientRect().right : 260;

        var top, left;

        if (winW < 768) {
            left = Math.max(12, Math.floor((winW - popW) / 2));
            var bottomNavLimit = step.requiresSheet ? (winH - 12) : (winH - 74);
            var spaceBelow = bottomNavLimit - (boxTop + boxHeight) - 10;
            var spaceAbove = boxTop - 12;

            if (spaceBelow >= popH || spaceBelow >= spaceAbove) {
                top = Math.min(winH - popH - 12, boxTop + boxHeight + 12);
            } else {
                top = Math.max(12, boxTop - popH - 12);
            }
        } else {
            // Posisi Layar PC & Laptop (Tetap Sempurna)
            var isSidebarItem = ((step.elementId && step.elementId.startsWith('tourMenu')) || (rect.left < 340 && rect.right <= sidebarRight + 40));
            var isTopNavbarItem = (rect.top < 90 && rect.right > 300);
            var isBottomFooterItem = (rect.bottom > winH - 90);

            if (isSidebarItem) {
                left = Math.max(rect.right, sidebarRight) + 24;
                top = Math.max(20, Math.min(rect.top - 15, winH - popH - 20));
            } else if (isTopNavbarItem) {
                top = rect.bottom + 14;
                left = Math.max(20, Math.min(rect.left - 120, winW - popW - 24));
            } else if (isBottomFooterItem) {
                top = Math.max(20, rect.top - popH - 14);
                left = Math.max(20, Math.min(rect.left, winW - popW - 24));
            } else {
                if (rect.right + popW + 24 < winW) {
                    left = rect.right + 24;
                    top = Math.max(20, Math.min(rect.top - 10, winH - popH - 20));
                } else if (rect.left - popW - 24 > 0) {
                    left = rect.left - popW - 24;
                    top = Math.max(20, Math.min(rect.top - 10, winH - popH - 20));
                } else {
                    top = rect.bottom + 14;
                    left = Math.max(20, Math.min(rect.left, winW - popW - 24));
                }
            }
        }

        popover.style.top = top + 'px';
        popover.style.left = left + 'px';
    },

    nextTourStep: function() {
        this.currentTourStep++;
        if (this.currentTourStep < this.activeSteps.length) {
            this.renderTourStep();
        } else {
            this.endTour(true);
        }
    },

    prevTourStep: function() {
        if (this.currentTourStep > 0) {
            this.currentTourStep--;
            this.renderTourStep();
        }
    },

    endTour: function(completed) {
        this.tourActive = false;
        var overlay = document.getElementById('jesca-spotlight-overlay');
        var box = document.getElementById('jesca-spotlight-box');
        var popover = document.getElementById('jesca-spotlight-popover');
        if (overlay) overlay.remove();
        if (box) box.remove();
        if (popover) popover.remove();

        var wrapper = document.getElementById('wrapper');
        if (wrapper && window.innerWidth < 768) {
            wrapper.classList.remove('toggled');
        }
        if (window.JescaMobileSheet && typeof window.JescaMobileSheet.close === 'function') {
            window.JescaMobileSheet.close(false);
        }

        if (completed === true) {
            localStorage.setItem(this.getCompletionKey(), 'true');
            localStorage.setItem('jesca_tour_completed', 'true');
            try { sessionStorage.removeItem('jesca_tour_session_dismissed'); } catch (e) {}
            JescaToast.show('Selamat! Anda telah menyelesaikan seluruh panduan interaktif JESCA.', 'success');
        } else {
            try { sessionStorage.setItem('jesca_tour_session_dismissed', 'true'); } catch (e) {}
            localStorage.removeItem(this.getCompletionKey());
            JescaToast.show('Panduan dilewati. Sesuai aturan, panduan akan otomatis muncul kembali di setiap sesi login hingga Anda menyelesaikannya.', 'warning');
        }
    }
};

// ==========================================
// 12. INITIALIZATION & THEME LISTENERS
// ==========================================
document.addEventListener('DOMContentLoaded', function() {
    // Theme options click binding
    document.querySelectorAll('.theme-option').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            var theme = this.getAttribute('data-theme');
            applyTheme(theme);
            localStorage.setItem('jesca_theme_manual', '1');
        });
    });

    // Language options click binding & initial apply
    if (window.JescaI18n) {
        JescaI18n.apply(JescaI18n.getCurrent());
        document.querySelectorAll('.lang-option').forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                var selectedLang = this.getAttribute('data-lang');
                JescaI18n.apply(selectedLang);
                if (window.JescaToast) {
                    var msg = (selectedLang === 'en') ? 'Language switched to English.' : 'Bahasa dialihkan ke Bahasa Indonesia.';
                    JescaToast.show(msg, 'info');
                }
            });
        });
    }

    // Init Bulk Select on assets page
    if (document.getElementById('assetsTable')) {
        BulkSelect.init();
    }

    // Init Lazy Charts
    JescaCharts.init();

    // Init Background Cache & Offline Sync if authenticated
    if (document.getElementById('sidebar-wrapper')) {
        JescaOfflineDB.cacheAssets();
        JescaOfflineDB.syncQueue();
        JescaOnboarding.init();
    }

    // Reset session tour dismissed flag on logout click
    document.querySelectorAll('a[href*="logout"]').forEach(function(el) {
        el.addEventListener('click', function() {
            try { sessionStorage.removeItem('jesca_tour_session_dismissed'); } catch (e) {}
        });
    });
});
