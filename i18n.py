"""
JESCA Server-Side Internationalization (i18n) Module.
Menyediakan kamus terjemahan ID <-> EN dan helper Flask/Jinja2 berbasis Python.
"""

from flask import request, session

SUPPORTED_LANGUAGES = ("id", "en")
DEFAULT_LANGUAGE = "id"

# Kamus Istilah Baku Bahasa Indonesia (Standar Operasional JESCA)
STANDARD_TERMS_ID = {
    "Dashboard": "Beranda",
    "Purchase Order": "Pengadaan Barang (PO)",
    "System Update": "Pembaruan Sistem",
    "Sudo Mode": "Mode Akses Khusus (Sudo)",
    "Runtime & Server": "Lingkungan Server & Waktu Proses",
    "WAL (Write-Ahead Log)": "Mode Jurnal WAL",
    "Active": "Aktif",
}

TRANSLATIONS_EN = {
    # Purchase Order Form
    "Form Permohonan Pengadaan Barang Baru": "New Purchase Order Request Form",
    "Isi data permohonan belanja, rincian barang, dan vendor penyedia.": "Fill in procurement details, item list, and vendor information.",
    "Judul Pengadaan / Keperluan": "Procurement Title / Purpose",
    "Mitra Vendor / Supplier": "Vendor / Supplier Partner",
    "-- Pilih Vendor (Opsional) --": "-- Select Vendor (Optional) --",
    "Catatan / Justifikasi Pengadaan (Opsional)": "Procurement Notes / Justification (Optional)",
    "Jelaskan latar belakang atau peruntukan barang yang diajukan...": "Describe the background or purpose of the requested items...",
    "Rincian Barang yang Diajukan": "Requested Items Breakdown",
    "Masukkan daftar item barang yang ingin dibeli beserta estimasi harga satuannya.": "Enter the list of items to purchase along with estimated unit prices.",
    "Tambah Baris": "Add Row",
    "Nama & Spesifikasi Barang": "Item Name & Specifications",
    "Jumlah (Qty)": "Quantity (Qty)",
    "Harga Satuan (IDR)": "Unit Price (IDR)",
    "TOTAL ESTIMASI BIAYA:": "TOTAL ESTIMATED COST:",
    "Simpan Draft": "Save Draft",
    "Simpan & Langsung Ajukan": "Save & Submit Now",
    "Batal": "Cancel",
    "Kembali": "Back",
    # Common UI
    "Beranda": "Dashboard",
    "Ekspor Data": "Export Data",
    "Impor CSV": "Import CSV",
    "Ekspor PDF": "Export PDF",
    "Ekspor Excel": "Export Excel",
    "Ekspor CSV": "Export CSV",
    "Cadangan DB": "DB Backups",
    "Palet Perintah": "Command Palette",
    "Cetak": "Print",
}


def get_current_lang() -> str:
    """Ambil bahasa aktif dari session atau cookie (default: 'id')."""
    lang = session.get("jesca_lang") or request.cookies.get("jesca_lang") or DEFAULT_LANGUAGE
    lang = str(lang).lower().strip()
    return lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def translate(text: str, lang: str | None = None) -> str:
    """Terjemahkan teks ke bahasa target berdasarkan kamus Python."""
    active_lang = lang or get_current_lang()
    if active_lang == "en":
        return TRANSLATIONS_EN.get(text, text)
    return text
