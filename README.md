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

- **Command Center** — Job queue, batch dispatch, real-time status via WebSocket
- **Sample Matrix** — Cross-model comparison on shared test samples
- **AI Advisor** — Automated result evaluation, parameter recommendation, failure diagnosis
- **Resource Monitor** — GPU/CPU/memory/disk real-time monitoring
- **Report Export** — HTML/PDF comparison reports with depth heatmaps and GIF animations
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
├── backend/           # FastAPI backend
│   ├── app.py         # Main application
│   ├── job_store.py   # Job persistence
│   ├── job_scheduler.py
│   ├── resource_monitor.py
│   ├── metrics_calculator.py
│   ├── report_exporter.py
│   ├── visual_artifacts.py
│   ├── advisor.py
│   ├── ssh_runner.py
│   ├── model_registry.py
│   ├── model_contracts.py
│   └── requirements.txt
├── client/            # React + Tauri frontend
│   ├── src/
│   ├── src-tauri/
│   └── package.json
├── runners/           # Remote model execution scripts
│   ├── dust3r_runner.py
│   ├── mast3r_runner.py
│   ├── monst3r_runner.py
│   ├── spann3r_runner.py
│   └── fast3r_runner.py
├── agent/             # One-click setup & experiment orchestration
│   ├── model_specs/   # Declarative model configurations
│   ├── env_builder.py
│   ├── smoke_runner.py
│   └── experiment_agent.py
├── docs/              # Documentation
├── tools/             # Utility scripts
└── samples/           # Shared test samples manifest
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

## Version History

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.

## License

MIT License — See [LICENSE](LICENSE)

---

*Evolved from KYKT Vision UI (2026-03 ~ 2026-05)*
