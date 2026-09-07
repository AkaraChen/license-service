"""Small single-instance deployment; override with WEB_CONCURRENCY/GUNICORN_CMD_ARGS."""

import os

bind = "0.0.0.0:8000"
workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
worker_class = "gthread"
threads = 2
timeout = 30
graceful_timeout = 30
worker_tmp_dir = "/tmp"
accesslog = "-"
errorlog = "-"
# Django alone handles proxy trust via LICENSE_TRUST_PROXY.
forwarded_allow_ips = ""
