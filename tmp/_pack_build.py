# -*- coding: utf-8 -*-
"""Copy only relevant project files into a clean staging dir, pruning build artifacts."""
import os, shutil, fnmatch
from pathlib import Path

SRC = Path(r"e:\Demo\3R_All_in_One\3R_All_in_One")
DST = Path(r"e:\Demo\3R_All_in_One\_package\3R_All_in_One")

DIRS = ["backend", "client", "runners", "agent", "tests", "e2e", "docs"]
TOOLS_KEEP = ["run_backend.py", "build_backend.ps1", "3r_backend.spec", "release_check.py"]
POST_REMOVE_DIRS = ["backend/local_jobs"]
DOCS_EXCLUDE = [
    "ch4-final.txt", "ch4-structure-check.txt", "current-report-extracted.txt",
    "current-report-with-styles.txt", "final-defense-ppt-plan.md", "final-report-demo-plan.md",
    "final-spot-check.txt", "full-final-dump.txt", "opening-report-jbw.txt", "rewritten-report-dump.txt",
    "Dream3R与3R-All-in-One视频录制脚本.md",
]
ROOT_FILES = [
    "README.md", "CHANGELOG.md", "pyproject.toml", "requirements.txt",
    "Dockerfile", "docker-compose.yml", ".dockerignore",
    ".gitignore", ".gitattributes", "playwright.config.ts",
]
PRUNE_DIRS = {
    "__pycache__", "node_modules", ".venv", "venv", "target", "dist", "build",
    ".pytest_cache", ".git", ".idea", ".vscode", ".mypy_cache", ".ruff_cache",
}
PRUNE_FILE_GLOBS = ["*.pyc", "*.pyo", "*.log", ".coverage", "*.swp", "*.swo",
                    ".DS_Store", "Thumbs.db", "*.exe", "*.msi"]


def ignore(dirpath, names):
    drop = set()
    for n in names:
        full = os.path.join(dirpath, n)
        if os.path.isdir(full):
            if n in PRUNE_DIRS:
                drop.add(n)
        elif any(fnmatch.fnmatch(n, g) for g in PRUNE_FILE_GLOBS):
            drop.add(n)
    return drop


def main():
    if DST.exists():
        shutil.rmtree(DST)
    DST.mkdir(parents=True)
    for d in DIRS:
        s = SRC / d
        if s.exists():
            shutil.copytree(s, DST / d, ignore=ignore)
    (DST / "tools").mkdir(parents=True, exist_ok=True)
    for f in TOOLS_KEEP:
        if (SRC / "tools" / f).exists():
            shutil.copy2(SRC / "tools" / f, DST / "tools" / f)
    for f in ROOT_FILES:
        if (SRC / f).exists():
            shutil.copy2(SRC / f, DST / f)
    for rel in POST_REMOVE_DIRS:
        if (DST / rel).exists():
            shutil.rmtree(DST / rel)
    for f in DOCS_EXCLUDE:
        if (DST / "docs" / f).exists():
            (DST / "docs" / f).unlink()

    total = sum(len(fs) for _, _, fs in os.walk(DST))
    per = {}
    for root, _, files in os.walk(DST):
        for fn in files:
            rel = Path(root, fn).relative_to(DST)
            top = rel.parts[0] if len(rel.parts) > 1 else "(root)"
            per[top] = per.get(top, 0) + 1
    print("=== STAGING MANIFEST ===")
    for k in sorted(per):
        print(f"  {k:14s} {per[k]:5d}")
    print(f"  TOTAL {total} files")


if __name__ == "__main__":
    main()
