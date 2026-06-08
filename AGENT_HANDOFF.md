# Agent Handoff — 3R All-in-One 项目交接文档

> **给接手的 Agent：** 请先**完整阅读本文档**，再开始工作。本文档记录了 2026-05-25 / 05-26 的工作内容。
> **重要：千万不要重复创建已存在的文件，不要破坏现有结构。如有疑问，先用 `python -m agent status` 验证现状。**

---

## 0. 一句话现状

**项目根目录**：`E:\Demo\3R_All_in_One\3R_All_in_One`
**当前阶段**：v0.4.0 — Agent 模块基础设施搭建完成，7 个模型蓝图全部通过校验，CLI 可用。
**接下来重心**：将 Agent 模块与 backend 集成、补充测试、跑通真实 SSH 远程构建流程。

---

## 1. 项目身份与背景

### 1.1 这是什么项目

`3R_All_in_One` 是从 `E:\kykt\Coding\4.06\vision_ui` 拆分独立出来的 **3R 模型聚合管理平台**。

技术栈：
- **后端**：FastAPI + SSH/SCP 远程派发（端口 8765）
- **前端**：Tauri 2 + React + TypeScript
- **Agent 模块**：声明式 YAML 蓝图 + 一键环境搭建 + AI 诊断
- **Runners**：每个模型一个 `runners/<model>_runner.py` 适配器

### 1.2 服务器信息（远程执行环境）

| 项 | 值 |
|---|---|
| Host | `172.17.140.97` |
| User | `kykt26` |
| SSH alias | `KYKT-UI`（已配置 `~/.ssh/config`）|
| GPU | TITAN RTX (sm_75, 24 GB) |
| OS | Ubuntu 20.04 |
| CUDA | 12.6 (`/usr/local/cuda-12.6`) |
| Code root | `/hdd3/kykt26/code/<model>` |
| Conda | 默认安装 |

### 1.3 7 个 3R 模型

| Key | 状态 | 类型 | 显存 |
|---|---|---|---|
| dust3r | integrated | static_multiview | 8 GB |
| mast3r | integrated | static_matching | 10 GB |
| monst3r | integrated | dynamic_video | 18 GB |
| spann3r | integrated | spatial_memory | 14 GB |
| fast3r | integrated | fast_multiview | 16 GB |
| align3r | env_ready | video_depth | 20 GB |
| cut3r | env_ready | online_persistent | 18 GB |

---

## 2. 已完成工作清单（**勿重复**）

### 2.1 项目基础（v0.1.0 - v0.3.0）

```
3R_All_in_One/
├── README.md                    ✓ 已创建（项目概述）
├── CHANGELOG.md                 ✓ 已创建（v0.1.0 - v0.4.0）
├── LICENSE                      ✓ 已创建
├── .gitignore                   ✓ 已创建
├── .gitattributes               ✓ 已创建
├── pyproject.toml               ✓ 已创建（v0.4.0 添加）
├── requirements.txt             ✓ 已创建（v0.4.0 添加）
└── AGENT_HANDOFF.md             ← 你正在读的文件
```

### 2.2 backend/ 后端（已迁移自 vision_ui）

```
backend/
├── app.py                       ✓ FastAPI 主入口（91 KB）
├── advisor.py                   ✓ AI Advisor 模块
├── job_scheduler.py             ✓ 任务调度
├── job_store.py                 ✓ 任务持久化
├── ssh_runner.py                ✓ SSH 执行器（45 KB）
├── model_registry.py            ✓ 模型 contract（注意：与 agent/registry.py 不同！）
├── model_contracts.py           ✓ 模型参数合同
├── metrics_calculator.py        ✓ 评估指标
├── report_exporter.py           ✓ 报告导出
├── resource_monitor.py          ✓ 资源监控
├── visual_artifacts.py          ✓ 可视化产物
├── development_store.py         ✓ 开发轨迹
└── requirements.txt             ✓
```

### 2.3 client/ 前端（已迁移自 vision_ui）

