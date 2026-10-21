"""Build behind the existing cloud proxy, preserving TLS verification.

No proxy values or credentials are printed or persisted in image layers.
Run from the repository root; normal environments can use docker build directly.
"""

import os
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

args = [
    "docker",
    "build",
    "--network=host",
    "--build-arg",
    "HTTP_PROXY",
    "--build-arg",
    "HTTPS_PROXY",
    "--build-arg",
    "NO_PROXY",
]
ca = Path(os.environ.get("SSL_CERT_FILE", "/etc/ssl/certs/ca-certificates.crt"))
if ca.is_file():
    args += ["--secret", f"id=build_ca_bundle,src={ca}"]
for host in {
    urlsplit(os.environ.get(name, "")).hostname for name in ("HTTP_PROXY", "HTTPS_PROXY")
} - {None}:
    args += ["--add-host", f"{host}:{socket.gethostbyname(host)}"]
args += ["-t", "tg-api-buyer:local", "."]
process_env = dict(os.environ)
process_env.setdefault("DOCKER_CONFIG", "/tmp/tg-api-buyer-docker")
raise SystemExit(subprocess.run(args, env=process_env).returncode)
