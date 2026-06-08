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
- Agent 后端 API：`/api/agent/registry`、`/api/agent/validate`、后台环境构建任务接口
- AgentWorkbench 前端工作台：蓝图状态、校验摘要、模型详情、后台构建任务状态
- 发布检查脚本 `tools/release_check.py`：版本对齐、Agent 校验、Python 测试、前端构建、Docker 静态配置、Docker Compose 和正式产物检查
- 发布依赖清单补齐 loguru/psutil 等运行依赖
- 开发/打包依赖声明补齐 PyInstaller
- Docker 生产镜像改为 Python 3.11，保留 backend/agent/runners/samples/tools 运行时布局
- Docker health check 统一到 `/api/health`
- Docker 运行时数据根设置为 `KYKT_DATA_ROOT=/app/data`，确保容器数据写入挂载目录
- PyInstaller 后端侧车打包纳入 Agent 蓝图、根级 runner 脚本和 React 构建产物
- Tauri NSIS 正式安装包路径验证：`3R All-in-One_0.5.0_x64-setup.exe`

### Changed
- QueueWorkspace 默认展示 50 条任务（原 10 条）
- Docker Runner 和 Online API Runner 仅作为可选后备（不在默认 UI 显示）
- FastAPI 启动/关闭流程迁移到 lifespan，移除 `@app.on_event` 弃用用法
- Agent CLI 状态输出改为 ASCII 标记，避免 Windows GBK 控制台编码失败
- HealthDoctor 从诊断方案中提取反引号命令作为 `fix_command`，常见可修复错误会正确归类为 fixable
- Agent `smoke` CLI 使用 `SmokeReport.ready/smoke_output`，修复远程 smoke 成功后仍因字段名错误崩溃的问题
- Vite 构建按 React/Recharts/Three/lucide 拆分 vendor chunks，消除正式构建大块警告

### Fixed
- `runners/__init__.py` 导入 docker 模块时 try/except 防止 ImportError
- `/api/runners/availability` 在缺少可选 Docker runner 模块时返回 `docker: false`，不再抛出 500
- 远程 `python -m agent health/smoke/build dust3r --alias KYKT-UI` 验证通过
- 130 个后端/Agent 测试全部通过，1 个创建任务流程测试按设计跳过

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
