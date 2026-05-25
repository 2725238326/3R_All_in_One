# Changelog

All notable changes to this project will be documented in this file.

## [v0.4.0] - 2026-05-25

### Added
- Job scheduler with concurrency control, priority queue, and automatic retry
- Evaluation metrics engine (RMSE, AbsRel, point cloud density, trajectory ATE/RPE)
- Report export in HTML/PDF format with styled templates
- Resource monitor for GPU/CPU/memory/disk (local)
- Visual artifact generation (depth heatmaps, comparison GIF, diff maps)
- ResourceMonitor frontend component in System workspace
- Frontend types for SchedulerStatus, SystemResources, JobMetrics

### Fixed
- Netstat/taskkill/where console window popup on Windows (CREATE_NO_WINDOW)
- Duplicate API route conflict on `/api/compare/samples/{id}/report`
- CSS global transition causing white screen on navigation

## [v0.3.1] - 2026-05-03

### Changed
- Default frontend switched to React/Vite client (Jinja as fallback)
- Tauri desktop made portable-friendly (flexible Python resolver chain)

### Fixed
- Align3R curope rebuilt against env torch + CUDA 12.6 (GLIBC mismatch)
- CUT3R curope built from scratch (no prior build artifact)
- Cancel flow hardened: SIGTERM → grace → SIGKILL → verify
- Orphan running jobs rehydrated on backend restart

## [v0.3.0] - 2026-04-21

### Added
- 6-model integration: DUSt3R, MASt3R, MonST3R, Spann3R, Fast3R, CUT3R
- Sample matrix and shared test sample manifest
- Remote deployment status panel
- Manual evaluation scoring with persistence
- Model catalog with family/status/priority flags
- `/api/samples`, `/api/deployment/status` endpoints

## [v0.2.0] - 2026-04-13

### Added
- MonST3R video/dynamic reconstruction support
- MASt3R static matching integration (DUSt3R-family)
- AI advisor layer (OpenAI-compatible) with evaluation and report generation
- Workspace navigation layout (工作台/文件/运行/AI评估/系统)
- AI configuration modal (no manual JSON editing)
- Model registry for extensible model management
- Preset parameter tiers (快速/标准/增强)

## [v0.1.0] - 2026-04-06

### Added
- DUSt3R multi-view stereo remote dispatch via SSH/SCP
- Local job cache system (job.json, status.json, input/, output/, logs/)
- React + TypeScript + Tauri 2 desktop skeleton
- FastAPI backend with job lifecycle APIs
- Chinese localization end-to-end
- Input drag-and-drop upload with file management
- Live log streaming and progress tracking
- Task actions: run, retry, duplicate, cancel
