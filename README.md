# 3R All-in-One

> 3D Reconstruction Model Management Platform — 一站式 3R 模型管理、对比与评估平台

## Overview

3R All-in-One 是一个面向 3D 重建/空间智能研究的本地桌面工作台，支持多模型统一管理、远程 GPU 调度、自动化实验编排和 AI 辅助评估。

### Supported Models

| Model | Type | Status |
|-------|------|--------|
| DUSt3R | Static multi-view stereo | ✅ Integrated |
| MASt3R | Static matching + reconstruction | ✅ Integrated |
| MonST3R | Dynamic video reconstruction | ✅ Integrated |
| Spann3R | Spatial memory reconstruction | ✅ Integrated |
| Fast3R | Fast multi-image reconstruction | ✅ Integrated |
| Align3R | Video depth alignment | 🔧 Env ready |
| CUT3R | Online persistent reconstruction | 🔧 Env ready |

### Key Features

- **Command Center** — Job queue with search/filter, batch dispatch, real-time progress via WebSocket
- **Comparison Charts** — Radar / bar charts + side-by-side visual preview for multi-model comparison
- **Sample Matrix** — Cross-model comparison on shared test samples
- **AI Advisor** — Automated result evaluation, parameter recommendation, failure diagnosis
- **Parameter Templates** — Save/load param configs for quick reuse across experiments
- **Multi-Server Management** — Multiple SSH server profiles with one-click switching
- **Upload Progress** — Real-time file upload progress bar with XHR streaming
- **Failure Diagnosis** — Error message visible directly in queue, hover for full detail
- **Resource Monitor** — GPU/CPU/memory/disk real-time monitoring
- **Report Export** — HTML/PDF comparison reports with depth heatmaps and GIF animations
- **Agent Workbench** — Model blueprint registry, validation, and environment build task orchestration
- **Experiment Agent** — One-click environment setup and batch experiment orchestration
- **Desktop App** — Tauri 2 desktop shell with embedded backend

## Architecture

```
┌──────────────────────────────────────────────────┐
│                  Tauri Desktop Shell               │
│  ┌──────────────────────────────────────────────┐ │
│  │           React + TypeScript Frontend         │ │
│  │   Queue · Compare · Samples · System · AI     │ │
│  └──────────────┬───────────────────────────────┘ │
│                 │ HTTP / WebSocket                  │
│  ┌──────────────┴───────────────────────────────┐ │
│  │           FastAPI Backend (Python)             │ │
│  │  Jobs · Scheduler · Metrics · Reports · Agent │ │
│  └──────────────┬───────────────────────────────┘ │
│                 │ SSH / SCP                         │
│  ┌──────────────┴───────────────────────────────┐ │
│  │          Remote GPU Server                     │ │
│  │   conda envs · model weights · runners        │ │
│  └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

## Project Structure

```
3R_All_in_One/
├── backend/               # FastAPI backend
│   ├── app.py             # Main application (~2600 LOC)
│   ├── job_store.py       # Job persistence & query
│   ├── job_scheduler.py   # Concurrency control & priority queue
│   ├── ssh_runner.py      # SSH/SCP remote execution
│   ├── param_templates.py # Parameter template storage
│   ├── server_profiles.py # Multi-server configuration
│   ├── logging_config.py  # Structured logging (loguru)
│   ├── retry_policy.py    # Auto-retry with exponential backoff
│   ├── state_reconciler.py# Crash recovery
│   ├── resource_monitor.py
│   ├── metrics_calculator.py
│   ├── report_exporter.py
│   ├── visual_artifacts.py
│   ├── advisor.py
│   ├── model_registry.py
│   ├── model_contracts.py
│   └── runners/           # Runner implementations
│       ├── ssh.py         # SSH runner (primary)
│       ├── docker.py      # Docker runner (optional)
│       └── online_api.py  # API runner (optional)
├── client/                # React + Tauri frontend
│   ├── src/
│   │   ├── App.tsx        # Main app (Zustand migration in progress)
│   │   ├── CompareCharts.tsx    # Radar/bar/preview charts
│   │   ├── CompareBoard.tsx     # Comparison board
│   │   ├── ParamTemplates.tsx   # Param template selector
│   │   ├── QueueWorkspace.tsx   # Queue with search & filter
│   │   ├── AgentWorkbench.tsx   # Agent blueprint and environment orchestration
│   │   ├── uploadProgress.ts   # Upload progress utility
│   │   ├── store/appStore.ts   # Zustand global store
│   │   └── hooks/              # Custom hooks
│   ├── src-tauri/
│   └── package.json
├── runners/               # Remote model execution scripts
│   ├── dust3r_runner.py
│   ├── mast3r_runner.py
│   ├── monst3r_runner.py
│   ├── spann3r_runner.py
│   └── fast3r_runner.py
├── tests/                 # Backend/Agent tests (130 passing, 1 skipped)
│   └── backend/
├── agent/                 # One-click setup & experiment orchestration
│   ├── model_specs/
│   ├── env_builder.py
│   ├── smoke_runner.py
│   └── experiment_agent.py
├── docs/                  # Documentation
├── tools/                 # Utility scripts
└── samples/               # Shared test samples manifest
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Rust toolchain (for Tauri desktop build)
- SSH access to GPU server

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

### Frontend (Dev)

```bash
cd client
npm install
npm run dev
```

### Desktop Build

```bash
cd client
npm run tauri build
```

### Release Verification

```bash
python tools/release_check.py
```

The release gate checks version alignment, Agent blueprint validity, backend tests,
frontend build output, and Docker Compose syntax when Docker is installed.

For a Windows desktop release, also run:

```powershell
.\tools\build_backend.ps1
cd client
npm run desktop:build
```

## Version History

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.

## License

MIT License — See [LICENSE](LICENSE)

---

*Evolved from KYKT Vision UI (2026-03 ~ 2026-05)*
