# Architecture

## System Overview

3R All-in-One is a local-first desktop workbench for 3D reconstruction model management. In the closing version, the core implementation is a React/Tauri desktop shell backed by a local FastAPI service. Model inference remains on remote GPU servers and is reached through SSH/SCP, so the local machine keeps task state, UI state, logs, and result indexes without owning the heavy model environments.

```
User Machine                        GPU Server
┌─────────────────────┐             ┌──────────────────────┐
│  Tauri Desktop App  │             │  conda envs          │
│  ├─ React Frontend  │             │  ├─ dust3r           │
│  │  └─ WebSocket    │ ◄──SSH──►   │  ├─ monst3r          │
│  └─ FastAPI Backend │             │  ├─ mast3r            │
│     ├─ Job Store    │             │  ├─ spann3r           │
│     ├─ Scheduler    │             │  ├─ fast3r            │
│     ├─ SSH Runner   │             │  ├─ align3r           │
│     ├─ Advisor (AI) │             │  └─ cut3r             │
│     └─ Metrics      │             │                      │
└─────────────────────┘             │  model weights/       │
                                    │  runners/             │
                                    │  jobs/<job_id>/       │
                                    └──────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Desktop Shell | Tauri 2 (Rust) |
| Frontend | React 19 + TypeScript + Vite |
| Backend | FastAPI (Python 3.11) |
| Transport | SSH / SCP (system binaries) |
| State | JSON files in `local_jobs/` |
| AI | OpenAI-compatible API |

## Closing Implementation Status

| Area | Status |
|------|--------|
| Desktop shell | Tauri 2 build path and Windows release gate are present |
| Frontend workspaces | Queue, model selection, compare, sample matrix, system config, advisor, and agent workbench are implemented |
| Backend APIs | Job, model, sample, deployment, template, server profile, report, advisor, and agent endpoints are present |
| Remote execution | SSH/SCP runner is the primary supported path |
| Optional runners | Docker and online API runners exist as fallback/experimental paths, not the default workflow |
| Model catalog | DUSt3R, MASt3R, MonST3R, Spann3R, Fast3R, Align3R, and CUT3R are registered |
| Testing | Backend and agent unit tests plus Playwright E2E smoke coverage are present |
| Release checks | `tools/release_check.py` validates version alignment, blueprints, tests, frontend build, and packaging prerequisites |

## Backend Modules

| Module | Responsibility |
|--------|---------------|
| `app.py` | FastAPI routes, WebSocket, lifecycle |
| `job_store.py` | Job persistence, status tracking |
| `job_scheduler.py` | Priority queue, concurrency control, retry |
| `ssh_runner.py` | Remote job dispatch via SSH/SCP |
| `model_registry.py` | Model catalog and metadata |
| `model_contracts.py` | Input/output contracts per model |
| `advisor.py` | AI evaluation and recommendation |
| `metrics_calculator.py` | Depth/pointcloud/trajectory metrics |
| `report_exporter.py` | HTML/PDF report generation |
| `resource_monitor.py` | System resource monitoring |
| `visual_artifacts.py` | Heatmaps, comparison GIFs, diff maps |
| `development_store.py` | Development lane tracking and model promotion drafts |

## Frontend Workspaces

| Workspace | Purpose |
|-----------|---------|
| Queue (工作队列) | Job list, batch operations, status overview |
| Create (新建任务) | Model selection, parameter configuration, file upload |
| Compare (对比面板) | Cross-model comparison viewer |
| Samples (样例矩阵) | Shared test sample management |
| Development (研发加速) | Development lane tracking |
| System (系统配置) | Backend status, deployment, resource monitor, AI config |

## Job Lifecycle

```
created → preparing_remote → uploading → running → downloading → finished
                                           ↓
                                        failed → (retry) → created
                                           ↓
                                      cancelled
```

## Agent Module

The agent module provides automated environment management:

1. **Model Specs** — Declarative YAML configuration for each model
2. **Env Builder** — SSH-based automatic environment setup
3. **Smoke Runner** — Automated readiness verification
4. **Experiment Agent** — Batch experiment orchestration

## Known Boundaries

- The platform does not hide model-specific environment complexity. Each model still needs a valid remote repository, conda environment, weights, and any custom CUDA extensions.
- `scene_meta.json` provides a common result index, but not every model can produce every artifact or metric.
- Quantitative metrics depend on the dataset and available ground truth; no-ground-truth samples are tracked through runtime, completeness, logs, and visual artifacts.
- The current architecture is intentionally local-first. Multi-user auth, cluster scheduling, and model marketplace features are outside the closing scope.
