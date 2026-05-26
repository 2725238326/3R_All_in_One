#!/usr/bin/env python3
"""
PyInstaller entry point for the 3R All-in-One backend.

This script starts the FastAPI backend using uvicorn. It is designed to be
frozen with PyInstaller --onefile mode.
"""
from __future__ import annotations

import os
import sys


def main() -> None:
    # Ensure backend package is importable when running from frozen exe
    if getattr(sys, "frozen", False):
        # Running as PyInstaller bundle
        bundle_dir = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        # Running as normal script - go up one level from tools/
        bundle_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    backend_dir = os.path.join(bundle_dir, "backend")
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    if bundle_dir not in sys.path:
        sys.path.insert(0, bundle_dir)

    # Import uvicorn after path setup
    import uvicorn

    # Default host and port, can be overridden by env vars
    host = os.environ.get("BACKEND_HOST", "127.0.0.1")
    port = int(os.environ.get("BACKEND_PORT", "8765"))

    # Run the FastAPI app
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
