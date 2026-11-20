document.addEventListener('DOMContentLoaded', function () {
    // 1. Toggle Show / Hide Password
    const toggleBtn = document.getElementById('togglePasswordBtn');
    const passInput = document.getElementById('password');
    const eyeIcon = document.getElementById('togglePasswordIcon');

    if (toggleBtn && passInput && eyeIcon) {
        toggleBtn.addEventListener('click', function () {
            const isPass = passInput.getAttribute('type') === 'password';
            passInput.setAttribute('type', isPass ? 'text' : 'password');
            eyeIcon.className = isPass ? 'bi bi-eye-slash text-primary' : 'bi bi-eye';
        });
    }

    // 2. Connector Arrow Click to Focus Username
    const connectorBtn = document.getElementById('connectorFocusBtn');
    const usernameInput = document.getElementById('username');
    if (connectorBtn && usernameInput) {
        connectorBtn.addEventListener('click', function () {
            usernameInput.focus();
            usernameInput.classList.add('border-primary');
            setTimeout(() => usernameInput.classList.remove('border-primary'), 1000);
        });
    }

    // 3. Tombol Login Loading Animation (Desktop & Mobile)
    const loginForm = document.getElementById('loginForm');
    const btnSubmit = document.getElementById('btnLoginSubmit');
    if (loginForm && btnSubmit) {
        loginForm.addEventListener('submit', function () {
            btnSubmit.disabled = true;
            btnSubmit.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Memverifikasi...';
        });
    }

    const mobileLoginForm = document.getElementById('mobileLoginForm');
    const mobileBtnSubmit = document.getElementById('mobileBtnLoginSubmit');
    if (mobileLoginForm && mobileBtnSubmit) {
        mobileLoginForm.addEventListener('submit', function () {
            mobileBtnSubmit.disabled = true;
            mobileBtnSubmit.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Memproses...';
        });
    }

    // Sinkronisasi status tombol bahasa di Mobile Login
    const savedLang = localStorage.getItem('jesca_lang') || 'id';
    setMobileLoginLang(savedLang, true);

    // 4. Kolom 1: Auto-fill Login sebagai Admin
    const btnFillAdmin = document.getElementById('btnFillAdmin');
    if (btnFillAdmin) {
        btnFillAdmin.addEventListener('click', function () {
            const u = this.getAttribute('data-user') || 'Admin';
            const p = this.getAttribute('data-pass') || 'Admin123';

            if (usernameInput) usernameInput.value = u;
            if (passInput) passInput.value = p;

            // Animasi Pulsing Ripple pada input fields
            [usernameInput, passInput].forEach(el => {
                if (!el) return;
                el.style.transition = 'all 0.3s ease';
                el.style.borderColor = '#553af6';
                el.style.boxShadow = '0 0 0 5px rgba(85, 58, 246, 0.25)';
                el.style.background = '#f5f3ff';

                setTimeout(() => {
                    el.style.borderColor = '';
                    el.style.boxShadow = '';
                    el.style.background = '';
                }, 900);
            });

            // Animasi Klik Tombol Auto-fill
            this.style.transform = 'scale(0.92)';
            setTimeout(() => {
                this.style.transform = '';
            }, 200);

            // Toast feedback
            if (window.JescaToast) {
                window.JescaToast.show('Kredensial Admin (' + u + ') berhasil diisi!', 'success');
            }
        });
    }
});

