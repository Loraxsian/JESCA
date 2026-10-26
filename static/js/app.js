// JESCA (Jessica Assets) Main Application Script

document.addEventListener('DOMContentLoaded', () => {
    // Sidebar toggle functionality
    const wrapper = document.getElementById('wrapper');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const sidebarClose = document.getElementById('sidebar-close');

    if (sidebarToggle && wrapper) {
        sidebarToggle.addEventListener('click', (e) => {
            e.preventDefault();
            wrapper.classList.toggle('toggled');
        });
    }

    if (sidebarClose && wrapper) {
        sidebarClose.addEventListener('click', (e) => {
            e.preventDefault();
            wrapper.classList.remove('toggled');
        });
    }

    // Auto-dismiss alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
    alerts.forEach((alert) => {
        setTimeout(() => {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            if (bsAlert) {
                bsAlert.close();
            }
        }, 5000);
    });
});