```
client/
├── package.json, vite.config.ts, tsconfig.json
├── src/                         ✓ 25+ React 组件
└── src-tauri/                   ✓ Rust 桌面壳
```

### 2.4 runners/ 远程脚本（已迁移）

```
runners/
├── dust3r_runner.py             ✓
├── mast3r_runner.py             ✓
├── monst3r_runner.py            ✓ (18 KB，最复杂)
├── spann3r_runner.py            ✓
├── fast3r_runner.py             ✓
├── align3r_runner.py            ✓
└── cut3r_runner.py              ✓
```

### 2.5 **agent/ 模块（v0.4.0 核心，本次工作重点）**

```
agent/
├── __init__.py                  ✓ 版本 + lazy import + __all__
├── __main__.py                  ✓ python -m agent 入口
├── cli.py                       ✓ 8 个子命令（list/status/info/validate/smoke/build/health/doctor）
├── registry.py                  ✓ ModelRegistry 单例 + 过滤/排序
├── schema_validator.py          ✓ 12 项校验规则
├── env_builder.py               ✓ 核心：SSHConfig/ModelSpec/EnvBuilder + 7 个函数
├── smoke_runner.py              ✓ SmokeRunner / SmokeReport
├── experiment_agent.py          ✓ 批量实验编排
├── health_doctor.py             ✓ AI 诊断（10+ 错误模式）
└── model_specs/
    ├── SCHEMA.md                ✓ 蓝图 Schema 规范文档
    ├── dust3r.yaml              ✓ 完整蓝图（150+ 行）
    ├── mast3r.yaml              ✓
    ├── monst3r.yaml             ✓
    ├── spann3r.yaml             ✓
    ├── fast3r.yaml              ✓
    ├── align3r.yaml             ✓
    └── cut3r.yaml               ✓
```

### 2.6 docs/ 文档

```
docs/
├── architecture.md              ✓ 系统架构
├── api-reference.md             ✓ API 参考
├── deployment.md                ✓ 部署指南
├── model-integration.md         ✓ 新模型接入
└── agent-guide.md               ✓ Agent 模块指南（v0.4.0 添加）
```

---

## 3. 关键设计决策（**勿擅自更改**）

### 3.1 模型蓝图 Schema（agent/model_specs/SCHEMA.md）

每个模型蓝图必须包含 12 个板块：
1. **身份**: name/key/family/version/paper
2. **能力标签**: tags.{type, paradigm, scene, input, output}
3. **源码**: repo.{url, branch, server_path, submodules}
4. **环境**: environment.{conda_env, python, torch, create_strategy, clone_source}
5. **权重**: checkpoints[].{name, path, size, source, required}
6. **编译**: build_steps[].{name, cmd, cwd, env, verify}
7. **资源**: resources.{gpu_memory_gb, ram_gb, max_frames}
8. **健康检查**: health_checks[].{name, type, command, expected, critical}
9. **烟雾测试**: smoke_test.{script, expected}
10. **Runner**: runner.{script, conda_env, default_params, param_tiers}
11. **输出合同**: output_contract.{required, optional, scene_meta}
12. **已知问题**: known_issues[].{id, description, workaround, resolved}
13. **兼容矩阵**: compatibility.{gpu_models, os, glibc, driver}

### 3.2 ModelSpec 类的关键属性（env_builder.py）

```python
spec.key             # "monst3r" — 全局唯一标识
spec.conda_env       # 环境名
spec.server_path     # 远程代码路径
spec.model_type      # tags.type
spec.paradigm        # tags.paradigm
spec.needs_curope    # 是否需要 curope
spec.is_ready        # status == "integrated"
spec.unresolved_issues  # 未解决问题列表
spec.get_param_tier("fast"|"standard"|"enhanced")  # 参数梯度
spec.summary()       # 摘要 dict
```

### 3.3 模型注册表（agent/registry.py）

- **单例模式**：全局只有一个 `ModelRegistry()` 实例
- **自动加载**：扫描 `agent/model_specs/*.yaml`
- **不要修改 `__new__`**：单例逻辑依赖它

### 3.4 两个 "registry" 不要混淆！

