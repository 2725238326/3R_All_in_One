#!/usr/bin/env python3
"""Local release gate for 3R All-in-One.

The script verifies version alignment, Agent blueprints, backend tests,
frontend build output, and Docker Compose syntax when Docker is available.
It is intentionally dependency-light so it can run before packaging.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class GateResult:
    name: str
    status: str
    detail: str


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _run(name: str, command: list[str], *, cwd: Path | None = None) -> GateResult:
    printable = " ".join(command)
    print(f"\n[RUN] {name}: {printable}", flush=True)
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    resolved = command[:]
    executable = shutil.which(resolved[0])
    if executable:
        resolved[0] = executable
    try:
        proc = subprocess.run(resolved, cwd=cwd or ROOT, env=env)
    except FileNotFoundError:
        return GateResult(name, "FAIL", f"command not found: {command[0]}")
    if proc.returncode == 0:
        return GateResult(name, "PASS", printable)
    return GateResult(name, "FAIL", f"{printable} exited {proc.returncode}")


def _extract_regex(path: str, pattern: str) -> str:
    match = re.search(pattern, _read(path), re.MULTILINE)
    if not match:
        raise ValueError(f"Could not extract version from {path}")
    return match.group(1)


def check_versions() -> GateResult:
    pyproject = tomllib.loads(_read("pyproject.toml"))
    client_package = json.loads(_read("client/package.json"))
    tauri_conf = json.loads(_read("client/src-tauri/tauri.conf.json"))

    versions = {
        "pyproject": pyproject["project"]["version"],
        "agent": _extract_regex("agent/__init__.py", r'__version__\s*=\s*"([^"]+)"'),
        "backend": _extract_regex("backend/app.py", r'version="([^"]+)"'),
        "client/package.json": client_package["version"],
        "client/src-tauri/Cargo.toml": _extract_regex(
            "client/src-tauri/Cargo.toml",
            r'(?m)^version\s*=\s*"([^"]+)"',
        ),
        "client/src-tauri/tauri.conf.json": tauri_conf["version"],
    }
    unique = sorted(set(versions.values()))
    if len(unique) == 1:
        return GateResult("version alignment", "PASS", f"all artifacts use {unique[0]}")
    detail = ", ".join(f"{key}={value}" for key, value in versions.items())
    return GateResult("version alignment", "FAIL", detail)


def check_packaged_resources() -> GateResult:
    spec = _read("tools/3r_backend.spec")
    required = [
        'PROJECT_ROOT / "agent"',
        'PROJECT_ROOT / "runners"',
        'PROJECT_ROOT / "client" / "dist"',
    ]
    missing = [item for item in required if item not in spec]
    if missing:
        return GateResult("packaged resources", "FAIL", "missing: " + ", ".join(missing))
    return GateResult("packaged resources", "PASS", "agent, runners, and client dist included")


def check_docker_static() -> GateResult:
    dockerfile = _read("Dockerfile")
    compose = _read("docker-compose.yml")
    required_dockerfile = [
        "FROM python:3.11-slim",
        "COPY agent/ /app/agent/",
        "COPY runners/ /app/runners/",
        "COPY samples/ /app/samples/",
        "COPY --from=frontend-builder /app/dist /app/client/dist",
        "ENV PYTHONPATH=/app/backend:/app",
        "ENV KYKT_DATA_ROOT=/app/data",
        "http://localhost:8000/api/health",
    ]
    required_compose = [
        "context: .",
        "dockerfile: Dockerfile",
        '"8000:8000"',
        "KYKT_DATA_ROOT=/app/data",
        "http://localhost:8000/api/health",
    ]
    missing = [
        f"Dockerfile:{item}"
        for item in required_dockerfile
        if item not in dockerfile
    ]
    missing.extend(
        f"docker-compose.yml:{item}"
        for item in required_compose
        if item not in compose
    )
    if missing:
        return GateResult("docker static config", "FAIL", "missing: " + ", ".join(missing))
    return GateResult(
        "docker static config",
        "PASS",
        "Python 3.11 image, runtime resources, KYKT_DATA_ROOT, and /api/health configured",
    )


def check_docker(require_docker: bool) -> GateResult:
    if not shutil.which("docker"):
        status = "FAIL" if require_docker else "WARN"
        return GateResult("docker compose config", status, "docker CLI not found")
    return _run("docker compose config", ["docker", "compose", "config"])


def check_release_artifacts() -> GateResult:
    version = tomllib.loads(_read("pyproject.toml"))["project"]["version"]
    artifacts = [
        ROOT / "dist" / "3r-backend.exe",
        ROOT / "client" / "src-tauri" / "binaries" / "3r-backend-x86_64-pc-windows-msvc.exe",
        ROOT
        / "client"
        / "src-tauri"
        / "target"
        / "release"
        / "bundle"
        / "nsis"
        / f"3R All-in-One_{version}_x64-setup.exe",
    ]
    missing = [str(path.relative_to(ROOT)) for path in artifacts if not path.exists()]
    too_small = [
        str(path.relative_to(ROOT))
        for path in artifacts
        if path.exists() and path.stat().st_size < 1_000_000
    ]
    if missing or too_small:
        details = []
        if missing:
            details.append("missing: " + ", ".join(missing))
        if too_small:
            details.append("too small: " + ", ".join(too_small))
        return GateResult("release artifacts", "FAIL", "; ".join(details))
    sizes = ", ".join(f"{path.name}={path.stat().st_size // 1_000_000}MB" for path in artifacts)
    return GateResult("release artifacts", "PASS", sizes)


def report(results: list[GateResult]) -> int:
    print("\n=== Release Gate Summary ===")
    for result in results:
        print(f"[{result.status}] {result.name}: {result.detail}")
    return 1 if any(result.status == "FAIL" for result in results) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local release verification gates.")
    parser.add_argument("--skip-tests", action="store_true", help="Skip pytest.")
    parser.add_argument("--skip-frontend", action="store_true", help="Skip npm run build.")
    parser.add_argument(
        "--require-docker",
        action="store_true",
        help="Fail when Docker is unavailable or docker compose config fails.",
    )
    parser.add_argument(
        "--require-artifacts",
        action="store_true",
        help="Require built backend sidecar and Tauri NSIS installer artifacts.",
    )
    args = parser.parse_args(argv)

    results = [
        check_versions(),
        check_packaged_resources(),
        check_docker_static(),
        _run("agent blueprint validation", [sys.executable, "-m", "agent", "validate"]),
    ]
    if not args.skip_tests:
        results.append(_run("python tests", [sys.executable, "-m", "pytest", "-q"]))
    if not args.skip_frontend:
        results.append(_run("frontend build", ["npm", "run", "build"], cwd=ROOT / "client"))
    if args.require_artifacts:
        results.append(check_release_artifacts())
    results.append(check_docker(args.require_docker))

    return report(results)


if __name__ == "__main__":
    raise SystemExit(main())
