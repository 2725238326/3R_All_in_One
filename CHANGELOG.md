# Changelog

All notable changes to this project will be documented in this file.

## [v0.5.0] - 2026-05-27

### Added

**对比与可视化**
- 模型对比图表面板（雷达图 / 柱状图 / 并排预览），支持 Tab 切换
- 雷达图：6 维评分（结构完整度/轨迹稳定性/噪声控制/动态处理/深度连续性/展示可用性）多模型叠加
- 柱状图：单维度横向对比 + 全维度缩略概览
- 并排预览：不同模型的点云/图片/视频同屏对比，自适应栅格

**任务管理**
- 任务队列搜索：支持按 ID、模型、备注全文搜索
- 状态筛选下拉（全部/运行中/待派发/已完成/失败）
- 列表扩展到 50 条（原 10 条）
- 失败任务在队列中直接显示错误原因摘要（hover 看全文）
- 运行中任务卡片实时显示 progress_message

**参数模板**
- 参数模板保存/加载/删除，按模型筛选
- 后端 `/api/templates` CRUD API
- 前端 ParamTemplateSelector 组件

**多服务器配置**
- 多 SSH 服务器 profile 管理（增删改查 + 活跃切换）
- 后端 `/api/servers` CRUD API + `/api/servers/active` 切换
- 配置持久化到 `local_jobs/servers/`

**上传体验**
- 文件上传进度条（XHR + onprogress），创建任务时实时显示百分比
- 按钮文案动态变化（"创建任务" → "上传 67%"）

**基础设施**
- 结构化日志模块（loguru），每任务独立日志文件
- 任务自动重试机制（指数退避，可配置策略）
- 崩溃恢复 / 状态 reconcile（启动时修复孤儿任务）
- Runner 统一接口（RunnerBase + SSH/Docker/OnlineAPI 三实现）
- Zustand 渐进迁移 hooks（useUIState.ts）

### Changed
- QueueWorkspace 默认展示 50 条任务（原 10 条）
- Docker Runner 和 Online API Runner 仅作为可选后备（不在默认 UI 显示）

### Fixed
- `runners/__init__.py` 导入 docker 模块时 try/except 防止 ImportError
- 116 个后端测试全部通过

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
