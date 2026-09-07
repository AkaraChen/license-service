"""Probe HTTP using only the standard library; no Django startup or curl needed."""

import http.client
import json
import os
import sys

host = os.environ.get("LICENSE_ALLOWED_HOSTS", "localhost").split(",")[0].strip().lstrip(".")
if host == "*":
    host = "localhost"
connection = http.client.HTTPConnection("127.0.0.1", 8000, timeout=4)
try:
    connection.request("GET", "/healthz", headers={"Host": host})
    response = connection.getresponse()
    healthy = response.status == 200 and json.loads(response.read()) == {"status": "ok"}
except (OSError, http.client.HTTPException, ValueError):
    healthy = False
finally:
    connection.close()
sys.exit(0 if healthy else 1)
