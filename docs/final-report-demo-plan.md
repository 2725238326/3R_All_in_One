# 结题报告、答辩 PPT 与软件演示规划

> 适用版本: 3R All-in-One v0.5.0 结题演示版  
> 当前验证口径: Agent blueprint validation 7/7 valid; Python tests 167 passed, 1 skipped; frontend build passed; release gate core checks passed; Docker CLI 缺失仅为本机环境 warning。

## 1. 项目当前结题定位

3R All-in-One 是面向前馈式 3D Reconstruction / 3R 模型的本地桌面工作台。系统以 React + Tauri 前端、FastAPI 后端和 SSH/SCP 远端 GPU 执行为主链路，将不同模型的环境差异、runner 差异和输出差异收敛到模型注册表、Agent 蓝图、任务记录、输出合同和实验记录中。

结题版本的表述重点不是“完整复现所有论文 benchmark”，而是“完成一个可演示、可验证、可解释的多模型集成与实验管理闭环”。

核心闭环可以概括为:

```text
模型蓝图 -> Agent 校验/健康检查/smoke/build -> 创建任务 -> 远端执行 -> 结果回传 -> scene_meta 解析 -> 输出合同检查 -> 前端审查/对比 -> 报告与实验记录包
```

## 2. 结题报告建议结构

### 2.1 摘要

建议控制在 400-600 字，说明四件事:

- 背景: 前馈式 3R 模型发展快，但环境、输入输出和运行脚本差异大。
- 目标: 构建本地化多模型实验管理工作台，统一任务创建、远端执行、结果记录和模型集成验证。
- 方法: React/Tauri + FastAPI + SSH/SCP 架构，结合 Agent 蓝图、runner 输出合同、scene_meta 归一化和实验记录包。
- 成果: 已集成 DUSt3R、MASt3R、MonST3R、Spann3R、Fast3R、Align3R、CUT3R 等模型状态，形成可演示闭环，并通过 release_check 核心验证。

### 2.2 绪论

推荐小节:

1. 研究与工程背景
2. 3D 重建模型平台化管理的痛点
3. 本项目目标与边界
4. 本文/本系统主要工作

边界要写清楚:

- 本项目关注平台集成、任务调度、结果记录和演示验证。
- 不宣称完整复现全部论文精度指标。
- 完整 benchmark 复现依赖公开数据集、权重、远端 GPU、CUDA/GLIBC 环境和模型官方脚本稳定性。

### 2.3 需求分析

建议分为三类需求:

- 用户需求: 本地桌面操作、创建任务、查看状态、下载结果、对比模型。
- 研究管理需求: 记录参数、模型版本、运行环境、输出产物和失败原因。
- 工程运维需求: 远端 GPU 调用、环境健康检查、smoke test、失败诊断、release gate。

可以配一张角色-能力表:

| 角色 | 关注点 | 系统能力 |
|------|--------|----------|
| 研究者 | 快速运行不同 3R 模型 | 任务创建、参数模板、结果审查 |
| 开发者 | 接入新模型和 runner | model_registry、model_specs、输出合同 |
| 演示/验收人员 | 确认系统能跑通 | release_check、实验记录包、报告导出 |
| 运维者 | 远端环境稳定性 | health/smoke/build、失败诊断、日志归档 |

### 2.4 系统总体设计

推荐展示三层架构:

```text
Tauri Desktop Shell
  React + TypeScript Frontend
    Queue / Create / Inspect / Compare / Agent / Experiments / System

FastAPI Backend
  Jobs / Scheduler / SSH Runner / Model Registry / Model Contracts / Reports / Agent APIs

Remote GPU Server
  conda envs / model weights / runner scripts / outputs
```

重点解释:

- 前端负责工作流编排和结果可视化。
- 后端负责任务记录、接口、调度、合同检查和归档。
- 远端服务器负责真正的模型推理。
- Agent 模块负责模型接入前后的环境验证和 smoke 证明。

### 2.5 关键模块设计

建议按模块写，每个模块用“目标、实现、证据”三段。

#### 任务管理与远端执行

