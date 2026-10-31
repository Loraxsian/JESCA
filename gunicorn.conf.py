import multiprocessing
import os

# Gunicorn Configuration for JESCA v2
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:5000")
pidfile = "/tmp/gunicorn.pid"

# Formula: (2 x CPU) + 1
workers = int(os.environ.get("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
threads = int(os.environ.get("GUNICORN_THREADS", 2))

timeout = 120
keepalive = 5
max_requests = 1000
max_requests_jitter = 50

accesslog = "-"
errorlog = "-"
loglevel = "info"