- `backend/model_registry.py` — 后端用的**模型合同**（参数表单等）
- `agent/registry.py` — Agent 模块的**蓝图注册表**

它们职责不同，**不要合并**。

---

## 4. 立即验证现状（**接手第一步必做**）

### 4.1 完整性检查

```powershell
# 进入项目目录
cd E:\Demo\3R_All_in_One\3R_All_in_One

# 1) 校验所有蓝图（应该 7/7 valid）
python -m agent validate

# 2) 查看注册表状态
python -m agent status

# 3) 查看某个模型详情
python -m agent info monst3r
```

### 4.2 期望输出

`python -m agent validate` 应输出：
```
Total: 7/7 valid, 0 errors
```

`python -m agent status` 应输出：
```
Total: 7 | Integrated: 5 | Env Ready: 2 | With Issues: 3
```

如果**任何一项**失败，**先修复再继续**，**不要新建文件覆盖**。

---

## 5. 下一步可选方向（按优先级）

### 5.1 P0 — 必做：Agent 与 Backend 集成

将 `agent/` 模块的 CLI 能力暴露为后端 API：

- [x] 在 `backend/app.py` 添加 `/api/agent/registry` 端点
- [x] 在 `backend/app.py` 添加 `/api/agent/validate` 端点
- [x] 在 `backend/app.py` 添加 `/api/agent/build/{model}` 端点（异步任务）
- [x] 前端 `client/src/` 添加 `AgentWorkbench.tsx` 组件

**注意**：`backend/app.py` 已有 91 KB，请**追加路由**到末尾，**不要重写**。

### 5.2 P1 — 测试与 CI

- [x] 创建 `tests/` 目录
- [x] 写 `tests/agent/test_schema_validator.py`（针对 7 个蓝图）
- [x] 写 `tests/agent/test_registry.py` 与后端 Agent API 覆盖
- [x] 写 `tests/agent/test_health_doctor.py`（错误模式匹配）

### 5.3 P2 — 真实远程构建验证

[x] 已在远程服务器上跑通 `python -m agent build dust3r --alias KYKT-UI`（2026-06-08）：
- conda env 检查通过（env 已存在）
- pip 依赖安装通过
- smoke test 通过
- `python -m agent health dust3r --alias KYKT-UI` 通过
- DUSt3R 蓝图没有 curope 编译步骤

**前提**：本地 `~/.ssh/config` 已配 `KYKT-UI` alias。

### 5.4 P3 — 文档完善

- [x] 补充 `docs/agent-guide.md` 的 API 参考
- [x] 给 `README.md` 加 Agent CLI 快速上手段
- [x] 在 `CHANGELOG.md` 记录 v0.5.0 详细变更

---

## 6. 已知约束与陷阱

### 6.1 文件大小限制

- 单次 edit 工具调用最大 64K tokens 输出
- `backend/app.py` 已 91 KB，**修改时务必 read 后 edit，不要 write_to_file 覆盖**

### 6.2 不要做的事

- ❌ 不要删除任何 `*.yaml` 蓝图（已通过校验）
- ❌ 不要修改 `agent/__init__.py` 的 `__getattr__` lazy import 逻辑
- ❌ 不要在同一个 response 里对同一文件做两次 edit（会被规则限制）
- ❌ 不要将 `backend/model_registry.py` 和 `agent/registry.py` 合并
- ❌ 不要把 `model_specs/` 里的 YAML 改回简化版（已废弃旧格式）

### 6.3 字符编码

所有文件必须 UTF-8。Windows 上写 YAML 时注意 BOM 问题。

### 6.4 路径分隔符

代码里用 `pathlib.Path` 或正斜杠，不要硬编码反斜杠。

---

## 7. CLI 命令速查表