- 目标: 从本地创建任务并派发到远端 GPU。
- 实现: job_store 记录 job.json/status.json; ssh_runner 负责上传、执行、下载; scheduler 负责队列与重试。
- 证据: 任务生命周期、WebSocket 状态更新、result_summary、bundle/report。

#### 模型注册与输出合同

- 目标: 不夸大模型能力，以注册表和蓝图为准管理接入状态。
- 实现: backend/model_registry.py 记录平台可见状态; backend/model_contracts.py 描述参数与结果合同。
- 证据: release_check API surface 与 model contract tests 通过。

#### Agent 工作台

- 目标: 把模型蓝图校验、health、smoke、build 和失败诊断接入前端。
- 实现: agent/env_builder.py、agent/smoke_runner.py、agent/health_doctor.py + 后端 /api/agent/* 异步任务接口 + AgentWorkbench。
- 证据: blueprint validation 7/7 valid; test_agent_checks 通过。

#### 实验编排与可复现实验记录

- 目标: 支持模板化批量实验和后续复盘。
- 实现: experiment_orchestrator 创建真实 job，复用 source job 输入，记录 run/job 关系; experiment_record 生成 manifest/zip。
- 证据: ExperimentWorkbench 连接真实 API; test_experiment_orchestrator 与 test_experiment_record 通过。

#### scene_meta 归一化与结果审查

- 目标: 不同 runner 输出字段不统一时，前端仍能读取稳定结构。
- 实现: backend/scene_meta.py 进行读取时归一化; 合同检查识别 required outputs。
- 证据: test_scene_meta 和 test_model_contracts 通过。

### 2.6 测试与验证

报告中建议直接列最终验证结果:

```text
python tools/release_check.py

[PASS] version alignment
[PASS] packaged resources
[PASS] api surface: 9 agent/closed-loop routes registered
[PASS] docker static config
[PASS] agent blueprint validation
[PASS] python tests: 167 passed, 1 skipped
[PASS] frontend build
[WARN] docker compose config: docker CLI not found
```

解释 Docker warning:

> Docker CLI 未安装导致 docker compose 动态配置无法解析，这是本机环境 warning，不影响当前主路径。项目主路径是 Tauri + FastAPI + SSH/SCP，Docker runner 是可选后备。

### 2.7 总结与展望

建议总结三点成果:

- 完成多模型本地工作台闭环。
- 完成 Agent 驱动的模型接入验证闭环。
- 完成可复现记录和 release gate 验证闭环。

后续展望要克制:

- 补 Align3R 标准样本验证。
- 增强 JobDetail 结果审查页。
- 补统一 events.jsonl 任务事件日志。
- 拆分 backend/app.py 大路由。
- 在固定公开数据集上做一组更完整的可复现实验表格。

## 3. 答辩 PPT 规划

### 3.1 推荐风格

推荐使用“瑞士国际主义”网页 PPT 风格。理由:

- 项目是工程平台和技术汇报，适合网格化、数据驱动和高对比信息展示。
- release_check、测试数量、模型状态、闭环流程适合做成 KPI 大字报和系统图。
- 软件截图、流程图、架构图可以保持清晰、冷静、可信。

推荐时长: 12-15 分钟。  
推荐页数: 13-16 页。  
推荐主题色: IKB 蓝或柠檬绿。IKB 蓝更稳重，柠檬绿更偏技术 demo。

### 3.2 PPT 页面结构

| 页码 | 标题 | 内容重点 | 建议版式 |
|------|------|----------|----------|
| 1 | 3R All-in-One | 项目名、定位、一句话目标 | 封面 |
| 2 | 为什么需要这个平台 | 多模型环境、runner、输出、复现实验割裂 | 问题陈述 |
| 3 | 项目目标与边界 | 做平台闭环，不夸大 benchmark | 四象限/对照 |
| 4 | 总体架构 | Tauri + React + FastAPI + SSH/SCP + Remote GPU | 系统图 |
| 5 | 核心工作流 | 创建任务到结果报告的闭环 | 横向时间线 |
| 6 | 模型接入状态 | 7 个模型及 status | 技术规格表 |
| 7 | Agent 工作台 | blueprint validation、health、smoke、build、diagnosis | 三层/四卡片 |
| 8 | 任务执行链路 | job.json/status.json/scene_meta/result_summary | 流程图 |
| 9 | 结果合同与 scene_meta | 不同 runner 输出统一成可读结构 | Before/After 对照 |
| 10 | 实验编排与记录包 | template -> run -> jobs -> manifest/zip | loop diagram |
| 11 | 软件界面展示 | Queue、Agent、Experiments、JobDetail 截图 | 图片网格 |
| 12 | 验证结果 | 167 passed、frontend build、release gate | KPI 大字报 |
| 13 | 已知限制 | Docker warning、benchmark 边界、远端依赖 | 风险清单 |
| 14 | 后续优化 | JobDetail polish、events.jsonl、报告增强 | 路线图 |
| 15 | 总结 | 可演示、可验证、可解释的闭环 | 收束页 |

### 3.3 每页讲稿口径

#### 第 1 页

> 我们做的是一个面向 3D 重建模型的本地实验管理平台，把模型运行从“手工开终端、手工改脚本、手工找输出”收敛到一个可管理的工作台里。

#### 第 2 页

> 这类模型最大的问题不只是算法，而是工程运行差异。每个模型有不同 conda 环境、权重路径、runner 脚本、输入格式和输出文件。没有平台时，复现实验和后续对比都很难稳定。

#### 第 3 页

> 所以本项目的边界很明确: 我们不宣称完整复现所有论文 benchmark，而是完成平台集成、任务执行、结果记录、对比审查和模型接入验证闭环。

#### 第 4 页

> 系统分三层: 本地桌面前端负责操作和展示，FastAPI 后端负责任务、调度、合同和记录，远端 GPU 服务器负责实际模型推理。三层之间通过 HTTP/WebSocket 和 SSH/SCP 连接。

#### 第 5 页

> 一次任务从本地创建开始，保存输入和参数，然后上传到远端运行，下载结果，解析 scene_meta，检查输出合同，最后在前端展示并导出记录。

#### 第 6 页

> 当前平台接入了 7 个主要模型，每个模型的状态来自 model_registry 和 Agent YAML 蓝图。这保证我们展示的是实际集成状态，而不是口头承诺。

#### 第 7 页

> Agent 工作台是这次增强重点。它把蓝图校验、环境健康检查、smoke test、自动构建和失败诊断接到前端，让模型接入过程也可以被验证和复盘。

#### 第 8 页

> 任务执行不是只看一个 running 状态，而是围绕 job.json、status.json、scene_meta.json、result_summary.json 形成证据链。

#### 第 9 页

> 不同 runner 的输出并不完全一致，所以我们增加了 scene_meta 归一化和输出合同检查，前端可以用稳定结构读取结果，后端也能判断关键产物是否缺失。

#### 第 10 页

> 实验编排支持从模板生成多组参数任务，并复用已有 source job 输入。每次实验可以生成记录包，包含任务、参数、模型蓝图、环境和输出摘要。

#### 第 11 页

> 这里展示软件实际界面: 队列、新建任务、Agent 编排、实验编排、结果审查和报告下载。这部分建议现场切到软件做 live demo。

#### 第 12 页

> 最终验证通过 release_check 汇总: 蓝图 7/7 valid，Python 测试 167 passed，前端 build 通过，新增 API surface 被 release gate 覆盖。

#### 第 13 页

> 已知限制主要来自外部环境: Docker CLI 本机未安装、完整 benchmark 依赖固定数据集和远端 GPU、部分模型仍需要更充分样本验证。这些不影响当前主闭环。

#### 第 14 页

> 后续优化会集中在三个方向: 结果页更清晰、事件日志更标准、报告导出更完整。

#### 第 15 页

> 总结来说，这个系统已经从模型接入、环境验证、远端执行、结果审查到实验归档形成闭环，满足结题阶段“能跑、能看、能解释、能验证”的目标。

## 4. 软件效果展示脚本

### 4.1 演示前准备

建议准备三类材料:

1. 已完成任务样本
   - 至少 1 个 finished job。
   - 最好包含 scene_meta.json、pointcloud/glb/image artifact、result_summary。

2. Agent 检查记录
   - 已有 blueprint validation 通过结果。
   - 有至少一个 smoke/health/build task 的前端记录或截图。

3. 实验编排样本
   - 至少 1 个 experiment template。
   - 至少 1 个 experiment run，包含 job_ids。

如果现场远端 GPU 不稳定，建议以“已有任务 + 手动触发轻量接口 + 展示记录包”为主，不把耗时模型推理作为唯一演示路径。

### 4.2 现场演示路线

#### Step 1: 启动系统并展示首页状态

演示点:

- 桌面端/浏览器前端打开。
- 后端 health ready。
- 侧边栏包含工作队列、新建任务、对比面板、Agent 编排、实验编排、系统配置等。

讲解:

> 这是本地工作台入口，所有任务和模型验证都通过统一界面进入。

#### Step 2: 工作队列

演示点:

- 展示 job 列表。
- 展示 running/finished/failed 状态筛选。
- 点开一个 finished job。

讲解:

> 每个任务都有本地持久化记录，失败原因和执行阶段会回写到任务状态中。

#### Step 3: 新建任务

演示点:

- 选择模型和 source_type。
- 上传图片/视频或选择样例。
- 展示参数区域。
- 如现场不实际提交，可以说明提交后进入远端执行链。

讲解:

> 前端创建的不是 UI 假任务，而是后端 job_store 中的真实任务记录，后续可以被 dispatch、retry、cancel 和导出。

#### Step 4: JobDetail 结果审查

演示点:

- 展示输入、状态、输出 artifact。
- 展示 result summary / scene_meta / contract check 相关信息。
- 点击下载 bundle 或 experiment record。

讲解:

> 结果审查的重点是证据链: 输入、参数、模型、输出文件、元数据和合同检查都在同一个任务下归档。

#### Step 5: Agent 编排

演示点:

- 打开 Agent 工作台。
- 展示模型 registry。
- 展示 blueprint validation。
- 触发单模型 health 或 smoke。
- 展示失败诊断摘要或 ready 状态。
- 展示批量 smoke 入口。

讲解:

> Agent 工作台解决的是模型接入是否可信的问题。它不只告诉我们有哪些模型，还能验证蓝图、环境、权重和最小运行路径。

#### Step 6: 实验编排

演示点:

- 打开 ExperimentWorkbench。
- 创建或选择模板。
- 选择 source job 复用输入。
- 设置参数网格。
- 启动 run 或展示已有 run。

讲解:

> 实验编排把“同一输入、多组参数、多模型/多任务”的过程结构化，最终可以回溯到每个 job 和实验记录包。

#### Step 7: 对比与报告

演示点:

- 打开 compare/sample matrix。
- 展示不同模型结果对比。
- 展示 report export 或 comparison report。

讲解:

> 平台最终要解决的是结果可审查和可比较，不只是把模型跑起来。

#### Step 8: release_check 证明

演示点:

展示终端输出或截图:

```text
7/7 valid
167 passed, 1 skipped
frontend build passed
api surface: 9 agent/closed-loop routes registered
```

讲解:

> 这部分是结题验证口径，证明当前交付不是只靠手动演示，而是有自动化检查覆盖。

### 4.3 备用演示策略

如果远端 GPU 临时不可用:

- 不现场跑完整模型，只展示已有 finished job。
- 现场触发 Agent validate 或读取已有 validation。
- 展示 release_check 输出。
- 展示 experiment record zip/manifest。

如果前端服务临时不可用:

- 用 README/docs/API reference 展示接口。
- 用 release_check 和 pytest 输出证明后端与构建通过。
- 用本地 job 目录截图展示 job.json/status.json/scene_meta/result_summary。

如果 Docker warning 被问到:

> Docker runner 是可选后备，当前主路径是 SSH/SCP 远端 GPU。warning 表示本机没有 Docker CLI，release_check 中主路径和静态 Docker 配置已通过。

## 5. 开发全流程日志描述

### 5.1 开发推进日志

可在报告中写成如下阶段:

```text
阶段一: 现状审计
- 阅读 README、architecture、model-integration、ROADMAP、CHANGELOG、model_registry 和 Agent schema。
- 梳理已完成能力、半完成能力、缺口和结题风险。

阶段二: 缺口定位
- 发现 Agent API 缺少 smoke/health/batch/diagnosis 前端闭环。
- 发现 experiment_orchestrator 与 job_store.create_job 签名不匹配。
- 发现 experiment_agent JSON dispatch 与 /api/jobs multipart form 不匹配。
- 发现不同 runner scene_meta 字段不统一。
- 发现前端 WorkspaceTab 类型重复，新增 experiments workspace 时容易漂移。

阶段三: 功能实现
- 增加 Agent checks API 与 AgentWorkbench 前端触发/轮询。
- 增加 scene_meta 归一化读取。
- 增加输出合同检查。
- 修复实验模板创建真实 job 和复用输入链路。
- 增加 ExperimentWorkbench。
- 增加实验记录 manifest/zip 下载。
- 将新增 API surface 纳入 release_check。

阶段四: 验证修复
- 运行 Python tests，全部通过。
- 运行 frontend build，发现 WorkspaceTab 类型漂移。
- 修复 WorkspaceTab 公共类型来源。
- 运行 release_check，核心 gate 全部通过。
```

### 5.2 平台运行日志

建议把一次任务的运行日志描述为生命周期证据链:

```text
created
  -> preparing_remote
  -> uploading
  -> running
  -> downloading
  -> finished
```

每个阶段关联文件:

| 文件 | 作用 |
|------|------|
| job.json | 任务基本信息、模型、输入类型、参数 |
| status.json | runner 执行状态和进度 |
| scene_meta.json | 结果元数据和 artifact 索引 |
| result_summary.json | 后端汇总后的结果摘要 |
| logs/job.log | 任务执行日志 |
| manifest.json | 实验记录包中的可复现说明 |

### 5.3 Agent 验证日志

Agent 验证日志可以描述为模型接入证据链:

```text
blueprint validate
  -> env health check
  -> checkpoint check
  -> build if needed
  -> smoke test
  -> failure diagnosis
  -> experiment record archive
```

对应证据:

- YAML blueprint 是否符合 SCHEMA。
- conda/env/checkpoint/build_steps 是否满足要求。
- smoke_runner 是否能完成最小样本运行。
- HealthDoctor 是否能对失败输出给出诊断摘要。
- 实验记录包是否归档模型蓝图、参数、环境和输出摘要。

### 5.4 报告中的推荐表述

可以直接使用下面这段:

> 本项目将日志与记录体系划分为三层: 开发推进日志、平台运行日志和 Agent 验证日志。开发推进日志记录从现状审计、缺口定位、功能实现到验证修复的全过程；平台运行日志围绕 job 生命周期记录任务创建、远端执行、结果下载、scene_meta 解析和输出合同检查；Agent 验证日志围绕模型蓝图、环境健康、构建、smoke test 和失败诊断记录模型接入状态。三类日志共同支撑结题演示、问题追踪和实验复现。

## 6. 后续功能优化优先级

### P0: 结题演示前必须稳定

- 统一 WorkspaceTab 类型来源，避免前端导航新增后 build 漂移。
- 确保 release_check 输出截图可用。
- 准备至少一个完整 finished job 和一个 experiment record 包。

### P1: 前端展示增强

- JobDetail 增加更清晰的 scene_meta、contract check、artifact index 区块。
- AgentWorkbench 按模型聚合 validation、smoke、health、build 的最近状态。
- ExperimentWorkbench 改成“模板 -> 输入 -> 参数网格 -> 运行摘要”的分步体验。

### P2: 后端闭环增强

- 增加统一 `events.jsonl` 任务事件日志。
- 将 Agent check stdout/stderr/diagnosis 归档到固定目录。
- Experiment run 自动聚合 finished/failed/running 和失败原因。
- 报告导出纳入模型蓝图、合同检查和实验记录链接。

### P3: 长期维护

- 拆分 backend/app.py 大路由。
- 补更完整 Playwright smoke 演示流程。
- 在固定公开数据集上形成一组可复现实验表格。
- 安装 Docker CLI 后补跑 docker compose config gate。
