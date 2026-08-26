"""Configure Gunicorn for the production container."""

import multiprocessing
import os


bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")
workers = int(
    os.getenv("GUNICORN_WORKERS", str(min((multiprocessing.cpu_count() * 2) + 1, 4)))
)
threads = int(os.getenv("GUNICORN_THREADS", "1"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))
control_socket_disable = True

accesslog = "-"
errorlog = "-"
capture_output = True
