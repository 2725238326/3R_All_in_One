# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for 3R All-in-One Backend.

Usage:
    pyinstaller tools/3r_backend.spec

Output:
    dist/3r-backend.exe (single file)
"""
import os
from pathlib import Path

# Project root (one level up from tools/)
PROJECT_ROOT = Path(SPECPATH).parent
BACKEND_DIR = PROJECT_ROOT / "backend"

block_cipher = None

# Collect all backend Python modules
backend_modules = []
for py_file in BACKEND_DIR.glob("*.py"):
    if py_file.name != "__pycache__":
        backend_modules.append((str(py_file), "backend"))

# Collect backend templates and static files (if they exist)
datas = []
templates_dir = BACKEND_DIR / "templates"
static_dir = BACKEND_DIR / "static"
if templates_dir.exists():
    datas.append((str(templates_dir), "backend/templates"))
if static_dir.exists():
    datas.append((str(static_dir), "backend/static"))

# Add samples manifest if exists
samples_manifest = PROJECT_ROOT / "samples" / "samples_manifest.json"
if samples_manifest.exists():
    datas.append((str(samples_manifest), "samples"))

# Add Agent blueprints and source modules used by /api/agent/*
agent_dir = PROJECT_ROOT / "agent"
if agent_dir.exists():
    datas.append((str(agent_dir), "agent"))

# Add tools scripts if needed for deployment checks
tools_dir = PROJECT_ROOT / "tools"
deployment_script = tools_dir / "check_3r_remote.ps1"
if deployment_script.exists():
    datas.append((str(deployment_script), "tools"))

# Add remote runner scripts shipped from the bundle root
runners_dir = PROJECT_ROOT / "runners"
if runners_dir.exists():
    datas.append((str(runners_dir), "runners"))

# Add backend runner modules used by /api/runners/availability
backend_runners_dir = BACKEND_DIR / "runners"
if backend_runners_dir.exists():
    datas.append((str(backend_runners_dir), "backend/runners"))

# Add built React client when present so the backend can serve it in frozen mode
client_dist_dir = PROJECT_ROOT / "client" / "dist"
if client_dist_dir.exists():
    datas.append((str(client_dist_dir), "client/dist"))

# Hidden imports that PyInstaller might miss
hiddenimports = [
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi",
    "fastapi.middleware",
    "fastapi.middleware.cors",
    "fastapi.responses",
    "fastapi.staticfiles",
    "fastapi.templating",
    "starlette",
    "starlette.routing",
    "starlette.responses",
    "starlette.staticfiles",
    "starlette.templating",
    "starlette.middleware",
    "starlette.middleware.cors",
    "starlette.middleware.base",
    "starlette.websockets",
    "pydantic",
    "pydantic_core",
    "jinja2",
    "multipart",
    "python_multipart",
    "anyio",
    "anyio._backends",
    "anyio._backends._asyncio",
    "httptools",
    "websockets",
    "yaml",
    "paramiko",
    "PIL",
    "PIL.Image",
    "numpy",
    "pandas",
    "matplotlib",
    "aiofiles",
    # Backend modules
    "advisor",
    "development_store",
    "job_store",
    "job_scheduler",
    "logging_config",
    "metrics_calculator",
    "model_contracts",
    "model_registry",
    "param_templates",
    "report_exporter",
    "resource_monitor",
    "retry_policy",
    "runtime_paths",
    "server_profiles",
    "ssh_runner",
    "state_reconciler",
    "visual_artifacts",
    "loguru",
    "agent",
    "agent.cli",
    "agent.env_builder",
    "agent.experiment_agent",
    "agent.health_doctor",
    "agent.registry",
    "agent.schema_validator",
    "agent.smoke_runner",
    "runners",
    "runners.online_api",
    "runners.ssh",
]

a = Analysis(
    [str(PROJECT_ROOT / "tools" / "run_backend.py")],
    pathex=[str(BACKEND_DIR), str(PROJECT_ROOT)],
    binaries=[],
    datas=datas + backend_modules,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "wx",
        "IPython",
        "notebook",
        "jupyter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="3r-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep console for debugging; set False for release
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "client" / "src-tauri" / "icons" / "icon.ico"),
)
