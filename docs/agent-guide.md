# Agent 模块使用指南

> 一键环境搭建、蓝图校验、健康检查、烟雾测试、实验编排、AI 诊断

## 快速开始

### 命令行工具

```bash
# 查看所有模型
python -m agent list

# 查看注册表状态
python -m agent status

# 查看模型详情
python -m agent info monst3r

# 校验所有蓝图
python -m agent validate

# 运行烟雾测试
python -m agent smoke monst3r --alias KYKT-UI

# 构建环境
python -m agent build monst3r --alias KYKT-UI

# 运行健康检查
python -m agent health monst3r --alias KYKT-UI

# AI 诊断
python -m agent doctor monst3r --alias KYKT-UI
```

### Python API

```python
from agent import ModelRegistry, EnvBuilder, SmokeRunner, SSHConfig

# 获取模型注册表
registry = ModelRegistry()

# 查询模型
spec = registry.get("monst3r")
print(spec.summary())

# 过滤模型
integrated = registry.filter(status="integrated")
dynamic_models = registry.filter(paradigm="pairwise", scene="dynamic")

# 配置 SSH
ssh = SSHConfig(host="172.17.140.97", user="kykt26", alias="KYKT-UI")

# 构建环境
from agent import build_environment
report = build_environment(ssh, spec)

# 烟雾测试
from agent import smoke_check_model
result = smoke_check_model(ssh, spec)
```

---

## 模块架构

```
agent/
├── __init__.py           # 导出 & 版本管理
├── __main__.py           # python -m agent 入口
├── cli.py                # 命令行接口
├── registry.py           # 模型注册表
├── schema_validator.py   # 蓝图校验器
├── env_builder.py        # 环境搭建核心
├── smoke_runner.py       # 烟雾测试
├── experiment_agent.py   # 实验编排
├── health_doctor.py      # AI 诊断
└── model_specs/          # 模型蓝图
    ├── SCHEMA.md         # Schema 定义
    ├── dust3r.yaml
    ├── mast3r.yaml
    ├── monst3r.yaml
    ├── spann3r.yaml
    ├── fast3r.yaml
    ├── align3r.yaml
    └── cut3r.yaml
```

---

## 模型蓝图

每个模型有一个 YAML 蓝图文件，定义了：

| 板块 | 用途 |
|------|------|
| **身份标签** | name, key, family, paper |
| **能力标签** | type, input, output, paradigm, scene |
| **源码配置** | repo URL, branch, server_path |
| **环境配置** | conda_env, torch, cuda, create_strategy |
| **权重检查点** | name, path, size, required |
| **编译步骤** | cmd, cwd, env, verify |
| **资源需求** | gpu_memory, ram, max_frames |
| **健康检查** | import, cuda_kernel, file_exists |
| **Runner 配置** | script, params, param_tiers |
| **输出合同** | required, optional outputs |
| **已知问题** | description, workaround, resolved |
| **兼容矩阵** | gpu_models, os, glibc, driver |

### 蓝图示例

```yaml
name: MonST3R
key: monst3r
family: dust3r
version: "main@574cc77"

tags:
  type: dynamic_video
  paradigm: pairwise
  scene: dynamic

environment:
  conda_env: monst3r
  create_strategy: clone_from
  clone_source: dust3r

build_steps:
  - name: compile_curope
    cmd: "python setup.py build_ext --inplace"
    cwd: croco/models/curope
    env:
      TORCH_CUDA_ARCH_LIST: "7.5"
    verify: "ls curope*.so"

health_checks:
  - name: curope_cuda_kernel
    type: cuda_kernel
    command: "python -c \"from croco.models.curope import cuRoPE2D; print('OK')\""
    expected: "OK"
    critical: true

runner:
  default_params:
    image_size: 512
    num_frames: 48
  param_tiers:
    fast:
      num_frames: 24
    enhanced:
      num_frames: 96
```

---

## 工作流程

### 1. 校验蓝图

```bash
python -m agent validate
```

校验结果：
- ✗ ERROR — 必须修复
- ⚠ WARNING — 建议修复
- ℹ INFO — 仅提示

### 2. 构建环境

```bash
python -m agent build monst3r
```

步骤：
1. 创建/克隆 conda env
2. 安装 pip 依赖
3. 执行 build_steps（编译 curope）
4. 运行健康检查
5. 烟雾测试

### 3. AI 诊断

如果健康检查失败：

```bash
python -m agent doctor monst3r
```

AI 诊断会：
1. 分析错误日志
2. 匹配已知模式
3. 查询 known_issues
4. 生成修复建议

---

## SSH 配置

Agent 通过 SSH 连接远程服务器。推荐在 `~/.ssh/config` 中配置：

```
Host KYKT-UI
    HostName 172.17.140.97
    User kykt26
    IdentityFile ~/.ssh/id_rsa
    ServerAliveInterval 60
```

然后使用：

```bash
python -m agent smoke monst3r --alias KYKT-UI
```

---

## ModelSpec API

```python
spec = registry.get("monst3r")

# 属性
spec.key           # "monst3r"
spec.conda_env     # "monst3r"
spec.server_path   # "/hdd3/kykt26/code/monst3r"
spec.model_type    # "dynamic_video"
spec.paradigm      # "pairwise"
spec.needs_curope  # True
spec.is_ready      # True (status == "integrated")

# 方法
spec.summary()                    # 摘要 dict
spec.get_param_tier("fast")       # {image_size: 224, num_frames: 24}
spec.unresolved_issues            # 未解决问题列表
```

---

## 扩展新模型

1. 创建 `agent/model_specs/<model>.yaml`
2. 按 SCHEMA.md 填写所有必填字段
3. 运行 `python -m agent validate <model>`
4. 运行 `python -m agent build <model>`
5. 编写 `runners/<model>_runner.py`
6. 更新状态为 `status: integrated`

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 0.4.0 | 2026-05 | 完整蓝图 schema、健康检查、AI 诊断 |
| 0.3.0 | 2026-04 | 基础 smoke_runner、env_builder |
| 0.2.0 | 2026-04 | 初始模型规格 YAML |
