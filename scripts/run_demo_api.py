from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
DEPS = os.path.join(ROOT, ".codex_deps")
for path in (SRC, DEPS):
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AML sidecar API in demo mode.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()

    os.environ.setdefault("DEMO_MODE", "true")
    os.environ.setdefault("SIDECAR_DB_PATH", os.path.join(ROOT, "data", "sidecar.sqlite3"))
    uvicorn.run("compliance_agent.api:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
