# -*- coding: utf-8 -*-
"""Zip the clean staging tree, copy the NSIS installer alongside, verify no junk."""
import os, re, glob, shutil, zipfile
from pathlib import Path

BASE = Path(r"e:\Demo\3R_All_in_One")
PKG = BASE / "_package"
DST = PKG / "3R_All_in_One"
ZIP = BASE / "3R_All_in_One.zip"

# 1. zip the staging tree (top-level folder 3R_All_in_One/)
if ZIP.exists():
    ZIP.unlink()
out = shutil.make_archive(str(ZIP.with_suffix("")), "zip", root_dir=str(PKG), base_dir="3R_All_in_One")
zp = Path(out)

# 2. verify no junk inside
zf = zipfile.ZipFile(zp)
names = zf.namelist()
JUNK = re.compile(r"(/__pycache__/|/node_modules/|/target/|/\.venv/|/\.git/|\.codex_doc_review|/\.omx/|/local_jobs/|\.pyc$|\.log$|\.exe$|\.msi$|开题报告|心得/|AGENT_HANDOFF|HANDOFF_PROMPT|/dist/)")
junk = [n for n in names if JUNK.search(n)]
tops = sorted({n.split("/")[1] for n in names if n.count("/") >= 1 and len(n.split("/")) > 1 and n.split("/")[1]})

# 3. copy installer alongside the zip
installers = glob.glob(str(BASE / "3R_All_in_One" / "client" / "src-tauri" / "target" / "release" / "bundle" / "nsis" / "*.exe"))
# pick the largest exe (guards against half-written stub files)
installers = sorted(installers, key=lambda p: os.path.getsize(p), reverse=True)
copied = None
if installers:
    src = installers[0]
    copied = BASE / os.path.basename(src)
    shutil.copy2(src, copied)

print("=== SOURCE ZIP ===")
print(" path :", zp)
print(" size : %.2f MB" % (zp.stat().st_size / 1024 / 1024))
print(" files:", sum(1 for n in names if not n.endswith("/")))
print(" junk :", junk if junk else "none")
print(" top  :", tops)
print("=== INSTALLER ===")
if copied:
    print(" src  :", src)
    print(" copy :", copied)
    print(" size : %.2f MB" % (copied.stat().st_size / 1024 / 1024))
else:
    print(" (no installer found)")
