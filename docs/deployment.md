# Deployment Guide

## Server Requirements

- GPU: NVIDIA with CUDA 12.x (tested on TITAN RTX / sm75)
- RAM: 32GB+ recommended
- Disk: 50GB+ for all model weights
- Conda / Miniconda installed
- SSH access from local machine

## Local Requirements

- Windows 10/11 (Tauri desktop)
- Python 3.11+ (for backend)
- Node.js 18+ (for frontend dev)
- Rust toolchain (for Tauri build)
- OpenSSH client

## Server Setup (One-time)

### Manual

```bash
# For each model, follow the spec in agent/model_specs/<model>.yaml
conda create -n dust3r python=3.11 -y
conda activate dust3r
cd /hdd3/kykt26/code/dust3r-main
pip install -r requirements.txt
```

### Automated (via Agent)

```python
from agent.env_builder import SSHConfig, build_all
from pathlib import Path

ssh = SSHConfig(host="172.17.140.97", user="kykt26", alias="KYKT-UI")
reports = build_all(ssh, Path("agent/model_specs"))

for r in reports:
    print(f"{r.model}: {'OK' if r.success else 'FAIL'}")
```

## Local Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

## Desktop Build

```bash
cd client
npm install
npm run tauri build
```

Output:
- `client/src-tauri/target/release/kykt_vision_client.exe`
- `client/src-tauri/target/release/bundle/nsis/3R All-in-One_0.5.0_x64-setup.exe`

## Release Verification

Run the local release gate before creating a release artifact:

```bash
python tools/release_check.py
```

This verifies version alignment, Agent blueprint validation, Python tests,
frontend build output, and Docker Compose configuration when Docker is installed.
Use `--require-docker` on a machine that has Docker when Docker packaging is a
release requirement.

For the Windows desktop release, rebuild the backend sidecar and installer:

```powershell
.\tools\build_backend.ps1
cd client
npm run desktop:build
```

## SSH Configuration

The platform expects an SSH alias `KYKT-UI` in `~/.ssh/config`:

```
Host KYKT-UI
    HostName 172.17.140.97
    User kykt26
    IdentityFile ~/.ssh/id_rsa
    StrictHostKeyChecking no
```

## Portable Bundle

See `PORTABLE_BUNDLE.md` for creating a self-contained distribution with embedded Python.
