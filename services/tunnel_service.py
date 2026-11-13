import re
import shutil
import time
import threading
import subprocess
from datetime import datetime
from config import ENABLE_QUICK_TUNNEL, QUICK_TUNNEL_MAX_MINUTES


_QUICK_TUNNEL_LOCK = threading.Lock()
_QUICK_TUNNEL_PROC = None
_QUICK_TUNNEL_TIMER = None
_QUICK_TUNNEL_INFO = {
    'active': False,
    'public_url': None,
    'expires_in': None,
    'started_at': None,
    'enabled': ENABLE_QUICK_TUNNEL
}


def start_quick_tunnel(port=5000):
    global _QUICK_TUNNEL_PROC, _QUICK_TUNNEL_TIMER, _QUICK_TUNNEL_INFO
    if not ENABLE_QUICK_TUNNEL:
        return {
            'active': False,
            'enabled': False,
            'error': 'Fitur tunnel instan dinonaktifkan oleh konfigurasi server (ENABLE_QUICK_TUNNEL=false).'
        }
    with _QUICK_TUNNEL_LOCK:
        if _QUICK_TUNNEL_PROC and _QUICK_TUNNEL_PROC.poll() is None:
            return _QUICK_TUNNEL_INFO

        try:
            ssh_bin = shutil.which('ssh')
            if not ssh_bin:
                return {
                    'active': False,
                    'error': 'Fitur tunnel otomatis memerlukan paket openssh-client di sistem.'
                }

            cmd = [
                ssh_bin,
                '-p', '443',
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'ServerAliveInterval=30',
                f'-R0:localhost:{port}',
                'a.pinggy.io'
            ]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            found_url = None
            expires = '60 Menit (Sesi Uji Coba Gratis)'
            start_time = time.time()

            while time.time() - start_time < 8:
                line = proc.stdout.readline()
                if not line:
                    break
                if 'expire' in line.lower():
                    expires = '60 Menit (Sesi Gratis)'
                matches = re.findall(r'https://[a-zA-Z0-9\.\-]+(?:pinggy\.link|pinggy\.net)', line)
                if matches:
                    found_url = matches[0]
                    break

            if found_url:
                _QUICK_TUNNEL_PROC = proc
                if _QUICK_TUNNEL_TIMER:
                    _QUICK_TUNNEL_TIMER.cancel()
                _QUICK_TUNNEL_TIMER = threading.Timer(QUICK_TUNNEL_MAX_MINUTES * 60, stop_quick_tunnel)
                _QUICK_TUNNEL_TIMER.daemon = True
                _QUICK_TUNNEL_TIMER.start()
                _QUICK_TUNNEL_INFO = {
                    'active': True,
                    'public_url': found_url,
                    'expires_in': f'{QUICK_TUNNEL_MAX_MINUTES} Menit (Auto-Expire)',
                    'started_at': datetime.utcnow().strftime('%H:%M:%S'),
                    'enabled': ENABLE_QUICK_TUNNEL
                }
                return _QUICK_TUNNEL_INFO
            else:
                proc.terminate()
                return {
                    'active': False,
                    'error': 'Gagal mendapatkan tautan dari server tunnel dalam 8 detik. Silakan coba lagi.'
                }
        except Exception as e:
            return {
                'active': False,
                'error': f'Gagal menjalankan tunnel otomatis: {str(e)}'
            }


def stop_quick_tunnel():
    global _QUICK_TUNNEL_PROC, _QUICK_TUNNEL_TIMER, _QUICK_TUNNEL_INFO
    with _QUICK_TUNNEL_LOCK:
        if _QUICK_TUNNEL_TIMER:
            _QUICK_TUNNEL_TIMER.cancel()
            _QUICK_TUNNEL_TIMER = None
        if _QUICK_TUNNEL_PROC:
            try:
                _QUICK_TUNNEL_PROC.terminate()
                _QUICK_TUNNEL_PROC.wait(timeout=2)
            except Exception:
                try:
                    _QUICK_TUNNEL_PROC.kill()
                except Exception:
                    pass
            _QUICK_TUNNEL_PROC = None

        _QUICK_TUNNEL_INFO = {
            'active': False,
            'public_url': None,
            'expires_in': None,
            'started_at': None,
            'enabled': ENABLE_QUICK_TUNNEL
        }
        return _QUICK_TUNNEL_INFO



def get_quick_tunnel_status():
    """Return current tunnel state, resetting it if the process has exited."""
    global _QUICK_TUNNEL_PROC, _QUICK_TUNNEL_INFO
    with _QUICK_TUNNEL_LOCK:
        if _QUICK_TUNNEL_PROC and _QUICK_TUNNEL_PROC.poll() is not None:
            _QUICK_TUNNEL_PROC = None
            _QUICK_TUNNEL_INFO = {
                'active': False,
                'public_url': None,
                'expires_in': None,
                'started_at': None,
                'enabled': ENABLE_QUICK_TUNNEL
            }
        info = dict(_QUICK_TUNNEL_INFO)
        info['enabled'] = ENABLE_QUICK_TUNNEL
        return info
