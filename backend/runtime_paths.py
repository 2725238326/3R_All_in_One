"""Runtime path resolution for the 3R All-in-One backend.

This is the single source of truth for filesystem layout. It deliberately
distinguishes three concepts that earlier versions of the project
conflated by using ``Path(__file__).resolve().parent`` everywhere:

* **bundle root** — read-only resources that ship with the application
  (templates, ``agent/model_specs/*.yaml``, ``runners/*.py``, the built
  React client, etc.). In dev this is the project root. When the
  backend has been frozen with PyInstaller this is ``sys._MEIPASS``.
* **backend root** — directory that contains ``app.py`` and friends.
  Mostly useful when something inside the backend package wants to
  resolve a sibling file (e.g. Jinja templates).
* **data root** — per-user, *writable* directory that holds the job
  cache, settings, advisor traces, etc. In dev this stays next to
  ``app.py`` so existing developer flows do not change. In a frozen
  install we relocate to ``%LOCALAPPDATA%\\3R All-in-One`` (Windows),
  ``~/Library/Application Support/3R All-in-One`` (macOS) or
  ``$XDG_DATA_HOME/3r-all-in-one`` (Linux). Setting the
  ``KYKT_DATA_ROOT`` environment variable overrides every default and
  is intended for portable installs and integration tests.

The helpers below intentionally cache nothing: every call recomputes
the path so a test can monkey-patch ``KYKT_DATA_ROOT`` mid-run without
restarting the process.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

__all__ = [
    "is_frozen",
    "bundle_root",
    "backend_root",
    "data_root",
    "local_jobs_dir",
    "settings_dir",
    "runners_dir",
    "model_specs_dir",
    "samples_manifest_path",
    "deployment_script_path",
    "client_dist_dir",
    "templates_dir",
]

_APP_NAME = "3R All-in-One"


def is_frozen() -> bool:
    """True when running inside a PyInstaller bundle (or similar)."""
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """Directory that holds *read-only* resources shipped with the app.

    * Frozen: ``sys._MEIPASS`` (PyInstaller temp extract dir for ``--onefile``,
      install dir for ``--onedir``).
    * Dev: the project root, i.e. ``backend/runtime_paths.py``'s grandparent.
    """
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
    return Path(__file__).resolve().parent.parent


def backend_root() -> Path:
    """Directory that contains ``app.py``.

    Always resolves to ``<bundle_root>/backend`` so frozen builds can keep
    the same on-disk layout as dev.
    """
    if is_frozen():
        return bundle_root() / "backend"
    return Path(__file__).resolve().parent


def data_root() -> Path:
    """Per-user writable directory for jobs, settings, traces, etc.

    Resolution order:

    1. ``KYKT_DATA_ROOT`` environment variable (always wins).
    2. Dev mode (not frozen): ``backend/`` — preserves historical behavior
       so developers see ``backend/local_jobs/`` exactly where they
       always have.
    3. Frozen mode: an OS-appropriate per-user data directory under the
       application name. The directory is created on first access by the
       caller; this function never touches the filesystem.
    """
    override = os.environ.get("KYKT_DATA_ROOT")
    if override:
        return Path(override).expanduser().resolve()

    if not is_frozen():
        return Path(__file__).resolve().parent

    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(base) / _APP_NAME

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / _APP_NAME

    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "3r-all-in-one"
    return Path.home() / ".local" / "share" / "3r-all-in-one"


def local_jobs_dir() -> Path:
    """Where ``job.json``/``status.json``/``input/``/``output/`` live."""
    return data_root() / "local_jobs"


def settings_dir() -> Path:
    """Per-user mutable settings (``advisor.json`` etc.)."""
    return data_root() / "settings"


def runners_dir() -> Path:
    """Source of truth for ``<model>_runner.py`` scripts.

    These are read-only, ship with the app, and get SCP'd to the remote
    server before each job. Always lives under ``bundle_root()``.
    """
    return bundle_root() / "runners"


def model_specs_dir() -> Path:
    """``agent/model_specs/`` with the seven YAML blueprints."""
    return bundle_root() / "agent" / "model_specs"


def samples_manifest_path() -> Path:
    """Shared sample manifest used by the comparison matrix."""
    return bundle_root() / "samples" / "samples_manifest.json"


def deployment_script_path() -> Path:
    """PowerShell helper that probes the remote 3R server."""
    return bundle_root() / "tools" / "check_3r_remote.ps1"


def client_dist_dir() -> Path:
    """``client/dist`` with the built Vite/React assets."""
    return bundle_root() / "client" / "dist"


def templates_dir() -> Path:
    """Optional Jinja2 templates (legacy fallback for the React client)."""
    return backend_root() / "templates"