// 5. Fungsi Kirim Feedback Modal
function submitFeedback() {
    const btnSubmit = document.getElementById('btnSubmitFeedback');
    const alertBox = document.getElementById('feedbackSuccessAlert');
    const form = document.getElementById('feedbackForm');
    const messageInput = document.getElementById('feedbackMessage');

    if (!messageInput || !messageInput.value.trim()) return;

    const name = document.getElementById('feedbackName') ? document.getElementById('feedbackName').value.trim() : '';
    const contact = document.getElementById('feedbackContact') ? document.getElementById('feedbackContact').value.trim() : '';
    const category = document.getElementById('feedbackCategory') ? document.getElementById('feedbackCategory').value.trim() : 'Saran Fitur Baru';
    const message = messageInput.value.trim();

    const formData = new FormData();
    formData.append('name', name);
    formData.append('contact', contact);
    formData.append('category', category);
    formData.append('message', message);

    btnSubmit.disabled = true;
    btnSubmit.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Mengirim...';

    fetch('/submit-feedback', {
        method: 'POST',
        body: formData
    })
    .then(function(resp) { return resp.json(); })
    .then(function(data) {
        btnSubmit.disabled = false;
        if (data.status === 'ok') {
            btnSubmit.innerHTML = '<i class="bi bi-check-lg me-1"></i>Terkirim';
            alertBox.classList.remove('d-none');
            alertBox.classList.add('d-flex');
            form.reset();
            setTimeout(function () {
                const modalEl = document.getElementById('feedbackModal');
                const modalInstance = bootstrap.Modal.getInstance(modalEl);
                if (modalInstance) modalInstance.hide();
                alertBox.classList.add('d-none');
                alertBox.classList.remove('d-flex');
                btnSubmit.innerHTML = '<i class="bi bi-send me-1"></i>Kirim Masukan';
                if (window.JescaToast) {
                    window.JescaToast.show('Laporan / saran Anda telah berhasil terkirim. Terima kasih!', 'success');
                }
            }, 1800);
        } else {
            btnSubmit.innerHTML = '<i class="bi bi-send me-1"></i>Kirim Masukan';
            if (window.JescaToast) {
                window.JescaToast.show(data.message || 'Gagal mengirim laporan. Coba lagi.', 'danger');
            }
        }
    })
    .catch(function() {
        btnSubmit.disabled = false;
        btnSubmit.innerHTML = '<i class="bi bi-send me-1"></i>Kirim Masukan';
        if (window.JescaToast) {
            window.JescaToast.show('Koneksi gagal. Pastikan server dapat dijangkau.', 'danger');
        }
    });
}

// Reset session tour dismissal state on login page
try {
    sessionStorage.removeItem('jesca_tour_session_dismissed');
} catch (e) {}

// Helper Fungsi Mobile Modern Login
function clearMobileUsername() {
    const el = document.getElementById('mobileUsername');
    if (el) {
        el.value = '';
        el.focus();
    }
}

function toggleMobilePassword() {
    const input = document.getElementById('mobilePassword');
    const icon = document.getElementById('m-icon-eye');
    if (!input || !icon) return;
    if (input.type === 'password') {
        input.type = 'text';
        icon.className = 'bi bi-eye-slash text-primary';
    } else {
        input.type = 'password';
        icon.className = 'bi bi-eye';
    }
}

function fillMobileAdmin() {
    const uInput = document.getElementById('mobileUsername');
    const pInput = document.getElementById('mobilePassword');
    if (uInput) uInput.value = 'Admin';
    if (pInput) pInput.value = 'Admin123';

    [uInput, pInput].forEach(function(el) {
        if (!el) return;
        el.style.borderColor = '#4361ee';
        el.style.boxShadow = '0 0 0 4px rgba(67, 97, 238, 0.2)';
        setTimeout(function() {
            el.style.borderColor = '';
            el.style.boxShadow = '';
        }, 800);
    });

    if (window.JescaToast) {
        window.JescaToast.show('Kredensial Admin berhasil diisi!', 'success');
    }
}

function setMobileLoginLang(lang, silent) {
    const btnId = document.getElementById('m-lang-id');
    const btnEn = document.getElementById('m-lang-en');
    if (btnId) btnId.classList.toggle('active', lang === 'id');
    if (btnEn) btnEn.classList.toggle('active', lang === 'en');

    const titleEl = document.getElementById('m-txt-title');
    const userLbl = document.getElementById('m-txt-label-user');
    const userInp = document.getElementById('mobileUsername');
    const passInp = document.getElementById('mobilePassword');
    const btnTxt = document.getElementById('m-txt-btn-login');

    if (lang === 'en') {
        if (titleEl) titleEl.textContent = 'Welcome Back';
        if (userLbl) userLbl.textContent = 'Username';
        if (userInp) userInp.placeholder = 'Enter your username';
        if (passInp) passInp.placeholder = 'Enter your password';
        if (btnTxt) btnTxt.textContent = 'Sign In';
    } else {
        if (titleEl) titleEl.textContent = 'Silahkan Masuk';
        if (userLbl) userLbl.textContent = 'Username';
        if (userInp) userInp.placeholder = 'Masukkan username';
        if (passInp) passInp.placeholder = 'Masukkan password';
        if (btnTxt) btnTxt.textContent = 'Login';
    }

    if (window.JescaI18n) {
        window.JescaI18n.apply(lang);
    }
    if (!silent && window.JescaToast) {
        window.JescaToast.show(lang === 'en' ? 'Language switched to English' : 'Bahasa Indonesia aktif', 'info');
    }
}
