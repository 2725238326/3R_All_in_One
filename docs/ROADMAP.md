# 3R All-in-One 结题状态与后续工作

> 更新时间: 2026-06-09
> 口径: 结题交付说明，不再展开长期产品化蓝图。

## 当前完成状态

3R All-in-One 当前已经完成一个可演示、可继续扩展的前馈式三维重建模型实验管理原型。系统以本地桌面端和本地 FastAPI 后端为中心，通过 SSH/SCP 调用远端 GPU 环境执行模型，并在本地保存任务状态、日志、结果索引和对比材料。

### 已完成模块

| 模块 | 当前状态 |
|------|----------|
| 桌面端 | React + Tauri 2 工作台已接入 |
| 后端服务 | FastAPI 接口、WebSocket、任务生命周期和配置管理已实现 |
| 任务管理 | 任务创建、队列检索、状态筛选、失败原因展示和重试策略已实现 |
| 远端执行 | SSH/SCP runner 作为主执行路径，支持上传、运行、下载和取消 |
| 模型注册 | DUSt3R、MASt3R、MonST3R、Spann3R、Fast3R、Align3R、CUT3R 已进入平台注册表 |
| 结果记录 | `job.json`、`status.json`、`scene_meta.json` 作为核心记录格式 |
| 对比与评估 | 对比面板、样例矩阵、基础指标、可视化产物和报告导出已具备 |
| Agent 工具 | 模型蓝图校验、环境检查、smoke 验证和构建任务编排已具备 |
| 发布检查 | `tools/release_check.py` 覆盖版本、蓝图、测试、前端构建和打包前置条件 |
| 测试 | backend / agent 单元测试和 Playwright E2E smoke 测试已建立 |

## 模型接入状态

| 模型 | 状态 | 说明 |
|------|------|------|
| DUSt3R | baseline | 基础静态重建路径 |
| MASt3R | validated_smoke | 静态匹配与重建 smoke 验证 |
| MonST3R | validated_standard_sample | 动态视频样本路径验证 |
| Spann3R | validated_smoke | spatial memory 路径 smoke 验证 |
| Fast3R | validated_smoke_attention_fallback | 长图集路径，含 attention fallback |
| Align3R | runner_ready | runner 已具备，完整数据集验证留作后续 |
| CUT3R | validated_smoke | persistent-state 路径 smoke 验证 |

平台的接入目标是统一实验管理流程，不等同于完整复现每篇论文的全部 benchmark。完整精度复现仍依赖数据集、权重、显卡环境和模型自身脚本稳定性。

## 已知限制

| 问题 | 当前处理方式 |
|------|--------------|
| 模型环境差异大 | 使用 agent YAML 蓝图记录 conda、权重、编译和 smoke 信息 |
| 输出格式不完全一致 | 使用 `scene_meta.json` 做统一索引，字段允许可选 |
| 定量指标依赖真值 | 有真值时计算指标，无真值时记录耗时、成功率、完整性和日志 |
| 远端环境不由平台完全控制 | 平台记录服务器 profile、任务日志和失败原因，便于复盘 |
| Docker / Online API runner 不是主路径 | 保留为可选后备，不作为结题核心流程 |
| 多用户、权限、集群调度未实现 | 不属于当前结题范围 |

## 后续可做但不影响结题的工作

1. 对 Align3R 做完整样本验证，并补充更明确的失败记录。
2. 继续补齐不同模型的 `scene_meta.json` 字段，使对比面板能读取更多统一产物。
3. 在固定公开数据集上补充一组可复现实验表格。
4. 拆分 `backend/app.py` 中的大路由模块，降低后续维护成本。
5. 继续推进前端状态管理收敛，减少跨组件状态传递。

## 结题验证入口

常用检查命令:

```bash
python tools/release_check.py
pytest tests
cd client
npm run build
npx playwright test
```

Windows 桌面打包:

```powershell
.\tools\build_backend.ps1
cd client
npm run desktop:build
python ..\tools\release_check.py --require-artifacts
```

远端模型健康检查:

```bash
python -m agent validate
python -m agent status
python -m agent smoke dust3r --alias KYKT-UI
```
