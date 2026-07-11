# -*- coding: utf-8 -*-
"""
One-shot desktop-exe build orchestrator for 3R All-in-One.

Runs the whole fragile pipeline in the background, logging to tmp/build_exe.log:
  1. Auto-detect a Python/conda env that has the backend runtime deps.
  2. Ensure PyInstaller is available there.
  3. Build the backend sidecar (tools/3r_backend.spec) -> dist/3r-backend.exe
  4. Copy to client/src-tauri/binaries/3r-backend-x86_64-pc-windows-msvc.exe
  5. Run `npm run desktop:build` (tauri build) -> NSIS installer.
  6. Report the produced installer path.

Everything is best-effort and heavily logged so status can be read from the log.
"""
import os
import sys
import glob
import shutil
import subprocess
from pathlib import Path

ROOT = Path(r"e:\Demo\3R_All_in_One\3R_All_in_One")
LOG = ROOT / "tmp" / "build_exe.log"
TRIPLE = "x86_64-pc-windows-msvc"

RUNTIME_DEPS = ["fastapi", "uvicorn", "paramiko", "PIL", "numpy",
                "pandas", "matplotlib", "loguru", "yaml", "pydantic",
                "jinja2", "httpx", "psutil", "aiofiles"]

CANDIDATE_ROOTS = [
    Path(r"D:\Anacondaenv\envs\kykt"),
    Path(r"D:\Anaconda"),
    Path(r"C:\Users\27252\miniconda3"),
]
# also scan all envs under D:\Anacondaenv\envs
for p in glob.glob(r"D:\Anacondaenv\envs\*"):
    pp = Path(p)
    if pp not in CANDIDATE_ROOTS:
        CANDIDATE_ROOTS.append(pp)


def log(msg):
    line = str(msg)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def env_for(root: Path):
    """Return an environment dict with conda-style PATH activation for `root`."""
    env = dict(os.environ)
    extra = [str(root), str(root / "Library" / "mingw-w64" / "bin"),
             str(root / "Library" / "usr" / "bin"), str(root / "Library" / "bin"),
             str(root / "Scripts"), str(root / "bin")]
    env["PATH"] = os.pathsep.join(extra) + os.pathsep + env.get("PATH", "")
    return env


def py_has_deps(py: Path, root: Path):
    if not py.exists():
        return None
    code = "import importlib.util as u,sys;" \
           "mods=%r;" \
           "miss=[m for m in mods if u.find_spec(m) is None];" \
           "print('MISS:'+','.join(miss))" % RUNTIME_DEPS
    try:
        r = subprocess.run([str(py), "-c", code], capture_output=True, text=True,
                           env=env_for(root), timeout=120)
    except Exception as e:
        return None
    out = (r.stdout or "") + (r.stderr or "")
    for tok in out.splitlines():
        if tok.startswith("MISS:"):
            miss = [m for m in tok[5:].split(",") if m]
            return miss
    return None


def run(cmd, cwd, root, timeout=1800):
    log(f"\n$ {cmd}  (cwd={cwd})")
    r = subprocess.run(cmd, cwd=str(cwd), env=env_for(root), shell=isinstance(cmd, str),
                       capture_output=True, text=True, timeout=timeout)
    if r.stdout:
        log(r.stdout[-8000:])
    if r.stderr:
        log("[stderr] " + r.stderr[-8000:])
    log(f"[exit={r.returncode}]")
    return r.returncode


def main():
    LOG.write_text("=== 3R desktop build ===\n", encoding="utf-8")
    log(f"root={ROOT}")

    # 1. pick env
    chosen_root = None
    chosen_py = None
    for root in CANDIDATE_ROOTS:
        py = root / "python.exe"
        miss = py_has_deps(py, root)
        if miss is None and not py.exists():
            continue
        log(f"env {root}: python={'yes' if py.exists() else 'no'} missing_deps={miss}")
        if miss == []:
            chosen_root, chosen_py = root, py
            break
    if chosen_py is None:
        # fall back to first env that at least has a python; install deps
        for root in CANDIDATE_ROOTS:
            py = root / "python.exe"
            if py.exists():
                chosen_root, chosen_py = root, py
                break
        if chosen_py is None:
            log("FATAL: no python found in any candidate env")
            log("STATUS=FAILED")
            return
        log(f"No env had all deps; installing into {chosen_root}")
        run([str(chosen_py), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], ROOT, chosen_root, timeout=2400)

    log(f"CHOSEN ENV: {chosen_root}")

    # 2. ensure pyinstaller
    miss_pi = py_has_deps(chosen_py, chosen_root)  # re-check deps quickly
    code = "import importlib.util as u;print('PI' if u.find_spec('PyInstaller') else 'NOPI')"
    r = subprocess.run([str(chosen_py), "-c", code], capture_output=True, text=True, env=env_for(chosen_root))
    if "NOPI" in (r.stdout or ""):
        log("Installing PyInstaller...")
        run([str(chosen_py), "-m", "pip", "install", "pyinstaller"], ROOT, chosen_root, timeout=900)

    # 3. build sidecar
    rc = run([str(chosen_py), "-m", "PyInstaller", "--clean", "--noconfirm", str(ROOT / "tools" / "3r_backend.spec")],
             ROOT, chosen_root, timeout=2400)
    exe = ROOT / "dist" / "3r-backend.exe"
    if rc != 0 or not exe.exists():
        log(f"FATAL: backend sidecar build failed (rc={rc}, exists={exe.exists()})")
        log("STATUS=FAILED_SIDECAR")
        return
    log(f"sidecar built: {exe} ({exe.stat().st_size/1024/1024:.1f} MB)")

    # 4. copy to tauri binaries
    bindir = ROOT / "client" / "src-tauri" / "binaries"
    bindir.mkdir(parents=True, exist_ok=True)
    target = bindir / f"3r-backend-{TRIPLE}.exe"
    shutil.copy2(exe, target)
    log(f"copied sidecar -> {target}")

    # 5. tauri build (uses node/cargo on PATH)
    rc = run("npm run desktop:build", ROOT / "client", chosen_root, timeout=3600)
    if rc != 0:
        log(f"FATAL: tauri build failed (rc={rc})")
        log("STATUS=FAILED_TAURI")
        return

    # 6. locate installer
    nsis = glob.glob(str(ROOT / "client" / "src-tauri" / "target" / "release" / "bundle" / "nsis" / "*.exe"))
    log(f"NSIS installers: {nsis}")
    log("STATUS=SUCCESS")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        log("EXCEPTION: " + traceback.format_exc())
        log("STATUS=EXCEPTION")
