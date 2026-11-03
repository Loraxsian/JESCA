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

    tourSteps: [
        {
            elementId: 'sidebar-wrapper',
            title: '1. Navigasi & Modul Inventaris',
            desc: 'Bilah menu samping ini adalah pusat kontrol utama Anda. Dari sini Anda bisa mengelola Inventaris Aset, Peminjaman Barang, Meja Servis Teknisi, Pengadaan (Purchase Order), dan Ekspor Laporan.',
            actionHint: 'Akses seluruh menu operasional melalui bilah navigasi ini.'
        },
        {
            elementId: 'navbarQrBtn',
            title: '2. Pemindai Kamera QR Code',
            desc: 'Pencet tombol kamera ini untuk membuka pemindai label fisik aset. Anda dapat memverifikasi kondisi fisik stok opname langsung di lapangan, bahkan saat perangkat offline di gudang.',
            actionHint: 'Arahkan kamera ke label stiker aset untuk verifikasi instan.'
        },
        {
            elementId: 'navbarAddAssetBtn',
            title: '3. Tambah Aset Baru',
            desc: 'Pencet tombol ini untuk mendaftarkan barang baru ke dalam sistem. Cukup isi nama, harga beli, kategori, dan sistem akan membuatkan label stiker QR Code secara otomatis.',
            actionHint: 'Klik tombol ini setiap kali ada penerimaan unit barang baru.'
        },
        {
            elementId: 'navbarNotifBell',
            title: '4. Pusat Notifikasi & Servis',
            desc: 'Ikon lonceng ini akan memberi peringatan jika ada jadwal perawatan servis aset yang mendekati jatuh tempo atau permohonan pengadaan barang (PO) yang menunggu persetujuan.',
            actionHint: 'Periksa lonceng ini untuk memantau tugas yang perlu ditindaklanjuti.'
        },
        {
            elementId: 'footerCommandBadge',
            title: '5. Pintasan Cepat (Command Palette)',
            desc: 'Tekan tombol Ctrl + K pada keyboard Anda kapan saja. Jendela pencarian pintar akan terbuka untuk mencari aset, membuka menu, atau berpindah halaman secara instan tanpa perlu klik mouse.',
            actionHint: 'Gunakan Ctrl + K untuk navigasi super cepat.'
        }
    ],

    init: function() {
        if (!document.getElementById('sidebar-wrapper')) {
            return;
        }
        var seen = localStorage.getItem('jesca_onboarding_seen');
        if (!seen) {
            setTimeout(function() {
                JescaOnboarding.startSpotlightTour();
            }, 800);
        }

        var carouselEl = document.getElementById('onboardingCarousel');
        if (carouselEl) {
            carouselEl.addEventListener('slid.bs.carousel', function(e) {
                var nextBtn = document.getElementById('btn-onboarding-next');
                if (!nextBtn) return;
                if (e.to === 3) {
                    nextBtn.innerHTML = 'Mulai Gunakan JESCA <i class="bi bi-check2 ms-1"></i>';
                    nextBtn.onclick = function() {
                        JescaOnboarding.complete();
                    };
                } else {
                    nextBtn.innerHTML = 'Selanjutnya <i class="bi bi-chevron-right ms-1"></i>';
                    nextBtn.onclick = null;
                }
            });
        }
    },

    showMenu: function() {
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
            nextBtn.innerHTML = 'Selanjutnya <i class="bi bi-chevron-right ms-1"></i>';
            nextBtn.onclick = null;
        }
        var bsModal = bootstrap.Modal.getOrCreateInstance(modalEl);
        bsModal.show();
    },

    complete: function() {
        localStorage.setItem('jesca_onboarding_seen', 'true');
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

    startSpotlightTour: function() {
        this.complete();
        this.tourActive = true;
        this.currentTourStep = 0;
        this.renderTourStep();
    },

    renderTourStep: function() {
        if (!this.tourActive) return;
        var step = this.tourSteps[this.currentTourStep];
        if (!step) {
            this.endTour();
            return;
        }

        var target = document.getElementById(step.elementId);
        if (!target) {
            this.currentTourStep++;
            if (this.currentTourStep < this.tourSteps.length) {
                this.renderTourStep();
            } else {
                this.endTour();
            }
            return;
        }

        try {
            target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        } catch (e) {}

        setTimeout(function() {
            var rect = target.getBoundingClientRect();
            JescaOnboarding.renderSpotlightUI(rect, step);
        }, 250);
    },

    renderSpotlightUI: function(rect, step) {
        var overlay = document.getElementById('jesca-spotlight-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'jesca-spotlight-overlay';
            document.body.appendChild(overlay);
        }

        var box = document.getElementById('jesca-spotlight-box');
        if (!box) {
            box = document.createElement('div');
            box.id = 'jesca-spotlight-box';
            document.body.appendChild(box);
        }

        var pad = 6;
        box.style.top = Math.max(0, rect.top - pad) + 'px';
        box.style.left = Math.max(0, rect.left - pad) + 'px';
        box.style.width = (rect.width + (pad * 2)) + 'px';
        box.style.height = (rect.height + (pad * 2)) + 'px';

        var popover = document.getElementById('jesca-spotlight-popover');
        if (!popover) {
            popover = document.createElement('div');
            popover.id = 'jesca-spotlight-popover';
            document.body.appendChild(popover);
        }

        var total = this.tourSteps.length;
        var cur = this.currentTourStep + 1;
        var isLast = (cur === total);

        popover.innerHTML = '<div class="d-flex justify-content-between align-items-center mb-2">' +
            '<span class="badge bg-primary-subtle text-primary font-monospace rounded-pill px-2.5 py-1" style="font-size:0.7rem;">Langkah ' + cur + ' dari ' + total + '</span>' +
            '<button type="button" class="btn-close" style="font-size:0.75rem;" onclick="JescaOnboarding.endTour()"></button>' +
            '</div>' +
            '<div class="fw-bold text-dark mb-1" style="font-size:0.92rem;">' + step.title + '</div>' +
            '<p class="text-secondary small mb-2" style="font-size:0.78rem;line-height:1.45;">' + step.desc + '</p>' +
            '<div class="p-2 rounded-2 bg-light border mb-3 small text-muted d-flex align-items-center gap-2" style="font-size:0.72rem;">' +
            '<i class="bi bi-hand-index-thumb text-primary fs-6 flex-shrink-0"></i>' +
            '<span>' + step.actionHint + '</span>' +
            '</div>' +
            '<div class="d-flex justify-content-between align-items-center">' +
            '<button type="button" class="btn btn-outline-secondary btn-sm rounded-pill px-3 py-1" style="font-size:0.75rem;" onclick="JescaOnboarding.endTour()">Lewati</button>' +
            '<div class="d-flex gap-1.5">' +
            (this.currentTourStep > 0 ? '<button type="button" class="btn btn-light border btn-sm rounded-pill px-2.5 py-1 me-1" style="font-size:0.75rem;" onclick="JescaOnboarding.prevTourStep()"><i class="bi bi-chevron-left"></i></button>' : '') +
            '<button type="button" class="btn btn-primary btn-sm rounded-pill px-3 py-1 fw-bold" style="font-size:0.75rem;" onclick="JescaOnboarding.nextTourStep()">' +
            (isLast ? 'Selesai & Mulai <i class="bi bi-check2 ms-1"></i>' : 'Lanjut <i class="bi bi-chevron-right ms-1"></i>') +
            '</button>' +
            '</div>' +
            '</div>';

        var popW = 340;
        var popH = 240;
        var winW = window.innerWidth;
        var winH = window.innerHeight;

        var top = rect.bottom + 14;
        var left = rect.left;

        if (top + popH > winH - 20) {
            top = Math.max(20, rect.top - popH - 14);
        }
        if (left + popW > winW - 20) {
            left = Math.max(20, winW - popW - 20);
        }
        if (left < 20) left = 20;

        popover.style.top = top + 'px';
        popover.style.left = left + 'px';
    },

    nextTourStep: function() {
        this.currentTourStep++;
        if (this.currentTourStep < this.tourSteps.length) {
            this.renderTourStep();
        } else {
            this.endTour();
            JescaToast.show('Tur panduan selesai. Anda siap menggunakan JESCA!', 'success');
        }
    },

    prevTourStep: function() {
        if (this.currentTourStep > 0) {
            this.currentTourStep--;
            this.renderTourStep();
        }
    },

    endTour: function() {
        this.tourActive = false;
        var overlay = document.getElementById('jesca-spotlight-overlay');
        var box = document.getElementById('jesca-spotlight-box');
        var popover = document.getElementById('jesca-spotlight-popover');
        if (overlay) overlay.remove();
        if (box) box.remove();
        if (popover) popover.remove();
        localStorage.setItem('jesca_onboarding_seen', 'true');
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
});
