"""Run the real frontend adapter against an isolated replay backend; no keys/model calls.

uv run --with-requirements scripts/integration-requirements.txt python scripts/check_integration.py
"""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
base = f"http://127.0.0.1:{port}"
with tempfile.TemporaryDirectory(prefix="evergreen-integration-") as cache:
    env = {**os.environ, "AGENT_MODE": "replay", "DATA_LAYER_LIVE": "0", "DATA_LAYER_CACHE_DIR": cache,
           "AGENT_DEMO_DIR": str(Path(cache) / "recordings"),
           "COSTAR_KIT_DIR": str(Path(cache) / "no-kit"),
           "RUN_API_INTEGRATION": "1", "VITE_API_BASE_URL": base, "PYTHONDONTWRITEBYTECODE": "1"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.server:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"], cwd=ROOT, env=env)
    try:
        deadline = time.monotonic() + 15
        while True:
            try:
                with urlopen(f"{base}/api/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                if server.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Isolated replay backend failed to start") from None
                time.sleep(0.1)
        result = subprocess.run(["npm", "exec", "--", "vitest", "run", "src/lib/api.integration.test.ts"], cwd=ROOT / "frontend", env=env)
        sys.exit(result.returncode)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