```bash
python -m agent list                     # 列出所有模型
python -m agent list --format json       # JSON 输出
python -m agent status                   # 注册表状态表
python -m agent info <key>               # 模型详情
python -m agent info <key> --format json # JSON
python -m agent validate                 # 校验全部蓝图
python -m agent validate <key>           # 校验单个
python -m agent smoke <key> --alias KYKT-UI    # 烟雾测试（需 SSH）
python -m agent build <key> --alias KYKT-UI    # 构建环境（需 SSH）
python -m agent health <key> --alias KYKT-UI   # 健康检查（需 SSH）
python -m agent doctor <key> --alias KYKT-UI   # AI 诊断（需 SSH）
```

---

## 8. Python API 速查

```python
from agent import ModelRegistry, EnvBuilder, SSHConfig
from agent import SchemaValidator, HealthDoctor

# 加载注册表
registry = ModelRegistry()
spec = registry.get("monst3r")
all_integrated = registry.filter(status="integrated")

# 构建环境
builder = EnvBuilder(alias="KYKT-UI")
report = builder.build(spec)

# 校验蓝图
validator = SchemaValidator()
results = validator.validate_all()

# AI 诊断
doctor = HealthDoctor()
report = doctor.diagnose(spec, build_results)
doctor.print_report(report)
```

---

## 9. 历史路径（**仅供参考，勿混淆**）

| 旧位置 | 新位置 | 状态 |
|---|---|---|
| `E:\kykt\Coding\4.06\vision_ui\app.py` | `E:\Demo\3R_All_in_One\3R_All_in_One\backend\app.py` | ✓ 已迁移 |
| `E:\kykt\Coding\4.06\vision_ui\client\` | `E:\Demo\3R_All_in_One\3R_All_in_One\client\` | ✓ 已迁移 |
| `E:\kykt\Coding\4.06\vision_ui\runners\` | `E:\Demo\3R_All_in_One\3R_All_in_One\runners\` | ✓ 已迁移 |
| 无 | `E:\Demo\3R_All_in_One\3R_All_in_One\agent\` | ✓ 全新创建 |

**`E:\kykt\Coding\4.06\vision_ui` 是历史目录**，新工作一律在 `E:\Demo\3R_All_in_One\3R_All_in_One` 进行。

---

## 10. 给接手 Agent 的明确指令

1. **先读完本文档**，再做任何动作。
2. **跑一次 `python -m agent validate` 和 `python -m agent status`** 确认环境正常。
3. **不要重复创建**任何已在第 2 节列出的文件。
4. **修改文件前先 read**，理解上下文再 edit。
5. **遵守第 6 节的"不要做的事"**。
6. **新增功能时优先选 P0 任务**（第 5.1 节）。
7. **每完成一个里程碑**，更新 `CHANGELOG.md`。
8. **遇到 known_issues**，先查 `agent/model_specs/<model>.yaml` 的 `known_issues` 字段，再扩展 `agent/health_doctor.py` 的 `ERROR_PATTERNS`。

---

## 附录 A：文件统计快照（2026-05-26 02:00）

```
项目总文件: 101 个（不含 .git/node_modules/__pycache__）
Python 代码: ~350 KB
TypeScript 代码: ~215 KB

agent/ 模块详细:
  __init__.py            3,317 B
  __main__.py              159 B
  cli.py                11,660 B
  env_builder.py        17,291 B
  experiment_agent.py    6,468 B
  health_doctor.py      10,435 B
  registry.py            8,532 B
  schema_validator.py   11,246 B
  smoke_runner.py        4,060 B
  model_specs/SCHEMA.md  6,485 B
  model_specs/*.yaml    7 files, 41 KB total
```

---

## 附录 B：联系/上下文

- **用户角色**：研究员 / 平台工程师
- **项目母仓**：`E:\kykt`（KYKT 工作区）
- **本项目 git 状态**：未初始化（待用户确认是否独立成 repo）
- **相关上下文文档**：
  - `E:\kykt\KYKT.md` — KYKT 工作区总览
  - `E:\kykt\Coding\4.06\vision_ui\THREER_MODEL_ROADMAP.md` — 3R 模型路线图
  - `E:\kykt\Coding\4.06\vision_ui\PLATFORM_EVOLUTION_PLAN.md` — 平台演进规划

---

**End of Handoff. Good luck. — Cascade @ 2026-05-26**
